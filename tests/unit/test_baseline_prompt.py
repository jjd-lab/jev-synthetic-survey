"""What the baseline arm actually sends, pinned.

The baseline used to run on a batched, question-major runner and now runs the per-persona walk
with `chain_own_answers: false`. Those two built their prompt inputs in different places, so the
migration rested on a claim: the rendered prompt is the same either way.

It was checked once, on the commit that still had both runners, and the rendered strings were
byte-identical (1,569 characters). The input dicts differed in exactly one key, `request_id`,
which the batched path always filled with a UUID and the walk leaves empty. The template has no
`{request_id}` placeholder, so the value never reaches the model.

These tests pin the two properties that made that true, since the batched runner is gone and the
comparison cannot be re-run in-tree:

  1. the survey prompt ignores `request_id`, so a per-call UUID cannot change what is asked;
  2. an unchained walk renders an empty conversation history, which is what made the walk's
     prompt equal to a runner that had no history at all.

If someone adds `{request_id}` to the template, (1) fails loudly rather than silently making
every cell's prompt unique and defeating prefix caching.
"""

import yaml
from pathlib import Path

import pytest
from langchain_core.prompts import ChatPromptTemplate

from src.core.survey_runner_excel import format_options_numbered, render_history

REPO_ROOT = Path(__file__).resolve().parents[2]
BASELINE = REPO_ROOT / "configs" / "twin2k" / "demographics_stateless.yaml"

DEMOGRAPHICS = {
    "age": "35-44", "sex": "Male", "region": "Midwest", "education": "BA", "race": "White",
    "citizen": "Yes", "marital": "Married", "religion": "None", "religious_attendance": "Never",
    "party": "Independent", "income": "$50k", "political_views": "Moderate",
    "household_size": "2", "employment": "Employed",
}
OPTIONS = ["Yes, I would purchase the product", "No, I would not purchase the product"]
QUESTION = "Would you or would you not purchase this product?"


def _template() -> ChatPromptTemplate:
    return ChatPromptTemplate.from_template(
        yaml.safe_load(BASELINE.read_text(encoding="utf-8"))["survey_prompt"]
    )


def _inputs(request_id: str, history: str) -> dict:
    return {
        **DEMOGRAPHICS,
        "question": QUESTION,
        "options": format_options_numbered(OPTIONS),
        "conversation_history": history,
        "request_id": request_id,
    }


@pytest.mark.unit
def test_the_prompt_ignores_the_request_id():
    """A per-call UUID must not reach the model, or every cell's prefix becomes unique."""
    template = _template()
    with_uuid = template.format(**_inputs("1_multi_bfe6fa86", ""))
    without = template.format(**_inputs("", ""))
    assert with_uuid == without


@pytest.mark.unit
def test_an_unchained_walk_renders_no_history():
    """`chain_own_answers: false` on a persona with no prior answers means an empty history.

    That is what let the walk stand in for a runner which had no conversation history at all.
    """
    persona = {"respid": "1", "demographics": DEMOGRAPHICS, "screener_profile": {},
               "screener_summary": ""}
    assert render_history(persona, ()) == ""


@pytest.mark.unit
def test_chaining_is_what_puts_answers_in_the_prompt():
    """The counterpart: with answers chained, they do appear, so the two arms really differ."""
    persona = {"respid": "1", "demographics": DEMOGRAPHICS, "screener_profile": {},
               "screener_summary": ""}
    chained = render_history(persona, [(QUESTION, "Yes, I would purchase the product")])
    assert QUESTION in chained
    assert "Yes, I would purchase the product" in chained

    template = _template()
    assert template.format(**_inputs("", chained)) != template.format(**_inputs("", ""))
