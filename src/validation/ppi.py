"""Prediction-Powered Inference (PPI++) estimators for rectifying LLM estimates with human labels.

Given a small human-labelled calibration sample `H` and a large LLM-labelled pool `U`, PPI combines
them into an estimate that is unbiased regardless of how wrong the LLM is: the LLM contributes only
through a power-tuned weight `lambda`, and the human labels correct whatever bias it carries.

Implements a prediction-powered-inference estimator — `lambda_ppi` is the power-tuning step,
`ppi_binary` is §3.1.

**Read §7.3 before interpreting results.** When the LLM carries no person-level signal,
`lambda -> 0` and `ppi_binary` reduces algebraically to `mean(y_h)` — the human-only estimate. That
is the estimator behaving correctly, not a bug, but it means an error reduction measured against the
raw LLM is *not* evidence that rectification worked. Callers should surface the median lambda
alongside any PPI number.

Numpy-only and panel-agnostic by design: no survey, question, or demographic knowledge lives here.
Survey-specific plumbing belongs outside this module.
"""

from __future__ import annotations

from typing import Any

import numpy as np


def lambda_ppi(g: np.ndarray, f: np.ndarray, n: int, n_pool: int) -> float:
    """The PPI++ power-tuning weight (spec §3.2), clipped to [0, 1].

    `lambda_opt = Cov_H(g, f) / ((1 + n/N) * Var_H(f))`, where `g` is the human label and `f` the
    LLM prediction on the same calibration respondents. Returns 0 when the LLM has no variance to
    exploit or the covariance is non-positive — in which case the caller's estimate collapses to
    human-only.
    """
    if n < 2 or n_pool < 1:
        return 0.0
    var_f = float(np.var(f, ddof=1))
    if var_f <= 0.0:
        return 0.0
    cov_gf = float(np.cov(g, f, ddof=1)[0, 1])
    lam = cov_gf / ((1.0 + n / n_pool) * var_f)
    return float(np.clip(lam, 0.0, 1.0))


def ppi_binary(y_hit: np.ndarray, z_hit_h: np.ndarray, z_hit_u: np.ndarray) -> float:
    """Rectified prevalence of one binary indicator (spec §3.1).

    `theta_hat = lambda * mean_U(z) + mean_H(y - lambda * z)`. At `lambda = 0` this is exactly
    `mean_H(y)`, the human-only estimate; at `lambda = 1` it is the classic PPI estimator.
    """
    n, n_pool = len(y_hit), len(z_hit_u)
    if n == 0:
        return 0.0
    synthetic = float(z_hit_u.mean()) if n_pool else 0.0
    lam = lambda_ppi(y_hit, z_hit_h, n, n_pool)
    correction = float((y_hit - lam * z_hit_h).mean())
    return lam * synthetic + correction


def normalize_probs(raw: dict[str, float]) -> dict[str, float]:
    """Clip negatives and rescale to sum 1, falling back to uniform if nothing survives.

    Rectification is unconstrained, so a rare option's estimate can land slightly below zero or the
    set can miss 1. Single-choice distributions must be simplex-valued for the distance metrics;
    multi-select marginals must *not* be normalized (they need not sum to 1).
    """
    clipped = {k: max(0.0, v) for k, v in raw.items()}
    total = sum(clipped.values())
    if total <= 0:
        n = len(clipped) or 1
        return {k: 1.0 / n for k in clipped}
    return {k: v / total for k, v in clipped.items()}


def hits(value: Any, option: str) -> bool:
    """Whether a parsed response selected `option` — list for multi-select, scalar otherwise."""
    if isinstance(value, list):
        return option in value
    return value == option


def ppi_marginals(
    y_h: list[Any],
    z_h: list[Any],
    z_u: list[Any],
    options: list[str],
    *,
    is_multi: bool,
) -> dict[str, float]:
    """Rectify each option independently, one `ppi_binary` per option indicator.

    Single-choice results are normalized to a distribution; multi-select marginals are returned raw,
    since selection rates across options need not sum to 1.
    """
    out: dict[str, float] = {}
    for opt in options:
        y_hit = np.array([1.0 if hits(v, opt) else 0.0 for v in y_h])
        zh_hit = np.array([1.0 if hits(v, opt) else 0.0 for v in z_h])
        zu_hit = np.array([1.0 if hits(v, opt) else 0.0 for v in z_u])
        out[opt] = ppi_binary(y_hit, zh_hit, zu_hit)
    return out if is_multi else normalize_probs(out)


def pearson(a: np.ndarray, b: np.ndarray) -> float:
    """Pearson correlation, NaN when either side is constant (lambda is 0 there anyway).

    Callers pass per-option hit vectors indexed by respondent, so the margin is across
    respondents within one option — the strict one. Do not compare the resulting r to an
    across-questions-within-participant figure: the two margins are not comparable.
    """
    if len(a) < 2 or a.std() == 0 or b.std() == 0:
        return float("nan")
    return float(np.corrcoef(a, b)[0, 1])
