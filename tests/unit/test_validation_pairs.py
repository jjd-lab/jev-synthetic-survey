"""Unit tests for validation_pairs (n_variations segment regression)."""

import pytest

from src.validation.response_validator import ValidationResult
from src.validation.validation_pairs import (
    build_segment_values,
    build_valid_pairs,
    replicate_ground_truth,
)


def _make_persona(respid, gt_mu1=None, age="25-34"):
    return {
        "respid": respid,
        "demographics": {"age": age, "income": "$75k-$100k"},
        "ground_truth": {"MU1": gt_mu1} if gt_mu1 is not None else {},
    }


@pytest.mark.unit
class TestValidationPairs:
    def test_replicate_ground_truth_three_variations(self):
        personas = [_make_persona(1, "A"), _make_persona(2, "B")]
        replicated = replicate_ground_truth(personas, "MU1", n_variations=3)
        assert replicated == ["A", "A", "A", "B", "B", "B"]

    def test_valid_pairs_excludes_none_ground_truth(self):
        personas = [_make_persona(1, "A"), _make_persona(2, None)]
        personas[1]["ground_truth"] = {"MU2": "X"}  # no MU1 gt
        replicated = replicate_ground_truth(personas, "MU1", n_variations=3)
        synthetic = ["A"] * 3 + ["B"] * 3
        tiers = [None] * 6
        indices = [0, 0, 0, 1, 1, 1]
        pairs = build_valid_pairs(synthetic, replicated, tiers, indices)
        assert len(pairs) == 3
        assert all(p[3] == 0 for p in pairs)

    def test_two_personas_three_variations_six_pairs(self):
        personas = [_make_persona(1, "A", "18-24"), _make_persona(2, "B", "35-44")]
        n_variations = 3
        replicated = replicate_ground_truth(personas, "MU1", n_variations)
        synthetic = ["A", "A", "B", "B", "C", "C"]
        tiers = [None] * 6
        indices = [0, 0, 0, 1, 1, 1]
        pairs = build_valid_pairs(synthetic, replicated, tiers, indices)
        assert len(pairs) == 6

        valid_indices = [p[3] for p in pairs]
        segment_values = build_segment_values(personas, valid_indices, "age")
        assert segment_values == ["18-24"] * 3 + ["35-44"] * 3

        result = ValidationResult("MU1", "single")
        result.synthetic = [p[0] for p in pairs]
        result.ground_truth = [p[1] for p in pairs]
        result.calculate_overall()
        result.calculate_segments("age", segment_values)
        assert sum(s["n"] for s in result.segment_results["age"].values()) == 6
