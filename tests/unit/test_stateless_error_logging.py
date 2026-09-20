"""The stateless runner must log *why* a cell failed, not just leave an "Error" behind.

Before this, a transient failure surfaced only as a dip in `n_valid`: BatchProcessor swallowed the
cause into `None`, and the runner re-labelled it "Response is None or missing variations". These
tests pin the real cause reaching the recorder, so `run_errors_*.jsonl` can drive a targeted re-run.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.core.survey_runner_excel import run_survey_single_choice_multi_var
from src.utils.progress import RunErrorRecorder

OPTIONS = ["Yes", "No"]


def _persona(respid):
    return {"respid": respid, "demographics": {"age": "35-44"}}


def _ok_response(choice=1):
    """Stands in for the structured-output model: one variation with a choice + explanation."""
    return SimpleNamespace(
        variations=[SimpleNamespace(choice=choice, explanation="because")]
    )


def _run(responses, recorder=None, personas=None):
    """Drive the runner with BatchProcessor's output stubbed to `responses`."""
    personas = personas or [_persona("r0"), _persona("r1")]
    processor = MagicMock()
    processor.process.return_value = responses

    with patch("src.core.survey_runner_excel.create_llm_instance"), \
         patch("src.core.survey_runner_excel.apply_langchain_retry", side_effect=lambda r, **kw: r), \
         patch("src.core.survey_runner_excel.BatchProcessor", return_value=processor):
        return run_survey_single_choice_multi_var(
            personas, "Do you agree?", OPTIONS, "{age} {question} {options}",
            n_variations=1, shuffle=False, question_id="QID9_1",
            error_recorder=recorder,
        )


@pytest.mark.unit
def test_a_failed_cell_is_recorded_with_its_real_cause():
    recorder = RunErrorRecorder()
    boom = RuntimeError("429 Too Many Requests")

    choices, explanations, _, persona_indices, _ = _run([_ok_response(1), boom], recorder)

    # The successful persona is unaffected; the failed one still gets its sentinel.
    assert choices == ["Yes", "Error"]
    assert persona_indices == [0, 1]

    assert len(recorder.records) == 1
    record = recorder.records[0]
    assert record["respid"] == "r1"
    assert record["item_id"] == "QID9_1"
    assert record["scope"] == "question"
    # The whole point: a 429 must not be laundered into "unknown" via "Response is None".
    assert record["category"] == "rate_limit"
    assert record["exception_class"] == "RuntimeError"
    assert "429" in record["reason"]
    assert "429" in explanations[1]


@pytest.mark.unit
def test_a_missing_response_still_records_rather_than_passing_silently():
    """BatchProcessor now returns exceptions, but a None must not become an unlogged hole."""
    recorder = RunErrorRecorder()

    choices, _, _, _, _ = _run([_ok_response(1), None], recorder)

    assert choices == ["Yes", "Error"]
    assert len(recorder.records) == 1
    assert recorder.records[0]["respid"] == "r1"
    assert recorder.records[0]["scope"] == "question"


@pytest.mark.unit
def test_a_clean_run_records_nothing():
    recorder = RunErrorRecorder()

    choices, _, _, _, _ = _run([_ok_response(1), _ok_response(2)], recorder)

    assert choices == ["Yes", "No"]
    assert recorder.records == []


@pytest.mark.unit
def test_the_recorder_stays_optional():
    """Callers that pass no recorder: the runner must behave exactly as before."""
    choices, explanations, _, persona_indices, variation_ids = _run(
        [_ok_response(1), RuntimeError("boom")], recorder=None
    )

    assert choices == ["Yes", "Error"]
    assert persona_indices == [0, 1]
    assert variation_ids == [0, 0]
    assert explanations[1].startswith("Failed:")
