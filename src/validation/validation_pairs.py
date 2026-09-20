"""Aligning synthetic responses with their ground truth."""

from typing import List, Any


def replicate_ground_truth(personas: List[dict], question_id: str, n_variations: int) -> List[Any]:
    """Replicate each persona's ground truth once per variation."""
    replicated = []
    for persona in personas:
        gt = persona["ground_truth"].get(question_id)
        for _ in range(n_variations):
            replicated.append(gt)
    return replicated
