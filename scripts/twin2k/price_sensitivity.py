"""Measure whether an arm's purchase probability responds to the price it was shown.

Reports three numbers per arm over the 40 pricing columns (`QID9_*`), each of which pipes a
per-respondent randomized price into its stem:

    corr(price, P(yes))  -- whether the probability moves with the price, and which way
    signed bias          -- mean P(yes) minus the humans' actual yes-rate, per column
    threshold recovery   -- committed accuracy regained by shifting the commit threshold

The threshold is chosen on the same cells it is scored on, so `accuracy @best` is in-sample and
optimistic by construction. It bounds the failure rather than measuring it: a large recovery means
the ranking is sound and only the operating point is wrong.

Usage, from the repo root:

    python scripts/twin2k/price_sensitivity.py \\
        --arm jev_choice=runs/jev_vs_gpt41_n300/jev_choice.jsonl \\
        --arm jev_noul=runs/jev_vs_gpt41_n300/jev_noul.jsonl \\
        --arm gpt41_probs=runs/jev_vs_gpt41_n300/gpt41_probs.jsonl

Also needs the parquet chunks under `data/twin2k500/wave_split` for the per-respondent prices --
run `fetch_twin2k.py` first.
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.twin2k.prob_scoring import open_jsonl  # noqa: E402
from src.data.preprocessors.twin2k import _load_stem_prices  # noqa: E402

PRICING_PREFIX = "QID9_"
STEM_PREFIX = "__stem__"
DEFAULT_STEM_DIR = REPO_ROOT / "data" / "twin2k500" / "wave_split"


def load_arm(path: Path) -> dict:
    """(respid, qid) -> (P(yes), human answer) for the pricing columns of one arm.

    Reads P(yes) off the vector rather than any arm-specific field, so `Noul`'s derived
    two-entry vector and a native `Choice` vector are read by the identical path.
    """
    cells = {}
    with open_jsonl(path) as handle:
        for line in handle:
            record = json.loads(line)
            qid = record.get("qid")
            if not qid or not qid.startswith(PRICING_PREFIX) or record.get("error"):
                continue
            probs = record.get("probs") or {}
            yes = [key for key in probs if key.lower().startswith("yes")]
            if yes:
                cells[(str(record["respid"]), qid)] = (probs[yes[0]], record.get("human"))
    return cells


def _price(value) -> float:
    return float(str(value).replace("$", "").strip())


def summarize(name: str, cells: dict, prices) -> dict:
    qids = sorted({q for _, q in cells}, key=lambda s: int(s.split("_")[1]))
    corrs, biases, flat_p, flat_y = [], [], [], []

    for qid in qids:
        column = f"{STEM_PREFIX}{qid}"
        if column not in prices.columns:
            continue
        shown, predicted, human = [], [], []
        for (respid, cell_qid), (prob, truth) in cells.items():
            if cell_qid != qid or respid not in prices.index:
                continue
            raw = prices.at[respid, column]
            if raw is None or (isinstance(raw, float) and np.isnan(raw)):
                continue
            try:
                shown.append(_price(raw))
            except (TypeError, ValueError):
                continue
            predicted.append(prob)
            human.append(1.0 if str(truth).lower().startswith("yes") else 0.0)

        if len(predicted) > 3 and np.std(predicted) > 1e-9:
            corrs.append(np.corrcoef(shown, predicted)[0, 1])
        if human:
            biases.append(float(np.mean(predicted) - np.mean(human)))
        flat_p.extend(predicted)
        flat_y.extend(human)

    p, y = np.asarray(flat_p), np.asarray(flat_y)
    accuracy = lambda t: float(((p >= t).astype(int) == y).mean())  # noqa: E731
    grid = np.arange(0.05, 0.96, 0.01)
    best = max(grid, key=accuracy)
    return {
        "arm": name,
        "columns": len(biases),
        "cells": int(len(p)),
        "corr_price_mean": float(np.mean(corrs)),
        "corr_negative_in": f"{sum(c < 0 for c in corrs)}/{len(corrs)}",
        "mean_p_yes": float(p.mean()),
        "human_yes_rate": float(y.mean()),
        "signed_bias": float(np.mean(biases)),
        "columns_biased_high": sum(b > 0 for b in biases),
        "accuracy_at_half": accuracy(0.5),
        "accuracy_at_best": accuracy(best),
        "best_threshold": float(best),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--arm", action="append", required=True, metavar="NAME=PATH",
                        help="Repeatable. NAME is a label; PATH is that arm's probs JSONL.")
    parser.add_argument("--stem-values-dir", default=str(DEFAULT_STEM_DIR),
                        help="Parquet chunks carrying the per-respondent prices.")
    parser.add_argument("--out", default=None, help="Write the rows as JSON.")
    args = parser.parse_args()

    arms = {}
    for spec in args.arm:
        if "=" not in spec:
            raise SystemExit(f"--arm expects NAME=PATH, got {spec!r}")
        name, _, path = spec.partition("=")
        arms[name] = load_arm(Path(path))
        if not arms[name]:
            raise SystemExit(f"{name}: no pricing cells with a probability vector in {path}")

    respids = {respid for cells in arms.values() for respid, _ in cells}
    prices = _load_stem_prices(Path(args.stem_values_dir),
                               {int(r) for r in respids if r.isdigit()} | respids)
    prices = prices.set_index("pid")
    prices.index = prices.index.astype(str)

    rows = [summarize(name, cells, prices) for name, cells in arms.items()]

    print(f"\n{len(rows[0]['columns'] * [0])} pricing columns, "
          f"human yes-rate {rows[0]['human_yes_rate']:.3f}\n")
    print(f"{'':22s}" + "".join(f"{r['arm']:>13s}" for r in rows))
    for label, key, fmt in [
        ("corr(price, P(yes))", "corr_price_mean", "{:13.3f}"),
        ("negative in", "corr_negative_in", "{:>13s}"),
        ("mean P(yes)", "mean_p_yes", "{:13.3f}"),
        ("signed bias", "signed_bias", "{:+13.3f}"),
        ("columns biased high", "columns_biased_high", "{:13d}"),
        ("accuracy @0.50", "accuracy_at_half", "{:13.2%}"),
        ("accuracy @best", "accuracy_at_best", "{:13.2%}"),
        ("best threshold", "best_threshold", "{:13.2f}"),
    ]:
        print(f"{label:22s}" + "".join(fmt.format(r[key]) for r in rows))

    print("\n`accuracy @best` is chosen ON the cells it scores -- an in-sample upper bound that"
          "\nlocalises the failure to the commit threshold. It is not an achievable score.")

    if args.out:
        Path(args.out).write_text(json.dumps(rows, indent=2), encoding="utf-8")
        print(f"\nreport -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
