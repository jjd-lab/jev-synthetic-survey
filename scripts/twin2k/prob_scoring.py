"""Score probability vectors from any Twin arm — Jev's native ones or gpt-4.1's verbalized ones.

Two subcommands over one interchange format, so no metric ever grows a second code path:

    convert   a run's respondent_details_*.xlsx -> probs JSONL   (the gpt-4.1 arms)
    score     one or more arms' JSONL           -> one report    (every arm, including Jev)

`probe_jev.py` writes the same JSONL directly, which is the whole point: after `convert`, JC and BC
differ only in which model produced the numbers, and every metric below reads them identically.

What the arms are and what decides between them was fixed in a written plan before the runs; this
module implements it and nothing more. The two criteria:

  * C3 — soft distributional error and multiclass Brier, JC vs BC, paired.
  * C1 — calibration: equal-task-weighted ECE on the 65 binary columns.

Four choices here are load-bearing, and all four are the plan's, fixed before any data:

  1. **Equal weight per task, never pooled cells.** 40 of 108 columns are the pricing study, so a
     cell-pooled mean is 37% one experiment. Column mean -> task mean -> mean over the 16 tasks,
     borrowed from `paper_accuracy.score_pairs` rather than reimplemented.
  2. **Pricing reported separately, always.** TypeSafe documents Jev as weak on numeric
     representations and those 40 columns pipe a randomised price into the stem, so every headline
     comes with a pricing-excluded twin. If the two disagree in sign, that split IS the finding.
  3. **Raw vectors in, normalised only at the point of use.** How far a source's vector is from
     summing to 1 is itself a result (Jev's docs promise 1; gpt-4.1's verbalized vectors demonstrably
     do not), so `raw_sum` is reported as a distribution and never quietly repaired upstream.
  4. **Bootstrap over RESPONDENTS, not cells.** ~84 cells from one respondent are correlated, so
     resampling cells would understate the interval several-fold. Arm differences resample the SAME
     respondents, which is what makes a paired margin readable against the determinism floor.

The scorer's external anchor: `score` on the existing `prior_answers` run over the full panel must
reproduce `paper_accuracy`'s recorded 72.92% accuracy / 73.27% leave-one-out majority. The formulae
below are all short enough to look right while being wrong; that pair of numbers is what pins them.

Usage:
    python scripts/twin2k/prob_scoring.py convert \\
        --details runs/jev_vs_gpt41_n300/gpt41_probs_source/respondent_details_20260919_112211.xlsx \\
        --arm gpt41_probs_chained --out /tmp/gpt41_probs.jsonl --sample 300

    python scripts/twin2k/prob_scoring.py score \\
        --arm jev_chained=runs/jev_vs_gpt41_n300/jev_choice.jsonl \\
        --arm gpt41_probs_chained=runs/jev_vs_gpt41_n300/gpt41_probs.jsonl \\
        --out /tmp/report.json
"""

import argparse
import json
import random
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.twin2k.paper_accuracy import (  # noqa: E402
    EXPECTED_TASKS,
    load_entries,
    score_pairs,
    task_of,
)
from src.validation.probs import normalize_probs  # noqa: E402
from src.validation.response_validator import (  # noqa: E402
    total_variation_distance,
    wasserstein_from_pcts,
)

PRICING_TASK = "Pricing"
# 10 equal-width bins is the reliability-diagram convention and what the plan pre-registered. ECE is
# bin-sensitive, so `--ece-bins` exists and an adaptive (equal-count) cross-check is always reported
# alongside -- a number that moves a lot between the two is not a calibration finding.
ECE_BINS = 10
BOOTSTRAP_RESAMPLES = 1_000
BOOTSTRAP_SEED = 20260919
# Log loss needs a floor or one zero-probability cell makes the arm's score infinite, which reports
# nothing about the other 25,000 cells. The count of those cells is reported on its own instead.
LOGLOSS_CLIP = 1e-3


# Interchange format
def open_jsonl(path) -> "object":
    """Open a run file, transparently handling gzip.

    The n=300 arms ship as plain `.jsonl`; the 2,058-respondent panel file stays gzipped, since
    it is 71 MB raw. Both read the same way.
    """
    path = Path(path)
    if path.suffix == ".gz":
        import gzip
        return gzip.open(path, "rt", encoding="utf-8")
    return open(path, encoding="utf-8")


def read_jsonl(path: Path) -> list:
    """Cell rows only: `done` / `aborted` markers are resume bookkeeping, not measurements."""
    rows = []
    with open_jsonl(path) as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if row.get("done") or row.get("aborted"):
                continue
            rows.append(row)
    if not rows:
        raise SystemExit(f"{path}: no cell rows")
    return rows


def vector_of(row: dict, options: list) -> np.ndarray:
    """One cell's forecast over CANONICAL options, as a simplex.

    `probs: null` means the source only ever committed an answer (the `hard_choice` arms), which is
    a one-hot forecast -- the honest reading, and the one that makes a hard-choice arm comparable on
    Brier at all rather than unscoreable. A vector that cannot be normalised (all zero, or all
    negative) falls back to one-hot on the committed choice for the same reason.
    """
    probs = row.get("probs")
    if isinstance(probs, dict) and probs:
        normalised = normalize_probs({opt: float(probs.get(opt, 0.0)) for opt in options})
        vector = np.array([normalised[opt] for opt in options], dtype=float)
        # `normalize_probs` returns uniform when nothing survives clipping. Uniform is a real
        # forecast for a model that said nothing, but here it means the vector was unusable, so the
        # committed answer -- which the model did give -- is the better reading.
        if np.allclose(vector, 1.0 / len(options)) and sum(
            max(0.0, float(probs.get(opt, 0.0))) for opt in options
        ) <= 0:
            return _one_hot(row.get("choice"), options)
        return vector
    return _one_hot(row.get("choice"), options)


def _one_hot(label, options: list):
    if label not in options:
        return None
    vector = np.zeros(len(options), dtype=float)
    vector[options.index(label)] = 1.0
    return vector


def match_option(raw, options: list):
    """Coerce one xlsx cell back onto the MAPPING's option label, or None if it is not a label.

    Needed because `pd.read_excel` types a numeric-coded column as float64, so the 10 `QID198_*`
    columns arrive as `1.0` / `2.0` against a mapping that calls the scale `"1"` / `"2"`.
    `paper_accuracy` never notices: its unordered branch is a string equality between two cells from
    the same file, so `"1.0" == "1.0"` scores correctly without the option list. A probability vector
    has no such luxury -- it is indexed BY the option list, so an unmatched label is an unscorable
    cell, and dropping those 10 columns silently would change the denominator of a 16-task mean.

    Only an exactly-integral float is rewritten. A genuine `"1.5"` against options `"1"`/`"2"` stays
    unmatched and is counted, because guessing which end of the scale it meant is not this
    function's business.
    """
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return None
    text = str(raw).strip()
    if text in ("", "Error", "LLM Error", "nan", "None"):
        return None
    if text in options:
        return text
    try:
        number = float(text)
    except ValueError:
        return text
    if number.is_integer() and str(int(number)) in options:
        return str(int(number))
    return text


def raw_sum(row: dict):
    """What the source's vector actually summed to, before any normalisation. None for hard choice."""
    probs = row.get("probs")
    if not isinstance(probs, dict) or not probs:
        return None
    return float(sum(float(value) for value in probs.values()))


def build_columns(rows: list, entries: dict) -> dict:
    """Group cells into per-column numpy blocks, dropping what cannot be scored.

    Returns {qid: {options, ordered, task, respids, P (n,k), y (n,), raw_sums, had_probs}}.
    A cell is dropped when the human label is missing (`is_asked` false in the human data, or an
    unmapped label) or the forecast is unusable -- counted in `coverage`, never scored as wrong.
    """
    by_qid: dict = {}
    dropped = {"no_human": 0, "no_vector": 0, "unknown_qid": 0, "human_off_scale": 0}

    for row in rows:
        qid = row["qid"]
        entry = entries.get(qid)
        if entry is None:
            dropped["unknown_qid"] += 1
            continue
        options = list(entry["choices"].values())
        human = row.get("human")
        if human is None or (isinstance(human, float) and pd.isna(human)):
            dropped["no_human"] += 1
            continue
        human = str(human).strip()
        if human in ("", "nan", "None", "Error"):
            dropped["no_human"] += 1
            continue
        if human not in options:
            # The mapping's option list is the scale; a label outside it cannot be placed on it.
            dropped["human_off_scale"] += 1
            continue
        vector = vector_of(row, options)
        if vector is None:
            dropped["no_vector"] += 1
            continue

        block = by_qid.setdefault(qid, {
            "options": options,
            "ordered": bool(entry.get("ordered_scale")),
            "task": task_of(qid, entry),
            "respids": [], "vectors": [], "y": [], "raw_sums": [], "choices": [],
        })
        block["respids"].append(str(row["respid"]))
        block["vectors"].append(vector)
        block["y"].append(options.index(human))
        block["raw_sums"].append(raw_sum(row))
        block["choices"].append(row.get("choice"))

    columns = {}
    for qid, block in by_qid.items():
        # Two scorable respondents is the same floor `paper_accuracy` uses: a leave-one-out
        # reference has nothing to predict a lone respondent from, and the marginal of one
        # respondent is not a marginal.
        if len(block["y"]) < 2:
            continue
        block["P"] = np.vstack(block["vectors"])
        block["y"] = np.array(block["y"], dtype=int)
        del block["vectors"]
        columns[qid] = block
    return columns, dropped


# Aggregation: column -> task -> equal weight across tasks
def by_task(per_column: dict, columns: dict, exclude=()) -> dict:
    """Column values -> task means. `exclude` drops whole tasks (the pricing split)."""
    buckets: dict = {}
    for qid, value in per_column.items():
        task = columns[qid]["task"]
        if task in exclude or value is None or not np.isfinite(value):
            continue
        buckets.setdefault(task, []).append(float(value))
    return {task: float(np.mean(values)) for task, values in buckets.items()}


def equal_weight(task_means: dict):
    """The one aggregation every headline uses. None when no task survived."""
    if not task_means:
        return None
    return float(np.mean(list(task_means.values())))


def headline(per_column: dict, columns: dict) -> dict:
    """A per-column metric reported the two pre-registered ways: all tasks, and pricing excluded."""
    all_tasks = by_task(per_column, columns)
    no_pricing = by_task(per_column, columns, exclude=(PRICING_TASK,))
    return {
        "all_tasks": equal_weight(all_tasks),
        "excl_pricing": equal_weight(no_pricing),
        "n_tasks": len(all_tasks),
        "per_task": all_tasks,
    }


# Distributional fidelity (C3 primary)
def marginals(block: dict, how: str, qid: str = "") -> np.ndarray:
    """The arm's predicted marginal for one column, under one of the three commit rules.

    All three read the SAME vectors, which is the point: an earlier survey established that soft
    aggregation is the expected value of the weighted draw, so any gap between `soft` and `draw`
    here is Monte Carlo error on ~250 cells rather than a difference in elicitation.
    """
    P = block["P"]
    if how == "soft":
        return P.mean(axis=0)
    if how == "argmax":
        picks = P.argmax(axis=1)
    elif how == "draw":
        # `random.Random(f"{respid}|{qid}")` and `rng.choices` are `_weighted_draw_answer`'s exact
        # seed and draw, so a cell scored here gets the answer a `weighted_draw` RUN would have
        # committed for it -- the offline replay is the arm, not an approximation of it. Seeding per
        # (respid, qid) and not per respondent also matters on its own: one seed per persona would
        # correlate all ~84 of that persona's draws and narrow the resulting marginal.
        picks = np.array([
            _draw_index(P[index], respid, qid)
            for index, respid in enumerate(block["respids"])
        ], dtype=int)
    else:
        raise ValueError(how)
    return np.bincount(picks, minlength=P.shape[1]) / len(picks)


def _draw_index(vector: np.ndarray, respid: str, qid: str) -> int:
    weights = np.clip(vector, 0.0, None)
    if weights.sum() <= 0:
        return int(vector.argmax())
    rng = random.Random(f"{respid}|{qid}")
    return rng.choices(range(len(weights)), weights=list(weights), k=1)[0]


def human_marginal(block: dict) -> np.ndarray:
    return np.bincount(block["y"], minlength=len(block["options"])) / len(block["y"])


def distance(block: dict, predicted: np.ndarray, actual: np.ndarray) -> float:
    """TVD for the 65 nominal columns, Wasserstein-1 for the 43 ordinal ones.

    Both come from `src/validation/response_validator.py` unchanged -- the repo's shipped
    distributional metrics, so a number here is comparable to every other arm ever scored. They take
    label-keyed dicts, hence the round trip.
    """
    options = block["options"]
    a = {opt: float(predicted[i]) for i, opt in enumerate(options)}
    b = {opt: float(actual[i]) for i, opt in enumerate(options)}
    if block["ordered"]:
        return wasserstein_from_pcts(a, b, options)
    return total_variation_distance(a, b, options)


def fidelity(columns: dict) -> dict:
    """Distributional error per commit rule, plus the entropy ratio.

    Nominal and ordinal are reported in SEPARATE buckets and never averaged together: TVD is
    bounded by 1 and Wasserstein-1 is in scale positions, so a mean over both is a number with no
    unit. The plan's Wilcoxon comparison is within a bucket for the same reason.
    """
    out: dict = {}
    for how in ("soft", "argmax", "draw"):
        per_column = {
            qid: distance(block, marginals(block, how, qid), human_marginal(block))
            for qid, block in columns.items()
        }
        for bucket in ("nominal", "ordinal"):
            subset = {qid: value for qid, value in per_column.items()
                      if (columns[qid]["ordered"] is (bucket == "ordinal"))}
            out[f"{how}_{bucket}"] = headline(subset, columns)
            out[f"{how}_{bucket}"]["per_column"] = subset

    # Entropy ratio: < 1 is the collapse chaining is meant to fix, > 1 is a twin hedging where the
    # humans were decided. Normalised by log(k) so columns with different option counts compare.
    ratios, collapsed = {}, []
    for qid, block in columns.items():
        predicted, actual = marginals(block, "soft", qid), human_marginal(block)
        h_actual = _entropy(actual)
        ratios[qid] = float(_entropy(predicted) / h_actual) if h_actual > 0 else None
        if len(set(marginals(block, "argmax", qid).nonzero()[0])) == 1:
            collapsed.append(qid)
    out["entropy_ratio"] = headline({k: v for k, v in ratios.items() if v is not None}, columns)
    out["collapsed_columns"] = sorted(collapsed)
    return out


def _entropy(distribution: np.ndarray) -> float:
    positive = distribution[distribution > 0]
    if len(positive) == 0:
        return 0.0
    return float(-(positive * np.log(positive)).sum() / np.log(len(distribution)))


# Brier, its decomposition, and the two reference forecasts
def brier_cells(block: dict) -> np.ndarray:
    """Multiclass Brier per cell: sum_k (p_k - 1[y=k])^2. Lower is better, 0 is an oracle."""
    onehot = np.zeros_like(block["P"])
    onehot[np.arange(len(block["y"])), block["y"]] = 1.0
    return ((block["P"] - onehot) ** 2).sum(axis=1)


def loo_marginal_forecast(block: dict) -> np.ndarray:
    """F1: each cell forecast by the OTHER respondents' label marginal in that column.

    Persona-blind by construction and out of sample, so it is a fair competitor rather than the
    inflated in-sample marginal. This repo has already measured that the in-sample version inverts
    a conclusion at n=50, which is why the leave-one-out form is the only one used.
    """
    n, k = len(block["y"]), len(block["options"])
    counts = np.bincount(block["y"], minlength=k).astype(float)
    forecast = np.tile(counts, (n, 1))
    forecast[np.arange(n), block["y"]] -= 1.0
    return forecast / (n - 1)


def brier_report(columns: dict) -> dict:
    """Brier, log loss, the Murphy decomposition, and skill against both reference forecasts."""
    per_column, per_column_f1, per_column_f2, per_column_ll = {}, {}, {}, {}
    zero_prob_cells = 0
    for qid, block in columns.items():
        per_column[qid] = float(brier_cells(block).mean())
        k = len(block["options"])
        rows = np.arange(len(block["y"]))

        f1 = loo_marginal_forecast(block)
        onehot = np.zeros_like(f1)
        onehot[rows, block["y"]] = 1.0
        per_column_f1[qid] = float(((f1 - onehot) ** 2).sum(axis=1).mean())
        per_column_f2[qid] = float(
            ((np.full_like(onehot, 1.0 / k) - onehot) ** 2).sum(axis=1).mean()
        )

        truth_prob = block["P"][rows, block["y"]]
        zero_prob_cells += int((truth_prob == 0).sum())
        per_column_ll[qid] = float(-np.log(np.clip(truth_prob, LOGLOSS_CLIP, 1.0)).mean())

    brier = headline(per_column, columns)
    f1_brier = headline(per_column_f1, columns)
    f2_brier = headline(per_column_f2, columns)
    return {
        "brier": brier,
        "log_loss": headline(per_column_ll, columns),
        "brier_per_column": per_column,
        "reference_loo_marginal": f1_brier,
        "reference_uniform": f2_brier,
        # BSS is reported as CONTEXT, not a criterion: on demographics-only grounding every model
        # here is expected to sit below a persona-blind reference, which is exactly why the
        # individual-signal arm waits for prior-answers grounding.
        "bss_vs_loo_marginal": _skill(brier, f1_brier),
        "bss_vs_uniform": _skill(brier, f2_brier),
        "cells_with_zero_probability_on_truth": zero_prob_cells,
        "murphy": murphy(columns),
    }


def _skill(brier: dict, reference: dict) -> dict:
    out = {}
    for key in ("all_tasks", "excl_pricing"):
        value, ref = brier[key], reference[key]
        # `value is None` and not `not value`: a Brier of exactly 0 is a perfect arm, i.e. skill 1,
        # not a missing measurement. Only the DIVISOR being 0 or absent makes the ratio undefined.
        out[key] = None if value is None or not ref else float(1.0 - value / ref)
    return out


def murphy(columns: dict, bins: int = ECE_BINS) -> dict:
    """Brier = reliability - resolution + uncertainty, on the binary columns where it is defined.

    Restricted to the 65 nominal (all binary) columns on purpose. The decomposition is a statement
    about a scalar forecast of a binary event; extending it to a 7-point ordinal needs a choice of
    which event, and any such choice would make the three terms incomparable to the literature the
    words reliability/resolution come from. Multiclass Brier over all 108 is reported above.

    Reads the forecast as P(first canonical option), the same scalar the ECE below uses, so a
    reliability diagram and this decomposition describe one object.
    """
    forecasts, outcomes = [], []
    for block in columns.values():
        if block["ordered"] or len(block["options"]) != 2:
            continue
        forecasts.append(block["P"][:, 0])
        outcomes.append((block["y"] == 0).astype(float))
    if not forecasts:
        return {"n_cells": 0}
    f = np.concatenate(forecasts)
    y = np.concatenate(outcomes)
    base = y.mean()
    edges = np.linspace(0.0, 1.0, bins + 1)
    index = np.clip(np.digitize(f, edges[1:-1]), 0, bins - 1)

    reliability = resolution = 0.0
    for b in range(bins):
        mask = index == b
        if not mask.any():
            continue
        weight = mask.sum() / len(f)
        reliability += weight * (f[mask].mean() - y[mask].mean()) ** 2
        resolution += weight * (y[mask].mean() - base) ** 2
    return {
        "n_cells": int(len(f)),
        "bins": bins,
        "reliability": float(reliability),   # lower is better
        "resolution": float(resolution),     # higher is better
        "uncertainty": float(base * (1 - base)),
        "base_rate": float(base),
        "brier_binary_pooled": float(((f - y) ** 2).mean()),
    }


# Calibration (C1)
def _ece(f: np.ndarray, y: np.ndarray, bins: int, adaptive: bool) -> float:
    """Expected calibration error: |mean forecast - mean outcome| per bin, weighted by bin size.

    `adaptive` uses equal-COUNT bins instead of equal-width. Both are reported because equal-width
    bins leave most cells in one or two bins when a model is confident, which can hide a
    miscalibration or invent one -- a verdict that flips between the two is not a verdict.
    """
    if len(f) == 0:
        return float("nan")
    if adaptive:
        edges = np.quantile(f, np.linspace(0.0, 1.0, bins + 1))
        edges = np.unique(edges)
        if len(edges) < 3:
            return float(abs(f.mean() - y.mean()))
        index = np.clip(np.digitize(f, edges[1:-1]), 0, len(edges) - 2)
        n_bins = len(edges) - 1
    else:
        edges = np.linspace(0.0, 1.0, bins + 1)
        index = np.clip(np.digitize(f, edges[1:-1]), 0, bins - 1)
        n_bins = bins
    error = 0.0
    for b in range(n_bins):
        mask = index == b
        if mask.any():
            error += (mask.sum() / len(f)) * abs(f[mask].mean() - y[mask].mean())
    return float(error)


def calibration(columns: dict, bins: int = ECE_BINS) -> dict:
    """C1. Binary columns on P(first canonical option); ordinal columns on the top label.

    The primary number is EQUAL-TASK-WEIGHTED, not pooled: pricing is 40 of 108 columns, so a
    pooled ECE is mostly a statement about how the pricing block is calibrated. Pooled is reported
    beside it, and a large gap between them is itself the finding.
    """
    binary: dict = {}
    ordinal: dict = {}
    diagram: dict = {}
    for qid, block in columns.items():
        rows = np.arange(len(block["y"]))
        if not block["ordered"] and len(block["options"]) == 2:
            f, y = block["P"][:, 0], (block["y"] == 0).astype(float)
            binary[qid] = (f, y)
        else:
            # Top-label calibration: is "the option I was most sure of" right as often as I said?
            f = block["P"].max(axis=1)
            y = (block["P"].argmax(axis=1) == block["y"]).astype(float)
            ordinal[qid] = (f, y)
        del rows

    def _bucket(cells: dict, label: str) -> dict:
        if not cells:
            return {"n_columns": 0}
        per_task: dict = {}
        for qid, (f, y) in cells.items():
            per_task.setdefault(columns[qid]["task"], []).append((f, y))
        task_ece = {
            task: _ece(np.concatenate([f for f, _ in pairs]),
                       np.concatenate([y for _, y in pairs]), bins, adaptive=False)
            for task, pairs in per_task.items()
        }
        pooled_f = np.concatenate([f for f, _ in cells.values()])
        pooled_y = np.concatenate([y for _, y in cells.values()])
        result = {
            "n_columns": len(cells),
            "n_cells": int(len(pooled_f)),
            "bins": bins,
            "ece_equal_task_weight": equal_weight(task_ece),
            "ece_equal_task_weight_excl_pricing": equal_weight(
                {t: v for t, v in task_ece.items() if t != PRICING_TASK}
            ),
            "ece_pooled": _ece(pooled_f, pooled_y, bins, adaptive=False),
            "ece_pooled_adaptive_bins": _ece(pooled_f, pooled_y, bins, adaptive=True),
            "ece_per_task": task_ece,
        }
        diagram[label] = reliability_diagram(pooled_f, pooled_y, bins)
        return result

    return {
        "binary": _bucket(binary, "binary"),
        "ordinal_top_label": _bucket(ordinal, "ordinal_top_label"),
        "reliability_diagram": diagram,
    }


def reliability_diagram(f: np.ndarray, y: np.ndarray, bins: int) -> list:
    """The printable diagram: per bin, mean forecast vs observed frequency and the cell count."""
    edges = np.linspace(0.0, 1.0, bins + 1)
    index = np.clip(np.digitize(f, edges[1:-1]), 0, bins - 1)
    out = []
    for b in range(bins):
        mask = index == b
        out.append({
            "bin": f"[{edges[b]:.1f},{edges[b + 1]:.1f})",
            "n": int(mask.sum()),
            "mean_forecast": float(f[mask].mean()) if mask.any() else None,
            "observed": float(y[mask].mean()) if mask.any() else None,
        })
    return out


# Diagnostics: raw sums, and the between-subject framing contrast
def raw_sum_report(columns: dict) -> dict:
    """What the vectors summed to before normalisation — a result, not a health check.

    Jev's docs promise a distribution over the criteria; gpt-4.1 asked to verbalize one demonstrably
    does not deliver one. Reported so a fidelity win can be read against how much repair it needed.
    """
    sums = [value for block in columns.values() for value in block["raw_sums"] if value is not None]
    if not sums:
        return {"n_cells_with_vectors": 0}
    array = np.array(sums, dtype=float)
    return {
        "n_cells_with_vectors": int(len(array)),
        "mean": float(array.mean()),
        "p01": float(np.quantile(array, 0.01)),
        "median": float(np.median(array)),
        "p99": float(np.quantile(array, 0.99)),
        "share_within_1pct_of_1": float(np.mean(np.abs(array - 1.0) <= 0.01)),
    }


def framing_contrast(columns: dict, entries: dict) -> dict:
    """Per between-subject group: does the model move between arms the way the humans did?

    Diagnostic, never a criterion. Per-arm fit cannot detect a twin that ignores the frame -- it can
    fit each arm's marginal well while predicting no difference at all, which is the specific
    failure a between-subject manipulation exists to expose. Reported as sign agreement plus a
    magnitude ratio on P(first canonical option), averaged over a group's columns.

    Only groups whose arms the run actually covers appear, and only with exactly two arms: the
    contrast is a difference, and a three-arm group has no single one.
    """
    groups: dict = {}
    for qid, block in columns.items():
        entry = entries[qid]
        group, condition_arm = entry.get("condition_group"), entry.get("condition_arm")
        if not group or not condition_arm:
            continue
        predicted = marginals(block, "soft", qid)
        actual = human_marginal(block)
        groups.setdefault(group, {}).setdefault(str(condition_arm), []).append(
            (float(predicted[0]), float(actual[0]))
        )

    out = {}
    for group, arms in groups.items():
        if len(arms) != 2:
            out[group] = {"skipped": f"{len(arms)} arms covered, need exactly 2"}
            continue
        first, second = sorted(arms)
        model_delta = (np.mean([p for p, _ in arms[first]])
                       - np.mean([p for p, _ in arms[second]]))
        human_delta = (np.mean([h for _, h in arms[first]])
                       - np.mean([h for _, h in arms[second]]))
        out[group] = {
            "arms": [first, second],
            "human_delta": float(human_delta),
            "model_delta": float(model_delta),
            "sign_agrees": bool(np.sign(model_delta) == np.sign(human_delta)),
            "magnitude_ratio": (float(model_delta / human_delta)
                                if abs(human_delta) > 1e-9 else None),
        }
    agreeing = [g for g in out.values() if g.get("sign_agrees")]
    out["_summary"] = {
        "groups_compared": sum(1 for g in out.values() if "sign_agrees" in g),
        "signs_agreeing": len(agreeing),
    }
    return out


def accuracy_anchor(columns: dict, entries: dict, arm: str, how: str = "argmax") -> dict:
    """`paper_accuracy`'s own metric over these cells, as the scorer's external check.

    Reuses `score_pairs` unchanged, which is what makes 72.92 / 73.27 reproducible from JSONL: if
    the loading, the option lists or the task taxonomy here drifted, this pair of numbers moves.
    Committed answers come from the same vectors as everything else, so the accuracy and the
    distributional numbers below are statements about one set of forecasts.
    """
    pairs: dict = {}
    for qid, block in columns.items():
        options = block["options"]
        if how == "choice":
            synthetic = list(block["choices"])
        else:
            picks = (block["P"].argmax(axis=1) if how == "argmax"
                     else np.array([options.index(label) for label in block["choices"]]))
            synthetic = [options[index] for index in picks]
        pairs[qid] = list(zip(synthetic, [options[index] for index in block["y"]]))
    task_means, coverage = score_pairs(pairs, entries)
    if not task_means:
        return {"accuracy_pct": None}
    return {
        "commit_rule": how,
        "accuracy_pct": 100 * sum(task_means.values()) / len(task_means),
        "loo_majority_pct": 100 * sum(coverage["majority_per_task"].values()) / len(task_means),
        "tasks": len(task_means),
        "columns_scored": coverage["columns_scored"],
    }


# Uncertainty: bootstrap over respondents, Wilcoxon over columns
def _respondent_index(columns: dict, respids: list = None):
    """One respondent ordering, plus per-column row lookups keyed on it.

    `respids` may be passed in so two arms share ONE ordering: a paired bootstrap's whole premise is
    that position *j* of the pick vector is the same person in both arms, and each arm deriving its
    own ordering breaks that silently whenever the arms' respondent sets differ (which `_restrict`
    can cause, by dropping a column that was a respondent's only shared one).

    A respondent maps to ALL of their rows in a column, not one: repeat measurements (`--repeat-tag`)
    put several cells on the same (respid, qid), `build_columns` counts every one of them in the
    point estimate, and keeping only the last would make the interval describe a different statistic
    than the value it is printed beside. Stored CSR-style -- flat row indices ordered by respondent,
    plus per-respondent start and count -- so a resample is still one vectorised gather rather than a
    dict walk, which is what keeps 1,000 resamples affordable.
    """
    if respids is None:
        respids = sorted({respid for block in columns.values() for respid in block["respids"]})
    position = {respid: index for index, respid in enumerate(respids)}
    lookup = {}
    for qid, block in columns.items():
        buckets: list = [[] for _ in respids]
        for row, respid in enumerate(block["respids"]):
            index = position.get(respid)
            if index is not None:
                buckets[index].append(row)
        counts = np.array([len(rows) for rows in buckets], dtype=np.intp)
        flat = np.array([row for rows in buckets for row in rows], dtype=np.intp)
        starts = np.concatenate(([0], np.cumsum(counts)[:-1])).astype(np.intp)
        lookup[qid] = (flat, starts, counts)
    return respids, lookup


def _gather(entry, picks) -> np.ndarray:
    """Row indices for one column under one respondent resample, repeats included.

    Vectorised ragged gather: a picked respondent contributes all `counts[p]` of their rows, so a
    respondent drawn twice contributes their cells twice — the resampling unit is the person.
    """
    flat, starts, counts = entry
    taken = counts[picks]
    total = int(taken.sum())
    if total == 0:
        return np.empty(0, dtype=np.intp)
    out_starts = np.concatenate(([0], np.cumsum(taken)[:-1]))
    offsets = np.arange(total) - np.repeat(out_starts, taken)
    return flat[np.repeat(starts[picks], taken) + offsets]


def bootstrap(columns: dict, statistic, resamples: int, seed: int) -> dict:
    """Percentile interval for one scalar statistic, resampling RESPONDENTS with replacement.

    `statistic(resampled_columns) -> float`. Cells within a respondent are correlated (~84 of them
    walk one chained history), so resampling cells would report an interval several times too
    narrow. Seeded, so a reported interval is reproducible.
    """
    respids, lookup = _respondent_index(columns)
    rng = np.random.default_rng(seed)
    values = []
    for _ in range(resamples):
        picks = rng.integers(0, len(respids), len(respids))
        value = statistic(_resample(columns, lookup, picks))
        if value is not None and np.isfinite(value):
            values.append(value)
    if not values:
        return {"n": 0}
    array = np.array(values)
    return {"n": len(array), "mean": float(array.mean()),
            "ci_low": float(np.quantile(array, 0.025)),
            "ci_high": float(np.quantile(array, 0.975))}


def _soft_error_statistic(bucket: str):
    def statistic(columns: dict):
        subset = {qid: distance(block, marginals(block, "soft", qid), human_marginal(block))
                  for qid, block in columns.items()
                  if block["ordered"] is (bucket == "ordinal")}
        return equal_weight(by_task(subset, columns))
    return statistic


def _brier_statistic(columns: dict):
    return equal_weight(by_task(
        {qid: float(brier_cells(block).mean()) for qid, block in columns.items()}, columns
    ))


def paired_comparison(arms: dict, resamples: int, seed: int) -> dict:
    """The C3 read: JC vs BC, on the columns and respondents BOTH arms actually cover.

    Restricting to shared cells is what makes the comparison paired at all. A column one arm aborted
    out of is not evidence about the other arm, and Wilcoxon over columns needs the same columns.
    """
    if len(arms) < 2:
        return {}
    names = list(arms)
    out = {}
    for i, left in enumerate(names):
        for right in names[i + 1:]:
            out[f"{left}_vs_{right}"] = _compare(left, arms[left], right, arms[right],
                                                 resamples, seed)
    return out


def _compare(left, left_columns, right, right_columns, resamples, seed) -> dict:
    shared_qids = sorted(set(left_columns) & set(right_columns))
    shared_respids = (
        {r for q in shared_qids for r in left_columns[q]["respids"]}
        & {r for q in shared_qids for r in right_columns[q]["respids"]}
    )
    a = _restrict(left_columns, shared_qids, shared_respids)
    b = _restrict(right_columns, shared_qids, shared_respids)

    result = {"shared_columns": len(a), "shared_respondents": len(shared_respids),
              "lower_is_better": True}
    for bucket in ("nominal", "ordinal"):
        statistic = _soft_error_statistic(bucket)
        left_per = {qid: distance(block, marginals(block, "soft", qid), human_marginal(block))
                    for qid, block in a.items() if block["ordered"] is (bucket == "ordinal")}
        right_per = {qid: distance(block, marginals(block, "soft", qid), human_marginal(block))
                     for qid, block in b.items() if block["ordered"] is (bucket == "ordinal")}
        result[f"soft_{bucket}"] = _paired_bucket(
            left, right, a, b, statistic, left_per, right_per, resamples, seed
        )
    left_brier = {qid: float(brier_cells(block).mean()) for qid, block in a.items()}
    right_brier = {qid: float(brier_cells(block).mean()) for qid, block in b.items()}
    result["brier"] = _paired_bucket(
        left, right, a, b, _brier_statistic, left_brier, right_brier, resamples, seed
    )
    # C3 passes only if BOTH halves favour the left arm, per the pre-registered criterion.
    result["c3_left_wins"] = bool(
        all(result[key]["delta"] is not None and result[key]["delta"] <= 0
            for key in ("soft_nominal", "soft_ordinal", "brier"))
    )
    return result


def _restrict(columns: dict, qids, respids) -> dict:
    out = {}
    for qid in qids:
        block = columns[qid]
        rows = [i for i, r in enumerate(block["respids"]) if r in respids]
        if len(rows) < 2:
            continue
        out[qid] = {**block, "P": block["P"][rows], "y": block["y"][rows],
                    "respids": [block["respids"][i] for i in rows],
                    "raw_sums": [block["raw_sums"][i] for i in rows],
                    "choices": [block["choices"][i] for i in rows]}
    return out


def _paired_bucket(left, right, a, b, statistic, left_per, right_per, resamples, seed) -> dict:
    """One metric's paired margin: bootstrap on the difference, Wilcoxon over the shared columns."""
    from scipy.stats import wilcoxon

    left_value, right_value = statistic(a), statistic(b)
    # ONE ordering over the union of both arms, so pick position j is the same person on both sides.
    # Letting each arm sort its own respondents looks equivalent and is not: `_restrict` drops a
    # column with < 2 shared rows, which can remove a respondent from one arm only, after which the
    # two orderings are different permutations of different-length lists -- an IndexError if the
    # right arm is shorter, and a silently unpaired bootstrap if it merely differs. Union rather than
    # intersection because a respondent missing from one arm has no rows there and contributes
    # nothing, which `_gather` already handles.
    respids = sorted(
        {r for block in a.values() for r in block["respids"]}
        | {r for block in b.values() for r in block["respids"]}
    )
    _, left_lookup = _respondent_index(a, respids)
    _, right_lookup = _respondent_index(b, respids)
    rng = np.random.default_rng(seed)
    deltas = []
    for _ in range(resamples):
        # The SAME respondent picks feed both arms -- that is the pairing.
        picks = rng.integers(0, len(respids), len(respids))
        one = statistic(_resample(a, left_lookup, picks))
        two = statistic(_resample(b, right_lookup, picks))
        if one is not None and two is not None:
            deltas.append(one - two)
    delta_array = np.array(deltas) if deltas else np.array([])

    shared = sorted(set(left_per) & set(right_per))
    wilcoxon_p = None
    if len(shared) >= 6:
        differences = [left_per[q] - right_per[q] for q in shared]
        if any(abs(d) > 1e-12 for d in differences):
            wilcoxon_p = float(wilcoxon(differences, alternative="less").pvalue)
    return {
        f"{left}": left_value,
        f"{right}": right_value,
        "delta": None if left_value is None or right_value is None else left_value - right_value,
        "delta_ci_low": float(np.quantile(delta_array, 0.025)) if len(delta_array) else None,
        "delta_ci_high": float(np.quantile(delta_array, 0.975)) if len(delta_array) else None,
        # One-sided: the pre-registered direction is "the left arm is no worse", so a two-sided p
        # would answer a question nobody asked.
        "wilcoxon_p_left_lower": wilcoxon_p,
        "n_columns": len(shared),
    }


def _resample(columns: dict, lookup: dict, picks) -> dict:
    """One resampled copy of every column. A column left with < 2 rows is dropped, as upstream."""
    out = {}
    for qid, block in columns.items():
        rows = _gather(lookup[qid], picks)
        if len(rows) < 2:
            continue
        out[qid] = {**block, "P": block["P"][rows], "y": block["y"][rows],
                    "respids": [block["respids"][r] for r in rows],
                    "raw_sums": [block["raw_sums"][r] for r in rows],
                    "choices": [block["choices"][r] for r in rows]}
    return out


def repeat_agreement(rows: list, entries: dict) -> dict:
    """Mean TVD between two `repeat_tag`s or `order_salt`s of the same cells — the noise floor.

    Jev is NOT deterministic: the vendor's own consistency cookbook reports a flipped top label on
    2 of 8 questions over 15 repeats. So a JC-vs-BC margin smaller than this figure is not a result,
    and it has to be measured on the instrument rather than assumed.
    """
    by_key: dict = {}
    for row in rows:
        entry = entries.get(row["qid"])
        if entry is None or not isinstance(row.get("probs"), dict):
            continue
        options = list(entry["choices"].values())
        vector = vector_of(row, options)
        if vector is None:
            continue
        variant = (row.get("repeat_tag", "r1"), row.get("order_salt", ""))
        by_key.setdefault((str(row["respid"]), row["qid"]), {})[variant] = (vector, options)

    pairs: dict = {}
    for (_respid, _qid), variants in by_key.items():
        if len(variants) < 2:
            continue
        keys = sorted(variants)
        for i, left in enumerate(keys):
            for right in keys[i + 1:]:
                (u, options), (v, _) = variants[left], variants[right]
                tvd = total_variation_distance(
                    {o: float(u[i]) for i, o in enumerate(options)},
                    {o: float(v[i]) for i, o in enumerate(options)},
                    options,
                )
                pairs.setdefault(f"{left}|{right}", []).append(tvd)
    return {
        label: {"n_cells": len(values), "mean_tvd": float(np.mean(values)),
                "max_tvd": float(np.max(values)),
                "share_over_0.05": float(np.mean(np.array(values) > 0.05))}
        for label, values in pairs.items()
    }


def convert(details_path: Path, arm: str, out_path: Path, entries: dict,
            sample: int = None, respid_order: list = None) -> int:
    """A run's respondent details -> probs JSONL, one line per (respondent, question).

    `--sample` keeps the FIRST N respondents in the LOADER's order, not in xlsx row order, because
    that is the order `--sample` means everywhere else in this pipeline; pass `--respid-order` to
    supply it. Without it, xlsx order is used and said so in the output.
    """
    frame = pd.read_excel(details_path)
    id_column = next((c for c in ("respid", "respondent_id", "pid") if c in frame.columns), None)
    if id_column is None:
        raise SystemExit(f"{details_path}: no respid column (looked for respid/respondent_id/pid)")
    frame[id_column] = frame[id_column].map(lambda v: str(v).strip())

    if respid_order:
        rank = {str(r): i for i, r in enumerate(respid_order)}
        frame = frame[frame[id_column].isin(rank)].copy()
        frame["_rank"] = frame[id_column].map(rank)
        frame = frame.sort_values("_rank").drop(columns="_rank")
    elif sample:
        print(f"[warn] no --respid-order given; --sample {sample} takes the first {sample} XLSX "
              "rows. Pass --respid-order to match the loader's order exactly.")
    if sample:
        frame = frame.head(sample)

    written = 0
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as handle:
        for _, record in frame.iterrows():
            for qid, entry in entries.items():
                options = list(entry["choices"].values())
                choice = match_option(record.get(f"{qid}_synthetic"), options)
                if choice is None:
                    continue
                human = match_option(record.get(f"{qid}_ground_truth"), options)
                raw = record.get(f"{qid}_probs")
                probs = None
                if isinstance(raw, str) and raw.strip():
                    try:
                        parsed = json.loads(raw)
                        probs = parsed if isinstance(parsed, dict) else None
                    except ValueError:
                        probs = None
                order = record.get(f"{qid}_option_order")
                handle.write(json.dumps({
                    "arm": arm, "respid": str(record[id_column]), "qid": qid,
                    "options": options,
                    "probs": probs, "choice": choice, "human": human,
                    "presented_order": json.loads(order) if isinstance(order, str) and order.strip()
                                       else None,
                    # A converted run cannot report how long the history was at each cell; the
                    # runner does not export it. Null rather than a guess.
                    "history_len": None, "repeat_tag": "r1", "order_salt": "",
                    "model": None, "elicitation": "verbalized_probs" if probs else "hard_choice",
                    "latency_ms": None, "error": None,
                }, ensure_ascii=False) + "\n")
                written += 1
    print(f"{written} cells from {len(frame)} respondents -> {out_path}")
    return 0


def score_arms(arm_paths: dict, entries: dict, resamples: int, seed: int, bins: int) -> dict:
    report = {"arms": {}, "bins": bins, "bootstrap_resamples": resamples, "seed": seed}
    columns_by_arm = {}
    for arm, path in arm_paths.items():
        rows = read_jsonl(path)
        columns, dropped = build_columns(rows, entries)
        if not columns:
            raise SystemExit(f"{arm}: no scorable columns in {path}")
        columns_by_arm[arm] = columns
        respondents = {r for block in columns.values() for r in block["respids"]}
        report["arms"][arm] = {
            "path": str(path),
            "coverage": {
                "columns": len(columns),
                "respondents": len(respondents),
                "cells": sum(len(block["y"]) for block in columns.values()),
                "cells_dropped": dropped,
                "tasks": len({block["task"] for block in columns.values()}),
                "models_seen": sorted({str(r.get("model")) for r in rows if r.get("model")}),
            },
            "accuracy_anchor": accuracy_anchor(columns, entries, arm),
            "fidelity": fidelity(columns),
            **brier_report(columns),
            "calibration": calibration(columns, bins),
            "raw_sums": raw_sum_report(columns),
            "framing_contrast": framing_contrast(columns, entries),
            "repeat_agreement": repeat_agreement(rows, entries),
            "bootstrap": {
                "soft_nominal": bootstrap(columns, _soft_error_statistic("nominal"),
                                          resamples, seed),
                "soft_ordinal": bootstrap(columns, _soft_error_statistic("ordinal"),
                                          resamples, seed),
                "brier": bootstrap(columns, _brier_statistic, resamples, seed),
            },
        }
    report["paired"] = paired_comparison(columns_by_arm, resamples, seed)
    return report


def print_report(report: dict) -> None:
    for arm, result in report["arms"].items():
        coverage = result["coverage"]
        print(f"\n=== {arm} ===")
        print(f"{coverage['respondents']} respondents, {coverage['columns']} columns, "
              f"{coverage['cells']} cells, {coverage['tasks']}/{EXPECTED_TASKS} tasks")
        if coverage["tasks"] != EXPECTED_TASKS:
            print(f"  [warn] {coverage['tasks']} tasks, not {EXPECTED_TASKS} — the equal weighting "
                  "is over a different denominator than the paper's")
        anchor = result["accuracy_anchor"]
        if anchor.get("accuracy_pct") is not None:
            print(f"paper accuracy {anchor['accuracy_pct']:.2f}%  "
                  f"LOO majority {anchor['loo_majority_pct']:.2f}%  "
                  f"edge {anchor['accuracy_pct'] - anchor['loo_majority_pct']:+.2f}")
        print(f"{'metric':<28} {'all tasks':>10} {'excl pricing':>13}")
        for label, block in (
            ("soft TVD (nominal)", result["fidelity"]["soft_nominal"]),
            ("soft W1 (ordinal)", result["fidelity"]["soft_ordinal"]),
            ("argmax TVD (nominal)", result["fidelity"]["argmax_nominal"]),
            ("draw TVD (nominal)", result["fidelity"]["draw_nominal"]),
            ("entropy ratio", result["fidelity"]["entropy_ratio"]),
            ("Brier (multiclass)", result["brier"]),
            ("log loss", result["log_loss"]),
        ):
            print(f"{label:<28} {_fmt(block['all_tasks']):>10} {_fmt(block['excl_pricing']):>13}")
        skill = result["bss_vs_loo_marginal"]
        print(f"{'BSS vs LOO marginal':<28} {_fmt(skill['all_tasks']):>10} "
              f"{_fmt(skill['excl_pricing']):>13}   (context, not a criterion)")
        murphy_block = result["murphy"]
        if murphy_block.get("n_cells"):
            print(f"Murphy on {murphy_block['n_cells']} binary cells: "
                  f"reliability {murphy_block['reliability']:.4f} (lower better)  "
                  f"resolution {murphy_block['resolution']:.4f} (higher better)  "
                  f"uncertainty {murphy_block['uncertainty']:.4f}")
        binary = result["calibration"]["binary"]
        if binary.get("n_columns"):
            print(f"ECE binary: equal-task {_fmt(binary['ece_equal_task_weight'])}  "
                  f"pooled {_fmt(binary['ece_pooled'])}  "
                  f"adaptive {_fmt(binary['ece_pooled_adaptive_bins'])}  "
                  f"({binary['n_columns']} cols, {binary['bins']} bins)")
            print(f"  C1: {_c1_verdict(binary['ece_equal_task_weight'])}")
        sums = result["raw_sums"]
        if sums.get("n_cells_with_vectors"):
            print(f"raw vector sums: mean {sums['mean']:.4f}  "
                  f"median {sums['median']:.4f}  "
                  f"{100 * sums['share_within_1pct_of_1']:.1f}% within 1% of 1")
        print(f"zero probability on the human's answer: "
              f"{result['cells_with_zero_probability_on_truth']} cells")
        print(f"collapsed columns (one answer for everyone): "
              f"{len(result['fidelity']['collapsed_columns'])}")
        framing = result["framing_contrast"]["_summary"]
        print(f"framing contrast: {framing['signs_agreeing']}/{framing['groups_compared']} "
              "groups move the human direction  (diagnostic)")
        for label, block in result["repeat_agreement"].items():
            print(f"repeat {label}: mean TVD {block['mean_tvd']:.4f} over "
                  f"{block['n_cells']} cells (noise floor)")
        for label, block in result["bootstrap"].items():
            if block.get("n"):
                print(f"bootstrap {label}: {block['mean']:.4f} "
                      f"[{block['ci_low']:.4f}, {block['ci_high']:.4f}]")

    for pair, block in report.get("paired", {}).items():
        print(f"\n=== paired: {pair} ===")
        print(f"{block['shared_columns']} shared columns, "
              f"{block['shared_respondents']} shared respondents  (lower is better)")
        for key in ("soft_nominal", "soft_ordinal", "brier"):
            metric = block[key]
            delta = metric["delta"]
            interval = ("" if metric["delta_ci_low"] is None
                        else f" [{metric['delta_ci_low']:+.4f}, {metric['delta_ci_high']:+.4f}]")
            p = ("" if metric["wilcoxon_p_left_lower"] is None
                 else f"  wilcoxon p={metric['wilcoxon_p_left_lower']:.4f}")
            print(f"  {key:<14} delta {_fmt(delta, '+.4f')}{interval}{p}")
        # Sign check only, NOT the registered distribution test. The registered rule is the
        # per-column Wilcoxon within each bucket, printed above; this line reads the deltas.
        # The two disagree whenever an arm wins the task-weighted mean and loses per column,
        # which is exactly what the Noul follow-up did, so do not read this as the verdict.
        print(f"  deltas all favour the left arm: {'yes' if block['c3_left_wins'] else 'no'}"
              "   (sign check, not the registered test: read the wilcoxon p per bucket)")
        print("  Read every delta against the measured repeat-agreement floor above; a margin "
              "smaller than the floor is not a result.")


def _fmt(value, spec=".4f") -> str:
    return "n/a" if value is None or not np.isfinite(value) else format(value, spec)


def _c1_verdict(ece) -> str:
    """The plan's pre-registered bands, fixed before any data was seen."""
    if ece is None or not np.isfinite(ece):
        return "not computed"
    if ece <= 0.05:
        return f"PASS (ECE {ece:.4f} <= 0.05)"
    if ece <= 0.10:
        return f"MARGINAL (ECE {ece:.4f} in 0.05-0.10) — no individual-level claim"
    return f"FAIL (ECE {ece:.4f} > 0.10)"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    subparsers = parser.add_subparsers(dest="command", required=True)

    converter = subparsers.add_parser("convert", help="respondent details xlsx -> probs JSONL")
    converter.add_argument("--details", required=True)
    converter.add_argument("--arm", required=True)
    converter.add_argument("--out", required=True)
    converter.add_argument("--sample", type=int, default=None)
    converter.add_argument("--respid-order", default=None,
                          help="Text file of respids, one per line, in the loader's order. "
                               "Without it --sample falls back to xlsx row order.")
    converter.add_argument("--mapping", default=None)

    scorer = subparsers.add_parser("score", help="probs JSONL -> one report")
    scorer.add_argument("--arm", action="append", required=True, metavar="NAME=PATH",
                       help="Repeatable. The FIRST arm is the left side of every paired "
                            "comparison, so pass the arm under test first.")
    scorer.add_argument("--out", default=None, help="Write the full report as JSON.")
    scorer.add_argument("--bootstrap", type=int, default=BOOTSTRAP_RESAMPLES)
    scorer.add_argument("--seed", type=int, default=BOOTSTRAP_SEED)
    scorer.add_argument("--ece-bins", type=int, default=ECE_BINS)
    scorer.add_argument("--mapping", default=None)

    args = parser.parse_args()
    entries = load_entries(Path(args.mapping)) if args.mapping else load_entries()

    if args.command == "convert":
        order = None
        if args.respid_order:
            order = [line.strip() for line in Path(args.respid_order).read_text(
                encoding="utf-8").splitlines() if line.strip()]
        return convert(Path(args.details), args.arm, Path(args.out), entries,
                       sample=args.sample, respid_order=order)

    arm_paths = {}
    for item in args.arm:
        if "=" not in item:
            raise SystemExit(f"--arm expects NAME=PATH, got {item!r}")
        name, path = item.split("=", 1)
        arm_paths[name] = Path(path)
    report = score_arms(arm_paths, entries, args.bootstrap, args.seed, args.ece_bins)
    print_report(report)
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, indent=2, default=float), encoding="utf-8")
        print(f"\nreport -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
