"""Shared pytest fixtures."""

import os

# A fresh clone has no `.env`, and `create_llm_instance` builds a real `ChatOpenAI` before any
# test gets to patch it -- the OpenAI SDK raises on construction when no key is present. The
# suite never makes a call (every LLM test patches or mocks), so a placeholder is enough, and
# setting it here rather than in each test keeps `python -m pytest` green on a bare checkout.
# A real key already in the environment is left alone.
os.environ.setdefault("OPENAI_API_KEY", "test-key-not-used")
os.environ.setdefault("API_KEY", "test-key-not-used")

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures"


@pytest.fixture(autouse=True)
def _clear_llm_instance_cache():
    """Reset create_llm_instance's lru_cache around every test.

    The factory is cached by argument tuple, so an instance built in one test would be
    returned in a later test with the same args — skipping ChatOpenAI construction and
    breaking tests that patch ChatOpenAI or set env vars. Clear before and after each test
    so cache state never leaks across tests.
    """
    from src.utils.llm_factory import create_llm_instance

    create_llm_instance.cache_clear()
    yield
    create_llm_instance.cache_clear()


@pytest.fixture
def repo_root():
    return REPO_ROOT


@pytest.fixture
def fixtures_dir():
    return FIXTURES_DIR


@pytest.fixture
def minimal_excel_path(fixtures_dir):
    return str(fixtures_dir / "minimal_respondents.xlsx")


@pytest.fixture
def test_survey_config_path(fixtures_dir):
    return str(fixtures_dir / "test_survey_config.yaml")


@pytest.fixture
def test_demographic_mapping(fixtures_dir):
    return str(fixtures_dir / "test_screener_mapping.json")


@pytest.fixture
def test_question_mapping(fixtures_dir):
    return str(fixtures_dir / "test_response_mapping.json")


@pytest.fixture
def question_mapper(test_demographic_mapping, test_question_mapping):
    from src.data import QuestionMapper

    return QuestionMapper(test_demographic_mapping, test_question_mapping)


@pytest.fixture
def respondents_from_fixture(minimal_excel_path, question_mapper):
    from src.data import ExcelSurveyLoader

    loader = ExcelSurveyLoader(minimal_excel_path, question_mapper)
    return loader.load_respondents()


@pytest.fixture
def personas_from_respondents(respondents_from_fixture):
    """Build personas without LLM calls."""
    return [
        {
            "respid": r.respid,
            "response_id": r.response_id,
            "demographics": r.demographics,
            "screener_summary": "Test screener summary.",
            "screener_profile": r.screener_profile,
            "ground_truth": r.ground_truth,
        }
        for r in respondents_from_fixture
    ]
