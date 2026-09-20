"""Tests for the probability scorer.

Two kinds, and the split is deliberate. The FIRST test is an external anchor: `convert` + `score`
over the recorded `prior_answers` panel must reproduce `paper_accuracy`'s 72.92% / 73.27% bit for
bit. Every formula in the module is short enough to look right while being wrong, and that pair of
numbers is the only check that does not come from the same head that wrote the code.

The rest are synthetic forecasters with known answers -- an oracle, a base-rate predictor, a
confidently-wrong predictor -- because a metric is only trustworthy if it returns the value theory
says it must on inputs whose value theory fixes. They also pin the four aggregation choices the plan
pre-registered, since those are what a later reader is most likely to "simplify" back into a pooled
cell mean.
"""

import json
from pathlib import Path

import numpy as np
import pytest

from scripts.twin2k.paper_accuracy import load_entries
from scripts.twin2k.prob_scoring import (
    PRICING_TASK,
    _c1_verdict,
    _draw_index,
    accuracy_anchor,
    brier_cells,
    build_columns,
    calibration,
    convert,
    distance,
    equal_weight,
    fidelity,
    framing_contrast,
    human_marginal,
    loo_marginal_forecast,
    marginals,
    match_option,
    murphy,
    raw_sum_report,
    read_jsonl,
    score_arms,
    vector_of,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
ANCHOR_DETAILS = (REPO_ROOT / "outputs" / "twin2k" / "prior_answers"
                  / "respondent_details_20260908_074918.xlsx")
ANCHOR_RECORDED = REPO_ROOT / "outputs" / "twin2k" / "paper_accuracy_full_prior_answers.json"

# Real Twin qids, so `task_of` resolves without a stub. Four within-subject tasks are reachable
# without condition groups, which is enough to test the equal-weighting rule.
PRICING_QID = "QID9_1"          # task "Pricing" -- the 40-column block the weighting protects against
CONSENSUS_QID = "QID287_1"      # task "False consensus"
OMISSION_QID = "QID291_1"       # task "Omission bias"
DOMINATOR_QID = "QID196_1"      # task "Dominator neglect"
BINARY = ["Yes", "No"]
SCALE = ["Strongly oppose", "Somewhat oppose", "Somewhat support", "Strongly support"]


def _entries(spec: dict) -> dict:
    """{qid: (options, ordered_scale)} -> mapping entries shaped like the real ones."""
    return {
        qid: {
            "column": qid,
            "choices": {str(i + 1): option for i, option in enumerate(options)},
            "ordered_scale": ordered,
        }
        for qid, (options, ordered) in spec.items()
    }


def _rows(qid, options, forecasts, humans, arm="test"):
    """One cell per (respondent, question). `forecasts[i]` may be a vector or None (hard choice)."""
    rows = []
    for index, (vector, human) in enumerate(zip(forecasts, humans)):
        probs = None if vector is None else {o: float(v) for o, v in zip(options, vector)}
        choice = options[int(np.argmax(vector))] if vector is not None else human
        rows.append({"arm": arm, "respid": f"r{index}", "qid": qid, "options": list(options),
                     "probs": probs, "choice": choice, "human": human})
    return rows


# --------------------------------------------------------------------------
# The external anchor
# --------------------------------------------------------------------------
@pytest.mark.unit
def test_the_recorded_panel_reproduces_paper_accuracy_exactly(tmp_path):
    """`convert` + `score` must land on the SAME accuracy `paper_accuracy.py` recorded.

    Not "close to": bit-identical. The two scorers share `score_pairs` and the task taxonomy, so any
    drift in how this module reads a details file, matches option labels, or drops an unscorable cell
    moves this number -- which is exactly what an equality assertion catches and a tolerance hides.

    The 10 `QID198_*` columns are the reason `match_option` exists: pandas types them float64, so
    their labels arrive as `1.0` against a mapping that says `"1"`. `paper_accuracy` compares two
    cells from the same file and never notices; a vector indexed BY the option list does.
    """
    if not ANCHOR_DETAILS.exists() or not ANCHOR_RECORDED.exists():
        pytest.skip(
            "the source respondent_details workbook is not shipped (6.9 MB, and it is the "
            "only thing in the repo that would need it). This test covers the Excel -> JSONL "
            "`convert` path; the already-converted arms in runs/ exercise everything after it. "
            "Drop the workbook at the path above to run it."
        )

    entries = load_entries()
    out = tmp_path / "anchor.jsonl"
    convert(ANCHOR_DETAILS, "prior_answers", out, entries)
    columns, dropped = build_columns(read_jsonl(out), entries)

    assert len(columns) == 108, f"scored {len(columns)} of 108 columns; dropped {dropped}"
    assert dropped["human_off_scale"] == 0, "every human label must land on the mapping's scale"

    scored = accuracy_anchor(columns, entries, "prior_answers")
    recorded = next(iter(json.loads(ANCHOR_RECORDED.read_text(encoding="utf-8")).values()))
    assert scored["accuracy_pct"] == recorded["overall"]
    assert scored["loo_majority_pct"] == recorded["majority_overall"]
    assert scored["tasks"] == 16


# --------------------------------------------------------------------------
# Forecasters whose scores theory fixes
# --------------------------------------------------------------------------
@pytest.mark.unit
class TestKnownForecasters:
    def test_an_oracle_scores_zero_brier(self):
        humans = ["Yes", "No", "Yes", "No", "Yes"]
        forecasts = [[1.0, 0.0] if h == "Yes" else [0.0, 1.0] for h in humans]
        columns, _ = build_columns(_rows(PRICING_QID, BINARY, forecasts, humans),
                                  _entries({PRICING_QID: (BINARY, False)}))
        assert brier_cells(columns[PRICING_QID]).mean() == pytest.approx(0.0)

    def test_a_maximally_wrong_forecaster_scores_the_brier_maximum(self):
        """Two is the multiclass Brier ceiling: probability 1 on the one wrong option."""
        humans = ["Yes", "No", "Yes", "No"]
        forecasts = [[0.0, 1.0] if h == "Yes" else [1.0, 0.0] for h in humans]
        columns, _ = build_columns(_rows(PRICING_QID, BINARY, forecasts, humans),
                                  _entries({PRICING_QID: (BINARY, False)}))
        assert brier_cells(columns[PRICING_QID]).mean() == pytest.approx(2.0)

    def test_a_base_rate_forecaster_has_no_resolution_and_no_reliability(self):
        """Forecasting the base rate for everyone: perfectly calibrated, zero discrimination.

        The Murphy decomposition's whole point is telling those two apart -- a base-rate forecaster
        is unimprovable on reliability and useless on resolution, and an aggregate score that cannot
        distinguish it from a skilled forecaster is not reporting skill.
        """
        humans = ["Yes"] * 30 + ["No"] * 70
        forecasts = [[0.30, 0.70]] * 100
        columns, _ = build_columns(_rows(PRICING_QID, BINARY, forecasts, humans),
                                  _entries({PRICING_QID: (BINARY, False)}))
        decomposition = murphy(columns)
        assert decomposition["reliability"] == pytest.approx(0.0, abs=1e-9)
        assert decomposition["resolution"] == pytest.approx(0.0, abs=1e-9)
        assert decomposition["uncertainty"] == pytest.approx(0.3 * 0.7)
        # Brier = reliability - resolution + uncertainty, the identity the three terms exist to state.
        assert decomposition["brier_binary_pooled"] == pytest.approx(
            decomposition["reliability"] - decomposition["resolution"]
            + decomposition["uncertainty"]
        )

    def test_a_skilled_forecaster_earns_resolution(self):
        """The contrast that makes the previous test meaningful."""
        humans = ["Yes"] * 50 + ["No"] * 50
        forecasts = [[0.9, 0.1]] * 50 + [[0.1, 0.9]] * 50
        columns, _ = build_columns(_rows(PRICING_QID, BINARY, forecasts, humans),
                                  _entries({PRICING_QID: (BINARY, False)}))
        decomposition = murphy(columns)
        assert decomposition["resolution"] == pytest.approx(0.25, abs=1e-9)
        assert decomposition["reliability"] == pytest.approx(0.01, abs=1e-9)

    @pytest.mark.parametrize("confidence", [0.7, 0.8, 0.95])
    def test_a_confidently_wrong_forecaster_has_ece_equal_to_its_confidence(self, confidence):
        """Says `confidence` on an option that never happens, so ECE is exactly `confidence`.

        This is the overconfidence tell C1 exists to catch, and it pins the sign convention: ECE
        measures |claimed - observed|, so a model that is sure and wrong scores its own certainty.
        """
        humans = ["No"] * 40
        forecasts = [[confidence, 1 - confidence]] * 40
        columns, _ = build_columns(_rows(PRICING_QID, BINARY, forecasts, humans),
                                  _entries({PRICING_QID: (BINARY, False)}))
        report = calibration(columns)["binary"]
        assert report["ece_pooled"] == pytest.approx(confidence)
        assert report["ece_equal_task_weight"] == pytest.approx(confidence)
        assert _c1_verdict(report["ece_equal_task_weight"]).startswith("FAIL")

    def test_a_calibrated_forecaster_passes_c1(self):
        """60% confidence that is right 60% of the time: ECE ~ 0 and the C1 band says PASS."""
        humans = ["Yes"] * 60 + ["No"] * 40
        forecasts = [[0.6, 0.4]] * 100
        columns, _ = build_columns(_rows(PRICING_QID, BINARY, forecasts, humans),
                                  _entries({PRICING_QID: (BINARY, False)}))
        report = calibration(columns)["binary"]
        assert report["ece_pooled"] == pytest.approx(0.0, abs=1e-9)
        assert _c1_verdict(report["ece_equal_task_weight"]).startswith("PASS")

    def test_the_zero_probability_cells_are_counted(self):
        """Log loss is clipped, so the only honest record of a flat-out-wrong vector is a count."""
        humans = ["Yes", "Yes", "Yes"]
        forecasts = [[0.0, 1.0], [0.0, 1.0], [0.5, 0.5]]
        columns, _ = build_columns(_rows(PRICING_QID, BINARY, forecasts, humans),
                                  _entries({PRICING_QID: (BINARY, False)}))
        from scripts.twin2k.prob_scoring import brier_report
        assert brier_report(columns)["cells_with_zero_probability_on_truth"] == 2


# --------------------------------------------------------------------------
# soft / argmax / draw over the same vectors
# --------------------------------------------------------------------------
@pytest.mark.unit
class TestCommitRules:
    def test_soft_is_the_expected_value_of_the_draw(self):
        """exp-007's finding, re-derived here: aggregating the vectors IS the mean of the draws.

        If this drifts, `soft` and `draw` have stopped being two readings of one elicitation, and the
        plan's claim that the three commit rules are comparable stops holding.
        """
        rng = np.random.default_rng(7)
        n, replications = 100, 2_000
        raw = rng.dirichlet([1.0, 1.0], size=n)
        humans = ["Yes"] * n
        columns, _ = build_columns(_rows(PRICING_QID, BINARY, raw, humans),
                                  _entries({PRICING_QID: (BINARY, False)}))
        block = columns[PRICING_QID]
        soft = marginals(block, "soft", PRICING_QID)

        # Each replication reseeds by varying the qid the seed is built from -- the same knob
        # `--order-salt` turns -- so this measures the estimator rather than one lucky seed.
        draws = np.array([
            np.bincount([_draw_index(block["P"][i], block["respids"][i], f"{PRICING_QID}|{rep}")
                         for i in range(n)], minlength=2) / n
            for rep in range(replications)
        ])
        spread = draws.std(axis=0, ddof=1).max()
        tolerance = 4 * spread / np.sqrt(replications)
        assert np.abs(draws.mean(axis=0) - soft).max() < tolerance

    def test_the_draw_replays_the_runners_own_commit_rule(self):
        """Cell by cell, not just in distribution.

        `_weighted_draw_answer` is what a `weighted_draw` RUN commits. Same seed string, same
        `rng.choices` call, so an offline draw here must be the identical option -- otherwise the
        `draw` column reports a rule nothing ever ran.
        """
        from src.core.survey_runner_excel import _weighted_draw_answer

        rng = np.random.default_rng(11)
        options = ["A", "B", "C", "D"]
        for index in range(200):
            vector = rng.dirichlet([0.4] * 4)
            respid, qid = f"resp{index}", f"QID{index}"
            probs = {o: float(v) for o, v in zip(options, vector)}
            expected = _weighted_draw_answer("A", probs, options, respid, qid, multi=False)
            assert options[_draw_index(vector, respid, qid)] == expected

    def test_a_degenerate_vector_falls_back_to_the_argmax(self):
        assert _draw_index(np.zeros(3), "r1", "Q1") == 0

    def test_a_hard_choice_arm_is_scored_one_hot(self):
        """`probs: null` is a forecast of 1 on the committed answer, which is what makes the
        existing gpt-4.1 arms comparable on Brier rather than unscoreable."""
        row = {"probs": None, "choice": "No"}
        assert list(vector_of(row, BINARY)) == [0.0, 1.0]

    def test_an_unusable_vector_falls_back_to_the_committed_answer(self):
        """All-zero is not a uniform forecast -- the model did commit an answer, so use it."""
        row = {"probs": {"Yes": 0.0, "No": 0.0}, "choice": "No"}
        assert list(vector_of(row, BINARY)) == [0.0, 1.0]

    def test_a_genuinely_uniform_vector_is_kept_as_uniform(self):
        row = {"probs": {"Yes": 0.5, "No": 0.5}, "choice": "Yes"}
        assert list(vector_of(row, BINARY)) == [0.5, 0.5]

    def test_a_choice_off_the_option_list_makes_the_cell_unscorable(self):
        assert vector_of({"probs": None, "choice": "Maybe"}, BINARY) is None


# --------------------------------------------------------------------------
# The four pre-registered aggregation choices
# --------------------------------------------------------------------------
@pytest.mark.unit
class TestAggregation:
    def _pricing_heavy(self):
        """39 pricing columns where the arm is perfect, 1 other column where it is hopeless.

        Mirrors the real shape: 40 of 108 columns are one experiment. A cell-pooled or column-pooled
        mean would read ~0.02; equal weight per task reads ~0.5, because there are two tasks.
        """
        spec, rows = {}, []
        for index in range(1, 40):
            qid = f"QID9_{index}"
            spec[qid] = (BINARY, False)
            rows += _rows(qid, BINARY, [[1.0, 0.0]] * 6, ["Yes"] * 6)
        spec[CONSENSUS_QID] = (BINARY, False)
        rows += _rows(CONSENSUS_QID, BINARY, [[0.0, 1.0]] * 6, ["Yes"] * 6)
        return build_columns(rows, _entries(spec))[0]

    def test_pricing_cannot_dominate_the_headline(self):
        columns = self._pricing_heavy()
        report = fidelity(columns)["soft_nominal"]
        assert report["n_tasks"] == 2
        # Two tasks, one at 0 error and one at maximal error -> 0.5. A per-column mean would be 1/40.
        assert report["all_tasks"] == pytest.approx(0.5)
        assert report["per_task"][PRICING_TASK] == pytest.approx(0.0)

    def test_the_pricing_excluded_headline_drops_the_pricing_task(self):
        columns = self._pricing_heavy()
        report = fidelity(columns)["soft_nominal"]
        assert report["excl_pricing"] == pytest.approx(1.0), (
            "with pricing removed only the failing task remains"
        )

    def test_a_task_with_more_columns_does_not_get_more_weight(self):
        """The rule stated on its own: within a task, columns average; across tasks, tasks average."""
        assert equal_weight({"a": 0.0, "b": 1.0}) == pytest.approx(0.5)

    def test_the_two_buckets_are_never_averaged_together(self):
        """TVD is bounded by 1; Wasserstein-1 is in scale positions. A mean over both has no unit."""
        spec = {PRICING_QID: (BINARY, False), CONSENSUS_QID: (SCALE, True)}
        rows = (_rows(PRICING_QID, BINARY, [[1.0, 0.0]] * 4, ["Yes"] * 4)
                + _rows(CONSENSUS_QID, SCALE, [[1.0, 0, 0, 0]] * 4, [SCALE[3]] * 4))
        columns, _ = build_columns(rows, _entries(spec))
        report = fidelity(columns)
        assert report["soft_nominal"]["per_task"].keys() == {PRICING_TASK}
        assert report["soft_ordinal"]["per_task"].keys() == {"False consensus"}
        # Maximal disagreement on a 4-point scale is 3 positions, which TVD could never report.
        assert report["soft_ordinal"]["all_tasks"] == pytest.approx(3.0)

    def test_ordinal_distance_counts_scale_positions(self):
        """An adjacent miss must cost less than an opposite one; TVD would score both the same."""
        entries = _entries({CONSENSUS_QID: (SCALE, True)})
        near = build_columns(_rows(CONSENSUS_QID, SCALE, [[0, 0, 1.0, 0]] * 4, [SCALE[3]] * 4),
                             entries)[0][CONSENSUS_QID]
        far = build_columns(_rows(CONSENSUS_QID, SCALE, [[1.0, 0, 0, 0]] * 4, [SCALE[3]] * 4),
                            entries)[0][CONSENSUS_QID]
        assert distance(near, marginals(near, "soft"), human_marginal(near)) == pytest.approx(1.0)
        assert distance(far, marginals(far, "soft"), human_marginal(far)) == pytest.approx(3.0)

    def test_a_column_with_one_respondent_is_dropped_not_scored(self):
        """Same floor `paper_accuracy` uses: a leave-one-out reference needs someone to hold out."""
        rows = (_rows(PRICING_QID, BINARY, [[1.0, 0.0]], ["Yes"])
                + _rows(CONSENSUS_QID, BINARY, [[1.0, 0.0]] * 3, ["Yes"] * 3))
        columns, _ = build_columns(rows, _entries({PRICING_QID: (BINARY, False),
                                                  CONSENSUS_QID: (BINARY, False)}))
        assert set(columns) == {CONSENSUS_QID}


# --------------------------------------------------------------------------
# Reference forecasts and uncertainty
# --------------------------------------------------------------------------
@pytest.mark.unit
class TestReferencesAndUncertainty:
    def test_the_loo_marginal_is_out_of_sample(self):
        """Each row must exclude its OWN label, or the reference is fitted to what it predicts.

        The in-sample version is not a smaller version of this: on this repo's n=50 Twin arm the two
        gave opposite signs for the edge, which is why only the leave-one-out form is used.
        """
        humans = ["Yes", "Yes", "Yes", "No"]
        columns, _ = build_columns(
            _rows(PRICING_QID, BINARY, [[0.5, 0.5]] * 4, humans),
            _entries({PRICING_QID: (BINARY, False)}),
        )
        forecast = loo_marginal_forecast(columns[PRICING_QID])
        # Respondent 0 said Yes; the other three are 2 Yes / 1 No.
        assert forecast[0].tolist() == pytest.approx([2 / 3, 1 / 3])
        # Respondent 3 said No; the other three are 3 Yes / 0 No.
        assert forecast[3].tolist() == pytest.approx([1.0, 0.0])
        assert np.allclose(forecast.sum(axis=1), 1.0)

    def test_a_forecaster_that_beats_the_reference_has_positive_skill(self):
        from scripts.twin2k.prob_scoring import brier_report

        humans = ["Yes"] * 5 + ["No"] * 5
        forecasts = [[1.0, 0.0]] * 5 + [[0.0, 1.0]] * 5
        columns, _ = build_columns(_rows(PRICING_QID, BINARY, forecasts, humans),
                                  _entries({PRICING_QID: (BINARY, False)}))
        report = brier_report(columns)
        assert report["bss_vs_loo_marginal"]["all_tasks"] == pytest.approx(1.0)
        assert report["bss_vs_uniform"]["all_tasks"] == pytest.approx(1.0)

    def test_the_bootstrap_resamples_respondents_not_cells(self):
        """The interval must widen when cells within a respondent are correlated.

        Built so each respondent answers 12 columns identically: resampling CELLS then treats 120
        correlated observations as 120 independent ones and reports an interval several times too
        narrow. This is the specific error the respondent-level bootstrap exists to avoid, so it is
        asserted rather than argued.
        """
        from scripts.twin2k.prob_scoring import _brier_statistic, bootstrap

        spec, rows = {}, []
        # Ten respondents, each perfectly consistent across 12 columns of one task.
        qids = [f"QID9_{i}" for i in range(1, 13)]
        humans = ["Yes"] * 5 + ["No"] * 5
        for qid in qids:
            spec[qid] = (BINARY, False)
            rows += _rows(qid, BINARY, [[0.75, 0.25]] * 10, humans)
        columns, _ = build_columns(rows, _entries(spec))

        by_respondent = bootstrap(columns, _brier_statistic, 400, 1)
        respondent_width = by_respondent["ci_high"] - by_respondent["ci_low"]

        # The same interval computed by resampling cells inside each column independently.
        rng = np.random.default_rng(1)
        cell_values = []
        for _ in range(400):
            resampled = {}
            for qid, block in columns.items():
                picks = rng.integers(0, len(block["y"]), len(block["y"]))
                resampled[qid] = {**block, "P": block["P"][picks], "y": block["y"][picks],
                                  "respids": [block["respids"][p] for p in picks],
                                  "raw_sums": [block["raw_sums"][p] for p in picks],
                                  "choices": [block["choices"][p] for p in picks]}
            cell_values.append(_brier_statistic(resampled))
        cell_width = np.quantile(cell_values, 0.975) - np.quantile(cell_values, 0.025)

        assert respondent_width > 1.5 * cell_width, (
            f"respondent bootstrap {respondent_width:.4f} is not meaningfully wider than the "
            f"cell bootstrap {cell_width:.4f} — the correlation is going unaccounted for"
        )

    def test_the_paired_comparison_uses_only_cells_both_arms_cover(self, tmp_path):
        """A column one arm aborted out of is not evidence about the other arm."""
        entries = _entries({PRICING_QID: (BINARY, False), CONSENSUS_QID: (BINARY, False)})
        left = tmp_path / "left.jsonl"
        right = tmp_path / "right.jsonl"
        # The left arm covers both columns; the right arm only covers the first.
        _write(left, _rows(PRICING_QID, BINARY, [[0.9, 0.1]] * 5, ["Yes"] * 5, "left")
               + _rows(CONSENSUS_QID, BINARY, [[0.9, 0.1]] * 5, ["Yes"] * 5, "left"))
        _write(right, _rows(PRICING_QID, BINARY, [[0.6, 0.4]] * 5, ["Yes"] * 5, "right"))

        report = score_arms({"left": left, "right": right}, entries, 20, 1, 10)
        paired = report["paired"]["left_vs_right"]
        assert paired["shared_columns"] == 1
        assert paired["shared_respondents"] == 5
        # Left is closer to the all-Yes human marginal, so its error is lower on the shared column.
        assert paired["soft_nominal"]["delta"] < 0
        # ...and C3 still does not pass, because there is no ordinal bucket to judge. The criterion
        # is "no worse in EACH bucket", so an unmeasured bucket is not a silent pass.
        assert paired["soft_ordinal"]["delta"] is None
        assert paired["c3_left_wins"] is False

    def test_c3_needs_every_bucket_to_favour_the_left_arm(self, tmp_path):
        """One bucket going the other way sinks it — the pre-registered conjunction, asserted.

        Left wins nominal and Brier and loses ordinal. Averaging the buckets would hide that; a
        conjunction cannot, which is why the verdict is written as one.
        """
        entries = _entries({PRICING_QID: (BINARY, False), CONSENSUS_QID: (SCALE, True)})
        humans_binary = ["Yes"] * 6
        humans_scale = [SCALE[3]] * 6

        def _arm(path, binary_vector, scale_vector, name):
            _write(path, _rows(PRICING_QID, BINARY, [binary_vector] * 6, humans_binary, name)
                   + _rows(CONSENSUS_QID, SCALE, [scale_vector] * 6, humans_scale, name))

        left, right = tmp_path / "l.jsonl", tmp_path / "r.jsonl"
        # Left: perfect on the binary column, slightly hedged on the scale.
        _arm(left, [1.0, 0.0], [0.0, 0.0, 0.2, 0.8], "left")
        # Right: backwards on the binary column, perfect on the scale.
        _arm(right, [0.0, 1.0], [0.0, 0.0, 0.0, 1.0], "right")

        paired = score_arms({"left": left, "right": right},
                            entries, 20, 1, 10)["paired"]["left_vs_right"]
        assert paired["soft_nominal"]["delta"] < 0
        assert paired["brier"]["delta"] < 0
        assert paired["soft_ordinal"]["delta"] > 0
        assert paired["c3_left_wins"] is False

    def test_the_paired_bootstrap_survives_arms_with_different_respondents(self, tmp_path):
        """Both arms index off ONE respondent ordering, so pick position j is the same person.

        `_restrict` drops a column left with fewer than two shared rows, which can take a
        respondent out of one arm only. Letting each arm sort its own respondents then draws picks
        against the left arm's length and applies them to a shorter right-arm index.
        """
        entries = _entries({PRICING_QID: (BINARY, False), CONSENSUS_QID: (BINARY, False)})
        left, right = tmp_path / "l.jsonl", tmp_path / "r.jsonl"
        _write(left, _rows(PRICING_QID, BINARY, [[0.9, 0.1]] * 6, ["Yes"] * 6, "left")
               + _rows(CONSENSUS_QID, BINARY, [[0.9, 0.1]] * 6, ["Yes"] * 6, "left"))

        def _cell(respid):
            return {"arm": "right", "respid": respid, "qid": CONSENSUS_QID,
                    "options": list(BINARY), "probs": {"Yes": 0.6, "No": 0.4},
                    "choice": "Yes", "human": "Yes"}

        # The right arm covers r0-r4 on the first column, and on the second covers only r5 plus an
        # r6 the left arm never had. Both of the second column's rows survive `build_columns`, but
        # only one of them is shared, so `_restrict` drops the column -- and r5 with it, leaving the
        # right arm one respondent shorter than the left.
        _write(right, _rows(PRICING_QID, BINARY, [[0.6, 0.4]] * 5, ["Yes"] * 5, "right")
               + [_cell("r5"), _cell("r6")])

        paired = score_arms({"left": left, "right": right},
                            entries, 30, 1, 10)["paired"]["left_vs_right"]
        assert paired["shared_respondents"] == 6
        # An interval exists at all, i.e. the resamples ran instead of the scorer dying on the
        # right arm's shorter index.
        assert paired["soft_nominal"]["delta_ci_low"] is not None
        assert paired["soft_nominal"]["delta"] < 0

    def test_repeat_measurements_of_one_respondent_all_ride_along(self):
        """A resample carries ALL of a picked respondent's rows, not an arbitrary one of them.

        `--repeat-tag` puts several cells on the same (respid, qid) and `build_columns` counts every
        one of them, so an index keeping one row per respondent would make the interval describe a
        different statistic than the point estimate printed beside it. The two repeats here disagree
        as far as they can -- one perfect, one backwards -- so keeping only the last would move the
        bootstrap off the true 1.0 to the backwards repeat's 2.0.
        """
        from scripts.twin2k.prob_scoring import _brier_statistic, bootstrap

        humans = ["Yes"] * 6
        rows = (_rows(PRICING_QID, BINARY, [[1.0, 0.0]] * 6, humans)        # repeat r1: perfect
                + _rows(PRICING_QID, BINARY, [[0.0, 1.0]] * 6, humans))     # repeat r2: backwards
        columns, _ = build_columns(rows, _entries({PRICING_QID: (BINARY, False)}))
        assert len(columns[PRICING_QID]["respids"]) == 12

        assert _brier_statistic(columns) == pytest.approx(1.0)
        interval = bootstrap(columns, _brier_statistic, 50, 1)
        # Every respondent carries both repeats, so every resample scores exactly 1.0.
        assert interval["mean"] == pytest.approx(1.0)
        assert interval["ci_low"] == pytest.approx(1.0)
        assert interval["ci_high"] == pytest.approx(1.0)


def _write(path: Path, rows: list) -> None:
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------
# Reading the interchange format
# --------------------------------------------------------------------------
@pytest.mark.unit
class TestInterchangeFormat:
    def test_resume_markers_are_not_scored(self, tmp_path):
        """`done` / `aborted` lines are bookkeeping. Scored as cells they would be silent garbage."""
        path = tmp_path / "in.jsonl"
        _write(path, _rows(PRICING_QID, BINARY, [[1.0, 0.0]] * 3, ["Yes"] * 3)
               + [{"arm": "test", "respid": "r9", "done": True, "n_cells": 3},
                  {"arm": "test", "respid": "r8", "aborted": True, "error": {"kind": "transient"}}])
        assert len(read_jsonl(path)) == 3

    def test_raw_sums_are_reported_and_never_repaired(self):
        """How far a vector is from summing to 1 is a finding, so the raw figure must survive."""
        rows = _rows(PRICING_QID, BINARY, [[0.6, 0.6], [0.3, 0.3]], ["Yes", "No"])
        columns, _ = build_columns(rows, _entries({PRICING_QID: (BINARY, False)}))
        report = raw_sum_report(columns)
        assert sorted(columns[PRICING_QID]["raw_sums"]) == [0.6, 1.2]
        assert report["mean"] == pytest.approx(0.9)
        assert report["share_within_1pct_of_1"] == pytest.approx(0.0)
        # ...while the vectors used for scoring ARE on the simplex.
        assert np.allclose(columns[PRICING_QID]["P"].sum(axis=1), 1.0)

    def test_a_hard_choice_arm_reports_no_raw_sums(self):
        rows = _rows(PRICING_QID, BINARY, [None, None], ["Yes", "No"])
        columns, _ = build_columns(rows, _entries({PRICING_QID: (BINARY, False)}))
        assert raw_sum_report(columns)["n_cells_with_vectors"] == 0

    @pytest.mark.parametrize("raw,expected", [
        ("1", "1"),            # already a label
        (1.0, "1"),            # pandas float64 on a numeric-coded column
        ("2.0", "2"),
        (2, "2"),
        ("1.5", "1.5"),        # not on the scale — kept, and counted as off-scale downstream
        ("Yes", "Yes"),
        ("", None), ("Error", None), ("LLM Error", None), ("nan", None), (None, None),
        (float("nan"), None),
    ])
    def test_match_option_rewrites_only_integral_floats(self, raw, expected):
        assert match_option(raw, ["1", "2"]) == expected

    def test_match_option_does_not_invent_a_label(self):
        """`"3.0"` is integral but not an option, so it stays unmatched rather than being clamped."""
        assert match_option("3.0", ["1", "2"]) == "3.0"

    def test_an_unscorable_human_label_is_counted_not_scored(self):
        rows = _rows(PRICING_QID, BINARY, [[1.0, 0.0]] * 3, ["Yes", "Maybe", "No"])
        columns, dropped = build_columns(rows, _entries({PRICING_QID: (BINARY, False)}))
        assert dropped["human_off_scale"] == 1
        assert len(columns[PRICING_QID]["y"]) == 2


# --------------------------------------------------------------------------
# Diagnostics
# --------------------------------------------------------------------------
@pytest.mark.unit
class TestDiagnostics:
    def test_the_entropy_ratio_flags_collapse(self):
        """Every twin giving the same answer where the humans split is the failure chaining targets."""
        humans = ["Yes"] * 5 + ["No"] * 5
        columns, _ = build_columns(_rows(PRICING_QID, BINARY, [[1.0, 0.0]] * 10, humans),
                                  _entries({PRICING_QID: (BINARY, False)}))
        report = fidelity(columns)
        assert report["entropy_ratio"]["all_tasks"] == pytest.approx(0.0)
        assert report["collapsed_columns"] == [PRICING_QID]

    def test_a_twin_matching_the_human_spread_has_ratio_one(self):
        humans = ["Yes"] * 5 + ["No"] * 5
        forecasts = [[0.9, 0.1]] * 5 + [[0.1, 0.9]] * 5
        columns, _ = build_columns(_rows(PRICING_QID, BINARY, forecasts, humans),
                                  _entries({PRICING_QID: (BINARY, False)}))
        report = fidelity(columns)
        assert report["entropy_ratio"]["all_tasks"] == pytest.approx(1.0)
        assert report["collapsed_columns"] == []

    def test_a_uniformly_hedged_column_still_counts_as_collapsed(self):
        """`collapsed_columns` is a statement about the COMMITTED answer, not the vector.

        A twin that says 50/50 for everyone has full entropy yet commits the same option for
        everyone under `argmax`, so the two diagnostics disagree here by design -- and that
        disagreement is the information. Pinned so nobody "fixes" one to match the other.
        """
        humans = ["Yes"] * 5 + ["No"] * 5
        columns, _ = build_columns(_rows(PRICING_QID, BINARY, [[0.5, 0.5]] * 10, humans),
                                  _entries({PRICING_QID: (BINARY, False)}))
        report = fidelity(columns)
        assert report["entropy_ratio"]["all_tasks"] == pytest.approx(1.0)
        assert report["collapsed_columns"] == [PRICING_QID]

    def test_framing_contrast_catches_a_twin_that_ignores_the_frame(self):
        """Per-arm fit cannot see this; a between-subject contrast can.

        Both arms are fitted perfectly *on average* by a twin that answers identically in both, yet
        the humans moved 40 points between frames and the twin moved 0. Sign agreement is the read.
        """
        entries = {
            "QID100": {"column": "QID100", "choices": {"1": "Yes", "2": "No"},
                       "ordered_scale": False, "condition_group": "Disease",
                       "condition_arm": "gain"},
            "QID101": {"column": "QID101", "choices": {"1": "Yes", "2": "No"},
                       "ordered_scale": False, "condition_group": "Disease",
                       "condition_arm": "loss"},
        }
        # Humans: 80% Yes under `gain`, 40% Yes under `loss`. Twin: 60% either way.
        gain = _rows("QID100", BINARY, [[0.6, 0.4]] * 10, ["Yes"] * 8 + ["No"] * 2)
        loss = _rows("QID101", BINARY, [[0.6, 0.4]] * 10, ["Yes"] * 4 + ["No"] * 6)
        columns, _ = build_columns(gain + loss, entries)
        contrast = framing_contrast(columns, entries)["Disease"]
        assert contrast["human_delta"] == pytest.approx(0.4)
        assert contrast["model_delta"] == pytest.approx(0.0)
        assert contrast["magnitude_ratio"] == pytest.approx(0.0)
        assert contrast["sign_agrees"] is False

    def test_framing_contrast_skips_a_group_it_cannot_difference(self):
        entries = {
            "QID100": {"column": "QID100", "choices": {"1": "Yes", "2": "No"},
                       "ordered_scale": False, "condition_group": "Disease",
                       "condition_arm": "gain"},
        }
        columns, _ = build_columns(_rows("QID100", BINARY, [[0.6, 0.4]] * 4, ["Yes"] * 4), entries)
        result = framing_contrast(columns, entries)
        assert "skipped" in result["Disease"]
        assert result["_summary"]["groups_compared"] == 0

    def test_repeat_agreement_measures_the_noise_floor(self):
        """Jev is not deterministic, so a JC-vs-BC margin below this figure is not a result."""
        from scripts.twin2k.prob_scoring import repeat_agreement

        entries = _entries({PRICING_QID: (BINARY, False)})
        rows = []
        for tag, vector in (("r1", [0.70, 0.30]), ("r2", [0.75, 0.25])):
            rows.append({"arm": "jev", "respid": "r0", "qid": PRICING_QID, "options": BINARY,
                         "probs": dict(zip(BINARY, vector)), "choice": "Yes", "human": "Yes",
                         "repeat_tag": tag, "order_salt": ""})
        report = repeat_agreement(rows, entries)
        assert report["('r1', '')|('r2', '')"]["mean_tvd"] == pytest.approx(0.05)
        assert report["('r1', '')|('r2', '')"]["n_cells"] == 1

    def test_repeat_agreement_is_empty_without_a_repeat(self):
        from scripts.twin2k.prob_scoring import repeat_agreement

        rows = _rows(PRICING_QID, BINARY, [[0.7, 0.3]] * 3, ["Yes"] * 3)
        assert repeat_agreement(rows, _entries({PRICING_QID: (BINARY, False)})) == {}


# --------------------------------------------------------------------------
# The verdict bands, fixed before any data
# --------------------------------------------------------------------------
@pytest.mark.unit
@pytest.mark.parametrize("ece,verdict", [
    (0.0, "PASS"), (0.05, "PASS"), (0.0500001, "MARGINAL"),
    (0.10, "MARGINAL"), (0.1000001, "FAIL"), (0.9, "FAIL"),
])
def test_the_c1_bands_are_the_preregistered_ones(ece, verdict):
    """0.05 / 0.10 with inclusive lower edges, written down before any Jev data existed."""
    assert _c1_verdict(ece).startswith(verdict)
