"""Tests for between-subject condition arms (Twin-2K-500's 13 randomized groups).

Twin's holdout carries 48 columns belonging to 13 between-subject groups — Asian disease
gain/loss, anchoring low/high, Linda with and without the conjunction item, and so on. Each
respondent saw ONE arm, so each twin must be asked one arm too: showing both would convert a
between-subject manipulation into a within-subject one and erase the effect being measured.

The arm is derived from which columns a respondent's own answer sheet FILLS — presence is the
randomization record Qualtrics left behind. Only presence is ever read, never answer content;
that boundary is what keeps this from being leakage, and it must not be generalized to
non-condition questions.

Half of these tests are about the OTHER surveys. The gate lives in `QuestionRouter`, which
every stateful walk goes through, and in main.py's stateless loop, which every stateless question
goes through — so "inert unless a question declares a `condition_group`" is the property that
has to hold.
"""

import importlib
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

from src.core.persona_cache import load_personas_from_excel
from src.core.question_router import QuestionRouter
from src.core.config_loader import FullSurveyConfig, RoutingRule, SkipIfRule
from src.data.preprocessors.twin2k import NUMERIC_LABEL_COLUMNS, cast_numeric_labels
from src.data.question_mapper import CONDITION_PREFIX, QuestionMapper
from src.data.respondent import Respondent
from src.validation.response_validator import MIN_N_FOR_GATING, ValidationResult
from src.validation.validation_pairs import replicate_ground_truth

from tests.unit.test_question_router import MockQuestionMapper

REPO_ROOT = Path(__file__).resolve().parents[2]
TWIN_QUESTION_MAPPING = REPO_ROOT / "configs" / "twin2k" / "twin2k_question_mapping.json"

# A two-group instrument: one 2-arm group, one plain question outside any group. Small enough
# to reason about, and it exercises both branches of every gate below.
_MAPPING = {
    "QID157": {"question": "gain frame", "type": "single", "column": "QID157",
               "choices": {"1": "A", "2": "B"},
               "condition_group": "Disease", "condition_arm": "gain"},
    "QID158": {"question": "loss frame", "type": "single", "column": "QID158",
               "choices": {"1": "A", "2": "B"},
               "condition_group": "Disease", "condition_arm": "loss"},
    "QID196": {"question": "marble tray", "type": "single", "column": "QID196",
               "choices": {"1": "Tray A", "2": "Tray B"}},
}

_CONDITION_FREE_MAPPING = {
    "MU1": {"question": "which package", "type": "single", "column": "MU1",
            "choices": {"1": "Premium", "2": "Basic"}},
}


def _mapper(tmp_path, question_mapping, name="questions.json") -> QuestionMapper:
    """A real QuestionMapper over an inline mapping — no fixture CSV needed."""
    demographics = tmp_path / "demographics.json"
    demographics.write_text(json.dumps({}), encoding="utf-8")
    questions = tmp_path / name
    questions.write_text(json.dumps(question_mapping), encoding="utf-8")
    return QuestionMapper(str(demographics), str(questions), data_format="text")


# --------------------------------------------------------------------------
# QuestionMapper.condition_assignments — presence -> arm
# --------------------------------------------------------------------------

@pytest.mark.unit
def test_condition_assignments_reads_the_arm_off_the_filled_column(tmp_path):
    mapper = _mapper(tmp_path, _MAPPING)
    assert mapper.condition_assignments({"QID157": "A", "QID196": "Tray B"}) == {
        CONDITION_PREFIX + "Disease": "gain"
    }
    assert mapper.condition_assignments({"QID158": "B", "QID196": "Tray A"}) == {
        CONDITION_PREFIX + "Disease": "loss"
    }


@pytest.mark.unit
def test_condition_assignments_is_empty_without_condition_groups(tmp_path):
    """Surveys with no between-subject design: no group is declared, nothing to gate on."""
    mapper = _mapper(tmp_path, _CONDITION_FREE_MAPPING)
    assert mapper.condition_assignments({"MU1": "Premium"}) == {}


@pytest.mark.unit
def test_condition_assignments_rejects_a_respondent_in_two_arms(tmp_path):
    """Both arms filled means the grouping disagrees with how Qualtrics randomized."""
    mapper = _mapper(tmp_path, _MAPPING)
    with pytest.raises(ValueError, match="2 arm"):
        mapper.condition_assignments({"QID157": "A", "QID158": "B"})


@pytest.mark.unit
def test_condition_assignments_rejects_a_group_with_no_arm_answered(tmp_path):
    """Silently returning {} here would gate EVERY arm off and lose the group entirely."""
    mapper = _mapper(tmp_path, _MAPPING)
    with pytest.raises(ValueError, match="0 arm"):
        mapper.condition_assignments({"QID196": "Tray A"})


@pytest.mark.unit
def test_respondent_names_itself_when_its_arms_are_inconsistent(tmp_path):
    """The mapper knows the group; only the Respondent knows which human it was."""
    mapper = _mapper(tmp_path, _MAPPING)
    with pytest.raises(ValueError, match="respondent r7"):
        Respondent({"respid": "r7", "QID157": "A", "QID158": "B"}, mapper)


@pytest.mark.unit
def test_respondent_exposes_the_assignment_for_the_persona(tmp_path):
    mapper = _mapper(tmp_path, _MAPPING)
    respondent = Respondent({"respid": "r1", "QID158": "B", "QID196": "Tray A"}, mapper)
    assert respondent.condition_assignments == {CONDITION_PREFIX + "Disease": "loss"}
    assert respondent.to_dict()["condition_assignments"] == respondent.condition_assignments


# --------------------------------------------------------------------------
# QuestionRouter.is_asked — the gate itself
# --------------------------------------------------------------------------

_CONDITIONS = {"QID157": ("Disease", "gain"), "QID158": ("Disease", "loss")}


@pytest.mark.unit
def test_is_asked_admits_only_the_assigned_arm():
    router = QuestionRouter(None, MockQuestionMapper({}, conditions=_CONDITIONS))
    state = {CONDITION_PREFIX + "Disease": "gain"}
    assert router.is_asked("QID157", state) is True
    assert router.is_asked("QID158", state) is False


@pytest.mark.unit
def test_is_asked_is_true_for_every_question_of_a_condition_free_mapping():
    """The regression guard for ungated surveys: the gate is inert, not branched around."""
    router = QuestionRouter(None, MockQuestionMapper({"Q1": [], "Q2": []}))
    assert all(router.is_asked(q, {}) for q in ["Q1", "Q2", "Q99"])


@pytest.mark.unit
def test_an_unassigned_group_gates_both_arms_off():
    """A persona whose state carries no assignment must not be shown either arm."""
    router = QuestionRouter(None, MockQuestionMapper({}, conditions=_CONDITIONS))
    assert not router.is_asked("QID157", {})
    assert not router.is_asked("QID158", {})


# --------------------------------------------------------------------------
# next_question — conditioning composed with the other routing rules
# --------------------------------------------------------------------------

@pytest.mark.unit
def test_next_question_walks_only_the_assigned_arm():
    router = QuestionRouter(None, MockQuestionMapper({}, conditions=_CONDITIONS))
    question_list = ["QID157", "QID158", "QID196"]

    state = {CONDITION_PREFIX + "Disease": "loss"}
    assert router.next_question(state, question_list) == "QID158"
    state["QID158"] = "B"
    assert router.next_question(state, question_list) == "QID196"
    state["QID196"] = "Tray A"
    assert router.next_question(state, question_list) is None


@pytest.mark.unit
def test_an_off_arm_question_does_not_fire_its_own_skip_if():
    """A question that was never shown must not route either.

    QID157 is gated off, and its own rule would have skipped the rest of the survey. The gate
    is checked BEFORE `skip_if` precisely so a question nobody saw cannot end the walk.
    """
    rules = [RoutingRule(
        question_id="QID157",
        skip_if=SkipIfRule(source_question="Q0", skip_on=["No"], skip_to="QID196"),
    )]
    router = QuestionRouter(rules, MockQuestionMapper({}, conditions=_CONDITIONS))
    state = {"Q0": "No", CONDITION_PREFIX + "Disease": "loss"}
    assert router.next_question(state, ["QID157", "QID158", "QID196"]) == "QID158"


@pytest.mark.unit
def test_a_skip_target_inside_a_condition_group_still_resolves():
    """Routing x conditioning: `question_list` stays shared, so `index(skip_to)` never raises.

    Per-persona filtering of `question_list` would have made this `skip_to` unresolvable —
    `next_question` returns None on that ValueError, silently ending the persona's survey with
    no error anywhere. Gating inside the router removes the failure mode entirely.
    """
    rules = [RoutingRule(
        question_id="Q1",
        skip_if=SkipIfRule(source_question="Q0", skip_on=["No"], skip_to="QID157"),
    )]
    router = QuestionRouter(rules, MockQuestionMapper({}, conditions=_CONDITIONS))
    # Assigned the OTHER arm: the walk lands on QID157, gates past it, and continues.
    state = {"Q0": "No", CONDITION_PREFIX + "Disease": "loss"}
    assert router.next_question(state, ["Q0", "Q1", "QID157", "QID158", "QID196"]) == "QID158"


# --------------------------------------------------------------------------
# The stateless panel: indices must land back on the full persona list
# --------------------------------------------------------------------------

def _persona(respid, arm, answer):
    return {
        "respid": respid,
        "demographics": {"age": "35-44"},
        "ground_truth": {"QID157": answer} if arm == "gain" else {"QID158": answer},
        "condition_assignments": {CONDITION_PREFIX + "Disease": arm},
    }


@pytest.mark.unit
def test_the_asked_panel_and_its_ground_truth_stay_aligned_after_the_lift():
    """The load-bearing step in main.py's stateless loop.

    `run_survey_for_question` receives only the asked personas and returns indices into THAT
    list, while the exporter and segmentation index the full `personas`. Ground truth is
    replicated over the asked panel (matching the runner's ordering) and the indices are lifted
    afterwards; getting either half wrong scores a persona against someone else's answer.
    """
    personas = [
        _persona("r0", "loss", "B"),
        _persona("r1", "gain", "A"),
        _persona("r2", "loss", "B"),
        _persona("r3", "gain", "B"),
    ]
    router = QuestionRouter(None, MockQuestionMapper({}, conditions=_CONDITIONS))

    asked_idx = [i for i, p in enumerate(personas)
                 if router.is_asked("QID157", p["condition_assignments"])]
    assert asked_idx == [1, 3]
    asked = [personas[i] for i in asked_idx]

    # What `_run_survey_multi_var` returns at n_variations=2: per persona, indices into `asked`.
    runner_indices = [0, 0, 1, 1]
    lifted = [asked_idx[j] for j in runner_indices]

    ground_truth = replicate_ground_truth(asked, "QID157", n_variations=2)
    assert ground_truth == ["A", "A", "B", "B"]
    assert [personas[i]["ground_truth"]["QID157"] for i in lifted] == ground_truth


@pytest.mark.unit
def test_the_asked_panel_stays_aligned_when_half_of_it_comes_from_a_checkpoint():
    """The same invariant across a resume, where the lift is no longer a single contiguous slice.

    On resume only the *pending* asked personas are re-asked, so the runner's indices point into
    `pending_idx`, not `asked_idx`. Merging in `asked_idx` order is what keeps the output ordering
    the "per persona, n_variations each" shape `replicate_ground_truth` assumes — here the
    checkpointed persona is the *later* one, so a positional (rather than respid) join of saved
    rows would score r1 against r3's answer.
    """
    from src.utils import survey_checkpoint as ckpt

    personas = [
        _persona("r0", "loss", "B"),
        _persona("r1", "gain", "A"),
        _persona("r2", "loss", "B"),
        _persona("r3", "gain", "B"),
    ]
    router = QuestionRouter(None, MockQuestionMapper({}, conditions=_CONDITIONS))
    asked_idx = [i for i, p in enumerate(personas)
                 if router.is_asked("QID157", p["condition_assignments"])]
    assert asked_idx == [1, 3]

    # r3 is already on disk; r1 is not, so only r1 is re-asked.
    saved = [{"respid": "r3", "response": "B", "explanation": "saved", "tier": None,
              "variation_id": v} for v in range(2)]
    done_respids = {"r3"}
    pending_idx = [i for i in asked_idx
                   if ckpt.norm_respid(personas[i]["respid"]) not in done_respids]
    assert pending_idx == [1]

    # main.py's merge: fresh rows joined positionally, saved rows by respid, then asked_idx order.
    fresh_persona_indices, fresh_responses = [0, 0], ["A", "A"]
    rows_by_persona = {}
    for k, pos in enumerate(fresh_persona_indices):
        rows_by_persona.setdefault(pending_idx[pos], []).append(
            {"respid": ckpt.norm_respid(personas[pending_idx[pos]]["respid"]),
             "response": fresh_responses[k], "variation_id": k}
        )
    saved_rows = {}
    for row in saved:
        saved_rows.setdefault(ckpt.norm_respid(row["respid"]), []).append(row)
    for i in asked_idx:
        if i not in rows_by_persona:
            rows_by_persona[i] = saved_rows[ckpt.norm_respid(personas[i]["respid"])]

    persona_indices, responses = [], []
    for i in asked_idx:
        for row in rows_by_persona[i]:
            persona_indices.append(i)
            responses.append(row["response"])

    assert persona_indices == [1, 1, 3, 3]
    ground_truth = replicate_ground_truth(
        [personas[i] for i in asked_idx], "QID157", n_variations=2
    )
    assert ground_truth == ["A", "A", "B", "B"]
    assert [personas[i]["ground_truth"]["QID157"] for i in persona_indices] == ground_truth
    assert responses == ground_truth


@pytest.mark.unit
def test_the_lift_is_the_identity_without_condition_groups():
    """Ungated regression: every persona is asked, so `asked_idx` is range(len(personas))."""
    personas = [{"condition_assignments": {}} for _ in range(4)]
    router = QuestionRouter(None, MockQuestionMapper({"MU1": []}))
    asked_idx = [i for i, p in enumerate(personas)
                 if router.is_asked("MU1", p["condition_assignments"])]
    assert asked_idx == [0, 1, 2, 3]


# --------------------------------------------------------------------------
# The persona cache — the second construction site
# --------------------------------------------------------------------------

@pytest.mark.unit
def test_a_cache_hit_carries_the_arm_assignments(tmp_path):
    """The cached sheet holds only demographics and the summary.

    Arm assignments are re-read from the live respondent, so a cache hit cannot silently drop
    them — which would gate every condition question off for the whole run.
    """
    mapper = _mapper(tmp_path, _MAPPING)
    respondents = [
        Respondent({"respid": "r1", "QID157": "A", "QID196": "Tray A"}, mapper),
        Respondent({"respid": "r2", "QID158": "B", "QID196": "Tray B"}, mapper),
    ]
    cache_path = tmp_path / "persona_cache.xlsx"
    pd.DataFrame([
        {"respid": "r1", "response_id": "r1", "screener_summary": "", "demo_age": "35-44"},
        {"respid": "r2", "response_id": "r2", "screener_summary": "", "demo_age": "45-54"},
    ]).to_excel(cache_path, sheet_name="Personas", index=False)

    personas = load_personas_from_excel(str(cache_path), respondents)
    assert [p["condition_assignments"] for p in personas] == [
        {CONDITION_PREFIX + "Disease": "gain"},
        {CONDITION_PREFIX + "Disease": "loss"},
    ]


# --------------------------------------------------------------------------
# The preprocessor cast: QID198's options are the integers 1 and 2
# --------------------------------------------------------------------------

@pytest.mark.unit
def test_numeric_labels_become_integral_strings():
    """`1.0` cannot match the option `'1'`; the canonicalizer stringifies before normalizing."""
    df = cast_numeric_labels(pd.DataFrame({"QID198_1": [1.0, 2.0, float("nan")]}))
    assert df["QID198_1"].tolist()[:2] == ["1", "2"]
    assert df["QID198_1"].tolist()[2] is None


@pytest.mark.unit
def test_a_fractional_cell_is_rejected_rather_than_truncated():
    with pytest.raises(RuntimeError, match="not whole numbers"):
        cast_numeric_labels(pd.DataFrame({"QID198_2": [1.5]}))


@pytest.mark.unit
def test_the_cast_is_inert_for_columns_it_does_not_name():
    """Every other survey, and every other Twin column, passes through untouched."""
    frame = pd.DataFrame({"MU1": [1.0, 2.5], "QID9_1": ["Yes", "No"]})
    assert cast_numeric_labels(frame).equals(frame)


# --------------------------------------------------------------------------
# min_n_for_gating — now per-survey, still 50 by default
# --------------------------------------------------------------------------

def _result(n, min_n_for_gating=None):
    """One question where every persona gives the same answer: entropy 0, so collapse-eligible."""
    kwargs = {} if min_n_for_gating is None else {"min_n_for_gating": min_n_for_gating}
    result = ValidationResult("Q1", "single", **kwargs)
    result.synthetic = ["A"] * n
    result.ground_truth = (["A"] * (n // 2)) + (["B"] * (n - n // 2))
    result.calculate_overall(all_options=["A", "B"], ordered_scale=False)
    return result


@pytest.mark.unit
def test_the_default_floor_is_the_module_constant():
    assert ValidationResult("Q1", "single").min_n_for_gating == MIN_N_FOR_GATING
    assert _result(MIN_N_FOR_GATING - 1).entropy_thin is True
    assert _result(MIN_N_FOR_GATING).entropy_thin is False
    # A total collapse at n >= the floor is still flagged, unchanged.
    assert _result(MIN_N_FOR_GATING).collapse is True


@pytest.mark.unit
def test_the_config_default_cannot_drift_from_the_module_constant():
    """`FullSurveyConfig` restates the 50 as a literal, so something has to hold them equal.

    It cannot import `MIN_N_FOR_GATING`: `src.core.config_loader` depends on nothing under
    `src.validation` today, and inverting that for one scalar costs more than this assertion.
    A survey that says nothing therefore scores exactly as it did before the key existed.
    """
    assert FullSurveyConfig.model_fields["min_n_for_gating"].default == MIN_N_FOR_GATING


@pytest.mark.unit
@pytest.mark.parametrize("config_path", sorted(
    p for p in REPO_ROOT.glob("configs/*/*survey_config*.yaml") if "twin2k" not in p.parts
))
def test_no_other_surveys_config_sets_the_floor(config_path):
    """Only twin2k may state a gating floor; every other survey takes the default.

    This repo ships only twin2k configs, so the parameter set is empty and pytest skips.
    Kept as a guard that fires if a config for another survey is ever added."""
    assert "min_n_for_gating" not in config_path.read_text(encoding="utf-8")


@pytest.mark.unit
def test_a_raised_floor_moves_both_thin_flags():
    """The honest use of the config key: report but do not flag a bigger thin band."""
    result = _result(MIN_N_FOR_GATING, min_n_for_gating=200)
    assert result.entropy_thin is True
    assert result.collapse is False       # suppressed, not recomputed
    assert result.kl_thin is True
    assert result.kl is None
    assert result.entropy_ratio is not None   # still REPORTED


@pytest.mark.unit
def test_every_segment_row_uses_the_same_floor_as_its_overall_row():
    """Two copies of the floor drifting apart is the bug the instance attribute prevents.

    n=20 is BELOW the default floor and above the lowered one, so the segment row can only
    come out un-thin if it inherited the instance's value rather than the module constant.
    """
    assert _result(20).kl_thin is True                      # default floor: thin
    result = _result(20, min_n_for_gating=10)
    assert result.kl_thin is False
    result.calculate_segments("age", ["35-44"] * 20)
    assert result.segment_results["age"]["35-44"]["kl_thin"] is False


# --------------------------------------------------------------------------
# The shipped Twin-2K-500 mapping
# --------------------------------------------------------------------------

@pytest.mark.unit
def test_the_shipped_mapping_tags_both_arms_of_every_condition_group():
    """48 columns, 13 groups, every group with >= 2 arms — the recovered scored set."""
    mapping = json.loads(TWIN_QUESTION_MAPPING.read_text(encoding="utf-8"))
    groups = {}
    for entry in mapping.values():
        group = entry.get("condition_group")
        if group is not None:
            groups.setdefault(group, set()).add(entry["condition_arm"])

    tagged = [e for e in mapping.values() if e.get("condition_group")]
    assert len(mapping) == 108
    assert len(tagged) == 48
    assert len(groups) == 13
    assert all(len(arms) >= 2 for arms in groups.values())
    # A tagged entry missing its arm would make `is_asked` compare against None and gate the
    # whole group off, so the pair is required together.
    assert all(e.get("condition_arm") for e in tagged)


@pytest.mark.unit
def test_no_other_survey_mapping_declares_a_condition_group():
    """A stray `condition_group` in an ungated survey would gate real questions off mid-run."""
    offenders = [
        path.name
        for path in sorted(REPO_ROOT.glob("configs/*/*question_mapping*.json"))
        if "twin2k" not in path.parts and "condition_group" in path.read_text(encoding="utf-8")
    ]
    assert not offenders


# --------------------------------------------------------------------------
# The generator's arm-aware completeness assertion
# --------------------------------------------------------------------------

@pytest.fixture(scope="module")
def generator():
    """`scripts/twin2k/build_twin2k_config.py` — the one place the grouping is hand-authored."""
    scripts_dir = REPO_ROOT / "scripts" / "twin2k"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    return importlib.import_module("build_twin2k_config")


def _condition_frame(rows):
    """One row per respondent; `None` means that column was not shown to them."""
    return pd.DataFrame([{"pid": pid, **cells} for pid, cells in rows])


@pytest.mark.unit
def test_the_assertion_accepts_exactly_one_arm_per_respondent(generator):
    df = _condition_frame([
        ("p1", {"QID157": "A", "QID158": None, "QID196": "Tray A"}),
        ("p2", {"QID157": None, "QID158": "B", "QID196": "Tray B"}),
    ])
    generator.assert_ground_truth_complete(_MAPPING, df)  # must not raise


@pytest.mark.unit
def test_the_assertion_rejects_a_respondent_in_two_arms(generator):
    """The failure `condition_assignments` would otherwise raise on mid-run."""
    df = _condition_frame([
        ("p1", {"QID157": "A", "QID158": "B", "QID196": "Tray A"}),
        ("p2", {"QID157": None, "QID158": "B", "QID196": "Tray B"}),
    ])
    with pytest.raises(RuntimeError, match="not exactly 1"):
        generator.assert_ground_truth_complete(_MAPPING, df)


@pytest.mark.unit
def test_the_assertion_rejects_a_respondent_in_no_arm(generator):
    df = _condition_frame([
        ("p1", {"QID157": None, "QID158": None, "QID196": "Tray A"}),
        ("p2", {"QID157": None, "QID158": "B", "QID196": "Tray B"}),
    ])
    with pytest.raises(RuntimeError, match="not exactly 1"):
        generator.assert_ground_truth_complete(_MAPPING, df)


@pytest.mark.unit
def test_the_assertion_rejects_a_partially_filled_arm(generator):
    """A half-filled arm would route a twin into questions with no ground truth."""
    mapping = {
        "QID159_1": {"question": "a", "type": "single", "column": "QID159_1",
                     "choices": {"1": "yes"},
                     "condition_group": "Linda", "condition_arm": "no_conjunction"},
        "QID159_2": {"question": "b", "type": "single", "column": "QID159_2",
                     "choices": {"1": "yes"},
                     "condition_group": "Linda", "condition_arm": "no_conjunction"},
        "QID160_1": {"question": "c", "type": "single", "column": "QID160_1",
                     "choices": {"1": "yes"},
                     "condition_group": "Linda", "condition_arm": "conjunction"},
    }
    df = _condition_frame([
        ("p1", {"QID159_1": "yes", "QID159_2": None, "QID160_1": None}),
        ("p2", {"QID159_1": None, "QID159_2": None, "QID160_1": "yes"}),
    ])
    with pytest.raises(RuntimeError, match="some but not all"):
        generator.assert_ground_truth_complete(mapping, df)


@pytest.mark.unit
def test_the_assertion_still_demands_a_full_panel_for_non_condition_columns(generator):
    """Unchanged for ordinary questions: a half-filled one silently shrinks n_valid."""
    df = _condition_frame([
        ("p1", {"QID157": "A", "QID158": None, "QID196": "Tray A"}),
        ("p2", {"QID157": None, "QID158": "B", "QID196": None}),
    ])
    with pytest.raises(RuntimeError, match=r"QID196: 1/2 filled"):
        generator.assert_ground_truth_complete(_MAPPING, df)


@pytest.mark.unit
def test_the_assertion_rejects_an_off_list_condition_answer(generator):
    """Same decode rule as everywhere else — this is what caught QID198's `1.0` cells."""
    df = _condition_frame([
        ("p1", {"QID157": "Z", "QID158": None, "QID196": "Tray A"}),
        ("p2", {"QID157": None, "QID158": "B", "QID196": "Tray B"}),
    ])
    with pytest.raises(RuntimeError, match="outside the option list"):
        generator.assert_ground_truth_complete(_MAPPING, df)


@pytest.mark.unit
def test_the_probability_matching_columns_are_the_ones_the_preprocessor_casts():
    """The cast list and the mapping must name the same columns.

    They are separate constants in separate modules; if the mapping ever scored a
    numeric-labelled column the cast does not cover, its ground truth would decode off-list.
    """
    mapping = json.loads(TWIN_QUESTION_MAPPING.read_text(encoding="utf-8"))
    numeric_labelled = {
        qid for qid, entry in mapping.items()
        if all(str(text).isdigit() for text in entry.get("choices", {}).values())
    }
    assert numeric_labelled == set(NUMERIC_LABEL_COLUMNS)
