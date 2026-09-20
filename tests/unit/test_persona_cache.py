"""Unit tests for persona_cache."""

import pytest

from src.core.persona_cache import (
    get_persona_cache_path,
    load_personas_from_excel,
    save_personas_to_excel,
)


@pytest.mark.unit
class TestPersonaCache:
    def test_explicit_cache_path_overrides_output_default(self):
        assert get_persona_cache_path(
            "hillclimb/runs/exp-001-grid-shuffle",
            "C:/repo/outputs/twin2k/persona_cache.xlsx",
        ) == "C:/repo/outputs/twin2k/persona_cache.xlsx"

    def test_cache_path_defaults_to_output_directory(self):
        assert get_persona_cache_path("outputs/twin2k") == (
            "outputs/twin2k/persona_cache.xlsx"
        )

    def test_save_creates_configured_cache_parent(self, personas_from_respondents, tmp_path):
        cache_path = tmp_path / "shared" / "personas" / "persona_cache.xlsx"
        save_personas_to_excel(personas_from_respondents, str(cache_path))
        assert cache_path.exists()

    def test_round_trip_preserves_order(self, personas_from_respondents, respondents_from_fixture, tmp_path):
        cache_path = tmp_path / "persona_cache.xlsx"
        save_personas_to_excel(personas_from_respondents, str(cache_path))
        loaded = load_personas_from_excel(str(cache_path), respondents_from_fixture)
        assert loaded is not None
        assert len(loaded) == len(respondents_from_fixture)
        assert [p["respid"] for p in loaded] == [r.respid for r in respondents_from_fixture]

    def test_reversed_respondent_order_still_loads(self, personas_from_respondents, respondents_from_fixture, tmp_path):
        """Cache loads by respid lookup; respondent order does not matter."""
        cache_path = tmp_path / "persona_cache.xlsx"
        save_personas_to_excel(personas_from_respondents, str(cache_path))
        loaded = load_personas_from_excel(str(cache_path), list(reversed(respondents_from_fixture)))
        assert loaded is not None
        assert {p["respid"] for p in loaded} == {r.respid for r in respondents_from_fixture}

    def test_extra_respondent_not_in_cache_returns_none(
        self, personas_from_respondents, respondents_from_fixture, tmp_path
    ):
        cache_path = tmp_path / "persona_cache.xlsx"
        save_personas_to_excel(personas_from_respondents, str(cache_path))

        class MissingRespondent:
            respid = 999
            screener_profile = {}
            ground_truth = {}

        loaded = load_personas_from_excel(
            str(cache_path),
            respondents_from_fixture + [MissingRespondent()],
        )
        assert loaded is None

    def test_missing_cache_returns_none(self, respondents_from_fixture, tmp_path):
        loaded = load_personas_from_excel(str(tmp_path / "missing.xlsx"), respondents_from_fixture)
        assert loaded is None
