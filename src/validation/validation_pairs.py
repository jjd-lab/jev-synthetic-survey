"""Helpers for aligning synthetic responses with ground truth and segments."""

from typing import List, Tuple, Any


def replicate_ground_truth(personas: List[dict], question_id: str, n_variations: int) -> List[Any]:
    """Replicate each persona's ground truth once per variation."""
    replicated = []
    for persona in personas:
        gt = persona["ground_truth"].get(question_id)
        for _ in range(n_variations):
            replicated.append(gt)
    return replicated


def build_valid_pairs(
    synthetic_responses: List[Any],
    ground_truth_replicated: List[Any],
    subscription_tiers: List[Any],
    persona_indices: List[int],
) -> List[Tuple[Any, Any, Any, int]]:
    """Build validation pairs, excluding rows where ground truth is None."""
    return [
        (syn, gt, tier, p_idx)
        for syn, gt, tier, p_idx in zip(
            synthetic_responses,
            ground_truth_replicated,
            subscription_tiers,
            persona_indices,
        )
        if gt is not None
    ]


def build_segment_values(
    personas: List[dict],
    valid_persona_indices: List[int],
    demographic_key: str,
) -> List[str]:
    """Build segment values aligned with valid validation pairs."""
    return [
        personas[p_idx]["demographics"].get(demographic_key, "Unknown")
        for p_idx in valid_persona_indices
    ]
