"""Write site/data/figures.json from the shipped scored reports.

The visual explainer never reads the 70 MB JSONL dumps. This script is the only
bridge: it pulls the handful of headline series from reports/ and copies a few
constants that live only in the write-up (ceilings, costs, price-block means,
panel distribution gaps).

Usage, from the repo root:

    python scripts/twin2k/export_site_data.py
    python scripts/twin2k/export_site_data.py --out site/data/figures.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = REPO_ROOT / "site" / "data" / "figures.json"

REPORTS = REPO_ROOT / "reports"
PAPER_ARM1 = REPORTS / "gpt41_panel_n2058" / "paper_accuracy_full_arm1.json"
PAPER_CHAINED = REPORTS / "gpt41_panel_n2058" / "paper_accuracy_full_chained.json"
PAPER_PRIOR = REPORTS / "gpt41_panel_n2058" / "paper_accuracy_full_prior_answers.json"
SIGNAL_ARM1 = REPORTS / "gpt41_panel_n2058" / "individual_signal_full_arm1.json"
SIGNAL_CHAINED = REPORTS / "gpt41_panel_n2058" / "individual_signal_full_chained.json"
SIGNAL_PRIOR = REPORTS / "gpt41_panel_n2058" / "individual_signal_full_prior_answers.json"
SCORE_NOUL = REPORTS / "jev_vs_gpt41_n300" / "score_with_noul.json"
SCORE_ALL = REPORTS / "jev_vs_gpt41_n300" / "score_all_arms.json"
SCORE_DESCRIBED = REPORTS / "jev_vs_gpt41_n300" / "score_with_described.json"

# Numbers that the scored JSON does not carry. Each points at the page that owns it.
DOCUMENTED = {
    "human_ceiling_pct": {
        "value": 81.68,
        "source": "docs/survey/03-grounding-panel.md",
    },
    "paper_twin_pct": {
        "value": 71.72,
        "source": "Toubia et al., Twin-2K-500, arXiv 2505.17479",
    },
    "panel_loo_floor_pct": {
        "value": 73.27,
        "source": "docs/survey/03-grounding-panel.md",
    },
    "costs": {
        "jev_choice": 4.01,
        "jev_noul": 4.02,
        "jev_described": 4.03,
        "gpt41_probs": 136.0,
        "gpt41_hard": None,
        "source": "docs/jev/02-planned-comparison.md",
    },
    "saturation": {
        "choice_zero_pct": 16.6,
        "noul_zero_pct": 0.0,
        "source": "docs/jev/03-noul-follow-up.md",
    },
    "price": {
        "human_mean_p_yes": 0.416,
        "jev_choice_mean_p_yes": 0.601,
        "jev_noul_mean_p_yes": 0.591,
        "gpt41_mean_p_yes": 0.343,
        "human_corr": -0.333,
        "jev_choice_corr": -0.551,
        "jev_noul_corr": -0.522,
        "gpt41_corr": -0.488,
        "jev_choice_bias": 0.185,
        "jev_noul_bias": 0.175,
        "gpt41_bias": -0.073,
        "source": "docs/jev/04-price-sensitivity.md",
    },
    # Distribution gaps for the n=2058 GPT-4.1 panel are reported in the survey
    # track, not in the paper-accuracy JSON (that file is the paper's accuracy
    # definition only).
    "panel_gaps": {
        "demographics_stateless": {"soft_nominal": 0.253, "soft_ordinal": 0.714},
        "demographics_stateful": {"soft_nominal": 0.200, "soft_ordinal": 0.651},
        "prior_answers_stateless": {"soft_nominal": 0.157, "soft_ordinal": 0.681},
        "source": "docs/survey/03-grounding-panel.md",
    },
}


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def first_value(payload: dict) -> dict:
    return next(iter(payload.values()))


def collapsed_columns(signal: dict) -> int:
    """Column collapses live in individual_signal, not paper_accuracy."""
    return sum(row["collapsed"] for row in signal["distributional"].values())


def arm_snapshot(arm: dict) -> dict:
    return {
        "accuracy_pct": arm["accuracy_anchor"]["accuracy_pct"],
        "loo_majority_pct": arm["accuracy_anchor"]["loo_majority_pct"],
        "soft_nominal": arm["fidelity"]["soft_nominal"]["all_tasks"],
        "soft_ordinal": arm["fidelity"]["soft_ordinal"]["all_tasks"],
        "ece": arm["calibration"]["binary"]["ece_equal_task_weight"],
        "brier": arm["brier"]["all_tasks"],
        "respondents": arm["coverage"]["respondents"],
        "cells": arm["coverage"]["cells"],
        "columns": arm["coverage"]["columns"],
    }


def paper_snapshot(paper_path: Path, signal_path: Path, gap_key: str) -> dict:
    report = first_value(load_json(paper_path))
    gaps = DOCUMENTED["panel_gaps"][gap_key]
    return {
        "accuracy_pct": report["overall"],
        "loo_majority_pct": report["majority_overall"],
        "edge_pct": report["edge_overall"],
        "collapsed_columns": collapsed_columns(load_json(signal_path)),
        "soft_nominal": gaps["soft_nominal"],
        "soft_ordinal": gaps["soft_ordinal"],
        "n": 2058,
    }


def build_figures() -> dict:
    noul = load_json(SCORE_NOUL)
    all_arms = load_json(SCORE_ALL)
    described = load_json(SCORE_DESCRIBED)

    jev_choice = arm_snapshot(noul["arms"]["jev"])
    jev_noul = arm_snapshot(noul["arms"]["jev_noul"])
    gpt41_probs = arm_snapshot(noul["arms"]["bc"])
    gpt41_hard = arm_snapshot(all_arms["arms"]["gpt41_hard_chained"])
    jev_described = arm_snapshot(described["arms"]["jev_described"])

    paired = noul["paired"]["jev_vs_bc"]

    return {
        "generated_by": "scripts/twin2k/export_site_data.py",
        "question": (
            "Does Jev's native probability vector beat gpt-4.1 asked to write one out?"
        ),
        "verdict": "reject",
        "references": {
            "repo": "https://github.com/jjd-lab/jev-synthetic-survey",
            "pages": "https://jjd-lab.github.io/jev-synthetic-survey/",
            "dataset": "https://huggingface.co/datasets/LLM-Digital-Twin/Twin-2K-500",
            "paper": "https://arxiv.org/abs/2505.17479",
            "writeup": "https://github.com/jjd-lab/jev-synthetic-survey/blob/main/docs/README.md",
        },
        "constants": {
            "human_ceiling_pct": DOCUMENTED["human_ceiling_pct"]["value"],
            "paper_twin_pct": DOCUMENTED["paper_twin_pct"]["value"],
            "panel_loo_floor_pct": DOCUMENTED["panel_loo_floor_pct"]["value"],
            "comparison_loo_floor_pct": jev_choice["loo_majority_pct"],
            "cells_per_arm": jev_choice["cells"],
            "respondents_comparison": jev_choice["respondents"],
            "columns": jev_choice["columns"],
            "tasks": 16,
            "sources": {
                "human_ceiling_pct": DOCUMENTED["human_ceiling_pct"]["source"],
                "paper_twin_pct": DOCUMENTED["paper_twin_pct"]["source"],
                "panel_loo_floor_pct": DOCUMENTED["panel_loo_floor_pct"]["source"],
            },
        },
        "panel": {
            "model": "gpt-4.1",
            "n": 2058,
            "source": "docs/survey/03-grounding-panel.md",
            "arms": {
                "demographics_stateless": paper_snapshot(
                    PAPER_ARM1, SIGNAL_ARM1, "demographics_stateless"
                ),
                "demographics_stateful": paper_snapshot(
                    PAPER_CHAINED, SIGNAL_CHAINED, "demographics_stateful"
                ),
                "prior_answers_stateless": paper_snapshot(
                    PAPER_PRIOR, SIGNAL_PRIOR, "prior_answers_stateless"
                ),
            },
        },
        "comparison": {
            "n": 300,
            "source": "reports/jev_vs_gpt41_n300/score_with_noul.json",
            "arms": {
                "jev_choice": {**jev_choice, "cost": DOCUMENTED["costs"]["jev_choice"]},
                "jev_described": {**jev_described, "cost": DOCUMENTED["costs"]["jev_described"]},
                "jev_noul": {**jev_noul, "cost": DOCUMENTED["costs"]["jev_noul"]},
                "gpt41_probs": {**gpt41_probs, "cost": DOCUMENTED["costs"]["gpt41_probs"]},
                "gpt41_hard": {**gpt41_hard, "cost": DOCUMENTED["costs"]["gpt41_hard"]},
            },
            "paired_jev_choice_vs_gpt41_probs": {
                "soft_nominal_delta": paired["soft_nominal"]["delta"],
                "soft_nominal_p": paired["soft_nominal"]["wilcoxon_p_left_lower"],
                "soft_ordinal_delta": paired["soft_ordinal"]["delta"],
                "soft_ordinal_p": paired["soft_ordinal"]["wilcoxon_p_left_lower"],
                "c3_jev_wins": paired["c3_left_wins"],
            },
        },
        "noul": {
            "source": "docs/jev/03-noul-follow-up.md",
            "choice_soft_nominal": jev_choice["soft_nominal"],
            "noul_soft_nominal": jev_noul["soft_nominal"],
            "choice_ece": jev_choice["ece"],
            "noul_ece": jev_noul["ece"],
            "choice_zero_pct": DOCUMENTED["saturation"]["choice_zero_pct"],
            "noul_zero_pct": DOCUMENTED["saturation"]["noul_zero_pct"],
        },
        "price": {
            **{k: v for k, v in DOCUMENTED["price"].items() if k != "source"},
            "source": DOCUMENTED["price"]["source"],
        },
    }


def write_figures(out: Path) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = build_figures()
    out.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    path = write_figures(args.out if args.out.is_absolute() else REPO_ROOT / args.out)
    print(f"wrote {path.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
