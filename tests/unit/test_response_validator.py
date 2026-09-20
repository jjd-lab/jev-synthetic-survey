"""Unit tests for response_validator."""

import math

import pytest

from src.validation.response_validator import (
    COLLAPSE_RATIO_MAX,
    MIN_N_FOR_GATING,
    ValidationResult,
    calculate_phi_correlation,
    classify_metric_bucket,
    kl_and_blind_spot,
    mae_scale_steps,
    marginal_prevalence_distance,
    optionwise_entropy,
    setwise_entropy,
    total_variation_distance,
    validate_multi_choice,
    validate_single_choice,
    wasserstein_1_scale,
)


@pytest.mark.unit
class TestValidateSingleChoice:
    def test_exact_match(self):
        assert validate_single_choice("A", "A") is True

    def test_mismatch(self):
        assert validate_single_choice("A", "B") is False

    def test_error_response(self):
        assert validate_single_choice("Error", "A") is False

    def test_none_ground_truth(self):
        assert validate_single_choice("A", None) is False


@pytest.mark.unit
class TestValidateMultiChoice:
    def test_perfect_jaccard(self):
        assert validate_multi_choice(["a", "b"], ["a", "b"]) == 1.0

    def test_partial_jaccard(self):
        assert validate_multi_choice(["a", "b"], ["b", "c"]) == pytest.approx(1 / 3)

    def test_empty_returns_zero(self):
        assert validate_multi_choice([], ["a"]) == 0.0


@pytest.mark.unit
class TestDistributionalMetrics:
    def test_tvd_identical(self):
        dist = {"A": 0.5, "B": 0.5}
        assert total_variation_distance(dist, dist, ["A", "B"]) == 0.0

    def test_tvd_maximally_different(self):
        assert total_variation_distance({"A": 1.0}, {"B": 1.0}, ["A", "B"]) == 1.0

    def test_mae_scale_steps(self):
        opts = ["low", "mid", "high"]
        assert mae_scale_steps(["low", "high"], ["low", "mid"], opts) == 0.5

    def test_wasserstein_identical(self):
        opts = ["a", "b", "c"]
        assert wasserstein_1_scale(["a", "b"], ["a", "b"], opts) == 0.0

    def test_marginal_prevalence_distance(self):
        syn = [["a", "b"], ["a"]]
        gt = [["a", "b"], ["b"]]
        assert marginal_prevalence_distance(syn, gt, ["a", "b"]) == pytest.approx(0.5)

    def test_classify_metric_bucket(self):
        assert classify_metric_bucket("single", ordered_scale=True) == "ordinal"
        assert classify_metric_bucket("single", ordered_scale=False) == "nominal"
        assert classify_metric_bucket("multi") == "multi"

    # ── KL divergence + blind-spot ────────────────────────────────────────
    def test_kl_nominal_identical(self):
        pct = {"A": 0.5, "B": 0.3, "C": 0.2}
        r = kl_and_blind_spot(pct, pct, ["A", "B", "C"], bucket="nominal", n=100)
        assert r["kl"] == pytest.approx(0.0, abs=0.01)
        assert r["blind_spot"] is False
        assert r["kl_thin"] is False

    def test_kl_nominal_blind_spot_detected(self):
        pct_h = {"A": 0.78, "B": 0.22}
        pct_l = {"A": 1.00, "B": 0.00}
        r = kl_and_blind_spot(pct_h, pct_l, ["A", "B"], bucket="nominal", n=100)
        assert r["blind_spot"] is True
        assert r["blind_spot_worst"] == pytest.approx(0.22)
        assert r["kl"] > 1.0

    def test_kl_nominal_no_blind_spot(self):
        pct_h = {"A": 0.6, "B": 0.4}
        pct_l = {"A": 0.55, "B": 0.45}
        r = kl_and_blind_spot(pct_h, pct_l, ["A", "B"], bucket="nominal", n=100)
        assert r["blind_spot"] is False
        assert r["kl"] < 0.1

    def test_kl_ordinal_returns_none_but_the_flag_is_still_computed(self):
        # Wire through ValidationResult so we test the full integration path. `blind_spot` used to be
        # None here too, and that was the defect: the flag is order-free, so excluding it along with
        # KL left ordinal — the worst bucket — with no coverage signal at all.
        vr = ValidationResult("q_test", "single")
        vr.synthetic    = ["A"] * 60 + ["B"] * 40
        vr.ground_truth = ["A"] * 55 + ["B"] * 45
        vr.calculate_overall(all_options=["A", "B"], ordered_scale=True)
        assert vr.kl is None
        assert vr.blind_spot is False, "the LLM used both options humans used — a real all-clear"
        assert vr.kl_thin is False, "and not a thin-n exclusion, which would also give kl=None"

    def test_kl_multi_identical(self):
        pct = {"A": 0.8, "B": 0.5, "C": 0.3}
        r = kl_and_blind_spot(pct, pct, ["A", "B", "C"], bucket="multi", n=100)
        assert r["kl"] == pytest.approx(0.0, abs=0.01)
        assert r["blind_spot"] is False

    def test_kl_multi_blind_spot_detected(self):
        pct_h = {"A": 0.78, "B": 0.22, "C": 0.10}
        pct_l = {"A": 0.95, "B": 0.00, "C": 0.50}
        r = kl_and_blind_spot(pct_h, pct_l, ["A", "B", "C"], bucket="multi", n=100)
        assert r["blind_spot"] is True
        assert r["blind_spot_worst"] == pytest.approx(0.22)

    def test_kl_thin_guardrail(self):
        pct_h = {"A": 0.6, "B": 0.4}
        pct_l = {"A": 1.0, "B": 0.0}
        r = kl_and_blind_spot(pct_h, pct_l, ["A", "B"], bucket="nominal", n=10)
        assert r["kl"] is None
        assert r["blind_spot"] is None
        assert r["kl_thin"] is True

    def test_kl_llm_covered_nothing_is_a_blind_spot_not_an_all_clear(self):
        # The maximal coverage gap: zero LLM mass on every option humans used. `False` here
        # would read as an all-clear at kl_thin=False, i.e. affirmatively scored and clean.
        r = kl_and_blind_spot({"A": 0.78, "B": 0.22, "C": 0.004}, {}, ["A", "B", "C"],
                              bucket="nominal", n=100)
        assert r["blind_spot"] is True
        assert r["blind_spot_worst"] == pytest.approx(0.78)
        assert r["kl"] is None
        assert r["kl_thin"] is False
        # This path names its options separately from the general one, so it gets the ordering and
        # the >= 5% filter asserted separately too: `C` is under the human floor and is not "missed".
        assert r["blind_spot_options"] == ["A", "B"]

    def test_kl_no_human_mass_makes_no_coverage_claim(self):
        # Mirror case: nothing on the human side, so there is no blind spot to assert.
        r = kl_and_blind_spot({}, {"A": 0.6, "B": 0.4}, ["A", "B"],
                              bucket="nominal", n=100)
        assert r["blind_spot"] is False
        assert r["blind_spot_worst"] == 0.0
        assert r["kl"] is None

    def test_kl_empty_multi_selections_flag_a_blind_spot(self):
        # Reachable on a stateless multi run: `require_selection=False` makes an empty
        # `choices` list schema-legal, and it is not the "Error" sentinel, so it survives
        # _filter_valid_pairs and contributes no mass to any option.
        vr = ValidationResult("q_test", "multi")
        vr.synthetic    = [[] for _ in range(60)]
        vr.ground_truth = [["A"] if i % 3 else ["B"] for i in range(60)]
        vr.calculate_overall(all_options=["A", "B"])
        assert vr.blind_spot is True
        assert vr.kl_thin is False
        assert vr.entropy_ratio == 0.0  # entropy independently reports the collapse

    def test_ordinal_carries_the_flag_and_never_kl(self):
        # The two halves of this function need different things from the scale and only KL needs
        # ordering: the flag asks whether the LLM ever produced an answer humans used. Excluding
        # both cost the worst bucket its coverage signal: 18 of the reference run's 22 gate-eligible
        # ordinal questions carry a blind spot, and 4 of G9's 9 failures are ordinal.
        r = kl_and_blind_spot({"Very": 0.4, "Somewhat": 0.3, "Not at all": 0.3},
                              {"Very": 0.7, "Somewhat": 0.3},
                              ["Very", "Somewhat", "Not at all"], bucket="ordinal", n=100)
        assert r["blind_spot"] is True
        assert r["blind_spot_worst"] == pytest.approx(0.3)
        assert r["blind_spot_options"] == ["Not at all"]
        assert r["kl"] is None, "KL would treat ordered scale points as unordered labels; W1 is the"\
                               " ordinal metric precisely because ordering matters"
        assert r["kl_thin"] is False, "None kl here is by design, not a thin-n exclusion"

    def test_missed_options_are_named_worst_first(self):
        # A collapse ratio explains itself; a blind spot does not until you know which answer went
        # missing — an abandoned end of a scale and an unpicked middle option are different defects.
        r = kl_and_blind_spot({"A": 0.5, "B": 0.2, "C": 0.3}, {"A": 1.0},
                              ["A", "B", "C"], bucket="nominal", n=100)
        assert r["blind_spot_options"] == ["C", "B"]
        assert r["blind_spot_worst"] == pytest.approx(0.3)


@pytest.mark.unit
class TestValidationResult:
    def test_single_nominal_metrics(self):
        result = ValidationResult("MU1", "single")
        result.synthetic = ["A", "A", "B"]
        result.ground_truth = ["A", "B", "B"]
        result.calculate_overall(all_options=["A", "B"])
        assert result.n_valid == 3
        assert result.individual_baseline == pytest.approx(2 / 3)
        assert result.distributional_metric_name == "tvd"

    def test_ordinal_uses_mae_baseline(self):
        result = ValidationResult("Q5", "single")
        opts = ["1", "2", "3"]
        result.synthetic = ["1", "3"]
        result.ground_truth = ["1", "2"]
        result.calculate_overall(all_options=opts, ordered_scale=True)
        assert result.metric_bucket == "ordinal"
        assert result.individual_baseline == 0.5
        assert result.distributional_metric_name == "wasserstein_1"

    def test_multi_agreement_rate(self):
        result = ValidationResult("MU2", "multi")
        result.synthetic = [["a", "b"], ["a"]]
        result.ground_truth = [["a", "b"], ["a", "b"]]
        result.calculate_overall(all_options=["a", "b", "c"])
        assert result.individual_baseline == pytest.approx(0.75)
        assert result.distributional_metric_name == "marginal_prevalence_mad"

    def test_error_exclusion(self):
        result = ValidationResult("MU1", "single")
        result.synthetic = ["A", "Error", "B"]
        result.ground_truth = ["A", "X", "B"]
        result.calculate_overall()
        assert result.n_valid == 2
        assert result.n_failed == 1

    def test_multi_error_exclusion(self):
        result = ValidationResult("MU2", "multi")
        result.synthetic = [["a"], ["Error"], ["b"]]
        result.ground_truth = [["a"], ["x"], ["b"]]
        result.calculate_overall()
        assert result.n_valid == 2
        assert result.n_failed == 1

    def test_calculate_segments_aligned(self):
        result = ValidationResult("MU1", "single")
        result.synthetic = ["A", "B", "A", "B", "C", "C"]
        result.ground_truth = ["A", "B", "B", "B", "C", "D"]
        result.calculate_overall(all_options=["A", "B", "C"])
        seg = ["18-24", "18-24", "25-34", "25-34", "35-44", "35-44"]
        result.calculate_segments("age", seg)
        assert sum(s["n"] for s in result.segment_results["age"].values()) == 6
        assert "distributional_metric" in next(iter(result.segment_results["age"].values()))

    def test_calculate_segments_misaligned_raises(self):
        result = ValidationResult("MU1", "single")
        result.synthetic = ["A", "B"]
        result.ground_truth = ["A", "B"]
        with pytest.raises(ValueError, match="segment_values length"):
            result.calculate_segments("age", ["18-24"])


@pytest.mark.unit
class TestEntropy:
    """The diagnostic the distributional metric is blind to: a run can match the human option
    distribution well while every persona answers identically. Ported here from
    the predecessor project when the formulas moved out of its report module: that module and
    a second scorer each kept a copy and the two diverged."""

    def test_uniform_hits_the_log2k_ceiling(self):
        h, ceiling = optionwise_entropy({"percentages": {k: 0.25 for k in "ABCD"}}, 4)
        assert h == pytest.approx(2.0)
        assert ceiling == pytest.approx(2.0), "log2(4) — H equals its own ceiling when uniform"
        h3, ceiling3 = optionwise_entropy({"percentages": {k: 1 / 3 for k in "ABC"}}, 3)
        assert h3 == pytest.approx(math.log2(3)) == pytest.approx(ceiling3)

    def test_total_collapse_is_positive_zero_not_negative_zero(self):
        """`-sum(p*log2 p)` over a single p=1.0 yields -0.0, which prints as `-0.000`.

        Not cosmetic: a total collapse — the exact case the G3 gate exists to catch — would read as
        *negative* entropy, and any downstream ratio inherits the sign.
        """
        h, _ = optionwise_entropy({"percentages": {"Yes": 1.0}}, 3)
        assert h == 0.0
        assert math.copysign(1.0, h) > 0, "a collapsed distribution must be +0.0, not -0.0"

    def test_zero_probability_options_contribute_nothing(self):
        h, _ = optionwise_entropy(
            {"percentages": {"A": 0.5, "B": 0.5, "C": 0.0, "D": 0.0}}, 4
        )
        assert h == pytest.approx(1.0)

    def test_streaming_counterexample_metric_likes_a_collapsed_question(self):
        """The case that justifies the gate: TVD 0.227 (8th best of 40) at H(syn) = 0.

        Human mass is 77% on one option, so snapping 100% onto it is only 0.227 of total-variation
        distance away — a metric-only gate calls this a good question.
        """
        human, _ = optionwise_entropy(
            {"percentages": {"Yes": 0.773, "No": 0.118, "DK": 0.109}}, 3
        )
        synthetic, _ = optionwise_entropy({"percentages": {"Yes": 1.0}}, 3)
        assert human == pytest.approx(0.999, abs=1e-3)
        assert synthetic == 0.0
        assert synthetic - human == pytest.approx(-0.999, abs=1e-3)

    def test_collapse_ratio_catches_what_the_raw_gap_misses(self):
        """Why G3 gates on `H_syn/H_hum`, not on the raw gap.

        A 3-option question with 77% human mass has less entropy available to lose, so no raw-gap
        cut tight enough to be selective catches it — the scale-free ratio catches every collapse.
        """
        h_human, _ = optionwise_entropy(
            {"percentages": {"Yes": 0.773, "No": 0.118, "DK": 0.109}}, 3
        )
        h_syn, _ = optionwise_entropy({"percentages": {"Yes": 1.0}}, 3)
        assert h_syn - h_human > -1.0, "the raw-gap threshold provably fails on this question"
        assert h_syn / h_human <= COLLAPSE_RATIO_MAX

    def test_setwise_counts_answer_sets_not_options(self):
        """Multi-select entropy is over answer *sets*: order must not create outcomes."""
        h, _, n_distinct, top_share = setwise_entropy(
            [["A", "B"], ["B", "A"], ["A", "B"], ["C"]], 3
        )
        assert n_distinct == 2, "{A,B} and {B,A} are one outcome"
        assert top_share == pytest.approx(0.75)
        assert h == pytest.approx(-(0.75 * math.log2(0.75) + 0.25 * math.log2(0.25)))

    def test_setwise_ceiling_is_log2_n_not_log2_k(self):
        """All-distinct sets → H = log2 n, well above log2 K. This is why setwise and optionwise
        gaps are never averaged: they are bounded by different quantities."""
        responses = [["A"], ["B"], ["C"], ["A", "B"], ["A", "C"], ["B", "C"], ["A", "B", "C"]]
        h, ceiling, n_distinct, _ = setwise_entropy(responses, 3)
        assert n_distinct == 7
        assert h == pytest.approx(math.log2(7))
        assert h > math.log2(3), "setwise entropy exceeds the optionwise log2 K ceiling"
        assert ceiling == pytest.approx(math.log2(7)), "min(log2 7 responses, log2(2^3-1) sets)"

    def test_setwise_ceiling_depends_only_on_n_and_k_not_on_any_response(self):
        """Regression on a real bug: the ceiling was `2 ** len(responses[0])` — two raised to the
        number of boxes *the first row of the spreadsheet* happened to tick.

        4 people, 3 options, all four answers distinct, so H is maximal for 4 people. The buggy
        form yields normalized_h = 2.0 (200% of maximum) when row 0 ticked one box, and 1.0 when it
        ticked two — from the same panel in a different row order. Measured consequence before the
        fix: `overdispersion_flag` (normalized_h > 0.85) fired on 15 of 16 multi questions.
        """
        order_1 = [["A"], ["B"], ["C"], ["A", "B"]]
        order_2 = [["A", "B"], ["A"], ["B"], ["C"]]

        h1, ceiling1, _, _ = setwise_entropy(order_1, 3)
        h2, ceiling2, _, _ = setwise_entropy(order_2, 3)

        assert h1 == h2 == pytest.approx(2.0)
        assert ceiling1 == ceiling2, "row order must not move the ceiling"
        assert ceiling1 == pytest.approx(2.0), "min(log2 4 people, log2(2^3-1) possible sets)"
        assert h1 / ceiling1 == pytest.approx(1.0), "normalized_h must land in [0, 1], not at 2.0"

        # What the bug computed, kept explicit so restoring it fails here rather than silently.
        buggy = min(math.log2(len(order_1)), math.log2(2 ** len(order_1[0])))
        assert buggy == pytest.approx(1.0) and h1 / buggy == pytest.approx(2.0)

    def test_multi_result_uses_setwise_and_may_exceed_log2k(self):
        """`entropy_kind` is not decoration: it proves the marginals path wasn't used. Marginal
        inclusion rates sum to mean-k, not 1, so an "entropy" over them is not an entropy at all —
        and set-wise H can exceed the option-wise log2 K ceiling, as it does here."""
        result = ValidationResult("MU1", "multi")
        result.synthetic = [["A"], ["B"], ["A", "B"], ["A", "B", "C"], ["C"], ["B", "C"]]
        result.ground_truth = [["A"], ["A"], ["A"], ["A"], ["A"], ["A"]]
        result.calculate_overall(all_options=["A", "B", "C"])

        assert result.entropy_kind == "setwise"
        assert result.h_syn == pytest.approx(math.log2(6), abs=1e-4)
        assert result.h_syn > math.log2(3), "set-wise H exceeds the option-wise ceiling"
        assert result.n_sets_syn == 6 and result.n_sets_hum == 1
        assert result.h_hum == 0.0, "unanimous humans"
        assert result.entropy_ratio is None, "H_hum == 0 leaves the ratio undefined, not 0.0"
        assert result.collapse is False, "an undefined ratio must not gate"

    def test_undefined_ratio_is_none_not_zero(self):
        """`H_hum == 0` makes the ratio undefined. Reporting 0.0 would silently trip the collapse
        gate on a question where the *humans* were unanimous — it cannot lose entropy it never
        had."""
        unanimous = ValidationResult("Q1", "single")
        unanimous.synthetic = ["Yes"] * 60
        unanimous.ground_truth = ["Yes"] * 60
        unanimous.calculate_overall(all_options=["Yes", "No"])
        assert unanimous.h_hum == 0.0
        assert unanimous.entropy_ratio is None
        assert unanimous.collapse is False, "an undefined ratio must not gate"

        collapsed = ValidationResult("Q2", "single")
        collapsed.synthetic = ["Yes"] * 60
        collapsed.ground_truth = ["Yes"] * 30 + ["No"] * 30
        collapsed.calculate_overall(all_options=["Yes", "No"])
        assert collapsed.h_hum == pytest.approx(1.0)
        assert collapsed.entropy_ratio == 0.0
        assert collapsed.collapse is True

    def test_thin_question_reports_entropy_but_never_gates(self):
        """The other reason a ratio may not gate: too few respondents for it to mean anything. Same
        numbers, same crossed threshold, suppressed flag: a real case, one question scoring on 6 rows,
        where H_syn = 0 over 6 draws is sampling noise, not diversity collapse."""
        n = MIN_N_FOR_GATING - 1
        thin = ValidationResult("Q3", "single")
        thin.synthetic = ["Yes"] * n
        thin.ground_truth = (["Yes"] * (n // 2)) + (["No"] * (n - n // 2))
        thin.calculate_overall(all_options=["Yes", "No"])

        assert thin.entropy_thin is True
        assert thin.entropy_ratio == 0.0, "still reported"
        assert thin.entropy_ratio <= COLLAPSE_RATIO_MAX, "the threshold is crossed"
        assert thin.collapse is False, "n, not the ratio, is what suppresses this one"

    def test_open_ended_is_skipped_entirely(self):
        """Entropy over free text is log2(n) by construction — it measures string uniqueness, not
        response diversity. Left as None rather than reported as a large meaningless number."""
        result = ValidationResult("Q26", "open_ended")
        result.synthetic = ["a unique sentence", "another one", "a third"]
        result.ground_truth = ["human text", "more human text", "yet more"]
        result.calculate_overall(all_options=[])
        assert result.metric_bucket == "open_ended"
        assert result.h_syn is None and result.entropy_kind is None

    def test_segments_carry_the_entropy_pair(self):
        """Per-segment entropy exists because the distributional metric is blind to it.

        Both segments below score TVD 0.5 — the same number — yet "young" is a total collapse
        (every persona answered A while its humans split) and "old" matches its humans' spread
        exactly. Entropy is the only column that separates them.
        """
        result = ValidationResult("Q1", "single")
        result.synthetic = ["A", "A", "A", "A"] + ["A", "A", "A", "B"]
        result.ground_truth = ["A", "A", "B", "B"] + ["A", "B", "B", "B"]
        result.calculate_overall(all_options=["A", "B"])
        result.calculate_segments("age", ["young"] * 4 + ["old"] * 4)

        young = result.segment_results["age"]["young"]
        old = result.segment_results["age"]["old"]

        # The premise: the metric already on these sheets cannot tell the two apart.
        assert young["distributional_metric"] == old["distributional_metric"] == 0.5

        assert young["h_syn"] == 0.0, "every persona answered A"
        assert young["h_hum"] == pytest.approx(1.0), "its humans split evenly"
        assert young["entropy_ratio"] == 0.0, "total collapse, invisible to TVD 0.5"
        assert old["entropy_ratio"] == pytest.approx(1.0), "spread matches its humans"

        assert "collapse" not in young, "segment n is below the gating cut; no flag is emitted"

    def test_segment_entropy_matches_the_bucket_of_its_question(self):
        """Segments must not disagree with the overall row about which entropy applies — the whole
        reason the dispatch is one shared function."""
        result = ValidationResult("MU1", "multi")
        result.synthetic = [["a"], ["a", "b"], ["a"], ["b", "c"]]
        result.ground_truth = [["a"], ["a"], ["b"], ["b", "c"]]
        result.calculate_overall(all_options=["a", "b", "c"])
        result.calculate_segments("age", ["young", "young", "old", "old"])

        assert result.entropy_kind == "setwise"
        for stats in result.segment_results["age"].values():
            # Set-wise H over 2 respondents is at most log2(2) = 1.0; a marginals-based number
            # would not be bounded that way.
            assert 0.0 <= stats["h_syn"] <= 1.0
            assert stats["h_syn"] is not None and stats["h_hum"] is not None

    def test_open_ended_segments_omit_entropy_without_failing(self):
        """`entropy_pair_for_bucket` returns {} for open_ended, so the segment row carries None
        rather than raising or inventing a number."""
        result = ValidationResult("Q26", "open_ended")
        result.synthetic = ["some text", "other text"]
        result.ground_truth = ["human text", "more human text"]
        result.calculate_overall(all_options=[])
        result.calculate_segments("age", ["young", "old"])

        for stats in result.segment_results["age"].values():
            assert stats["h_syn"] is None and stats["entropy_ratio"] is None

    def test_no_valid_pairs_leaves_entropy_defined(self):
        """`calculate_overall` early-returns at n_valid == 0; the entropy fields must not be left
        stale from __init__ in that branch."""
        result = ValidationResult("Q4", "single")
        result.synthetic = ["Error"]
        result.ground_truth = ["Yes"]
        result.calculate_overall(all_options=["Yes", "No"])
        assert result.n_valid == 0
        assert result.h_syn == 0.0 and result.h_hum == 0.0
        assert result.entropy_ratio is None
        assert result.collapse is False


@pytest.mark.unit
class TestPhiCorrelation:
    def test_never_select_reports_insufficient_variance(self):
        corr = calculate_phi_correlation(
            ["A", "A"], ["A", "A"], ["A", "B"], "single"
        )
        assert corr["B"]["correlation"] is None
        assert corr["B"]["interpretation"] == "Insufficient variance"

    def test_insufficient_variance(self):
        corr = calculate_phi_correlation(
            ["A", "A", "A"], ["A", "A", "A"], ["A", "B"], "single"
        )
        assert corr["B"]["interpretation"] == "Insufficient variance"
