"""Tests for the paper-accuracy scorer in `scripts/twin2k/paper_accuracy.py`.

The formula is four lines long and every way of getting it wrong still returns a plausible
percentage, which is why it is tested rather than eyeballed:

  * scoring an ordinal item by exact match reads as "worse twins" rather than as a bug;
  * dividing by `n_options` instead of `n_options - 1` shifts every ordinal task by a few points;
  * averaging per QUESTION instead of per task hands 40 of 108 columns (37%) to the pricing study;
  * dropping or double-counting one merge turns the paper's 16 equally-weighted tasks into 17 or 15.

The aggregation tests therefore assert the WEIGHTING, not just the arithmetic: a task with many
columns must not outvote a one-column task. `test_ceiling_matches_recorded_value` is the end-to-end
guard — the same scorer on wave 1-3 vs wave 4 has to land on the recorded 81.68%.
"""

import importlib
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# A 2-option nominal column and a 5-point ordinal one — the scorer's two branches.
BINARY = {"choices": {"1": "more", "2": "fewer"}, "ordered_scale": False, "column": "QID163"}
SCALE_5 = {
    "choices": {
        "1": "Strongly oppose",
        "2": "Somewhat oppose",
        "3": "Neither oppose nor support",
        "4": "Somewhat support",
        "5": "Strongly support",
    },
    "ordered_scale": True,
    "column": "QID287_1",
}


@pytest.fixture(scope="module")
def scorer():
    """Import the script by path — `scripts/` is not a package."""
    scripts_dir = REPO_ROOT / "scripts" / "twin2k"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    return importlib.import_module("paper_accuracy")


def test_binary_item_is_exact_match(scorer):
    assert scorer.score_answer("more", "more", BINARY) == 1.0
    assert scorer.score_answer("more", "fewer", BINARY) == 0.0


def test_ordinal_item_is_graded_by_distance(scorer):
    """Range is `n_options - 1`, so one step off a 5-point scale is 0.75 — not 0, and not 0.8."""
    assert scorer.score_answer("Somewhat support", "Somewhat support", SCALE_5) == 1.0
    assert scorer.score_answer("Somewhat support", "Strongly support", SCALE_5) == 0.75
    assert scorer.score_answer("Strongly oppose", "Strongly support", SCALE_5) == 0.0


def test_off_list_label_is_unscorable_not_wrong(scorer):
    """An answer the option list has no position for is dropped; scoring it 0 would flatter nothing
    and understate the twin, and it usually means a mapping drifted rather than a bad answer."""
    assert scorer.score_answer("Mildly supportive", "Strongly support", SCALE_5) is None


def test_unordered_multi_option_column_raises(scorer):
    """All 65 nominal columns are binary today. If one gains a third option, exact match would
    silently understate it and the graded branch has no order to use — so this must fail loudly."""
    broken = {"choices": {"1": "a", "2": "b", "3": "c"}, "ordered_scale": False, "column": "QIDX"}
    with pytest.raises(SystemExit):
        scorer.score_answer("a", "b", broken)


def test_error_and_missing_cells_are_dropped(scorer):
    """Content-filter losses land in the sheet as `Error`; they must not count as wrong answers."""
    entries = {"QID196": dict(BINARY, column="QID196")}
    pairs = {
        "QID196": [("more", "more"), ("more", "more"), ("Error", "fewer"), (None, "more")],
    }
    task_means, coverage = scorer.score_pairs(pairs, entries)
    assert task_means == {"Dominator neglect": 1.0}
    assert coverage["pairs_scored"] == 2
    assert coverage["pairs_unscorable"] == 2


def test_a_column_with_one_scorable_respondent_is_dropped_and_counted(scorer):
    """Leave-one-out has nothing to predict a lone respondent from, and a column cannot enter the
    accuracy average unless it also enters the baseline average — otherwise `edge` subtracts two
    means taken over different columns. The drop is counted so it never passes as full coverage."""
    entries = {"QID196": dict(BINARY, column="QID196")}
    pairs = {"QID196": [("more", "more"), ("Error", "fewer")]}
    task_means, coverage = scorer.score_pairs(pairs, entries)
    assert task_means == {}
    assert coverage["pairs_scored"] == 0
    assert coverage["pairs_in_single_respondent_columns"] == 1


def test_tasks_are_equally_weighted_not_column_weighted(scorer):
    """Two perfect pricing columns and one failed single-column task average to 50%, not 67%."""
    entries = {
        "QID9_1": dict(BINARY, column="QID9_1"),
        "QID9_2": dict(BINARY, column="QID9_2"),
        "QID196": dict(BINARY, column="QID196"),
    }
    pairs = {
        "QID9_1": [("more", "more"), ("more", "more")],
        "QID9_2": [("more", "more"), ("more", "more")],
        "QID196": [("more", "fewer"), ("more", "fewer")],
    }
    task_means, coverage = scorer.score_pairs(pairs, entries)
    assert task_means == {"Pricing": 1.0, "Dominator neglect": 0.0}
    assert coverage["columns_per_task"] == {"Pricing": 2, "Dominator neglect": 1}


def test_full_instrument_yields_exactly_sixteen_tasks(scorer):
    """The paper's merges (nonseparability halves, both anchoring scenarios, both proportion
    dominance problems) are what make 19 question families into 16 equally-weighted tasks."""
    entries = scorer.load_entries()
    tasks = {scorer.task_of(qid, entry) for qid, entry in entries.items()}
    assert len(entries) == 108
    assert len(tasks) == scorer.EXPECTED_TASKS == 16
    assert scorer.task_of("QID288_1", entries["QID288_1"]) == scorer.task_of(
        "QID289_1", entries["QID289_1"]
    )
    assert scorer.task_of("QID163", entries["QID163"]) == scorer.task_of("QID167", entries["QID167"])
    assert scorer.task_of("QID174", entries["QID174"]) == scorer.task_of("QID177", entries["QID177"])


def test_majority_baseline_is_leave_one_out_not_in_sample(scorer):
    """The baseline must predict each respondent from the OTHERS, never from a mode fitted to the
    respondent being scored. On 3 `more` / 1 `fewer`, held-out prediction is right for the three
    `more` respondents and wrong for the `fewer` one — 0.75, which happens to match the in-sample
    mode here. The next test is the case where the two diverge, and it is the reason this matters:
    an in-sample mode inflated the baseline enough to turn our prior_answers arm's real +0.50 edge
    into a reported -1.08, i.e. to flip the sign of the conclusion."""
    entries = {"QID196": dict(BINARY, column="QID196")}
    pairs = {
        "QID196": [("more", "more"), ("fewer", "more"), ("fewer", "more"), ("fewer", "fewer")],
    }
    task_means, coverage = scorer.score_pairs(pairs, entries)
    assert coverage["majority_per_task"]["Dominator neglect"] == 0.75
    assert task_means["Dominator neglect"] == 0.5  # twin got 2 of 4


def test_leave_one_out_is_penalised_where_in_sample_mode_is_free(scorer):
    """On an evenly split column the in-sample mode still scores 0.5, but held-out prediction scores
    0.0 — every respondent's own answer is what tipped the mode, so removing it flips the prediction.
    A persona-blind predictor genuinely has no information here, and the baseline must say so."""
    entries = {"QID196": dict(BINARY, column="QID196")}
    pairs = {"QID196": [("more", "more"), ("more", "more"), ("more", "fewer"), ("more", "fewer")]}
    _, coverage = scorer.score_pairs(pairs, entries)
    assert coverage["majority_per_task"]["Dominator neglect"] == 0.0


def test_mode_tie_break_is_deterministic(scorer):
    """`max(set(...))` would order by string hash, so the same column could score differently across
    processes and the leave-one-out baseline would not be reproducible. Ties are routine."""
    assert scorer._mode(["more", "fewer"]) == scorer._mode(["fewer", "more"]) == "fewer"


def test_collapsed_column_is_flagged(scorer):
    """One answer for every respondent means the score is the humans' majority share and no arm
    change can move it — the reader needs to know before comparing arms."""
    entries = {"QID196": dict(BINARY, column="QID196"), "QID291": dict(BINARY, column="QID291")}
    pairs = {
        "QID196": [("more", "more"), ("more", "fewer")],  # twin never varies
        "QID291": [("more", "more"), ("fewer", "fewer")],  # twin varies
    }
    _, coverage = scorer.score_pairs(pairs, entries)
    assert coverage["collapsed_columns_per_task"] == {"Dominator neglect": 1, "Omission bias": 0}


@pytest.mark.skipif(
    not (REPO_ROOT / "data" / "twin2k500" / "wave4_response_label.csv").exists(),
    reason="wave CSVs not fetched",
)
def test_ceiling_matches_recorded_value(scorer):
    """End-to-end: the same scorer on the paper's own test-retest pairing must reproduce 81.68%."""
    entries = scorer.load_entries()
    task_means, coverage = scorer.score_pairs(scorer.pairs_from_retest(entries), entries)
    overall = 100 * sum(task_means.values()) / len(task_means)
    assert coverage["tasks"] == 16
    assert overall == pytest.approx(scorer.OUR_CEILING, abs=0.05)

    # The JSON must agree with the table it is written beside — a per-task `edge` that disagreed with
    # `accuracy - majority` would be read as a finding rather than as an assembly bug.
    payload = scorer.scored(task_means, coverage, overall)
    assert payload["overall"] == pytest.approx(overall)
    assert payload["edge_overall"] == pytest.approx(payload["overall"] - payload["majority_overall"])
    assert set(payload["per_task"]) == set(task_means)
    for task, row in payload["per_task"].items():
        assert row["edge"] == pytest.approx(row["accuracy"] - row["majority"])
        assert row["accuracy"] == pytest.approx(100 * task_means[task])
        assert row["collapsed_columns"] <= row["columns"]
