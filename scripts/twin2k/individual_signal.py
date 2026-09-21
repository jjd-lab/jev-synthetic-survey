"""Per-task individual-level correlation and distributional metrics for a Twin arm.

`paper_accuracy.py` answers "how often is the twin's answer right", which a persona-blind majority
predictor can win on any skewed column. This script answers the question that metric cannot:
**does the twin rank the RIGHT PEOPLE high?** Within one column, correlate the twin's answer position
against the human's across respondents. A twin reproducing the marginal distribution but assigning it
randomly across people scores ~0 here while still scoring well on accuracy — which is precisely the
failure the playbook warns demographics-only grounding falls into.

Spearman, not Pearson: the ordinal columns are 4-7 point scales where only order is meaningful. On a
binary column Spearman equals the phi coefficient, so one statistic covers both buckets. A column
where the twin gave every respondent the same answer has zero variance and NO defined correlation —
those are counted, not scored as 0, because "no signal measurable" and "signal measured as none" are
different claims and the collapsed columns are the majority here.

THE 40 PRICING COLUMNS NEED A CONTROL, and without it they dominate the headline. Twin randomizes
each product's price per respondent (see `src/data/preprocessors/twin2k.py`), and the twin is shown
the same price its human saw — so twin and human agree partly because both react to the price, with
no knowledge of the person involved. Pass `--stem-values-dir` and those columns are reported as a
partial Spearman holding price rank fixed. Measured on the full demographics-only panel the raw
correlation is +0.301 and the partial is +0.048: six sevenths of it was the price. The twin also
tracks price HARDER than its human does (rho +0.61 vs +0.44), which is a finding about the twin's
price sensitivity, not about individual grounding.

The partial is a SHORTCUT for stratifying, and it earns that shortcut: it assumes price acts
monotonically, so it was checked against two estimators that assume less. Stratifying by exact price
is impossible directly — 13,851 groups with a median of 5 respondents, only 4.6% of them carrying
variance on both sides — so the checks were within-price-decile rho pooled by size (+0.058 over 267
bins) and a Mantel-Haenszel odds ratio over all 13,851 exact-price groups (1.398, p<0.0001, n=82,320
cells). All three agree that the price-controlled signal is real, small, and near +0.05. If a future
arm's partial diverges from a decile-pooled rho, distrust the partial: it means the twin's price
response stopped being monotone.

Aggregation matches `paper_accuracy.py` (column -> task -> equal weight across 16 tasks), because 40
of the 108 columns are the pricing study and a pooled mean is 37% one experiment. The distributional
half is read from the run's `validation_summary_*.xlsx` and aggregated the same way, so the two live
on one sheet: TVD for the 65 nominal columns, Wasserstein-1 for the 43 ordinal ones. Both are
DISTANCES (0 = perfect); `individual_baseline` flips meaning by bucket, so it is reported as its two
separate metrics rather than averaged into one column.

Usage:
    python scripts/twin2k/individual_signal.py \\
        --details runs/gpt41_panel_n2058/demographics_stateless/respondent_details_20260904_091556.xlsx \\
        --summary runs/gpt41_panel_n2058/demographics_stateless/validation_summary_20260904_091556.xlsx
"""

import argparse
import gzip
import importlib
import json
import math
import sys
from pathlib import Path
from typing import Dict, Optional

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))  # `scripts/` is not a package
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # for `src.data.preprocessors`
paper_accuracy = importlib.import_module("paper_accuracy")
prob_scoring = importlib.import_module("prob_scoring")

MIN_N_FOR_CORRELATION = 30
STEM_PREFIX = "__stem__"


def column_correlation(
    frame: pd.DataFrame, question_id: str, entry: dict, control: Optional[pd.Series] = None
) -> dict:
    """Spearman correlation between twin and human answer POSITIONS for one column.

    `rho` is None when the column cannot carry a correlation: too few scorable respondents, or no
    variance on either side. Off-list labels and `Error` cells drop out with the position lookup.

    With `control`, also returns `partial` — Spearman between twin and human holding the control's
    rank fixed, via the standard first-order partial formula on the three rank correlations. That is
    the number to read for pricing, where twin and human share a randomized price.
    """
    options = list(entry["choices"].values())
    positions = {option: index for index, option in enumerate(options)}

    def to_position(column: pd.Series) -> pd.Series:
        """Map cells onto option positions, via the same coercion the scorer uses.

        `pd.read_excel` types a numeric-coded column as float64, so the 10 `QID198_*` columns
        arrive as `1.0` against a mapping that calls the scale `"1"`. A bare `.map()` returns
        NaN for every one of them, the column is then dropped as `thin`, and a whole task
        leaves the mean without saying so. `match_option` is what `prob_scoring` already uses
        for this; going through it keeps the two scorers reading the same cells.
        """
        return column.map(lambda raw: positions.get(prob_scoring.match_option(raw, options)))

    columns = {
        "twin": to_position(frame[f"{question_id}_synthetic"]),
        "human": to_position(frame[f"{question_id}_ground_truth"]),
    }
    if control is not None:
        columns["control"] = pd.to_numeric(control.reindex(frame.index), errors="coerce")
    paired = pd.DataFrame(columns).dropna()

    result = {"n": int(len(paired)), "rho": None, "partial": None, "reason": None}
    if len(paired) < MIN_N_FOR_CORRELATION:
        result["reason"] = "thin"
        return result
    if paired["twin"].nunique() < 2:
        result["reason"] = "twin collapsed"
        return result
    if paired["human"].nunique() < 2:
        result["reason"] = "humans unanimous"
        return result

    result["rho"] = float(paired["twin"].corr(paired["human"], method="spearman"))
    if control is not None and paired["control"].nunique() >= 2:
        twin_control = paired["twin"].corr(paired["control"], method="spearman")
        human_control = paired["human"].corr(paired["control"], method="spearman")
        spread = math.sqrt((1 - twin_control**2) * (1 - human_control**2))
        if spread:
            result["partial"] = (result["rho"] - twin_control * human_control) / spread
            result["rho_twin_control"] = float(twin_control)
            result["rho_human_control"] = float(human_control)
    return result


def load_stem_prices(stem_values_dir: str, source_csv: str) -> pd.DataFrame:
    """Per-respondent randomized prices, indexed by respid, via the run's own preprocessor.

    Reusing `preprocess` rather than re-parsing the parquet keeps one implementation of "which price
    did this respondent see": a second one could drift from the prices the run actually asked, and
    then the control would remove the wrong variance.
    """
    from src.data.preprocessors.twin2k import preprocess

    frame = preprocess(pd.read_csv(source_csv, low_memory=False), stem_values_dir=stem_values_dir)
    price_columns = [column for column in frame.columns if column.startswith(STEM_PREFIX)]
    return frame.set_index(frame["respid"].astype(str))[price_columns]


def frame_from_jsonl(details_path: Path) -> pd.DataFrame:
    """Build the wide frame this module expects from a per-cell JSONL arm.

    `main.py` writes one row per respondent and two columns per question; `probe_jev.py`
    writes one record per cell. Same content, transposed, so the correlation code below
    does not need to know which runner produced the arm.

    Records without a `qid` are skipped: the walk writes `done` markers per respondent and
    an `aborted` marker carrying the failure reason, and neither is a scorable cell. A cell
    that carries `error` is skipped for the same reason a blank Excel cell is.
    """
    opener = gzip.open if details_path.suffix == ".gz" else open
    rows: Dict[str, Dict[str, object]] = {}
    with opener(details_path, "rt", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            record = json.loads(line)
            question_id = record.get("qid")
            if question_id is None or record.get("error"):
                continue
            respid = str(record["respid"])
            row = rows.setdefault(respid, {"respid": respid})
            row[f"{question_id}_synthetic"] = record.get("choice")
            row[f"{question_id}_ground_truth"] = record.get("human")
    if not rows:
        raise SystemExit(f"no scorable cells in {details_path}")
    return pd.DataFrame.from_records(list(rows.values()))


def load_details(details_path: Path) -> pd.DataFrame:
    """Read an arm as a wide frame, from either runner's output format."""
    if details_path.suffix == ".gz" or details_path.suffix == ".jsonl":
        return frame_from_jsonl(details_path)
    return pd.read_excel(details_path)


def correlations_per_task(
    details_path: Path, entries: Dict[str, dict], prices: Optional[pd.DataFrame] = None
) -> Dict[str, dict]:
    """Aggregate per-column Spearman into per-task means, carrying the unmeasurable count."""
    frame = load_details(details_path)
    frame.index = frame["respid"].astype(str)
    per_task: Dict[str, dict] = {}
    for question_id, entry in entries.items():
        if f"{question_id}_synthetic" not in frame.columns:
            continue
        task = paper_accuracy.task_of(question_id, entry)
        bucket = per_task.setdefault(
            task, {"rhos": [], "partials": [], "unmeasurable": {}, "columns": 0}
        )
        bucket["columns"] += 1
        control = None
        if prices is not None and f"{STEM_PREFIX}{question_id}" in prices.columns:
            control = prices[f"{STEM_PREFIX}{question_id}"]
        column = column_correlation(frame, question_id, entry, control)
        if column["rho"] is None:
            reasons = bucket["unmeasurable"]
            reasons[column["reason"]] = reasons.get(column["reason"], 0) + 1
            continue
        bucket["rhos"].append(column["rho"])
        # Fall back to the raw rho where no control applies, so the two lists stay the same length
        # and the price-controlled headline is not silently averaged over pricing columns alone.
        bucket["partials"].append(column["partial"] if column["partial"] is not None else column["rho"])
    return per_task


def _mean_or_none(column: pd.Series) -> Optional[float]:
    """Mean skipping blanks, or None when the whole group is blank.

    `kl` is blank for every ordinal column by design, and both entropy columns go blank below the
    validator's `min_n_for_gating`, so an all-blank group is expected rather than a data error.
    Returning None keeps `--json` valid JSON, which `float('nan')` would not be.
    """
    mean = column.mean()
    return None if pd.isna(mean) else float(mean)


def _fmt(value: Optional[float], width: int) -> str:
    """Right-aligned 3dp, or a dash — so a not-applicable cell never reads as a measured 0.000."""
    return f"{'-':>{width}}" if value is None else f"{value:>{width}.3f}"


def distributional_per_task(summary_path: Path, entries: Dict[str, dict]) -> Dict[str, dict]:
    """Mean distance, individual baseline, entropy and blind spot per task, kept SPLIT by bucket.

    TVD and Wasserstein-1 are on different units (probability mass vs scale steps) and
    `individual_baseline` inverts direction between buckets, so a task mixing buckets gets two
    entries rather than one meaningless average. No Twin task mixes buckets today; the split is what
    guarantees a future one cannot be silently pooled. The split also keeps `kl` honest: it is
    defined on nominal columns only, so a mixed average would be over an unstated subset.

    The three diversity columns answer what a distance cannot. `entropy_ratio` (h_syn / h_hum, so
    1.0 = the twins are as varied as the humans and it is None where the humans were unanimous)
    separates a twin that reproduces the panel's spread from one that answers identically for
    everyone; `collapse` is its flagged extreme. `blind_spot`
    counts columns where an option real respondents chose gets essentially no synthetic mass — a
    failure that barely moves TVD when the option is small, but is the one that matters for reading
    a distribution as coverage of the population.
    """
    summary = pd.read_excel(summary_path)
    summary["task"] = [
        paper_accuracy.task_of(qid, entries[qid]) if qid in entries else None
        for qid in summary["question_id"]
    ]
    grouped = summary.dropna(subset=["task"]).groupby(["task", "metric_bucket"])
    return {
        (task, bucket): {
            "columns": int(len(group)),
            "distance": float(group["distributional_metric"].mean()),
            "individual": float(group["individual_baseline"].mean()),
            "collapsed": int(group["collapse"].sum()),
            "entropy_ratio": _mean_or_none(group["entropy_ratio"]),
            "kl": _mean_or_none(group["kl"]),
            "blind_spots": int(group["blind_spot"].sum()),
            "blind_spot_worst": _mean_or_none(group["blind_spot_worst"]),
        }
        for (task, bucket), group in grouped
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--details",
        required=True,
        help="respondent_details_*.xlsx of a run, or a per-cell .jsonl/.jsonl.gz arm",
    )
    parser.add_argument("--summary", help="validation_summary_*.xlsx of the same run")
    parser.add_argument(
        "--stem-values-dir", default=None,
        help="Parquet dir of per-respondent pricing prices (as in the config's `stem_values_dir`). "
             "Without it, the 40 pricing columns report a price-confounded correlation.",
    )
    parser.add_argument(
        "--source-csv", default=str(paper_accuracy.WAVE_1_3),
        help="Wave 1-3 label CSV the prices are recovered from (default: the scored wave)",
    )
    parser.add_argument("--json", help="write the aggregated numbers here")
    args = parser.parse_args()

    entries = paper_accuracy.load_entries()
    prices = (
        load_stem_prices(args.stem_values_dir, args.source_csv) if args.stem_values_dir else None
    )
    if prices is None:
        print("[WARN] no --stem-values-dir: the 40 pricing columns report a PRICE-CONFOUNDED "
              "correlation. On the demographics-only panel that reads +0.301 where the "
              "persona-attributable part is +0.048, so the headline is ~6x too high.")
    per_task = correlations_per_task(Path(args.details), entries, prices)

    controlled = "  (pricing: price held fixed)" if prices is not None else ""
    print(f"\n=== individual-level correlation (Spearman, twin vs human, across respondents) ==={controlled}")
    print(f"{'task':<30} {'cols':>5} {'scored':>7} {'raw rho':>9} {'controlled':>11}   unmeasurable")
    # Task means, then the equal-weight mean across tasks — the same order as `paper_accuracy.py`.
    # A column-weighted headline would be 45% pricing, the one task whose raw correlation is almost
    # entirely the shared price, so it would report the confound as the result.
    task_means, columns_measured = {}, 0
    for task, bucket in sorted(per_task.items(), key=lambda item: -len(item[1]["rhos"])):
        rhos, partials = bucket["rhos"], bucket["partials"]
        columns_measured += len(rhos)
        reasons = ", ".join(f"{count} {reason}" for reason, count in bucket["unmeasurable"].items())
        raw = f"{sum(rhos) / len(rhos):>+9.3f}" if rhos else f"{'-':>9}"
        control = f"{sum(partials) / len(partials):>+11.3f}" if partials else f"{'-':>11}"
        if rhos:
            task_means[task] = (sum(rhos) / len(rhos), sum(partials) / len(partials))
        print(f"{task:<30} {bucket['columns']:>5} {len(rhos):>7} {raw} {control}   {reasons}")
    if task_means:
        raw_mean = sum(raw for raw, _ in task_means.values()) / len(task_means)
        control_mean = sum(control for _, control in task_means.values()) / len(task_means)
        print(f"\n{f'EQUAL WEIGHT OVER {len(task_means)} TASKS':<30} {'':>5} {columns_measured:>7} "
              f"{raw_mean:>+9.3f} {control_mean:>+11.3f}")
        positive = sum(1 for _, control in task_means.values() if control > 0)
        print(f"  {positive}/{len(task_means)} tasks positive after control; "
              f"{paper_accuracy.EXPECTED_TASKS - len(task_means)} of "
              f"{paper_accuracy.EXPECTED_TASKS} tasks and "
              f"{len(entries) - columns_measured} of {len(entries)} columns carry no measurable "
              f"correlation (collapsed twin, unanimous humans, or n < {MIN_N_FOR_CORRELATION})")

    distributional = None
    if args.summary:
        distributional = distributional_per_task(Path(args.summary), entries)
        print("\n=== distributional fit (ours; distance 0 = identical panels) ===")
        print("  h_ratio = h_syn / h_hum (1.0 = twins as varied as humans); blind = columns where "
              "a real option got ~no synthetic mass; kl is nominal-only by construction")
        print(f"\n{'task':<30} {'bucket':<8} {'cols':>5} {'distance':>9} {'individual':>11} "
              f"{'metric':<10} {'h_ratio':>8} {'kl':>7} {'blind':>6} {'collapsed':>10}")
        for (task, bucket), row in sorted(distributional.items()):
            name = "exact" if bucket == "nominal" else "MAE steps"
            print(f"{task:<30} {bucket:<8} {row['columns']:>5} {row['distance']:>9.3f} "
                  f"{row['individual']:>11.3f} {name:<10} {_fmt(row['entropy_ratio'], 8)} "
                  f"{_fmt(row['kl'], 7)} {row['blind_spots']:>6} {row['collapsed']:>10}")
        for bucket, metric in (("nominal", "TVD"), ("ordinal", "Wasserstein-1")):
            rows = [row for (_, key), row in distributional.items() if key == bucket]
            if rows:
                ratios = [r["entropy_ratio"] for r in rows if r["entropy_ratio"] is not None]
                print(f"  {bucket} ({metric}): equal-weight task mean "
                      f"{sum(r['distance'] for r in rows) / len(rows):.3f} over {len(rows)} tasks; "
                      f"h_ratio {(sum(ratios) / len(ratios)) if ratios else float('nan'):.3f}; "
                      f"{sum(r['blind_spots'] for r in rows)} blind spots and "
                      f"{sum(r['collapsed'] for r in rows)} collapses over "
                      f"{sum(r['columns'] for r in rows)} columns")

    if args.json:
        # `details` and `summary` are recorded because a repaired run leaves two timestamped files
        # per arm in the same directory, and a bare number cannot say which one it scored.
        payload = {
            "source": {"details": args.details, "summary": args.summary,
                       "price_controlled": prices is not None},
            "correlation": {
                task: {"columns": b["columns"], "scored": len(b["rhos"]),
                       "mean_rho": (sum(b["rhos"]) / len(b["rhos"])) if b["rhos"] else None,
                       "mean_rho_controlled":
                           (sum(b["partials"]) / len(b["partials"])) if b["partials"] else None,
                       "unmeasurable": b["unmeasurable"]}
                for task, b in per_task.items()
            },
            # Keyed "task | bucket": the dict is keyed by a tuple, which JSON has no notion of.
            "distributional": None if distributional is None else {
                f"{task} | {bucket}": row for (task, bucket), row in distributional.items()
            },
        }
        Path(args.json).write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"\nwrote {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
