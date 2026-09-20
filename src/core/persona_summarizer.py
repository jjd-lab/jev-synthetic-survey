"""LLM-based persona summarization from screener responses"""

from typing import Dict, List, Optional
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field
from src.utils.llm_factory import create_llm_instance, apply_langchain_retry, structured_output_method
from src.utils.batch_processor import BatchProcessor


class ScreenerSummary(BaseModel):
    """Structured output for screener summary"""
    # min_length=1: `render_history` treats an empty summary as "this survey has no screener" and
    # falls back to the verbatim screener Q&A, so an LLM returning "" would silently give that one
    # persona a different prompt from the rest of the panel. Rejecting it here routes the persona
    # to the non-empty default below instead.
    summary: str = Field(..., min_length=1, description="Summary of screener responses in the format specified by the prompt")


def format_screener_responses(screener_profile: Dict[str, dict]) -> str:
    """Format screener profile for LLM prompt"""
    if not screener_profile:
        return "(No screener responses)"

    formatted = []
    for qid, data in screener_profile.items():
        formatted.append(f"- {data['question']}: {data['answer']}")

    return "\n".join(formatted)


def batch_summarize_screeners(screener_profiles: List[Dict[str, dict]],
                               screener_prompt_template: str = None,
                               model: str = None,
                               temperature: float = 0.7,
                               max_concurrency: Optional[int] = None,
                               max_retries: Optional[int] = None) -> List[str]:
    """Batch process screener summarization for multiple respondents"""
    llm = create_llm_instance(model=model, temperature=temperature, max_retries=max_retries)
    structured_llm = apply_langchain_retry(
        llm.with_structured_output(ScreenerSummary, method=structured_output_method(model)), max_retries=max_retries
    )
    prompt = ChatPromptTemplate.from_template(screener_prompt_template)
    chain = prompt | structured_llm

    batch_inputs = [
        {
            "count": len(profile) if profile else 0,
            "screener_responses": format_screener_responses(profile),
        }
        for profile in screener_profiles
    ]

    processor = BatchProcessor(max_concurrency=max_concurrency, label="screener summaries")
    results = processor.process(batch_inputs, chain)

    # Two ways to get no summary, both of which must take the default so every persona in the panel
    # gets a non-empty screener block: a failed item comes back as an Exception (truthy, and no
    # `.summary`), and a whitespace-only summary passes the model's min_length but still reads as
    # "this survey has no screener" to `render_history`. `strip()` is the emptiness test only -- the
    # summary itself is returned verbatim, since it goes straight into the prompt.
    summaries = []
    for result in results:
        summary = getattr(result, "summary", "")
        summaries.append(summary if summary.strip() else "No additional preference information available.")

    return summaries
