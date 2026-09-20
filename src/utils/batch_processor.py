"""Reusable batch processing utility for LLM operations"""

import time
from typing import Any, Callable, List, Optional

from src.utils.progress import ProgressHandler

# Consecutive sequential-fallback failures tolerated before giving up and re-raising. The fallback
# exists for a pool-creation failure, where sequential .invoke() succeeds; this many failures in a
# row means the cause is dispatch-level and every remaining item would fail identically.
_MAX_SEQUENTIAL_FAILURES = 3


class BatchProcessor:
    """Handles batch processing of LLM requests with rate limiting and fallback"""

    def __init__(self, max_concurrency: Optional[int] = None, label: str = "calls"):
        """
        Args:
            max_concurrency: LangChain .batch() thread-pool cap (None = LangChain default).
                This is the only concurrency knob: .batch() uses a rolling pool, so item N+1
                starts as soon as any earlier item finishes.
            label: noun used in progress lines ("12/50 calls done")
        """
        self.max_concurrency = max_concurrency
        self.label = label

    def _batch_config(self, total: int) -> dict:
        """Config for one .batch() call: the concurrency cap plus a progress counter.

        Mirrors the stateful runner's config so both paths report progress the same way. The
        interval keeps output bounded on long runs: one line per in-flight wave when a cap is
        set, else ~20 lines for the whole batch, since a flat interval would print hundreds of
        lines per question on a full panel.
        """
        config: dict = {
            "callbacks": [
                ProgressHandler(
                    total=total,
                    interval=self.max_concurrency or max(8, total // 20),
                    label=self.label,
                )
            ]
        }
        if self.max_concurrency is not None:
            config["max_concurrency"] = self.max_concurrency
        return config

    def process(self, items: List[Any], chain: Callable) -> List[Any]:
        """Process items in one batch with automatic fallback on errors

        Args:
            items: List of input items to process
            chain: Callable chain (prompt | llm) that takes batched input

        Returns:
            List of processed results (same length as items). A permanently failed item is
            returned as its Exception, so callers can report the real cause; callers that only
            need a sentinel can treat any non-result the same way they treated None.

        Raises:
            The triggering exception if the sequential fallback fails
            _MAX_SEQUENTIAL_FAILURES times in a row (see _sequential_fallback).
        """
        if not items:
            return []

        cap = self.max_concurrency or "LangChain default"
        print(f"  Processing {len(items)} requests (max_concurrency={cap})...")

        try:
            # return_exceptions keeps one bad item from discarding the whole batch's successes
            # (they were already paid for) and preserves each failure's real cause.
            batch_results = chain.batch(
                items, config=self._batch_config(len(items)), return_exceptions=True
            )
        except Exception as e:
            # Per-item failures come back as values, so reaching here means dispatch itself
            # failed -- the batch was never fanned out and nothing was billed.
            print(f"    Warning: Batch failed ({e}), falling back to sequential...")
            return self._sequential_fallback(items, chain, e)

        # Retry just the failed items once each, so a transient error still gets the second
        # chance the old whole-batch sequential fallback gave it.
        batch_results = list(batch_results)
        for i, result in enumerate(batch_results):
            if not isinstance(result, Exception):
                continue
            print(f"      Warning: Item {i} failed ({result}), retrying once...")
            time.sleep(0.5)
            try:
                batch_results[i] = chain.invoke(items[i])
            except Exception as retry_e:
                print(f"      Warning: Failed item {i}: {retry_e}")
                batch_results[i] = retry_e
        return batch_results

    def _sequential_fallback(
        self, items: List[Any], chain: Callable, batch_exc: Exception
    ) -> List[Any]:
        """Run items one at a time after a whole-batch dispatch failure.

        This rescues the real case it was written for: thread-pool creation failing
        ("can't start new thread"), where sequential .invoke() needs no pool and succeeds.

        The other case is a dispatch-level bug (bad config key, malformed input) that fails every
        item identically. The old chunk loop bounded that to one chunk; unchunked it would be the
        whole question -- thousands of guaranteed failures at 0.5s each, ending in a silent
        n_valid=0. So after _MAX_SEQUENTIAL_FAILURES consecutive failures, re-raise.

        Re-raising rather than filling the remaining items is deliberate: filled items would become
        "Error" sentinel rows that a checkpoint could commit, whereas the exception reaches the
        question-level handler, which records the failure and moves on WITHOUT checkpointing the
        question -- leaving it cleanly re-runnable by --resume.
        """
        results: List[Any] = []
        consecutive_failures = 0
        for i, item in enumerate(items):
            try:
                results.append(chain.invoke(item))
                time.sleep(0.5)  # Small delay between sequential calls
                consecutive_failures = 0
            except Exception as inner_e:
                print(f"      Warning: Failed item {i}: {inner_e}")
                results.append(inner_e)
                consecutive_failures += 1
                if consecutive_failures >= _MAX_SEQUENTIAL_FAILURES:
                    print(
                        f"    Sequential fallback failed {consecutive_failures} times in a row "
                        f"at item {i}; treating this as a dispatch-level failure rather than "
                        f"burning the remaining {len(items) - i - 1} items."
                    )
                    # `from batch_exc` keeps the original batch failure in the traceback: the
                    # repeated sequential failure is the evidence, the batch failure the trigger.
                    raise inner_e from batch_exc
        return results
