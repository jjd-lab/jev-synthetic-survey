"""Generate personas from Excel respondent data"""

from typing import List, Optional
from src.data.respondent import Respondent
from src.core.persona_summarizer import batch_summarize_screeners

_DISPLAY_WIDTH = 80


def generate_personas_from_respondents(respondents: List[Respondent],
                                        screener_summarization_prompt: str = None,
                                        model: str = None,
                                        temperature: float = 0.3,
                                        max_concurrency: Optional[int] = None,
                                        max_retries: Optional[int] = None) -> List[dict]:
    """Generate personas from list of respondents using LLM to summarize screener profiles

    Args:
        respondents: List of Respondent objects
        screener_summarization_prompt: Optional template for screener summarization
        model: LLM model to use
        temperature: Temperature for persona generation (factual summarization, default: 0.3)

    Returns:
        List of persona dictionaries
    """
    print(f"\nGenerating personas from {len(respondents)} respondents...")
    print("=" * _DISPLAY_WIDTH)

    # Batch summarize screener profiles (skip if no prompt - some surveys have no screener)
    if screener_summarization_prompt:
        print("\nSummarizing screener profiles...")
        screener_profiles = [r.screener_profile for r in respondents]

        screener_summaries = batch_summarize_screeners(
            screener_profiles,
            screener_prompt_template=screener_summarization_prompt,
            model=model,
            temperature=temperature,
            max_concurrency=max_concurrency,
            max_retries=max_retries,
        )

        print(f"[OK] Generated {len(screener_summaries)} screener summaries")
    else:
        print("\n[INFO] No screener summarization prompt - skipping (direct demographics mode)")
        screener_summaries = ["" for _ in respondents]  # Empty summaries

    print("\nBuilding persona objects...")
    personas = [
        {
            "respid": respondent.respid,
            "response_id": respondent.response_id,
            "demographics": respondent.demographics,
            "screener_summary": summary,
            "screener_profile": respondent.screener_profile,
            "ground_truth": respondent.ground_truth,
            # Per-respondent question text (Twin's randomized prices); {} for other surveys.
            "stem_values": respondent.stem_values,
            # Per-respondent between-subject arm assignments; {} for other surveys.
            "condition_assignments": respondent.condition_assignments,
        }
        for respondent, summary in zip(respondents, screener_summaries)
    ]

    print(f"[OK] Successfully generated {len(personas)} personas")
    print("=" * _DISPLAY_WIDTH)

    return personas


def display_sample_personas(personas: List[dict], n: int = 3):
    """Display sample personas for verification

    Args:
        personas: List of persona dictionaries
        n: Number of samples to display
    """
    print(f"\nSample Personas (showing {n} of {len(personas)}):")
    print("=" * _DISPLAY_WIDTH)

    for i, persona in enumerate(personas[:n], 1):
        demo_keys = ", ".join(persona['demographics'].keys()) or "(none)"
        print(f"\n{i}. Respondent ID: {persona['respid']}")
        print(f"   Demographic fields: {demo_keys}")
        print(f"   Ground Truth Questions: {list(persona['ground_truth'].keys())}")

    print("=" * _DISPLAY_WIDTH)
