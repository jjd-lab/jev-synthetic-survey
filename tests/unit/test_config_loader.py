"""Unit tests for config_loader."""

import pytest
from pydantic import ValidationError

from src.core.config_loader import FullSurveyConfig, load_survey_config


@pytest.mark.unit
class TestConfigLoader:
    def test_load_twin_baseline_config(self, repo_root):
        cfg = load_survey_config(
            str(repo_root / "configs" / "twin2k" / "demographics_stateless.yaml")
        )
        assert cfg.survey.name
        assert cfg.execution.output_dir == "outputs/twin2k/demographics_stateless"

    def test_missing_file_raises(self):
        with pytest.raises(FileNotFoundError):
            load_survey_config("nonexistent_config.yaml")

    def test_summarized_memory_mode_rejected(self):
        with pytest.raises(ValidationError):
            FullSurveyConfig(
                survey={
                    "name": "x",
                    "data_source": {
                        "excel_file": "x.xlsx",
                        "demographic_mapping": "a.json",
                        "question_mapping": "b.json",
                    },
                    "questions": [{"id": "Q1", "type": "single"}],
                },
                personas={"source": "excel"},
                survey_prompt="test {question}",
                memory_mode="summarized",
            )

    def test_duplicate_routing_rule_raises(self):
        from src.core.config_loader import validate_routing_rules

        cfg = FullSurveyConfig(
            survey={
                "name": "x",
                "data_source": {
                    "excel_file": "x.xlsx",
                    "demographic_mapping": "a.json",
                    "question_mapping": "b.json",
                },
                "questions": [{"id": "Q1", "type": "single"}, {"id": "Q2", "type": "single"}],
            },
            personas={"source": "excel"},
            survey_prompt="test {question}",
            routing_rules=[
                {"question_id": "Q2", "skip_if": {"source_question": "Q1", "skip_on": ["No"], "skip_to": "Q1"}},
                {"question_id": "Q2", "show_if": {"source_question": "Q1", "any_of": ["Yes"]}},
            ],
        )
        with pytest.raises(ValueError, match="Duplicate routing rule"):
            validate_routing_rules(cfg)

    def test_missing_screener_prompt_raises(self):
        with pytest.raises(ValidationError):
            FullSurveyConfig(
                survey={
                    "name": "x",
                    "data_source": {
                        "excel_file": "x.xlsx",
                        "screener_mapping": "a.json",
                        "response_mapping": "b.json",
                    },
                    "questions": [{"id": "MU1", "type": "single"}],
                },
                personas={"source": "excel"},
                survey_prompt="test {question}",
            )
