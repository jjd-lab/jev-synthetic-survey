"""Unit tests for question_mapper."""

import pytest

from src.core.config_loader import load_survey_config


@pytest.mark.unit
class TestQuestionMapper:
    def test_validate_question_types_passes(self, question_mapper, fixtures_dir):
        cfg = load_survey_config(str(fixtures_dir / "test_survey_config.yaml"))
        question_mapper.validate_question_types(cfg.survey.questions)

    def test_validate_question_types_raises_on_mismatch(self, question_mapper):
        class FakeQuestion:
            id = "MU1"
            type = "multi"

        with pytest.raises(ValueError, match="type mismatch"):
            question_mapper.validate_question_types([FakeQuestion()])

    def test_get_question_type(self, question_mapper):
        assert question_mapper.get_question_type("MU1") == "single"
        assert question_mapper.get_question_type("MU2") == "multi"

    def test_extract_demographics(self, question_mapper):
        row = {"S1": 2, "S2": 3, "S3": 1}
        demo = question_mapper.extract_demographics(row)
        assert demo["age"] == "25-34"
        assert demo["income"] == "$75k-$100k"
        assert demo["family_type"] == "Single"
