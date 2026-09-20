"""Probability-vector hygiene, shared by the runner and the scorer.

One function, kept in its own module because both the survey engine and
`scripts/twin2k/prob_scoring.py` need the same definition of "make this a distribution". A second
copy would drift, and a drifting normalizer changes every distributional metric silently.
"""

from __future__ import annotations


def normalize_probs(raw: dict[str, float]) -> dict[str, float]:
    """Clip negatives and rescale to sum 1, falling back to uniform if nothing survives.

    A model's stated vector can land slightly below zero on a rare option, or miss 1 altogether.
    Single-choice distributions must be simplex-valued for the distance metrics. Multi-select
    marginals must *not* be passed through here: they are per-option inclusion rates and need not
    sum to 1.
    """
    clipped = {k: max(0.0, v) for k, v in raw.items()}
    total = sum(clipped.values())
    if total <= 0:
        n = len(clipped) or 1
        return {k: 1.0 / n for k in clipped}
    return {k: v / total for k, v in clipped.items()}
