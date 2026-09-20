"""Score a Twin run with the PAPER's accuracy metric, so our arms can be read against theirs.

Toubia et al. report one number per arm: **exact match for binary items, `1 - |deviation| / range`
otherwise, averaged within a column, then within a task, then across equally-weighted tasks**
(arXiv 2505.17479 §6). Their published reference points are the human test-retest ceiling 81.72%,
the best twin 71.72% (Text Persona & GPT-4.1-mini), and random guessing 59.17%.

Nothing in `src/validation` computes this. Our shipped metrics are DISTRIBUTIONAL — TVD (nominal)
and Wasserstein-1 (ordinal) — plus `individual_baseline`, which is exact match on nominal and MAE on
ordinal, un-aggregated. All of those answer "does the panel look like the panel"; the paper's number
answers "does this twin match this person", which is the only currency their table is in. Hence a
separate, Twin-only scorer rather than a new bucket in the shared validator.

Two aggregation rules do the real work, and both come from the paper:

  1. EQUAL WEIGHT PER TASK. 40 of our 108 columns are the pricing study, so a per-question mean is
     37% one experiment. Averaging within task first is also why 16 tasks, not 19: nonseparability's
     benefits and risks halves count once, as do anchoring's two scenarios and proportion dominance's
     two problems. See the two task tables below and wiki/topics/twin2k-paper-vs-our-setting.md.
  2. RANGE IS `n_options - 1`. Deviation is in scale positions, so a 5-point item's worst answer
     scores 0 and an adjacent one 0.75. All 65 of our nominal columns are binary, so they all take
     the exact-match branch; all 43 ordinal columns carry an ordered `choices` list, so they all take
     the graded branch. A non-binary unordered column would be a mapping change and raises here
     rather than being silently scored as if its option order meant something.

Every report also carries a MAJORITY BASELINE, because the accuracy number is not interpretable
alone: it answers each column with the other respondents' modal label and ignores the persona
entirely, so a twin that cannot beat it is not reading the individual, however close its raw score
sits to the paper's table. Read the per-task `edge` column, not the headline.

The baseline is LEAVE-ONE-OUT (each respondent scored against the mode of the other n-1) and not the
in-sample mode, because the in-sample mode is fitted to the very labels it is scored against and at
small n the inflation is large enough to invert a conclusion. Measured on our n=50 prior_answers arm,
its edge is +0.50 against leave-one-out, -1.08 against the in-sample mode, and -1.70 against the true
modal answer from all 2,058 humans. Three defensible baselines, two different signs — which is why an
n=50 result is not reportable no matter how it is aggregated. The three converge as n grows, so the
ambiguity is a small-n artifact rather than a choice to argue about.

A column needs at least two scorable respondents to enter the report: leave-one-out has nothing to
predict a lone respondent from, and accuracy and baseline must be averaged over the SAME columns or
the `edge` column subtracts two means taken over different sets. Such columns are counted, not
silently dropped.

For scale: the human test-retest ceiling beats the same baseline by +8.41, so that is the headroom
real individual signal is worth on this metric. No arm has a positive edge at panel scale.

`--ceiling` re-runs the same scorer on wave 1-3 vs wave 4 (the paper's own test-retest pairing) and
must land on 81.68% across our 16 tasks. That is the implementation's only external check: the
formula is short enough to look right while being wrong, and the recorded figure pins it.

Usage:
    .venv\\Scripts\\python.exe scripts/twin2k/paper_accuracy.py \\
        --details outputs/twin2k/demographics_only/respondent_details_20260903_170807.xlsx \\
        --details outputs/twin2k/prior_answers/respondent_details_20260903_172818.xlsx \\
        --ceiling
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, Optional, Tuple

import pandas as pd

MAPPING = Path("configs/twin2k/twin2k_question_mapping.json")
WAVE_1_3 = Path("data/twin2k500/wave1_3_response_label.csv")
WAVE_4 = Path("data/twin2k500/wave4_response_label.csv")

# The paper's recorded reference points, for the side-by-side only — never used in a computation.
PAPER_CEILING = 81.72
PAPER_BEST_TWIN = 71.72
PAPER_FLOOR = 59.17
OUR_CEILING = 81.68  # recomputed on our 108 columns; --ceiling must reproduce it

# Task names for the 48 between-subject columns, keyed by the mapping's `condition_group`. The two
# pairs that share a value are the merges the paper makes: one anchoring task, one proportion
# dominance task.
CONDITION_GROUP_TASKS = {
    "Disease": "Asian disease",
    "OutcomeBias": "Outcome bias",
    "AnchoringAfrica": "Anchoring",
    "AnchoringRedwood": "Anchoring",
    "AbsoluteVsRelative": "Absolute vs relative saving",
    "Allais": "Allais paradox",
    "Myside": "Myside bias",
    "LessIsMore": "Less is more",
    "ProportionDominance1": "Proportion dominance",
    "ProportionDominance2": "Proportion dominance",
    "ThalerWTAWTP": "WTA/WTP (Thaler)",
    "Linda": "Linda (conjunction)",
    "ProbabilityMatching": "Probability matching",
}

# The 60 always-asked columns, keyed by question-id prefix. `QID288`/`QID289` share a task for the
# same reason as above: the paper counts nonseparability's benefits and risks halves as one task.
WITHIN_SUBJECT_TASKS = {
    "QID9_": "Pricing",
    "QID287": "False consensus",
    "QID288": "Nonseparability",
    "QID289": "Nonseparability",
    "QID196": "Dominator neglect",
    "QID291": "Omission bias",
}

EXPECTED_TASKS = 16


def load_entries(mapping_path: Path = MAPPING) -> Dict[str, dict]:
    """Return {question_id: mapping entry} for the 108 scored questions."""
    with open(mapping_path, encoding="utf-8") as handle:
        return json.load(handle)


def task_of(question_id: str, entry: dict) -> str:
    """Map one question to its paper task, failing loudly on a question we have no task for."""
    for prefix, task in WITHIN_SUBJECT_TASKS.items():
        if question_id.startswith(prefix):
            return task
    group = entry.get("condition_group")
    if group in CONDITION_GROUP_TASKS:
        return CONDITION_GROUP_TASKS[group]
    raise SystemExit(
        f"{question_id}: no paper task — condition_group={group!r}. A new scored column must be "
        f"added to CONDITION_GROUP_TASKS or WITHIN_SUBJECT_TASKS, or the 16-task equal weighting "
        f"silently becomes a 17-task one."
    )


def score_answer(synthetic: str, ground_truth: str, entry: dict) -> Optional[float]:
    """The paper's per-answer score: exact match if binary, else 1 - |deviation| / range.

    Returns None when the pair cannot be scored (missing, `Error`, or a label outside the option
    list), so the caller can report coverage instead of scoring a guess as wrong.
    """
    options = list(entry["choices"].values())
    if not entry.get("ordered_scale"):
        if len(options) != 2:
            raise SystemExit(
                f"{entry.get('column')}: unordered with {len(options)} options — the paper's graded "
                f"branch needs an order and exact match would understate it. Fix the mapping."
            )
        return 1.0 if synthetic == ground_truth else 0.0
    # A 2-option ordered column lands on 0.0 or 1.0 here anyway, so it needs no separate branch.
    positions = {option: index for index, option in enumerate(options)}
    if synthetic not in positions or ground_truth not in positions:
        return None
    return 1.0 - abs(positions[synthetic] - positions[ground_truth]) / (len(options) - 1)


def _clean(value) -> Optional[str]:
    """Normalise one cell to a scorable label, or None."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip()
    if not text or text in {"Error", "nan", "None"}:
        return None
    return text


def _mode(labels: list) -> str:
    """Most common label, breaking ties by sort order.

    The tie-break has to be deterministic: `max(set(...))` iterates a set, whose order depends on
    string hashing, so the same data would score differently across processes and the leave-one-out
    baseline below would stop being reproducible. Ties are common — a 2-option column with n-1 even
    hits one whenever the sample splits.
    """
    return max(sorted(set(labels)), key=labels.count)


def score_pairs(pairs: Dict[str, list], entries: Dict[str, dict],
                task_of=task_of, score=score_answer) -> Tuple[Dict[str, float], dict]:
    """Aggregate {question_id: [(synthetic, ground_truth), ...]} into per-task accuracy.

    Column mean -> task mean -> equal-weight mean across tasks, which is the paper's order. A column
    with no scorable pair is dropped rather than counted as 0, and reported in `coverage`.

    `task_of` and `score` default to this module's twin2k versions and are parameters only so a
    second instrument can borrow the aggregation without copying it — the two rules the tests here
    exist to pin (equal weight per task, leave-one-out baseline) are the part that must not drift,
    while the task taxonomy and the per-answer branch conditions are instrument-specific. See
    a caller that passes both.
    """
    column_scores = {}
    unscorable = 0
    below_minimum = 0
    for question_id, answers in pairs.items():
        entry = entries[question_id]
        scorable = []
        for synthetic, ground_truth in answers:
            synthetic, ground_truth = _clean(synthetic), _clean(ground_truth)
            if synthetic is None or ground_truth is None:
                unscorable += 1
                continue
            cell = score(synthetic, ground_truth, entry)
            if cell is None:
                unscorable += 1
                continue
            scorable.append((synthetic, ground_truth, cell))
        # A single respondent leaves the leave-one-out baseline nothing to predict from. Rather than
        # special-casing it, drop the column: accuracy and baseline must be averaged over the SAME
        # columns or `edge` compares two different things, and one respondent carries no information
        # about a column anyway. Counted separately below so the drop is visible, not silent.
        if len(scorable) < 2:
            below_minimum += len(scorable)
            continue
        truths = [truth for _, truth, _ in scorable]
        baseline = [
            score(_mode(truths[:index] + truths[index + 1:]), truth, entry)
            for index, truth in enumerate(truths)
        ]
        column_scores[question_id] = {
            "task": task_of(question_id, entry),
            "mean": sum(value for _, _, value in scorable) / len(scorable),
            # Leave-one-out majority baseline: predict each respondent from the OTHER respondents'
            # modal label, ignoring the persona entirely. Out-of-sample by construction, so unlike
            # the in-sample mode it is a fair competitor rather than an inflated one — see the module
            # docstring for how much that inflation moved our own conclusion.
            "majority": sum(baseline) / len(baseline),
            "n": len(scorable),
            # A column where every twin gave the SAME answer still gets full task weight, but it
            # cannot carry evidence that the grounding worked: its score is the humans' modal share
            # and no persona change can move it. Flagged because the equal weighting makes an inert
            # task as loud as an informative one. It can still beat the leave-one-out baseline, which
            # is penalised on exactly the near-even columns where a held-out mode is unstable.
            "collapsed": len({synthetic for synthetic, _, _ in scorable}) == 1,
        }

    per_task: Dict[str, list] = {}
    per_task_majority: Dict[str, list] = {}
    task_pairs: Dict[str, int] = {}
    task_collapsed: Dict[str, int] = {}
    for column in column_scores.values():
        task = column["task"]
        per_task.setdefault(task, []).append(column["mean"])
        per_task_majority.setdefault(task, []).append(column["majority"])
        task_pairs[task] = task_pairs.get(task, 0) + column["n"]
        task_collapsed[task] = task_collapsed.get(task, 0) + int(column["collapsed"])
    task_means = {task: sum(means) / len(means) for task, means in per_task.items()}
    coverage = {
        "columns_scored": len(column_scores),
        "tasks": len(task_means),
        "pairs_scored": sum(task_pairs.values()),
        "pairs_unscorable": unscorable,
        "pairs_in_single_respondent_columns": below_minimum,
        "columns_per_task": {task: len(means) for task, means in per_task.items()},
        "pairs_per_task": task_pairs,
        "collapsed_columns_per_task": task_collapsed,
        "majority_per_task": {
            task: sum(means) / len(means) for task, means in per_task_majority.items()
        },
    }
    return task_means, coverage


def pairs_from_details(details_path: Path, entries: Dict[str, dict]) -> Dict[str, list]:
    """Read `<qid>_synthetic` / `<qid>_ground_truth` pairs out of a run's respondent details."""
    frame = pd.read_excel(details_path)
    pairs: Dict[str, list] = {}
    for question_id in entries:
        synthetic_col, truth_col = f"{question_id}_synthetic", f"{question_id}_ground_truth"
        if synthetic_col not in frame.columns or truth_col not in frame.columns:
            continue
        pairs[question_id] = list(zip(frame[synthetic_col], frame[truth_col]))
    if not pairs:
        raise SystemExit(f"{details_path}: no `<qid>_synthetic` columns — is this a run's details file?")
    return pairs


def pairs_from_retest(entries: Dict[str, dict]) -> Dict[str, list]:
    """Pair each respondent's wave 1-3 answer with their own wave 4 answer — the paper's ceiling.

    This is the same person twice, so it measures how much of the gap to 100% is human instability
    rather than twin error. Respondents are matched on `pid`, which both label CSVs carry.
    """
    for path in (WAVE_1_3, WAVE_4):
        if not path.exists():
            raise SystemExit(f"{path} not found — run scripts/twin2k/fetch_twin2k.py first")
    wave_1_3 = pd.read_csv(WAVE_1_3, low_memory=False).set_index("pid")
    wave_4 = pd.read_csv(WAVE_4, low_memory=False).set_index("pid")
    shared = wave_1_3.index.intersection(wave_4.index)
    pairs: Dict[str, list] = {}
    for question_id, entry in entries.items():
        column = entry.get("column", question_id)
        if column not in wave_1_3.columns or column not in wave_4.columns:
            continue
        pairs[question_id] = list(zip(wave_4.loc[shared, column], wave_1_3.loc[shared, column]))
    return pairs


def report(label: str, task_means: Dict[str, float], coverage: dict,
           expected_tasks: int = EXPECTED_TASKS) -> float:
    """Print one scored run and return its equal-weight accuracy in percent."""
    overall = 100 * sum(task_means.values()) / len(task_means)
    majority = 100 * sum(coverage["majority_per_task"].values()) / len(task_means)
    print(f"\n=== {label} ===")
    print(f"{'task':<30} {'cols':>5} {'pairs':>7} {'accuracy':>9} {'LOO-mode':>9} {'edge':>7}")
    inert = []
    # Worst edge first: a task the twin loses to the majority baseline on is the actionable one.
    for task, mean in sorted(task_means.items(), key=lambda item: item[1] - coverage["majority_per_task"][item[0]]):
        collapsed = coverage["collapsed_columns_per_task"][task]
        columns = coverage["columns_per_task"][task]
        edge = 100 * (mean - coverage["majority_per_task"][task])
        flag = "  <- collapsed" if collapsed == columns else ""
        if collapsed == columns:
            inert.append(task)
        print(
            f"{task:<30} {columns:>5} {coverage['pairs_per_task'][task]:>7} "
            f"{100 * mean:>8.2f}% {100 * coverage['majority_per_task'][task]:>8.2f}% "
            f"{edge:>+6.2f}{flag}"
        )
    print(f"{'EQUAL-WEIGHT ACROSS TASKS':<30} {coverage['columns_scored']:>5} "
          f"{coverage['pairs_scored']:>7} {overall:>8.2f}% {majority:>8.2f}% "
          f"{overall - majority:>+6.2f}")
    if overall < majority:
        print(f"  [!] BELOW the persona-blind leave-one-out baseline by {majority - overall:.2f} pt — on "
              f"this metric the twin adds no net individual signal")
    if coverage["tasks"] != expected_tasks:
        print(f"  [WARN] {coverage['tasks']} tasks, expected {expected_tasks} — "
              f"equal weighting is not the paper's")
    if inert:
        print(f"  {len(inert)}/{coverage['tasks']} tasks carry one answer for every twin "
              f"({', '.join(inert)}) — {100 * len(inert) / coverage['tasks']:.0f}% of the weight "
              f"cannot move between arms")
    if coverage["pairs_in_single_respondent_columns"]:
        print(f"  {coverage['pairs_in_single_respondent_columns']} cells dropped in columns with one "
              f"respondent — leave-one-out is undefined there")
    if coverage["pairs_unscorable"]:
        print(f"  {coverage['pairs_unscorable']} cells unscorable (missing, Error, or off-list) "
              f"— dropped, not counted wrong")
    return overall


def scored(task_means: Dict[str, float], coverage: dict, overall: float) -> dict:
    """The printed report as data, so a per-task read needs no scraping of stdout.

    Carries the baseline and the edge, not accuracy alone: the headline is not interpretable without
    them (a persona-blind majority predictor beats it here), and a JSON holding only accuracy invites
    exactly the reading the report's own `[!]` line warns against. `columns`/`collapsed` come along
    because an all-collapsed task's edge is +0.00 by construction rather than by agreement.
    """
    majority = 100 * sum(coverage["majority_per_task"].values()) / len(task_means)
    return {
        "tasks": task_means,
        "overall": overall,
        "majority_overall": majority,
        "edge_overall": overall - majority,
        "per_task": {
            task: {
                "columns": coverage["columns_per_task"][task],
                "collapsed_columns": coverage["collapsed_columns_per_task"][task],
                "pairs": coverage["pairs_per_task"][task],
                "accuracy": 100 * mean,
                "majority": 100 * coverage["majority_per_task"][task],
                "edge": 100 * (mean - coverage["majority_per_task"][task]),
            }
            for task, mean in task_means.items()
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--details", action="append", default=[],
                        help="respondent_details_*.xlsx of a run; repeatable")
    parser.add_argument("--ceiling", action="store_true",
                        help="also score wave1-3 vs wave4 (human test-retest ceiling)")
    parser.add_argument("--json", help="write the full report per label (overall, majority, edge, "
                                       "and a per_task block) here")
    args = parser.parse_args()

    if not args.details and not args.ceiling:
        parser.error("nothing to score: pass --details and/or --ceiling")

    entries = load_entries()
    results = {}

    for path in args.details:
        path = Path(path)
        task_means, coverage = score_pairs(pairs_from_details(path, entries), entries)
        label = f"{path.parent.name} ({path.name})"
        results[label] = scored(task_means, coverage, report(label, task_means, coverage))

    if args.ceiling:
        task_means, coverage = score_pairs(pairs_from_retest(entries), entries)
        overall = report("human test-retest ceiling (wave 1-3 vs wave 4)", task_means, coverage)
        results["ceiling"] = scored(task_means, coverage, overall)
        drift = abs(overall - OUR_CEILING)
        verdict = "matches" if drift <= 0.05 else "DIVERGES from"
        print(f"  {verdict} the recorded {OUR_CEILING}% (delta {drift:.2f} pt)")

    # Both ceilings, always, and each labelled with the task set it covers. Printing only the paper's
    # invites reading an arm scored on our 16 tasks against a figure covering the paper's 17 — a 0.04 pt
    # gap that looks like one of the two being stale rather than the two measuring different things.
    print(f"\nCeiling on OUR 16 tasks: {OUR_CEILING}% — the one to read these arms against."
          f"\nPaper's reference points (its 17 tasks): ceiling {PAPER_CEILING}%, "
          f"best twin {PAPER_BEST_TWIN}%, random floor {PAPER_FLOOR}%")

    if args.json:
        Path(args.json).write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(f"wrote {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
