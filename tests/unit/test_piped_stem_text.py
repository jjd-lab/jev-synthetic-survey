"""Tests for per-respondent piped question text (Twin-2K-500's randomized pricing price).

Twin's pricing block randomizes its price per respondent, so `question_catalog.json` holds
one arbitrary draw that only 0.757% of respondents saw. The mapping therefore carries
`{stem_value}` and the price is substituted per persona at run time.

Half of these tests are about the OTHER surveys: the substitution has to be inert unless the
stem actually carries the token, which is the property `_fill_stem` is pinned on below.
"""

import json
from pathlib import Path

import pandas as pd
import pytest

from src.core.survey_runner_excel import (
    STEM_VALUE_TOKEN,
    _fill_stem,
)
from src.data.preprocessors.twin2k import preprocess
from src.data.respondent import Respondent

REPO_ROOT = Path(__file__).resolve().parents[2]
TWIN_QUESTION_MAPPING = REPO_ROOT / "configs" / "twin2k" / "twin2k_question_mapping.json"

PRICED_STEM = f"The product is priced at: ${STEM_VALUE_TOKEN}. Would you purchase it?"
PLAIN_STEM = "Which tray would you prefer to select a marble from?"


class _StubMapper:
    """Minimal QuestionMapper stand-in: Respondent only calls these four."""

    def extract_demographics(self, row):
        return {"age": row.get("age", "35-44")}

    def extract_screener_profile(self, row):
        return {}

    def extract_ground_truth(self, row):
        return {}

    def condition_assignments(self, ground_truth):
        return {}


def _persona(respid, stem_values=None):
    return {
        "respid": respid,
        "demographics": {"age": "35-44"},
        "screener_profile": {},
        "stem_values": stem_values or {},
    }


# _fill_stem

@pytest.mark.unit
def test_fill_stem_substitutes_the_respondents_own_value():
    filled = _fill_stem(PRICED_STEM, _persona("r1", {"QID9_1": "8.45"}), "QID9_1")
    assert filled == "The product is priced at: $8.45. Would you purchase it?"
    assert STEM_VALUE_TOKEN not in filled


@pytest.mark.unit
def test_fill_stem_is_identity_without_the_token():
    """The no-token path: no token means the persona is never even consulted."""
    assert _fill_stem(PLAIN_STEM, _persona("r1"), "QID196") == PLAIN_STEM
    # Populated stem_values must still not perturb a stem that has no token.
    assert _fill_stem(PLAIN_STEM, _persona("r1", {"QID196": "9.99"}), "QID196") == PLAIN_STEM
    # Nor must a missing question_id, which is what every non-Twin caller passes.
    assert _fill_stem(PLAIN_STEM, _persona("r1"), None) == PLAIN_STEM


@pytest.mark.unit
def test_fill_stem_raises_when_the_token_cannot_be_filled():
    """A stem promising a piped value must never reach the model with the token intact."""
    with pytest.raises(KeyError, match="QID9_1"):
        _fill_stem(PRICED_STEM, _persona("r1"), "QID9_1")
    # Right persona, wrong question: also unfillable.
    with pytest.raises(KeyError):
        _fill_stem(PRICED_STEM, _persona("r1", {"QID9_2": "8.45"}), "QID9_1")


# Respondent.stem_values

@pytest.mark.unit
def test_respondent_collects_stem_columns_and_strips_the_prefix():
    row = {"respid": "r1", "__stem__QID9_1": "8.45", "__stem__QID9_2": "0.00", "QID196": "A"}
    assert Respondent(row, _StubMapper()).stem_values == {"QID9_1": "8.45", "QID9_2": "0.00"}


@pytest.mark.unit
def test_respondent_stem_values_empty_for_surveys_without_the_columns():
    """Surveys with no `__stem__` column: nothing to substitute anywhere."""
    assert Respondent({"Response ID": "r1", "MU1": 3}, _StubMapper()).stem_values == {}


@pytest.mark.unit
def test_respondent_skips_unfilled_stem_cells():
    """A NaN from a failed join must not become the literal string "nan" in a prompt."""
    row = {"respid": "r1", "__stem__QID9_1": float("nan"), "__stem__QID9_2": "", "__stem__QID9_3": "5.00"}
    assert Respondent(row, _StubMapper()).stem_values == {"QID9_3": "5.00"}


# The batched stateless path — where the substitution actually happens

# The shipped mappings

@pytest.mark.unit
def test_exactly_the_forty_pricing_stems_are_piped():
    mapping = json.loads(TWIN_QUESTION_MAPPING.read_text(encoding="utf-8"))
    piped = {qid for qid, e in mapping.items() if STEM_VALUE_TOKEN in e["question"]}
    assert piped == {f"QID9_{i}" for i in range(1, 41)}
    # The other 68 scored questions have one stem for everyone; piping them would be a bug.
    assert len(mapping) - len(piped) == 68


@pytest.mark.unit
def test_no_other_survey_mapping_contains_the_token():
    """A stray `{stem_value}` in a stem without the column would raise KeyError mid-run."""
    offenders = []
    for mapping_path in sorted(REPO_ROOT.glob("configs/*/*question_mapping*.json")):
        if "twin2k" in mapping_path.parts:
            continue
        if STEM_VALUE_TOKEN in mapping_path.read_text(encoding="utf-8"):
            offenders.append(mapping_path.name)
    assert not offenders, f"unexpected piped-text token in {offenders}"


@pytest.mark.unit
def test_piped_stems_are_never_grid_members():
    """The stateful grid branch builds its stem from the parent and cannot substitute."""
    mapping = json.loads(TWIN_QUESTION_MAPPING.read_text(encoding="utf-8"))
    assert not [
        qid for qid, e in mapping.items()
        if STEM_VALUE_TOKEN in e["question"] and e.get("grid_group")
    ]


# The preprocessor

@pytest.mark.unit
def test_preprocessor_without_the_param_only_renames():
    """Omitting `stem_values_dir` keeps the original pure `df -> df` behaviour."""
    df = preprocess(pd.DataFrame({"pid": [1, 2], "QID9_1": ["Yes", "No"]}))
    assert list(df.columns) == ["respid", "QID9_1"]
    assert not [c for c in df.columns if c.startswith("__stem__")]


@pytest.mark.unit
def test_preprocessor_reports_a_missing_chunk_directory():
    with pytest.raises(FileNotFoundError, match="fetch_twin2k"):
        preprocess(pd.DataFrame({"pid": [1]}), stem_values_dir="does/not/exist")


def _chunk(tmp_path, records, name="chunk_001.parquet"):
    """Write a parquet shaped like `wave_split/chunks/*`, so no 189 MB download is needed.

    `records` is [(pid, {qid: price}, {qid: price for wave 4})]; the wave-4 dict defaults to
    the wave-1-3 one, which is what the real data does for all 11,760 cells.
    """
    def payload(prices):
        return json.dumps([{
            "BlockName": "Product Preferences - Pricing",
            "Questions": [
                {"QuestionID": qid,
                 "QuestionText": f"...The product is priced at: ${price}. Would you?"}
                for qid, price in prices.items()
            ],
        }])

    frame = pd.DataFrame([
        {"pid": pid,
         "wave1_3_persona_text": "",
         "wave4_Q_wave1_3_A": payload(prices),
         "wave4_Q_wave4_A": payload(wave4 if wave4 is not None else prices)}
        for pid, prices, wave4 in records
    ])
    path = tmp_path / name
    frame.to_parquet(path)
    return path


@pytest.mark.unit
def test_preprocessor_joins_each_respondents_own_price(tmp_path):
    _chunk(tmp_path, [
        (1, {"QID9_1": "8.45", "QID9_2": "1.99"}, None),
        (2, {"QID9_1": "0.00", "QID9_2": "1.99"}, None),
    ])
    df = preprocess(
        pd.DataFrame({"pid": [1, 2], "QID9_1": ["Yes", "No"]}),
        stem_values_dir=str(tmp_path),
    )
    assert df.loc[df["respid"] == 1, "__stem__QID9_1"].item() == "8.45"
    assert df.loc[df["respid"] == 2, "__stem__QID9_1"].item() == "0.00"
    # "0.00" must survive as a string; a float round-trip would render "$0.0" in the prompt.
    assert isinstance(df.loc[df["respid"] == 2, "__stem__QID9_1"].item(), str)


@pytest.mark.unit
def test_preprocessor_rejects_a_respondent_with_no_price(tmp_path):
    _chunk(tmp_path, [(1, {"QID9_1": "8.45"}, None)])
    with pytest.raises(RuntimeError, match="no per-respondent price"):
        preprocess(pd.DataFrame({"pid": [1, 2]}), stem_values_dir=str(tmp_path))


@pytest.mark.unit
def test_preprocessor_rejects_a_wave_dependent_price(tmp_path):
    """The real data has one price per person-product; if that ever breaks, stop."""
    _chunk(tmp_path, [(1, {"QID9_1": "8.45"}, {"QID9_1": "9.45"})])
    with pytest.raises(RuntimeError, match="one draw per person-product"):
        preprocess(pd.DataFrame({"pid": [1]}), stem_values_dir=str(tmp_path))


@pytest.mark.unit
def test_preprocessor_rejects_ragged_pricing_questions(tmp_path):
    """A price that fails to parse for one respondent must not silently drop the column."""
    _chunk(tmp_path, [
        (1, {"QID9_1": "8.45", "QID9_2": "1.99"}, None),
        (2, {"QID9_1": "0.00"}, None),
    ])
    with pytest.raises(RuntimeError, match="disagree on which pricing questions"):
        preprocess(pd.DataFrame({"pid": [1, 2]}), stem_values_dir=str(tmp_path))
