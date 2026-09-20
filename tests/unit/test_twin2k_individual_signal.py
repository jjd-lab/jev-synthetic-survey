"""Tests for the individual-signal scorer in `scripts/twin2k/individual_signal.py`.

Same hazard as its sibling `test_twin2k_paper_accuracy.py`: every way of getting a correlation wrong
returns a plausible number between -1 and 1. The specific ways here:

  * mapping labels to positions with the wrong order silently INVERTS the sign on ordinal columns;
  * scoring a collapsed column as rho=0 reads as "no individual signal" when the truth is "no signal
    is measurable" — and 20 of the 108 columns are in that state, so 0s would drag the mean down;
  * omitting the price control reports +0.30 on pricing where the persona-attributable part is +0.05,
    i.e. it reports the confound as the finding.
"""

import importlib
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

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

# The nonseparability block's 7-point scale — wide enough to hold a 4-level control plus a 4-way
# offset without clipping, which is what makes the partial-correlation fixture below exact.
SCALE_7 = {
    "choices": {str(index + 1): f"point {index + 1}" for index in range(7)},
    "ordered_scale": True,
    "column": "QID288_1",
}


@pytest.fixture(scope="module")
def signal():
    """Import the script by path — `scripts/` is not a package."""
    scripts_dir = REPO_ROOT / "scripts" / "twin2k"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    return importlib.import_module("individual_signal")


def _frame(synthetic, ground_truth, question_id="QID287_1"):
    return pd.DataFrame(
        {f"{question_id}_synthetic": synthetic, f"{question_id}_ground_truth": ground_truth}
    )


def test_perfect_rank_agreement_is_one(signal):
    labels = list(SCALE_5["choices"].values()) * 12  # 60 rows, above the n floor
    result = signal.column_correlation(_frame(labels, labels), "QID287_1", SCALE_5)
    assert result["rho"] == pytest.approx(1.0)
    assert result["n"] == 60


def test_reversed_ranks_are_minus_one(signal):
    labels = list(SCALE_5["choices"].values()) * 12
    result = signal.column_correlation(_frame(labels, labels[::-1]), "QID287_1", SCALE_5)
    assert result["rho"] == pytest.approx(-1.0)


def test_a_collapsed_twin_has_no_correlation_rather_than_zero(signal):
    """One answer for every respondent has no variance, so no correlation EXISTS. Reporting 0 would
    claim the twin was measured and found signal-free; the run has 10 such columns and pushing 0s
    into the mean would understate the columns that were actually measurable."""
    human = list(SCALE_5["choices"].values()) * 12
    result = signal.column_correlation(_frame(["Somewhat support"] * 60, human), "QID287_1", SCALE_5)
    assert result["rho"] is None
    assert result["reason"] == "twin collapsed"


def test_a_thin_column_is_refused_before_the_variance_check(signal):
    """The 48 between-subject columns split the panel; a correlation on a handful of respondents is
    noise, and `thin` has to be reported instead of a number so it can't be read as a result."""
    labels = list(SCALE_5["choices"].values()) * 2  # 10 rows, below MIN_N_FOR_CORRELATION
    result = signal.column_correlation(_frame(labels, labels), "QID287_1", SCALE_5)
    assert result["rho"] is None
    assert result["reason"] == "thin"


def test_error_and_off_list_cells_drop_out(signal):
    """`Error` cells and labels outside the option list have no scale position; they must reduce `n`
    rather than map to a position and bend the correlation."""
    labels = list(SCALE_5["choices"].values()) * 12
    synthetic = ["Error", "Mildly supportive"] + labels[2:]
    result = signal.column_correlation(_frame(synthetic, labels), "QID287_1", SCALE_5)
    assert result["n"] == 58


def test_the_control_removes_a_purely_shared_driver(signal):
    """Twin and human are independent GIVEN the price and share nothing else, so the whole +0.49 raw
    correlation is the price and the persona-attributable partial is 0. This is the pricing block's
    shape — 40 of 108 columns where an uncontrolled rho credits the persona for the twin reading the
    stem. Constructed by fully crossing the two offsets within each price level, which makes the
    conditional independence exact rather than approximate."""
    options = list(SCALE_7["choices"].values())
    price, synthetic, ground_truth = [], [], []
    for level in range(4):
        for twin_offset in range(4):
            for human_offset in range(4):
                price.append(level)
                synthetic.append(options[level + twin_offset])
                ground_truth.append(options[level + human_offset])
    frame = _frame(synthetic, ground_truth, "QID288_1")
    result = signal.column_correlation(
        frame, "QID288_1", SCALE_7, pd.Series(price, index=frame.index)
    )
    assert result["rho"] == pytest.approx(0.492, abs=0.005)
    assert result["partial"] == pytest.approx(0.0, abs=0.001)


def test_the_control_leaves_an_unconfounded_column_alone(signal):
    """A control the answers don't track must not move the partial — otherwise the price control
    would quietly deflate the 68 non-pricing columns too."""
    labels = list(SCALE_5["choices"].values()) * 12
    frame = _frame(labels, labels)
    control = pd.Series([7] * 30 + [8] * 30, index=frame.index)
    result = signal.column_correlation(frame, "QID287_1", SCALE_5, control)
    assert result["partial"] == pytest.approx(result["rho"], abs=0.05)


def test_uncontrolled_columns_fall_back_to_raw_rho_in_the_task_mean(tmp_path, signal):
    """`partials` has to stay the same length as `rhos`: if only pricing contributed to it, the
    'controlled' headline would be an average over the one confounded task instead of all of them."""
    frame = _frame(
        list(SCALE_5["choices"].values()) * 12, list(SCALE_5["choices"].values()) * 12
    )
    frame["respid"] = [f"r{index}" for index in range(len(frame))]
    details = tmp_path / "respondent_details_test.xlsx"
    frame.to_excel(details, index=False)

    per_task = signal.correlations_per_task(details, {"QID287_1": SCALE_5})
    task = per_task["False consensus"]
    assert task["partials"] == task["rhos"] == [pytest.approx(1.0)]


def test_an_inapplicable_metric_is_none_rather_than_zero(tmp_path, signal):
    """`kl` is blank on every ordinal column by construction, and averaging blanks as 0.000 would
    report the most confident possible distributional agreement exactly where nothing was measured.
    Entropy and blind spot are averaged over the same group, so they must not inherit that."""
    summary = pd.DataFrame({
        "question_id": ["QID287_1", "QID288_1"],
        "metric_bucket": ["ordinal", "ordinal"],
        "distributional_metric": [0.4, 0.6],
        "individual_baseline": [1.0, 1.2],
        "collapse": [False, True],
        "entropy_ratio": [0.8, 0.6],
        "kl": [None, None],
        "blind_spot": [True, False],
        "blind_spot_worst": [0.1, 0.0],
    })
    summary_path = tmp_path / "validation_summary_test.xlsx"
    summary.to_excel(summary_path, index=False)

    rows = signal.distributional_per_task(summary_path, {"QID287_1": SCALE_5, "QID288_1": SCALE_7})
    # Both fixtures land in their own task, so read the one that carries the blind spot.
    row = rows[("False consensus", "ordinal")]
    assert row["kl"] is None
    assert row["blind_spots"] == 1
    assert row["entropy_ratio"] == pytest.approx(0.8)
    assert signal._fmt(None, 7) == f"{'-':>7}"
