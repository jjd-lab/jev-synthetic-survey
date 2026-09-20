"""Progress callback and run error recording for LangChain .batch() runs."""

from __future__ import annotations

import json
import os
import threading
from typing import Any, Dict, List, Optional, Tuple

from langchain_core.callbacks import BaseCallbackHandler

_ERROR_CATEGORIES = (
    "content_filter",
    "budget",
    "rate_limit",
    "authentication",
    "timeout",
    "connection",
    "server",
    "structured_output",
    "unknown",
)


# A spend cap / quota block, in the wordings a provider and the OpenAI SDK use for one. Data next
# to `classify_error` so the retry gate in llm_factory and the error summary cannot disagree about
# what "budget" means. Deliberately narrow -- every marker names a limit explicitly -- because a
# false positive halts the whole run, which is the expensive direction to be wrong in.
_BUDGET_MARKERS = (
    "budgetexceeded",             # litellm's BudgetExceededError, matched on the class name
    "budgethalted",               # our own latch (llm_factory.BudgetHaltedError)
    "budget has been exceeded",
    "budget_exceeded",
    "exceeded budget",
    "max budget",
    "budget limit",
    "insufficient_quota",
    "insufficient credits",
    "exceeded your current quota",
    "billing_hard_limit_reached",
)


def classify_error(exc_or_msg: Any, category: Optional[str] = None) -> str:
    """Map an exception or message to a normalized error category."""
    if category in _ERROR_CATEGORIES:
        return category

    if isinstance(exc_or_msg, AttributeError):
        return "unknown"
    if isinstance(exc_or_msg, BaseException):
        exc = exc_or_msg
        message = str(exc).lower()
        exc_name = type(exc).__name__.lower()
    else:
        exc = None
        message = str(exc_or_msg).lower()
        exc_name = ""

    combined = f"{exc_name} {message}"

    # First, ahead of every other rule: a content-filter rejection carries "parse" in its message
    # ("Could not parse response content as the request was rejected by the content filter"), so
    # any later position lets structured_output steal it. Going first also guards against a filter
    # error that happens to carry a 400/403 or the word "server". Matched on the exception class
    # (ContentFilterFinishReasonError, ContentPolicyViolationError) rather than the message, which
    # varies; the text patterns are backups for the input-side rejection.
    # The category exists to keep the two apart in the error summary, not to gate retry: it is
    # retried like every other Exception (see apply_langchain_retry in llm_factory.py).
    if (
        "contentfilter" in combined
        or "contentpolicy" in combined
        or "content management policy" in combined
        or "responsibleaipolicy" in combined
    ):
        return "content_filter"
    # Ahead of rate_limit: OpenAI returns `insufficient_quota` with HTTP **429**, and a provider
    # budget block can carry a 429/400 too, so any later position files a spend cap as a transient
    # throttle -- the opposite of what it is. This is the one category that is never retried and
    # that latches the run to a halt (apply_langchain_retry in llm_factory.py).
    if any(m in combined for m in _BUDGET_MARKERS):
        return "budget"
    if "429" in combined or "rate limit" in combined or "too many requests" in combined:
        return "rate_limit"
    if "401" in combined or "403" in combined or "authentication" in combined or "unauthorized" in combined:
        return "authentication"
    if "timeout" in combined or "timed out" in combined:
        return "timeout"
    if "connection" in combined or "connect" in combined or "network" in combined:
        return "connection"
    if "500" in combined or "502" in combined or "503" in combined or "504" in combined or "server" in combined:
        return "server"
    if (
        "validation" in combined
        or "json" in combined
        or "parse" in combined
        or "structured" in combined
        or "pydantic" in combined
    ):
        return "structured_output"
    return "unknown"


def is_budget_error(exc_or_msg: Any) -> bool:
    """True if this failure is a spend cap / quota block rather than a transient error.

    One definition for both consumers: `classify_error` owns the taxonomy, this is the predicate
    over it. Retrying a budget block cannot succeed -- the cap is still there a second later.
    """
    return classify_error(exc_or_msg) == "budget"


def sanitize_reason(msg: Any, max_len: int = 200) -> str:
    """Return a truncated, single-line reason safe for logs."""
    text = " ".join(str(msg).split())
    if len(text) > max_len:
        return text[: max_len - 3] + "..."
    return text


class RunErrorRecorder:
    """Thread-safe collector for question/persona failures and LLM retries."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._records: List[Dict[str, Any]] = []
        self._retry_total = 0
        self._retry_by_item: Dict[Tuple[Optional[str], Optional[str]], int] = {}
        self._local = threading.local()

    @property
    def records(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._records)

    def set_context(self, respid: Optional[str], item_id: Optional[str]) -> None:
        self._local.respid = respid
        self._local.item_id = item_id

    def clear_context(self) -> None:
        self._local.respid = None
        self._local.item_id = None

    def _current_context(self) -> Tuple[Optional[str], Optional[str]]:
        return (
            getattr(self._local, "respid", None),
            getattr(self._local, "item_id", None),
        )

    def _retry_count_for_item(self, respid: Optional[str], item_id: Optional[str]) -> int:
        return self._retry_by_item.get((respid, item_id), 0)

    def record_failure(
        self,
        respid: Optional[str],
        item_id: Optional[str],
        scope: str,
        exc: BaseException,
        category: Optional[str] = None,
    ) -> None:
        record = {
            "respid": respid,
            "item_id": item_id,
            "scope": scope,
            "category": classify_error(exc, category=category),
            "exception_class": type(exc).__name__,
            "reason": sanitize_reason(exc),
        }
        retry_count = self._retry_count_for_item(respid, item_id)
        if retry_count > 0:
            record["retry_count"] = retry_count
        with self._lock:
            self._records.append(record)

    def record_retry(
        self,
        respid: Optional[str] = None,
        item_id: Optional[str] = None,
        attempt: Optional[int] = None,
    ) -> None:
        if respid is None and item_id is None:
            respid, item_id = self._current_context()
        key = (respid, item_id)
        with self._lock:
            self._retry_total += 1
            self._retry_by_item[key] = self._retry_by_item.get(key, 0) + 1

    def retry_hook(self, exc: Optional[BaseException], attempt: int) -> None:
        """Callable for apply_langchain_retry(on_retry=...): one call per retry.

        Attributes the retry to the current thread-local (respid, item_id) context
        set by the runner around each LLM call.
        """
        self.record_retry(attempt=attempt)

    def summary_by_category(self) -> Dict[str, int]:
        with self._lock:
            summary: Dict[str, int] = {}
            for record in self._records:
                category = record["category"]
                summary[category] = summary.get(category, 0) + 1
            return summary

    def retry_totals(self) -> int:
        with self._lock:
            return self._retry_total


class ProgressHandler(BaseCallbackHandler):
    """Prints a running completion counter during a .batch() run.

    Counts only ROOT chain completions (one per batched item). LangChain
    propagates the config callbacks into nested runnable invocations, so we
    filter on ``parent_run_id is None`` to avoid counting each item's inner
    chain calls. Because .batch() is unchunked, completions interleave across
    pool threads, so this is a thread-safe completion counter rather than a
    per-wave barrier. To keep output bounded, a line is printed only every
    ``interval`` completions (and on the last).
    """

    def __init__(self, total: int, interval: int = 8, label: str = "personas"):
        self.total = total
        self.interval = max(1, interval)
        self.label = label
        self._done = 0
        self._lock = threading.Lock()

    def on_chain_end(self, outputs, *, parent_run_id=None, **kwargs) -> None:
        if parent_run_id is not None:
            return
        with self._lock:
            self._done += 1
            done = self._done
        if done % self.interval == 0 or done == self.total:
            print(f"  [progress] {done}/{self.total} {self.label} done")


class TokenUsageRecorder(BaseCallbackHandler):
    """Thread-safe accumulator for billed token usage, including prompt-cache reads.

    `with_structured_output()` returns the parsed model and discards the AIMessage, so token
    counts are unreachable from the runners' data flow. This handler sits below the parser and
    below `apply_langchain_retry`, which is where the raw provider response still exists.

    Consequence worth knowing when reading the numbers: every retry attempt is counted, so
    `calls` is **billed** calls, not logical (question, persona) cells. That is what a cost
    meter wants.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.calls = 0
        self.calls_with_hit = 0
        self.prompt_tokens = 0
        self.cached_tokens = 0
        self.completion_tokens = 0

    def on_llm_end(self, response, **kwargs) -> None:
        # `langchain_openai` puts the provider's raw `usage` dict here, so
        # `prompt_tokens_details.cached_tokens` arrives unmodified. Deliberately NOT
        # `usage_metadata.input_token_details["cache_read"]`: LangChain prefixes that key with the
        # service tier, so it is absent under its plain name on some responses.
        usage = (getattr(response, "llm_output", None) or {}).get("token_usage") or {}
        details = usage.get("prompt_tokens_details") or {}
        # A non-caching model/provider omits the details block entirely -- count the call, not a hit.
        cached = int(details.get("cached_tokens") or 0) if isinstance(details, dict) else 0
        with self._lock:
            self.calls += 1
            self.prompt_tokens += int(usage.get("prompt_tokens") or 0)
            self.completion_tokens += int(usage.get("completion_tokens") or 0)
            self.cached_tokens += cached
            if cached:
                self.calls_with_hit += 1

    def summary(self) -> Dict[str, Any]:
        """Counters plus the two derived rates, or an empty dict if nothing was recorded."""
        with self._lock:
            if not self.calls:
                return {}
            return {
                "calls": self.calls,
                "calls_with_cache_hit": self.calls_with_hit,
                "call_hit_rate": self.calls_with_hit / self.calls,
                "prompt_tokens": self.prompt_tokens,
                "cached_prompt_tokens": self.cached_tokens,
                "cached_token_fraction": (
                    self.cached_tokens / self.prompt_tokens if self.prompt_tokens else 0.0
                ),
                "completion_tokens": self.completion_tokens,
            }


def write_token_json(
    summary: Dict[str, Any],
    output_dir: str,
    timestamp: str,
) -> Optional[str]:
    """Persist the token summary as JSON when any usage was captured."""
    if not summary:
        return None
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, f"run_tokens_{timestamp}.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(summary, handle, ensure_ascii=False, indent=2)
    return path


def print_token_summary(summary: Dict[str, Any], json_path: Optional[str] = None) -> None:
    """Print a compact run-end token/cache summary.

    Tokens and rates only, no dollars: a price table in code goes stale, and the multiply is the
    reader's to do against current list prices.
    """
    if not summary:
        print("\n[tokens] no usage recorded (no provider usage metadata on this run)")
        return
    print(
        f"\n[tokens] calls={summary['calls']:,} "
        f"prompt={summary['prompt_tokens']:,} "
        f"cached={summary['cached_prompt_tokens']:,} "
        f"({summary['cached_token_fraction']:.1%} of prompt) "
        f"completion={summary['completion_tokens']:,}"
    )
    print(
        f"[tokens] cache hit on {summary['calls_with_cache_hit']:,}/{summary['calls']:,} calls "
        f"({summary['call_hit_rate']:.1%})"
    )
    if json_path:
        print(f"[tokens] summary saved to: {json_path}")


def write_error_jsonl(
    records: List[Dict[str, Any]],
    output_dir: str,
    timestamp: str,
) -> Optional[str]:
    """Persist error records as JSONL when any failures were captured."""
    if not records:
        return None
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, f"run_errors_{timestamp}.jsonl")
    with open(path, "w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return path


def print_error_summary(recorder: RunErrorRecorder, jsonl_path: Optional[str] = None) -> None:
    """Print a compact run-end summary of failures and retries."""
    records = recorder.records
    by_category = recorder.summary_by_category()
    retry_total = recorder.retry_totals()
    print(
        f"\n[errors] total={len(records)} by_category={by_category or {}} retries_total={retry_total}"
    )
    if jsonl_path:
        print(f"[errors] log saved to: {jsonl_path}")
