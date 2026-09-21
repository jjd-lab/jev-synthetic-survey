"""LLM instance factory for creating configured LLM instances"""

import os
import threading
from functools import lru_cache
from typing import Any, Optional

from dotenv import load_dotenv

from src.utils.progress import is_budget_error, sanitize_reason


class BudgetHaltedError(RuntimeError):
    """Raised in place of an LLM call after a spend cap blocked an earlier one."""


# Process-wide, write-once: the cap belongs to the API account, not to a run, and
# `apply_langchain_retry` is called from five sites deep inside the runners with no run object in
# scope. Threading a per-run recorder to all of them is the five-signature change this design
# already declined once for the token meter, and it would still have to be a singleton to be
# correct -- two runs in one process share the same cap.
_budget_halt_lock = threading.Lock()
_budget_halt_reason: Optional[str] = None


def budget_halt_reason() -> Optional[str]:
    """The message of the first spend-cap block seen in this process, or None."""
    with _budget_halt_lock:
        return _budget_halt_reason



def _latch_budget_halt(exc: BaseException) -> None:
    """Record the first block. Later ones don't overwrite it -- the first message is the diagnosis."""
    global _budget_halt_reason
    with _budget_halt_lock:
        if _budget_halt_reason is not None:
            return
        _budget_halt_reason = sanitize_reason(exc)
        print(f"\n[BUDGET] Spend cap hit -- halting further LLM calls: {_budget_halt_reason}")


def resolve_max_retries(max_retries: Optional[int] = None) -> int:
    """Resolve LangChain retry count from arg or env LLM_MAX_RETRIES (default 2)."""
    load_dotenv()
    if max_retries is not None:
        return max_retries
    return int(os.getenv("LLM_MAX_RETRIES", "2"))


def structured_output_method(model: Optional[str] = None) -> str:
    """Pick the structured-output method for a model, resolving None like create_llm_instance.

    Bedrock's schema validator rejects array ``maxItems`` (silently erroring every
    multi-choice/grid question), so tool-calling is required there. OpenAI-compatible endpoints
    support the strict ``json_schema`` decoder, which hard-enforces the schema — no client-side
    shape drift, so the list-as-string / missing-field failures seen under ``function_calling``
    cannot occur. `None` falls back to the same MODEL_NAME env default as create_llm_instance
    (gpt-4.1).
    """
    load_dotenv()
    m = (model or os.getenv("MODEL_NAME", "gpt-4.1")).lower()
    # Match on the provider prefix, not a free-text substring, so an OpenAI-compatible deployment
    # whose alias happens to contain "claude"/"anthropic" isn't misrouted off the strict
    # json_schema path.
    if m.startswith("bedrock/"):
        return "function_calling"
    return "json_schema"


@lru_cache(maxsize=None)
def create_llm_instance(
    model: str = None,
    temperature: float = None,
    api_base_url: str = None,
    api_key: str = None,
    max_retries: int = None,
):
    """Factory function to create LLM instances with configuration.

    SDK retries are disabled (max_retries=0). Apply LangChain retries to the
    structured runnable via apply_langchain_retry() after with_structured_output().

    Cached by argument tuple (lru_cache): identical (model, temperature, api_base_url,
    api_key, max_retries) return one shared ChatOpenAI instance, so callers reuse a single
    OpenAI SDK client / httpx connection pool instead of building one per call. The client is
    thread-safe and shared safely across the survey's .batch() thread pool; distinct configs
    (e.g. a different temperature) get their own cached instance.
    """
    load_dotenv()

    from langchain_openai import ChatOpenAI

    default_model = os.getenv("MODEL_NAME", "gpt-4.1")
    default_temperature = float(os.getenv("TEMPERATURE", "0.7"))
    default_api_base_url = os.getenv("API_BASE_URL")
    default_api_key = os.getenv("API_KEY")

    return ChatOpenAI(
        model=model or default_model,
        temperature=temperature if temperature is not None else default_temperature,
        base_url=api_base_url or default_api_base_url,
        api_key=api_key or default_api_key,
        max_retries=0,
    )


def apply_langchain_retry(
    runnable: Any,
    max_retries: Optional[int] = None,
    on_retry: Optional[Any] = None,
) -> Any:
    """Wrap a runnable with a retry policy (initial attempt + max_retries).

    LangChain's ``.with_retry()`` gives no observable per-retry hook (its
    ``RunnableRetry`` never dispatches ``on_retry`` for chat models). To make
    retries countable, we drive tenacity directly via a small wrapper whose
    ``before_sleep`` fires exactly once per retry. Backoff matches
    ``.with_retry()`` defaults (exponential jitter).

    ``content_filter`` is retried like everything else. It was excluded until 2026-09-04, on the
    premise that a filter re-generates the same rejected text; that is false for the common case,
    because an *output*-side rejection is resampled at temperature > 0 and usually clears -- both
    filtered QID190 cells in the twin2k chained arm passed on a re-ask with no prompt change. An
    *input*-side rejection does repeat and is indistinguishable from the exception alone, so it now
    costs ``max_retries`` wasted calls (2 by default) instead of failing immediately -- cheap against
    silently losing the recoverable case.

    A **budget** error is the one exception (`is_budget_error`): not retried, and it latches the
    process so every later call fails without an API request. Until 2026-09-05 a spend cap left the
    pipeline marching through the whole remaining panel, burning ``max_retries + 1`` rejections per
    cell and filling the error log with one record each. Now the first block is the last call.

    Args:
        runnable: the runnable to wrap (typically ``llm.with_structured_output(...)``).
        max_retries: retry count; total attempts = max_retries + 1.
        on_retry: optional callable ``(exc: BaseException, attempt: int) -> None``
            invoked once per retry, before sleeping. ``attempt`` is 1-indexed and
            counts the retry (first retry = 1).

    Returns:
        A runnable exposing ``.invoke(...)`` with the retry policy applied.
    """
    from langchain_core.runnables import RunnableLambda
    from tenacity import (
        Retrying,
        retry_if_exception,
        stop_after_attempt,
        wait_exponential_jitter,
        wait_none,
    )

    resolved = resolve_max_retries(max_retries)
    # Backoff matches .with_retry() defaults in production; tests set
    # LLM_RETRY_NO_WAIT=1 to avoid multi-second sleeps.
    wait = wait_none() if os.getenv("LLM_RETRY_NO_WAIT") == "1" else wait_exponential_jitter()

    def _before_sleep(retry_state: Any) -> None:
        if on_retry is None:
            return
        exc = None
        outcome = getattr(retry_state, "outcome", None)
        if outcome is not None and outcome.failed:
            exc = outcome.exception()
        # attempt_number counts the attempt that just failed; before_sleep runs
        # once per retry, so this is a 1-indexed retry count.
        on_retry(exc, getattr(retry_state, "attempt_number", 0))

    def _retryable(exc: BaseException) -> bool:
        # Every Exception is retryable, ``content_filter`` included (see the note in the docstring);
        # ``Exception`` rather than ``BaseException`` so KeyboardInterrupt/SystemExit still abort at
        # once. Deliberately broader than LangGraph's ``default_retry_on``, which excludes
        # ValueError/TypeError/RuntimeError -- pydantic ``ValidationError`` is transient here
        # (temperature resamples, and the lenient parser recovers many) and must stay retryable.
        # The single exception is a spend cap: it is still there a second later, so a retry only
        # buys two more rejections per cell.
        return isinstance(exc, Exception) and not is_budget_error(exc)

    def _invoke_with_retry(value: Any) -> Any:
        # Fast-fail every call after the first spend-cap block, without touching the API: the cap
        # applies to the rest of the run too. Raised as an ordinary Exception, so the caller records
        # the cell/persona as failed -- never marked complete, so a --resume once the cap resets
        # re-runs exactly the unfinished work.
        halted = budget_halt_reason()
        if halted is not None:
            raise BudgetHaltedError(f"BudgetHalted: stopped after a spend-cap block: {halted}")

        retryer = Retrying(
            stop=stop_after_attempt(resolved + 1),
            wait=wait,
            retry=retry_if_exception(_retryable),
            before_sleep=_before_sleep,
            reraise=True,
        )
        try:
            return retryer(runnable.invoke, value)
        except Exception as exc:
            if is_budget_error(exc):
                _latch_budget_halt(exc)
            raise

    # RunnableLambda so the wrapper composes with ``prompt | structured_llm``.
    return RunnableLambda(_invoke_with_retry)
