"""Tests for rendering Twin-2K-500's 158 `Bipolar` economic-preference price lists.

A price-list cell stores only the code `'1'` or `'2'`. Which option that stands for lives in
the row label, which the catalog writes as `'LEFT:RIGHT'`, so the persona is only informative
if the generator splits that label and maps the code back to the option text. Everything here
guards that one seam:

  catalog row `'Lottery:$2.50'`  ->  choices `{'1': 'Lottery', '2': '$2.50'}`
                                ->  a cell of `1` renders `A: Lottery`

Two failure modes are silent rather than loud, which is why they get their own tests: a
`choices` map rebuilt from its own KEYS restores `A: 1` (the prompt reads as noise but nothing
raises), and a label split the wrong way renders the option the respondent did NOT choose (the
prompt reads fine and is backwards). The generator therefore raises on anything it cannot split
unambiguously, instead of skipping the row.

The last two tests are about the OTHER surveys: the value-preserving change lives in a
Twin-only generator, and any other survey must be provably out of its reach.
"""

import importlib
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

from src.data.question_mapper import QuestionMapper

REPO_ROOT = Path(__file__).resolve().parents[2]
PERSONA_MAPPING = REPO_ROOT / "configs" / "twin2k" / "twin2k_demographic_mapping_persona.json"

# One QID that really is a price list, so `_battery_tag` finds its hand-written tag. Using a
# real one keeps the fixture honest: an entry the tag table does not cover must raise, and
# that is asserted separately below.
_TAGGED_QID = "QID250"


@pytest.fixture(scope="module")
def generator():
    """`scripts/twin2k/build_twin2k_persona.py` — where the rendering rule is authored."""
    scripts_dir = REPO_ROOT / "scripts" / "twin2k"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    return importlib.import_module("build_twin2k_persona")


def _price_list(rows, question_id=_TAGGED_QID, columns=("1", "2")):
    """A catalog entry shaped like a `Bipolar` battery, one csv column per row."""
    return {
        question_id: {
            "QuestionID": question_id,
            "QuestionType": "Matrix",
            "Settings": {"Selector": "Bipolar"},
            "QuestionText": "In this question, the LOTTERY is a 50% chance ...",
            "Rows": list(rows),
            "Columns": list(columns),
            "csv_columns": [f"{question_id}_{i}" for i in range(1, len(rows) + 1)],
        }
    }


# Splitting the row label

@pytest.mark.unit
def test_a_row_label_becomes_the_two_options_it_offers(generator):
    entries, skipped, tagged = generator.candidate_entries(
        _price_list(["Lottery:$2.50", "$6.00 in 6 weeks:$3.00 in 5 weeks"]), excluded=set()
    )

    assert entries[f"{_TAGGED_QID}_1"]["choices"] == {"1": "Lottery", "2": "$2.50"}
    assert entries[f"{_TAGGED_QID}_2"]["choices"] == {
        "1": "$6.00 in 6 weeks",
        "2": "$3.00 in 5 weeks",
    }
    assert tagged == {_TAGGED_QID}
    assert skipped == {"excluded": 0}


@pytest.mark.unit
def test_the_question_carries_the_tag_and_both_sides(generator):
    """Both sides must appear: 'Lottery' alone does not say what was on offer."""
    entries, _, _ = generator.candidate_entries(_price_list(["Lottery:$2.50"]), excluded=set())

    question = entries[f"{_TAGGED_QID}_1"]["question"]
    assert generator.BATTERY_TAGS[_TAGGED_QID] in question
    assert "Lottery" in question and "$2.50" in question
    assert entries[f"{_TAGGED_QID}_1"]["type"] == "screener"


@pytest.mark.unit
def test_surrounding_space_is_stripped_from_each_side(generator):
    entries, _, _ = generator.candidate_entries(
        _price_list(["Lottery : $2.50"]), excluded=set()
    )
    assert entries[f"{_TAGGED_QID}_1"]["choices"] == {"1": "Lottery", "2": "$2.50"}


@pytest.mark.unit
@pytest.mark.parametrize("label", ["Lottery", "a:b:c", ":$2.50", "Lottery:"])
def test_a_label_that_does_not_split_cleanly_is_fatal(generator, label):
    """Skipping instead would be worse: `'a:b:c'` has no defensible left/right."""
    with pytest.raises(SystemExit, match="LEFT:RIGHT"):
        generator.candidate_entries(_price_list([label]), excluded=set())


@pytest.mark.unit
def test_a_scale_other_than_1_2_is_fatal(generator):
    """`1 = left` is an assumption about `Columns`, so it is checked rather than assumed."""
    with pytest.raises(SystemExit, match="Columns"):
        generator.candidate_entries(
            _price_list(["Lottery:$2.50"], columns=("A", "B")), excluded=set()
        )


@pytest.mark.unit
def test_an_untagged_price_list_is_fatal(generator):
    """A new battery must get a tag: without it the two 'Lottery' sides are ambiguous."""
    with pytest.raises(SystemExit, match="BATTERY_TAGS"):
        generator.candidate_entries(
            _price_list(["Lottery:$2.50"], question_id="QID99999"), excluded=set()
        )


@pytest.mark.unit
def test_excluded_columns_are_counted_and_contribute_nothing(generator):
    """The holdout filter must apply to price lists exactly as it does to Likert rows."""
    catalog = _price_list(["Lottery:$2.50", "Lottery:$3.00"])
    entries, skipped, _ = generator.candidate_entries(
        catalog, excluded={f"{_TAGGED_QID}_1"}
    )

    assert set(entries) == {f"{_TAGGED_QID}_2"}
    assert skipped["excluded"] == 1


@pytest.mark.unit
def test_a_fully_excluded_battery_leaves_no_tag_behind(generator):
    """`tagged` feeds the stale-key assert in `main`, so it must reflect real contributions."""
    entries, skipped, tagged = generator.candidate_entries(
        _price_list(["Lottery:$2.50"]), excluded={f"{_TAGGED_QID}_1"}
    )
    assert not entries and not tagged and skipped["excluded"] == 1


# Carrying the option text through the decode check

@pytest.mark.unit
def test_fit_to_csv_preserves_a_non_identity_answer_text(generator):
    """The regression that would silently restore `A: 1` for all 158 columns."""
    entries = {"QID250_1": {"question": "q", "type": "screener",
                            "choices": {"1": "Lottery", "2": "$2.50"}}}
    df = pd.DataFrame({"QID250_1": [1, 2, 1]})

    kept, dropped, answered = generator.fit_to_csv(entries, df)

    assert kept["QID250_1"]["choices"] == {"1": "Lottery", "2": "$2.50"}
    assert not dropped and answered == 3


@pytest.mark.unit
def test_fit_to_csv_keeps_only_the_codes_the_csv_actually_holds(generator):
    """Same rule as every other entry: the emitted key is the CSV's own spelling."""
    entries = {"QID250_1": {"question": "q", "type": "screener",
                            "choices": {"1": "Lottery", "2": "$2.50"}}}
    kept, _, _ = generator.fit_to_csv(entries, pd.DataFrame({"QID250_1": [1, 1]}))

    assert kept["QID250_1"]["choices"] == {"1": "Lottery"}


@pytest.mark.unit
def test_fit_to_csv_is_unchanged_for_identity_maps(generator):
    """Every pre-existing entry is an identity map; `.items()` must not move them."""
    entries = {"QID26_1": {"question": "q", "type": "screener",
                           "choices": generator._identity_choices(["Agree", "Disagree"])}}
    kept, dropped, _ = generator.fit_to_csv(
        entries, pd.DataFrame({"QID26_1": ["Agree", "Disagree"]})
    )

    assert kept["QID26_1"]["choices"] == {"Agree": "Agree", "Disagree": "Disagree"}
    assert not dropped


# Generator -> runtime, on the shipped artifact

@pytest.mark.unit
def test_the_shipped_persona_renders_options_not_codes():
    """The property that matters: a stored code reaches the prompt as its option text.

    Runs the real `extract_screener_profile` over the checked-in mapping, so a stale artifact
    or a change to `_normalize_choice_value` fails here rather than 9,000 calls into a run.
    """
    mapping = json.loads(PERSONA_MAPPING.read_text(encoding="utf-8"))
    price_lists = {
        qid: config for qid, config in mapping.items()
        if set(config.get("choices") or {}) == {"1", "2"}
        and set(config["choices"].values()) != {"1", "2"}
    }
    assert len(price_lists) == 158

    mapper = QuestionMapper.__new__(QuestionMapper)
    mapper.demographic_mapping = mapping
    profile = mapper.extract_screener_profile({qid: 1 for qid in price_lists})

    assert len(profile) == 158
    rendered = {entry["answer"] for entry in profile.values()}
    assert not rendered & {"1", "2", "nan", None}
    # `1` is the LEFT side, so every answer here is the option the label names first.
    for qid, config in price_lists.items():
        assert profile[qid]["answer"] == config["choices"]["1"]


# Inert for surveys that declare no price lists

@pytest.mark.unit
def test_no_other_survey_reads_the_prior_answer_persona():
    """Only the `_prior_answers` arm may point at the mapping this change regenerates.

    Other surveys and the other Twin arms keep their own `demographic_mapping`, so
    growing this file by 158 entries cannot move their prompts.
    """
    readers = sorted(
        path.name
        for path in REPO_ROOT.glob("configs/*/*.yaml")
        if PERSONA_MAPPING.name in path.read_text(encoding="utf-8")
    )
    assert readers == ["twin2k_survey_config_prior_answers.yaml"]


@pytest.mark.unit
def test_price_list_rendering_stays_inside_the_twin_generator():
    """`Bipolar` is a Twin catalog selector; no shared module may learn about it."""
    offenders = [
        str(path.relative_to(REPO_ROOT))
        for path in REPO_ROOT.glob("src/**/*.py")
        if "Bipolar" in path.read_text(encoding="utf-8")
    ]
    assert not offenders


@pytest.mark.unit
def test_every_shipped_config_is_a_public_twin_config():
    """The Jev probe sends prompts OUTSIDE any provider, on a personal key, so what may be sent is
    a property of the whole repo and not only of the probe.

    Twin-2K-500 is CC BY 4.0 and cleared for that. Stated as a POSITIVE invariant on purpose:
    the obvious form of this test enumerates the configs that must not reach the endpoint, which
    in a repo containing none of them passes by matching nothing. This one fails the moment a
    config for any other survey is added, which is the event actually worth catching.
    """
    configs = sorted(REPO_ROOT.glob("configs/**/*.yaml")) + sorted(REPO_ROOT.glob("configs/**/*.json"))
    assert configs, "no configs found -- the glob is wrong, not the repo"
    strays = sorted(
        str(p.relative_to(REPO_ROOT)) for p in configs
        if p.parent != REPO_ROOT / "configs" / "twin2k"
    )
    assert not strays, (
        f"configs outside configs/twin2k/: {strays}. Only Twin-2K-500 (CC BY 4.0) is cleared to "
        f"reach the TypeSafe endpoint; anything else needs its own licensing decision first."
    )

@pytest.mark.unit
def test_the_jev_transport_refuses_any_host_but_typesafe():
    """`--endpoint` must not be usable as an exfiltration flag."""
    from scripts.twin2k.jev_client import ENDPOINT, check_endpoint_is_typesafe

    check_endpoint_is_typesafe(ENDPOINT)
    for hostile in (
        "https://api.typesafe.ai.evil.example/v1/systemone",
        "http://localhost:8000/v1/systemone",
        "https://evil.example/?x=https://api.typesafe.ai",
    ):
        with pytest.raises(SystemExit, match="refusing"):
            check_endpoint_is_typesafe(hostile)
