"""Tests for the last 140 Twin-2K-500 prior-answer columns: 84 checkboxes and 56 free texts.

Both were previously skipped by selector, for two different reasons, so they get two different
mechanisms and two different failure modes to guard:

  84 `MAVR`/`MAHR` checkbox columns — a checked box stores the option's OWN LABEL and an
  unchecked one stores `NaN`, so an identity `choices` map decodes them through the ordinary
  single-choice branch. They must NOT acquire `is_multi_select`, whose `== 1` test belongs to
  the coded format Twin never produces. Silent failure mode: an unchecked cell rendering
  `A: nan`, which would tell the model the respondent endorsed a statement they skipped.

  56 `SL`/`ML`/`FORM` free-text columns — no option list exists, so they carry `free_text: true`
  and the runtime renders the cell verbatim. Silent failure mode: the flag being keyed on
  "choices is empty" instead, which would capture grid screeners the moment
  branch order changed. The inertness pin below is what holds that shut.

The last test is the one to read first if a future mapping breaks: it asserts no shipped
mapping outside Twin depends on the new branch at all.
"""

import importlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.data.question_mapper import QuestionMapper

REPO_ROOT = Path(__file__).resolve().parents[2]
PERSONA_MAPPING = REPO_ROOT / "configs" / "twin2k" / "twin2k_demographic_mapping_persona.json"

# Real QIDs, so `_battery_tag` finds their hand-written tags: a Beck Depression Inventory group
# (empty stem — the tag is the only place its instruction can come from) and a thought listing.
_CHECKBOX_QID = "QID126"
_FORM_QID = "QID271"


@pytest.fixture(scope="module")
def generator():
    """`scripts/twin2k/build_twin2k_persona.py` — where the rendering rule is authored."""
    scripts_dir = REPO_ROOT / "scripts" / "twin2k"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    return importlib.import_module("build_twin2k_persona")


@pytest.fixture(scope="module")
def shipped_mapping():
    return json.loads(PERSONA_MAPPING.read_text(encoding="utf-8"))


def _checkbox(options, question_id=_CHECKBOX_QID, selector="MAVR"):
    """A catalog entry shaped like a checkbox battery: one csv column per option."""
    return {
        question_id: {
            "QuestionID": question_id,
            "QuestionType": "MC",
            "Settings": {"Selector": selector},
            "QuestionText": "",
            "Options": list(options),
            "csv_columns": [f"{question_id}_{i}" for i in range(1, len(options) + 1)],
        }
    }


def _free_text(question_id, selector, rows=(), n_columns=1, stem="Describe yourself."):
    """A catalog entry shaped like a free-text question or a battery of text boxes."""
    columns = (
        [f"{question_id}_{i}" for i in range(1, len(rows) + 1)]
        if rows else [f"{question_id}_TEXT"] * n_columns
    )
    return {
        question_id: {
            "QuestionID": question_id,
            "QuestionType": "TE",
            "Settings": {"Selector": selector},
            "QuestionText": stem,
            "Rows": list(rows),
            "csv_columns": columns,
        }
    }


# --------------------------------------------------------------------------
# Checkbox batteries decode as ordinary single-column screeners
# --------------------------------------------------------------------------

@pytest.mark.unit
def test_every_checkbox_column_gets_the_whole_option_list(generator):
    """Column<->option alignment is deliberately irrelevant: `fit_to_csv` narrows each column.

    Unlike a price list, a checked box stores the option's own label, so handing every column
    the full list cannot render the wrong option — there is nothing to get backwards.
    """
    options = ["I don't feel sad", "I feel sad", "I am sad all the time"]
    entries, skipped, tagged = generator.candidate_entries(
        _checkbox(options), excluded=set()
    )

    assert set(entries) == {f"{_CHECKBOX_QID}_{i}" for i in (1, 2, 3)}
    for entry in entries.values():
        assert entry["type"] == "screener"
        assert entry["choices"] == {option: option for option in options}
        assert "free_text" not in entry
    assert tagged == {_CHECKBOX_QID}
    assert skipped == {"excluded": 0}


@pytest.mark.unit
def test_a_checkbox_battery_is_tagged_not_stemmed(generator):
    """The 20 BDI groups have an EMPTY stem, so a fallback to `stem` renders no question."""
    entries, _, _ = generator.candidate_entries(_checkbox(["I feel sad"]), excluded=set())

    assert entries[f"{_CHECKBOX_QID}_1"]["question"] == generator.BATTERY_TAGS[_CHECKBOX_QID]
    assert entries[f"{_CHECKBOX_QID}_1"]["question"].strip()


@pytest.mark.unit
def test_an_untagged_checkbox_battery_is_fatal(generator):
    with pytest.raises(SystemExit, match="BATTERY_TAGS"):
        generator.candidate_entries(
            _checkbox(["I feel sad"], question_id="QID99999"), excluded=set()
        )


@pytest.mark.unit
def test_fit_to_csv_narrows_a_checkbox_column_to_the_box_it_holds(generator):
    """The whole option list goes in; only the value that column actually stores comes out."""
    options = ["I don't feel sad", "I feel sad"]
    entries = {
        "QID126_2": {"question": "tag", "type": "screener",
                     "choices": {option: option for option in options}}
    }
    df = pd.DataFrame({"QID126_2": ["I feel sad", np.nan, "I feel sad"]})

    kept, dropped, answered = generator.fit_to_csv(entries, df)

    assert kept["QID126_2"]["choices"] == {"I feel sad": "I feel sad"}
    assert not dropped and answered == 2


@pytest.mark.unit
def test_an_unchecked_box_never_reaches_the_prompt():
    """`NaN` must be skipped silently: rendering it would invent an endorsement."""
    mapping = {
        "QID126_1": {"question": "tag", "type": "screener",
                     "choices": {"I feel sad": "I feel sad"}},
        "QID126_2": {"question": "tag", "type": "screener",
                     "choices": {"I am sad all the time": "I am sad all the time"}},
    }
    mapper = QuestionMapper.__new__(QuestionMapper)
    mapper.demographic_mapping = mapping

    profile = mapper.extract_screener_profile({"QID126_1": "I feel sad", "QID126_2": np.nan})

    assert set(profile) == {"QID126_1"}
    assert profile["QID126_1"]["answer"] == "I feel sad"


# --------------------------------------------------------------------------
# Free text renders the cell as written
# --------------------------------------------------------------------------

@pytest.mark.unit
def test_a_standalone_free_text_question_keeps_its_stem(generator):
    """For `SL`/`ML` the stem IS the question — one column, nothing to disambiguate."""
    entries, _, tagged = generator.candidate_entries(
        _free_text("QID53", "SL", stem="A bat and ball cost $1.10 ..."), excluded=set()
    )

    entry = entries["QID53_TEXT"]
    assert entry == {"question": "A bat and ball cost $1.10 ...", "type": "screener",
                     "free_text": True}
    assert "choices" not in entry
    assert not tagged  # a standalone question needs no tag


@pytest.mark.unit
def test_a_free_text_battery_is_tagged_and_numbered_by_its_row(generator):
    """The stem repeats once per box, so the tag carries it and the row label numbers the box."""
    entries, _, tagged = generator.candidate_entries(
        _free_text(_FORM_QID, "FORM", rows=["Thought 1", "Thought 2"]), excluded=set()
    )

    tag = generator.BATTERY_TAGS[_FORM_QID]
    assert entries[f"{_FORM_QID}_1"]["question"] == f"{tag} — Thought 1"
    assert entries[f"{_FORM_QID}_2"]["question"] == f"{tag} — Thought 2"
    assert tagged == {_FORM_QID}


@pytest.mark.unit
def test_fit_to_csv_carries_free_text_through_with_no_decode_map(generator):
    """No option list means no decode rate: a filled cell is by definition readable."""
    entries = {"QID268_TEXT": {"question": "q", "type": "screener", "free_text": True}}
    df = pd.DataFrame({"QID268_TEXT": ["I aspire to be kind", np.nan, "hardworking"]})

    kept, dropped, answered = generator.fit_to_csv(entries, df)

    assert kept["QID268_TEXT"] == entries["QID268_TEXT"]
    assert "choices" not in kept["QID268_TEXT"]
    assert not dropped and answered == 2


@pytest.mark.unit
def test_an_empty_free_text_column_is_still_dropped(generator):
    """`MIN_DECODE_RATE` is skipped, but a column nobody answered is still dead weight."""
    entries = {"QID268_TEXT": {"question": "q", "type": "screener", "free_text": True}}

    kept, dropped, _ = generator.fit_to_csv(
        entries, pd.DataFrame({"QID268_TEXT": [np.nan, np.nan]})
    )

    assert not kept
    assert dropped == [("QID268_TEXT", 0.0, 0, "no answers in the CSV")]


@pytest.mark.unit
def test_the_free_text_branch_renders_a_number_without_its_float_tail():
    """A cognitive-test answer pandas reads as `27.0` must reach the prompt as `27`."""
    mapper = QuestionMapper.__new__(QuestionMapper)
    mapper.demographic_mapping = {
        "QID50_TEXT": {"question": "How much does the ball cost?", "type": "screener",
                       "free_text": True},
        "QID51_TEXT": {"question": "How many days?", "type": "screener", "free_text": True},
    }

    profile = mapper.extract_screener_profile({"QID50_TEXT": 27.0, "QID51_TEXT": np.nan})

    assert profile["QID50_TEXT"]["answer"] == "27"
    assert "QID51_TEXT" not in profile


# --------------------------------------------------------------------------
# Every selector has a branch
# --------------------------------------------------------------------------

@pytest.mark.unit
def test_an_unhandled_selector_is_fatal_rather_than_skipped(generator):
    """The regression this replaces: columns silently vanishing from the persona."""
    catalog = _checkbox(["a", "b"], selector="SomeNewSelector")

    with pytest.raises(SystemExit, match="unhandled selector"):
        generator.candidate_entries(catalog, excluded=set())


@pytest.mark.unit
def test_a_column_less_block_is_not_mistaken_for_an_unhandled_selector(generator):
    """Descriptive `DB` blocks carry no csv columns, so they contribute nothing and must pass."""
    catalog = {
        "QID127": {
            "QuestionID": "QID127",
            "QuestionType": "DB",
            "Settings": {"Selector": "TB"},
            "QuestionText": "This page contains groups of statements ...",
            "csv_columns": [],
        }
    }
    entries, _, tagged = generator.candidate_entries(catalog, excluded=set())
    assert not entries and not tagged


# --------------------------------------------------------------------------
# Generator -> runtime, on the shipped artifact
# --------------------------------------------------------------------------

@pytest.mark.unit
def test_the_shipped_persona_carries_the_whole_non_holdout_record(shipped_mapping):
    """620 prior-answer columns = 760 response columns - 126 holdout - 14 demographics."""
    screeners = {
        qid: config for qid, config in shipped_mapping.items()
        if config.get("type") == "screener"
    }
    assert len(screeners) == 620
    assert sum(1 for c in screeners.values() if c.get("free_text")) == 56


@pytest.mark.unit
def test_the_shipped_checkbox_columns_render_only_checked_boxes(generator, shipped_mapping):
    """84 columns, one per option; the ones the respondent left blank must not appear."""
    tags = {generator.BATTERY_TAGS[qid] for qid in ["QID126", "QID221"]}
    checkboxes = {
        qid: config for qid, config in shipped_mapping.items()
        if config.get("question") in tags
    }
    assert len(checkboxes) == 84

    mapper = QuestionMapper.__new__(QuestionMapper)
    mapper.demographic_mapping = shipped_mapping
    # Check every second box, leave the rest blank, exactly as a real row does.
    row = {
        qid: (next(iter(config["choices"])) if index % 2 == 0 else np.nan)
        for index, (qid, config) in enumerate(sorted(checkboxes.items()))
    }
    profile = mapper.extract_screener_profile(row)

    assert set(profile) == {qid for qid, value in row.items() if isinstance(value, str)}
    assert not {entry["answer"] for entry in profile.values()} & {"nan", "", None}


@pytest.mark.unit
def test_the_shipped_free_text_columns_render_verbatim(shipped_mapping):
    free_text = {
        qid: config for qid, config in shipped_mapping.items() if config.get("free_text")
    }
    assert not any("choices" in config for config in free_text.values())

    mapper = QuestionMapper.__new__(QuestionMapper)
    mapper.demographic_mapping = shipped_mapping
    profile = mapper.extract_screener_profile(
        {qid: f"answer to {qid}" for qid in free_text}
    )

    assert set(profile) == set(free_text)
    assert all(entry["answer"] == f"answer to {qid}" for qid, entry in profile.items())


# --------------------------------------------------------------------------
# Inert for every other mapping
# --------------------------------------------------------------------------

@pytest.mark.unit
def test_no_shipped_screener_reaches_the_free_text_branch_by_accident():
    """The pin on branch order: `free_text` is an explicit flag, never "choices is empty".

    Grid screeners DO have empty `choices`, so a mapping that
    depended on emptiness would change meaning the moment the branches were reordered. Every
    screener in every shipped mapping must therefore be classifiable without that test.
    """
    unclassified = []
    for path in REPO_ROOT.glob("configs/*/*.json"):
        mapping = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(mapping, dict):
            continue
        for qid, config in mapping.items():
            if not isinstance(config, dict) or config.get("type") != "screener":
                continue
            classified = (
                config.get("is_grid")
                or config.get("is_multi_select")
                or config.get("free_text")
                or config.get("choices")
            )
            if not classified:
                unclassified.append(f"{path.name}:{qid}")

    assert not unclassified


@pytest.mark.unit
def test_free_text_screeners_exist_only_in_the_twin_prior_answer_mapping():
    """No other survey may start depending on the new branch without this test noticing."""
    carriers = sorted(
        path.name
        for path in REPO_ROOT.glob("configs/*/*.json")
        if '"free_text"' in path.read_text(encoding="utf-8")
    )
    assert carriers == [PERSONA_MAPPING.name]
