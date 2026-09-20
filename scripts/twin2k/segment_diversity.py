"""Does a synthetic panel reproduce the differences BETWEEN demographic groups?

The distributional metrics elsewhere in this repo ask whether an arm matches the population
marginal. An arm can match that marginal while handing every respondent the same answer regardless
of who they are, and the marginal will not notice. That is the failure that matters when a survey
is going to be broken out by segment, which is most of what survey data is used for.

Three numbers per demographic variable, each aggregated equal-weight-per-task like every other
headline in this repo:

    separation, humans   mean pairwise distance between segments' answer distributions
    separation, model    the same, computed from the arm's own forecasts
    separation ratio     model / humans

The ratio is the diversity measure. 1.0 means the arm spreads its segments as far apart as the
humans are; 0.0 means every segment got the same distribution, so the persona did nothing. Above
1.0 means the arm exaggerates group differences, which is its own failure and is not better.

    segment fidelity     mean distance between the arm and the humans WITHIN a segment

Fidelity and separation answer different questions. An arm can sit close to the humans inside every
segment and still flatten the gaps between them, and an arm that collapses to the overall marginal
scores well on a pooled metric precisely because it has stopped distinguishing anyone.

Distance is total variation, the same soft measure `prob_scoring.py` uses, taken over each
segment's mean forecast. A hard-choice arm carries no probability vector, so its cells are one-hot
and the segment mean is simply the share of that segment choosing each option, which is exactly
what a survey would tabulate. That makes every arm comparable here, including the hard-answer ones.

Usage, from the repo root:

    python scripts/twin2k/segment_diversity.py \\
        --arm jev_noul=runs/jev_vs_gpt41_n2058/jev_noul.jsonl.gz \\
        --arm gpt41_hard=runs/jev_vs_gpt41_n2058/gpt41_hard.jsonl

Demographics come from a shipped persona cache, so nothing needs downloading.
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.twin2k.prob_scoring import (  # noqa: E402
    build_columns,
    headline,
    load_entries,
    read_jsonl,
)

DEFAULT_PERSONA_CACHE = (
    REPO_ROOT / "runs" / "gpt41_panel_n2058" / "demographics_stateful" / "persona_cache.xlsx"
)
DEMO_PREFIX = "demo_"

# A segment smaller than this is mostly sampling noise: its marginal moves by 1/n per person, which
# at n=10 is 10 points of "separation" that no model could or should reproduce.
MIN_SEGMENT = 25
MIN_SEGMENTS_PER_COLUMN = 2


def load_demographics(path: Path) -> pd.DataFrame:
    """respid -> the 14 demographic items, as strings, indexed by respid."""
    frame = pd.read_excel(path)
    columns = [c for c in frame.columns if c.startswith(DEMO_PREFIX)]
    if not columns:
        raise SystemExit(f"{path} carries no {DEMO_PREFIX}* columns")
    out = frame[["respid"] + columns].copy()
    out["respid"] = out["respid"].astype(str)
    for column in columns:
        out[column] = out[column].astype(str).str.strip()
    return out.set_index("respid")


def _tvd(left: np.ndarray, right: np.ndarray) -> float:
    return float(0.5 * np.abs(left - right).sum())


def _segment_rows(block: dict, labels: pd.Series, min_segment: int) -> dict:
    """segment label -> row indices into this column's block, segments below the floor dropped."""
    groups: dict = {}
    for index, respid in enumerate(block["respids"]):
        value = labels.get(respid)
        if value is None or value in ("", "nan", "None"):
            continue
        groups.setdefault(value, []).append(index)
    return {k: np.array(v) for k, v in groups.items() if len(v) >= min_segment}


def _separation(distributions: dict, names: list) -> float:
    pairs = [(a, b) for i, a in enumerate(names) for b in names[i + 1:]]
    return float(np.mean([_tvd(distributions[a], distributions[b]) for a, b in pairs]))


def _null_separation(block: dict, sizes: list, rng, permutations: int) -> float:
    """Separation from sampling noise alone: the same segment sizes, assigned at random.

    Real segments differ partly because their members differ and partly because each segment's
    marginal is estimated from finitely many people. Only the first part is signal, and it is the
    only part a model could reproduce. Shuffling the labels destroys the first and keeps the
    second, so this is the floor the measured human separation has to clear.
    """
    k, n = len(block["options"]), len(block["y"])
    draws = []
    for _ in range(permutations):
        order = rng.permutation(n)
        start, distributions = 0, {}
        for index, size in enumerate(sizes):
            rows = order[start:start + size]
            distributions[index] = np.bincount(block["y"][rows], minlength=k) / size
            start += size
        draws.append(_separation(distributions, list(range(len(sizes)))))
    return float(np.mean(draws))


def score_variable(columns: dict, labels: pd.Series, min_segment: int = MIN_SEGMENT,
                   permutations: int = 0, seed: int = 20260919) -> dict:
    """Separation and fidelity for one demographic variable, per column then per task."""
    sep_human, sep_model, sep_null, fidelity, coverage = {}, {}, {}, {}, {}
    rng = np.random.default_rng(seed)

    for qid, block in columns.items():
        groups = _segment_rows(block, labels, min_segment)
        if len(groups) < MIN_SEGMENTS_PER_COLUMN:
            continue

        k = len(block["options"])
        human_by_segment, model_by_segment = {}, {}
        for name, rows in groups.items():
            human_by_segment[name] = np.bincount(block["y"][rows], minlength=k) / len(rows)
            model_by_segment[name] = block["P"][rows].mean(axis=0)

        names = sorted(groups)
        sep_human[qid] = _separation(human_by_segment, names)
        sep_model[qid] = _separation(model_by_segment, names)
        fidelity[qid] = float(np.mean([_tvd(model_by_segment[n], human_by_segment[n])
                                       for n in names]))
        coverage[qid] = len(names)
        if permutations:
            sep_null[qid] = _null_separation(
                block, [len(groups[n]) for n in names], rng, permutations
            )

    if not sep_human:
        return {"columns_scored": 0}

    human = headline(sep_human, columns)
    model = headline(sep_model, columns)
    out = {
        "columns_scored": len(sep_human),
        "segments_per_column_median": int(np.median(list(coverage.values()))),
        "separation_humans": human,
        "separation_model": model,
        "separation_ratio": model["all_tasks"] / human["all_tasks"] if human["all_tasks"] else None,
        "segment_fidelity": headline(fidelity, columns),
    }
    if sep_null:
        null = headline(sep_null, columns)
        out["separation_null"] = null
        # Both sides carry the same finite-sample floor, so subtracting it from each is what makes
        # the ratio comparable across sample sizes. Below the floor there is no signal to reproduce
        # and the ratio is not defined.
        excess_h = human["all_tasks"] - null["all_tasks"]
        out["separation_ratio_excess_null"] = (
            (model["all_tasks"] - null["all_tasks"]) / excess_h if excess_h > 1e-9 else None
        )
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--arm", action="append", required=True, metavar="NAME=PATH",
                        help="Repeatable. NAME is a label; PATH is that arm's per-cell JSONL.")
    parser.add_argument("--persona-cache", default=str(DEFAULT_PERSONA_CACHE),
                        help="Workbook carrying respid and the demo_* columns.")
    parser.add_argument("--variable", action="append", default=None,
                        help="Repeatable. Restrict to these demo_* columns. Default: all of them.")
    parser.add_argument("--min-segment", type=int, default=MIN_SEGMENT,
                        help=f"Drop segments smaller than this (default {MIN_SEGMENT}).")
    parser.add_argument("--permutations", type=int, default=20,
                        help="Label shuffles used to estimate the sampling-noise floor. 0 skips.")
    parser.add_argument("--out", default=None, help="Write the full result as JSON.")
    args = parser.parse_args()

    min_segment = args.min_segment
    demographics = load_demographics(Path(args.persona_cache))
    variables = args.variable or list(demographics.columns)
    missing = [v for v in variables if v not in demographics.columns]
    if missing:
        raise SystemExit(f"not in the persona cache: {missing}")

    entries = load_entries()
    report: dict = {"min_segment": min_segment, "arms": {}}

    for spec in args.arm:
        if "=" not in spec:
            raise SystemExit(f"--arm expects NAME=PATH, got {spec!r}")
        name, _, path = spec.partition("=")
        columns, _ = build_columns(read_jsonl(Path(path)), entries)
        if not columns:
            raise SystemExit(f"{name}: no scorable columns in {path}")
        report["arms"][name] = {
            "path": path,
            "respondents": len({r for b in columns.values() for r in b["respids"]}),
            "columns": len(columns),
            "by_variable": {v: score_variable(columns, demographics[v], min_segment,
                                              args.permutations)
                            for v in variables},
        }

    arms = list(report["arms"])
    print(f"\nsegment diversity, min segment {min_segment}, equal weight per task")
    for name in arms:
        meta = report["arms"][name]
        print(f"  {name}: {meta['respondents']} respondents, {meta['columns']} columns")

    print(f"\n{'variable':<26}" + "".join(f"{n:>30s}" for n in arms))
    print(f"{'':<26}" + "".join(f"{'humans   noise   model ratio':>30s}" for _ in arms))
    for variable in variables:
        cells = ""
        for name in arms:
            result = report["arms"][name]["by_variable"][variable]
            if not result.get("columns_scored"):
                cells += f"{'--':>22s}"
                continue
            null = result.get("separation_null")
            cells += (f"{result['separation_humans']['all_tasks']:>8.4f}"
                      + (f"{null['all_tasks']:>8.4f}" if null else f"{'--':>8s}")
                      + f"{result['separation_model']['all_tasks']:>8.4f}"
                      f"{result['separation_ratio']:>6.2f}")
        print(f"{variable:<26}{cells}")

    print(f"\n{'variable':<26}" + "".join(f"{n + ' fidelity':>22s}" for n in arms))
    for variable in variables:
        cells = ""
        for name in arms:
            result = report["arms"][name]["by_variable"][variable]
            cells += (f"{result['segment_fidelity']['all_tasks']:>22.4f}"
                      if result.get("columns_scored") else f"{'--':>22s}")
        print(f"{variable:<26}{cells}")

    print("\nseparation ratio 1.0 = the arm spreads its segments as far apart as the humans are."
          "\n0.0 = every segment got the same distribution, so the persona changed nothing."
          "\nAbove 1.0 = the arm exaggerates group differences, which is not better."
          "\nFidelity is the gap to the humans WITHIN a segment; separation is between segments."
          "\n"
          "\n`noise` is the separation that the same segment sizes produce with the labels shuffled."
          "\nHumans barely clear it on this instrument, whose holdout is built so that answers should"
          "\nnot track who you are, so read a variable whose humans column sits near its noise column"
          "\nas carrying little to reproduce. Both columns carry that floor, so the ratio understates"
          "\nan arm that is tracking real signal. `separation_ratio_excess_null` in the JSON nets it"
          "\nout and is unstable exactly where the excess is small.")

    if args.out:
        Path(args.out).write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"\nreport -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
