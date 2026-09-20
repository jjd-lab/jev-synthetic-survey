"""Survey runner for Excel-based validation with multi-choice support

This module supports two modes:
1. Stateless mode: Batch processing, no conversation history, no routing
2. Stateful mode: Sequential per-persona, full conversation history, routing-aware
"""

import random
import uuid
from typing import List, Literal, Optional, Any, Dict, Sequence, Tuple

ResponseMode = Literal["hard_choice", "choice_plus_confidence", "verbalized_probs", "weighted_draw"]

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableLambda
from pydantic import BaseModel, Field, create_model

from src.utils.llm_factory import create_llm_instance, apply_langchain_retry, structured_output_method
from src.utils.progress import (
    ProgressHandler,
    RunErrorRecorder,
    TokenUsageRecorder,
    print_error_summary,
)


def format_options_numbered(options: List[str]) -> str:
    """Format options with numbers"""
    return "\n".join([f"{i+1}. {opt}" for i, opt in enumerate(options)])


def _shuffled_option_order(options: List[str], rng, anchors=()) -> List[int]:
    """Index permutation of `options` with `anchors` held at the end, in listed order.

    Returns indices, NOT reordered strings: callers render via `[options[i] for i in order]`
    and map the LLM's 1-based choice back with `order[choice - 1]`. Answer extraction
    (`_extract_single_choice` / `_extract_multi_choice`) already indexes through that
    permutation, which is what keeps shuffling invisible to validation.

    Anchors absent from `options` are skipped rather than an error: `mask_by` removes options
    at runtime (Q20 masked by Q19, Q31/Q32 by Q30), so an anchor may legitimately be gone.

    `rng` needs only a `.shuffle` method — either a seeded `random.Random` (stateful path) or
    the global `random` module (stateless path).
    """
    anchor_indices = []
    for anchor in anchors:
        try:
            idx = options.index(anchor)
        except ValueError:
            continue  # masked out at runtime
        if idx not in anchor_indices:  # a repeated anchor must not duplicate an index
            anchor_indices.append(idx)

    anchor_set = set(anchor_indices)
    order = [i for i in range(len(options)) if i not in anchor_set]
    rng.shuffle(order)
    return order + anchor_indices


def _elicits_option_probabilities(response_mode: ResponseMode) -> bool:
    """Whether this mode asks the model for a per-option probability vector.

    `weighted_draw` elicits exactly like `verbalized_probs` -- same prompt, same schema, same
    `<qid>_probs` column -- and differs only in how the answer is committed. Holding elicitation
    constant is the point: it makes the draw-vs-stated comparison a test of the commit rule alone.
    """
    return response_mode in ("verbalized_probs", "weighted_draw")


def _field_names_in_order(model_fields: Dict[str, Any]) -> List[str]:
    return list(model_fields.keys())


def build_prompt_with_history(
    conversation_history: List[Tuple[str, Any]],
) -> str:
    """Build conversation history string for prompt injection

    Args:
        conversation_history: List of (question_text, answer) tuples

    Returns:
        Formatted conversation history string for {conversation_history} placeholder
        Empty string if no history

    Example output:
        Previous answers:
        Q: Do you watch live tv?
        A: Yes

        Q: How do you watch live tv?
        A: Cable/satellite, Streaming service
    """
    if not conversation_history:
        return ""  # No history yet

    # Format: "Previous answers:\nQ: [question]\nA: [answer]\n\n"
    lines = ["Previous answers:"]
    for q_text, answer in conversation_history:
        # Format answer (handle single vs multi)
        if isinstance(answer, list):
            answer_str = ", ".join(answer)
        else:
            answer_str = str(answer)

        lines.append(f"Q: {q_text}")
        lines.append(f"A: {answer_str}")
        lines.append("")  # Blank line between Q&As

    return "\n".join(lines)


def prior_answer_history(persona: dict) -> List[Tuple[str, Any]]:
    """Seed conversation history with the respondent's OWN answers to earlier questions.

    The Twin-2K-500 digital twins are grounded in the questions each respondent already
    answered, rendered as question/answer text (paper §4). Those arrive as `screener`
    mapping entries, so `screener_profile` already holds them as {question, answer} in
    survey order.

    Called only by `render_history`. Returns an empty list when a persona has no screener answers.
    """
    profile = persona.get("screener_profile") or {}
    return [
        (entry["question"], entry["answer"])
        for entry in profile.values()
        if entry.get("question") and entry.get("answer")
    ]


def render_history(
    persona: dict,
    own_answers: Sequence[Tuple[str, Any]] = (),
) -> str:
    """One channel for everything this persona has already 'said'.

    The persona's own earlier answers render as verbatim Q:/A: pairs, and `own_answers`, this
    run's chain on the stateful path, always follows them.
    """
    return build_prompt_with_history([*prior_answer_history(persona), *own_answers])


def _default_subscription_tier(subscription_tiers: List[str]) -> str:
    if "No Plan" in subscription_tiers:
        return "No Plan"
    return subscription_tiers[0]


STEM_VALUE_TOKEN = "{stem_value}"


def _fill_stem(question: str, persona: dict, question_id: Optional[str]) -> str:
    """Substitute this respondent's own piped-text value into the question stem.

    Qualtrics piped text makes a stem respondent-specific. Only Twin-2K-500's pricing block
    uses it here: its price is randomized per respondent, so the mapping carries
    `STEM_VALUE_TOKEN` where the price goes and the value rides in on the persona (see
    `src/data/preprocessors/twin2k.py` and `Respondent.stem_values`).

    Identity for every other survey: the fast path is the token test, so a stem without the
    token is returned unchanged without even looking at the persona. Surveys with no piped text have
    no `__stem__` columns and no token, so their prompts are byte-identical.

    Raises:
        KeyError: if the stem promises a piped value the persona cannot supply. Returning the
            stem as-is would send `{stem_value}` to the model in place of a price — a silently
            corrupt prompt that still parses and still scores.
    """
    if STEM_VALUE_TOKEN not in question:
        return question
    value = (persona.get("stem_values") or {}).get(question_id or "")
    if value is None:
        raise KeyError(
            f"{question_id}: stem needs {STEM_VALUE_TOKEN} but respondent "
            f"{persona.get('respid')} has no value for it — is the preprocessor's "
            f"`stem_values_dir` set?"
        )
    return question.replace(STEM_VALUE_TOKEN, value)


def _create_multi_variation_model(
    n_options: int,
    n_variations: int,
    choice_field: Literal["choice", "choices"],
    subscription_tiers: Optional[List[str]] = None,
    include_other_text: bool = False,
    require_selection: bool = False,
    response_mode: ResponseMode = "hard_choice",
    enforce_prob_length: bool = False,
):
    """Create response model for multiple variations of single- or multi-choice questions.

    When `include_other_text` is set (question has an "Other, please specify" option
    with an `oe_field`), each variation also carries an optional `other_text` the LLM
    fills ONLY when it selects that option — the generated free text used for piping.

    When `require_selection` is set, multi-choice answers must pick at least one option
    (`min_length=1`). Off by default: some surveys have multi-choice
    questions without a "None of the above" anchor where an empty selection is valid.

    `enforce_prob_length` puts the probability-vector length **in the schema** (`minItems`/
    `maxItems`) instead of only in the description. Caller-supplied because it is provider-dependent:
    OpenAI/Azure constrained-decode the schema and honour both keywords, while Bedrock's validator
    rejects array `maxItems` outright — see `structured_output_method`. Leaving it off is what
    produced 7 lost cells on an earlier survey: the description said "length must be 24", the schema said
    nothing, and the decoder emitted 25.
    """
    fields: Dict[str, Any] = {}
    if _elicits_option_probabilities(response_mode):
        prob_length = (
            {"min_length": n_options, "max_length": n_options} if enforce_prob_length else {}
        )
        fields["option_probabilities"] = (
            List[float],
            Field(
                ...,
                description=(
                    f"Probability for each of the {n_options} options in the order presented "
                    f"(length must be {n_options})"
                ),
                **prob_length,
            ),
        )
    if choice_field == "choice":
        fields["choice"] = (int, Field(..., ge=1, le=n_options, description=f"Option number (1-{n_options})"))
    elif require_selection:
        fields["choices"] = (List[int], Field(
            ..., min_length=1,
            description=f"List of selected option numbers (1-{n_options}); select at least one",
        ))
    else:
        fields["choices"] = (List[int], Field(..., description=f"List of selected option numbers (1-{n_options})"))
    fields["explanation"] = (str, Field(..., description="Brief explanation for this specific answer variation"))

    if include_other_text:
        fields["other_text"] = (Optional[str], Field(
            None,
            description="If you selected the 'Other'/'please specify' option, the free text for it; "
                        "otherwise leave null.",
        ))

    if subscription_tiers:
        tier_default = _default_subscription_tier(subscription_tiers)
        TierLiteral = Literal[*subscription_tiers]
        fields["subscription_tier"] = (TierLiteral, Field(
            tier_default, description="Subscription tier for this variation",
        ))

    # No length validator here on purpose. A raising validator discards the whole response --
    # a good `choice` and `explanation` with it -- over a miscounted diagnostic field.
    # `_extract_option_probabilities` already drops a wrong-length vector to None, so an unenforced
    # miscount costs the probs cell and nothing else.
    VariationAnswer = create_model("VariationAnswer", **fields)

    return create_model(
        'MultiVariationResponse',
        __base__=BaseModel,
        variations=(List[VariationAnswer], Field(
            ..., min_length=n_variations, max_length=n_variations,
            description=f"Exactly {n_variations} possible answer variations",
        ))
    )


def create_multi_variation_single_choice_model(
    n_options: int,
    n_variations: int,
    subscription_tiers: Optional[List[str]] = None,
    include_other_text: bool = False,
    response_mode: ResponseMode = "hard_choice",
    enforce_prob_length: bool = False,
):
    """Create response model for multiple variations of single-choice questions"""
    return _create_multi_variation_model(
        n_options, n_variations, "choice", subscription_tiers, include_other_text,
        response_mode=response_mode,
        enforce_prob_length=enforce_prob_length,
    )


def create_multi_variation_multi_choice_model(
    n_options: int,
    n_variations: int,
    subscription_tiers: Optional[List[str]] = None,
    include_other_text: bool = False,
    require_selection: bool = False,
    response_mode: ResponseMode = "hard_choice",
    enforce_prob_length: bool = False,
):
    """Create response model for multiple variations of multi-choice questions"""
    return _create_multi_variation_model(
        n_options, n_variations, "choices", subscription_tiers, include_other_text,
        require_selection=require_selection,
        response_mode=response_mode,
        enforce_prob_length=enforce_prob_length,
    )


def create_grid_response_model(
    n_items: int,
    n_options: int,
    n_variations: int = 1,
    subscription_tiers: Optional[List[str]] = None,
    response_mode: ResponseMode = "hard_choice",
    enforce_prob_length: bool = False,
):
    """Create response model for a grid question rated in ONE combined LLM call.

    The model sees the whole grid at once: it must return exactly `n_items` ratings,
    each a choice on the shared 1..n_options scale, in the SAME order the items are
    presented. Generic on `n_variations` (the stateless path may pass >1); the
    stateful caller passes 1 and takes variations[0], like sibling
    single/multi questions.

    `enforce_prob_length` is provider-dependent for the same reason as in
    `_create_multi_variation_model`: it emits `minItems`/`maxItems`, which OpenAI/Azure enforce and
    Bedrock rejects.
    """
    tier_default = _default_subscription_tier(subscription_tiers) if subscription_tiers else None
    TierLiteral = Literal[*subscription_tiers] if subscription_tiers else None

    grid_prob_desc = (
        f"Probability for each of the {n_options} scale options in the order presented "
        f"(length must be {n_options})"
    )

    grid_item_fields: Dict[str, Any] = {
        "item_index": (
            int,
            Field(
                ...,
                ge=1,
                le=n_items,
                description=f"Which grid item this rates (1-{n_items}, in the order presented)",
            ),
        ),
    }
    if _elicits_option_probabilities(response_mode):
        grid_prob_length = (
            {"min_length": n_options, "max_length": n_options} if enforce_prob_length else {}
        )
        grid_item_fields["option_probabilities"] = (
            List[float],
            Field(..., description=grid_prob_desc, **grid_prob_length),
        )
    grid_item_fields["choice"] = (
        int,
        Field(..., ge=1, le=n_options, description=f"Scale option number for this item (1-{n_options})"),
    )
    grid_item_fields["explanation"] = (
        str,
        Field(..., description="Brief reasoning for this item's rating"),
    )

    # No length validator, for the same reason as the single/multi model: a raising validator would
    # discard every item's rating in the grid over one miscounted diagnostic vector.
    GridItemAnswer = create_model(
        "GridItemAnswer",
        **grid_item_fields,
    )

    if subscription_tiers:
        class GridVariation(BaseModel):
            grid_answers: List[GridItemAnswer] = Field(
                ..., min_length=n_items, max_length=n_items,
                description=f"Exactly {n_items} ratings, one per grid item in order",
            )
            subscription_tier: TierLiteral = Field(
                tier_default, description="Subscription tier for this variation",
            )
    else:
        class GridVariation(BaseModel):
            grid_answers: List[GridItemAnswer] = Field(
                ..., min_length=n_items, max_length=n_items,
                description=f"Exactly {n_items} ratings, one per grid item in order",
            )

    return create_model(
        "GridResponse",
        __base__=BaseModel,
        variations=(List[GridVariation], Field(
            ..., min_length=n_variations, max_length=n_variations,
            description=f"Exactly {n_variations} grid-answer variation(s)",
        )),
    )


def create_open_ended_response_model(
    n_variations: int = 1,
    subscription_tiers: Optional[List[str]] = None,
):
    """Create response model for open-ended text questions."""
    tier_default = _default_subscription_tier(subscription_tiers) if subscription_tiers else None
    TierLiteral = Literal[*subscription_tiers] if subscription_tiers else None

    if subscription_tiers:
        class VariationAnswer(BaseModel):
            answer: str = Field(..., description="Open-ended text response")
            explanation: str = Field(..., description="Brief explanation for this response")
            subscription_tier: TierLiteral = Field(
                tier_default,
                description="Subscription tier for this variation",
            )
    else:
        class VariationAnswer(BaseModel):
            answer: str = Field(..., description="Open-ended text response")
            explanation: str = Field(..., description="Brief explanation for this response")

    return create_model(
        "OpenEndedResponse",
        __base__=BaseModel,
        variations=(List[VariationAnswer], Field(
            ..., min_length=n_variations, max_length=n_variations,
            description=f"Exactly {n_variations} open-ended answer variation(s)",
        )),
    )


def _extract_single_choice(variation, option_order, options):
    original_idx = option_order[variation.choice - 1]
    return options[original_idx]


def _extract_option_probabilities(variation, option_order, options) -> Optional[Dict[str, float]]:
    """Map presented-order probability list to canonical option labels."""
    if not hasattr(variation, "option_probabilities"):
        return None
    probs = variation.option_probabilities
    if probs is None or len(probs) != len(options):
        return None
    return {
        options[option_order[i]]: float(probs[i])
        for i in range(len(options))
    }


def _extract_multi_choice(variation, option_order, options):
    return [
        options[option_order[choice_num - 1]]
        for choice_num in variation.choices
    ]


def _weighted_draw_answer(
    committed,
    probs: Optional[Dict[str, float]],
    options: List[str],
    respid,
    question_id: str,
    multi: bool,
):
    """Replace a committed answer with a draw from the model's own probability vector.

    `response_mode: weighted_draw` (ELICIT_V11) changes only the commit rule; elicitation is
    identical to `verbalized_probs`. There is no argmax step being replaced -- the committed answer
    is the model's own `choice`/`choices` field, which coincided with the vector's argmax on 99.5%
    of nominal and 99.6% of ordinal cells on an earlier survey's panel.

    The two buckets are drawn differently, and this is not a detail:
      * single-choice -- the vector IS a distribution, so normalise to a simplex and draw one option.
      * multi-choice  -- the vector is **independent inclusion marginals**, not a distribution (raw
        sum mean 2.11 on that panel). So it is one Bernoulli per option, and renormalising it
        would be wrong. The downstream soft metric already splits the buckets this way.

    Seeded per (respid, question_id) rather than drawn from the persona's shuffle `rng` on purpose:
    the shuffle stream must stay identical to every other arm, or the presented option order differs
    and the comparison stops being about the commit rule. Unseeded would make the run unreproducible.

    Returns `committed` unchanged when the vector is missing or unusable -- a wrong-length vector is
    already dropped to None upstream, and an answer is worth more than a draw. A percentage-scaled
    vector (every value >= 1) clamps to all-options-selected on multi rather than being silently
    rescaled; D-1 (mean options selected vs human) surfaces that on the first pilot, which is the
    honest failure. Note the paired `<qid>_explanation` still justifies the *committed* answer, so on
    drawn cells the two can disagree by construction.
    """
    if not probs:
        return committed
    rng = random.Random(f"{respid}|{question_id}")
    if multi:
        drawn = [
            opt for opt in options
            if rng.random() < min(max(float(probs.get(opt, 0.0)), 0.0), 1.0)
        ]
        if drawn:
            return drawn
        # Where checkboxes are all [min 1], an empty selection can collapse a downstream
        # mask to zero options (Q31/Q32 by Q30), so an all-miss draw falls back to the single most
        # likely option rather than to nothing.
        best = max(options, key=lambda opt: float(probs.get(opt, 0.0)))
        return [best] if float(probs.get(best, 0.0)) > 0 else committed
    weights = [max(float(probs.get(opt, 0.0)), 0.0) for opt in options]
    if sum(weights) <= 0:
        return committed
    return rng.choices(options, weights=weights, k=1)[0]


def _canonical_slot_indices(rendered: List[str], canonical: List[str]) -> List[int]:
    """Record a presented option list as indices into the question's canonical option list.

    Storing labels costs ~13 MB per 1500-persona panel and is unusable as a permutation,
    because the presented list is often a masked SUBSET (Q20 by Q19, Q31/Q32 by Q30) whose
    positions mean nothing on their own. Indices into `get_choice_options_list` are stable
    across personas and comparable across rows, which is what the positional audit needs.

    A piped "Other" free text substitutes its placeholder option and so has no canonical
    index; it is recorded as -1. Callers analysing slots skip those cells rather than
    guessing which option a persona-specific string came from.

    Assumes labels are unique within a question — verified across all 108 twin2k
    questions. A duplicated label would collapse to one index and mis-record the permutation.
    """
    by_label = {label: idx for idx, label in enumerate(canonical)}
    return [by_label.get(label, -1) for label in rendered]


def _pin_cache_to_respid(llm, respid: Any):
    """Return a copy of `llm` that sends `prompt_cache_key` = respid, sharing its connection pool.

    OpenAI treats `prompt_cache_key` as a routing hint: calls carrying the same key are steered to
    the same cache. That is the fix for this provider fanning a single walk across deployments, where
    a cached prefix is only readable on the deployment that wrote it.

    `model_copy` rather than a second `create_llm_instance(...)` call: the factory is lru_cached on
    its argument tuple, so making the key an argument would mint one client -- and one httpx
    connection pool -- per respondent, undoing the shared-pool work this file relies on. A shallow
    copy carries its own `extra_body` while sharing `root_client`, and is still a ChatOpenAI, so the
    `with_structured_output` calls downstream keep working. The cached instance is left unmutated,
    which matters because it is shared across every concurrent persona-walk.
    """
    return llm.model_copy(
        update={"extra_body": {**(llm.extra_body or {}), "prompt_cache_key": str(respid)}}
    )


def run_stateful_survey(
    persona: Dict[str, Any],
    question_list: List[str],
    question_mapper,
    question_router,
    survey_prompt_template: str,
    model: str = None,
    temperature: float = 0.7,
    subscription_tiers: Optional[List[str]] = None,
    include_request_id: bool = True,
    max_retries: Optional[int] = None,
    error_recorder: Optional[RunErrorRecorder] = None,
    preserve_anchors: bool = False,
    chain_own_answers: bool = True,
    batch_grids: bool = True,
    prompt_cache_key_by_respid: bool = False,
    response_mode: ResponseMode = "hard_choice",
) -> Tuple[
    Dict[str, Any],
    Dict[str, str],
    Optional[str],
    Dict[str, Optional[Dict[str, float]]],
    Dict[str, Optional[List[str]]],
]:
    """Run survey for single persona with routing and conversation history

    This is the stateful mode. It:
    - Uses QuestionRouter to determine next question (skip, show-if logic)
    - Gets dynamic options (masking, piping)
    - Maintains full conversation history
    - Processes one persona sequentially through all questions

    Args:
        persona: Single persona dict with demographics, screener_summary, ground_truth
        question_list: Ordered list of question IDs from config
        question_mapper: QuestionMapper instance
        question_router: QuestionRouter instance
        survey_prompt_template: Prompt template with {conversation_history} placeholder
        model, temperature: LLM settings
        subscription_tiers: Optional tier list
        preserve_anchors: Honor each question's `anchor_options` by pinning those options to the
            end of the shuffled list. Off by default = uniform shuffle over all options.

    Returns:
        (state, explanations_dict, subscription_tier, probs_dict)
        - state: {question_id: answer} flat dict with all answers
        - explanations_dict: {question_id: explanation} for each answered question
        - subscription_tier: str (single tier for whole persona, or None)
        - probs_dict: {question_id: option→probability map or None}
        - orders_dict: {question_id: canonical option indices in prompt order, or None}
          Index i of the list is the slot the option was shown in; the value is that
          option's position in `get_choice_options_list` (-1 for piped free text).
    """
    state = {}
    # Between-subject arm assignments, read by `QuestionRouter.is_asked` so this persona only
    # sees the arm its human counterpart was randomized into. `CONDITION_PREFIX` keys are not
    # question ids, so the router's "already answered" check never sees them and validation
    # (which looks up real question ids) ignores them. Empty for surveys with no such groups.
    state.update(persona.get("condition_assignments", {}))
    # THIS run's answers only. Anything the persona said before the run belongs to
    # `render_history`, which always emits it ahead of this list.
    conversation_history = []
    explanations_dict = {}
    probs_dict: Dict[str, Optional[Dict[str, float]]] = {}
    orders_dict: Dict[str, Optional[List[int]]] = {}

    # NOTE: OE fields are NOT pre-populated from ground truth. The LLM generates its
    # own "Other" free text (stored under the question's oe_field), so downstream pipes
    # (e.g. Q31 <- Q30.A24.OE) consume generated text, not the human answer.

    # Determine subscription tier once (all questions use same tier)
    tier = subscription_tiers[0] if subscription_tiers else None

    rng = random.Random(str(persona["respid"]))

    # Declare the probability-vector length in the schema only where the provider honours it.
    # `json_schema` (OpenAI/Azure) constrained-decodes it, so the length is guaranteed rather than
    # merely requested in prose; `function_calling` (Bedrock/Claude) rejects array `maxItems`, which
    # is the reason that path exists at all. Derived once here from the same dispatch the
    # `with_structured_output` calls below use, so the two can never disagree.
    enforce_prob_length = structured_output_method(model) == "json_schema"

    llm = create_llm_instance(model=model, temperature=temperature, max_retries=max_retries)
    if prompt_cache_key_by_respid:
        llm = _pin_cache_to_respid(llm, persona["respid"])
    prompt = ChatPromptTemplate.from_template(survey_prompt_template)

    # Any prompt placeholder the persona doesn't supply (e.g. {children} when a
    # respondent's children field is empty) defaults to "" so formatting never fails.
    _template_vars = set(prompt.input_variables)

    def _fill_inputs(inputs: Dict[str, Any]) -> Dict[str, Any]:
        for var in _template_vars:
            inputs.setdefault(var, "")
        return inputs

    def _request_id(qid: str) -> str:
        # Per-call dedup buster. Empty when disabled so it can't sit at the prompt
        # prefix and defeat caching; the template for such configs omits the {request_id} placeholder,
        # and ChatPromptTemplate ignores extra input keys.
        if not include_request_id:
            return ""
        return f"{persona['respid']}_{qid}_{uuid.uuid4().hex[:8]}"

    def _history() -> str:
        # The single read seam for prompt history. Gated here rather than at the seven
        # `conversation_history.append(...)` sites: one switch instead of seven, and the list stays
        # correct-but-unread when chaining is off (`render_history` is its only consumer).
        # `chain_own_answers=False` yields the persona's PRIOR answers alone, constant across the
        # walk -- which both matches the stateless arm's elicitation and lets prefix caching serve
        # the whole history block on every call after the first.
        return render_history(persona, conversation_history if chain_own_answers else ())

    def _anchors_for(qid: str):
        # Anchor pinning is opt-in per config (`preserve_anchors`). Off means uniform shuffle
        # over all options, so `anchor_options` in the mapping stays inert data.
        return question_mapper.get_anchor_options(qid) if preserve_anchors else ()

    def _invoke_llm(item_id: str, chain, inputs: Dict[str, Any]):
        if error_recorder:
            error_recorder.set_context(persona["respid"], item_id)
        try:
            return chain.invoke(_fill_inputs(inputs))
        finally:
            if error_recorder:
                error_recorder.clear_context()

    # Iterate through questions using router
    while True:
        next_q = question_router.next_question(state, question_list)
        if next_q is None:
            break  # Survey complete

        # Grid questions: the LLM sees the WHOLE grid in one combined call, then we
        # fan the N ratings out to per-item state keys (validation stays per-item).
        # next_q is the first unanswered member whose (replicated) gate passed, so all
        # members of this group are due now. A gated-off grid never reaches here.
        # `batch_grids=False` treats every member as an ordinary standalone question, which is what
        # the stateless runner does. `grid_group` is still read below, for the row mask -- asking a
        # row on its own changes how it is asked, never whether it is asked.
        grid_group = question_mapper.get_grid_group(next_q) if batch_grids else None
        if grid_group is not None:
            members = [
                q for q in question_list
                if question_mapper.get_grid_group(q) == grid_group
            ]
            members_to_rate, masked_members = question_router.filter_grid_members(members, state)
            for member in masked_members:
                state[member] = None
                explanations_dict[member] = "Skipped (masked out)"

            if not members_to_rate:
                continue

            scale_options = question_mapper.get_choice_options_list(members_to_rate[0])
            # A grid renders ONE shared Options: block, so it gets one permutation for the
            # whole call -- not one per row. The scale is uniform across members, so the flag
            # and anchors are read from the representative member (same as scale_options).
            if question_mapper.get_shuffle_options(members_to_rate[0]):
                scale_order = _shuffled_option_order(
                    scale_options,
                    rng,
                    _anchors_for(members_to_rate[0]),
                )
            else:
                scale_order = list(range(len(scale_options)))
            rendered_scale = [scale_options[idx] for idx in scale_order]
            item_labels = [question_mapper.get_grid_label(m) for m in members_to_rate]
            stem_text = question_mapper.get_question_text(members_to_rate[0]).rsplit(" — ", 1)[0]

            items_block = "\n".join(
                f"{i}. {label}" for i, label in enumerate(item_labels, 1)
            )
            grid_question = (
                f"{stem_text}\n\n"
                f"Rate EACH of the following {len(members_to_rate)} items on the scale in Options "
                f"(return one rating per item):\n{items_block}"
            )
            history_str = _history()

            GridModel = create_grid_response_model(
                n_items=len(members_to_rate),
                n_options=len(scale_options),
                n_variations=1,
                subscription_tiers=subscription_tiers,
                response_mode=response_mode,
                enforce_prob_length=enforce_prob_length,
            )
            structured_llm = apply_langchain_retry(
                llm.with_structured_output(GridModel, method=structured_output_method(model)), max_retries=max_retries,
                on_retry=error_recorder.retry_hook if error_recorder else None,
            )
            chain = prompt | structured_llm
            inputs = {
                **persona["demographics"],
                "question": grid_question,
                "options": format_options_numbered(rendered_scale),
                "conversation_history": history_str,
                "request_id": _request_id(grid_group),
            }

            try:
                response = _invoke_llm(grid_group, chain, inputs)
                variation = response.variations[0]
                answers_by_index = {a.item_index: a for a in variation.grid_answers}
                if len(answers_by_index) != len(variation.grid_answers):
                    indices = [a.item_index for a in variation.grid_answers]
                    print(
                        f"  Warning: duplicate item_index in grid {grid_group} response: {indices}"
                    )

                history_parts = []
                for idx, member in enumerate(members_to_rate, 1):
                    ans = answers_by_index.get(idx)
                    if ans is None or not (1 <= ans.choice <= len(scale_options)):
                        state[member] = "Error"
                        explanations_dict[member] = "Failed: missing/invalid grid item rating"
                        if error_recorder:
                            error_recorder.record_failure(
                                persona["respid"],
                                member,
                                "question",
                                ValueError("missing/invalid grid item rating"),
                                category="structured_output",
                            )
                        continue
                    # The LLM answered against the RENDERED order; map back through the
                    # permutation so state/validation always see the canonical label.
                    choice_text = scale_options[scale_order[ans.choice - 1]]
                    if _elicits_option_probabilities(response_mode):
                        probs_dict[member] = _extract_option_probabilities(
                            ans, scale_order, scale_options
                        )
                    if response_mode == "weighted_draw":
                        # Grid rows are single-choice ratings on a shared scale, so they draw from
                        # the simplex. Seeded per row, not per grid: each row has its own vector.
                        choice_text = _weighted_draw_answer(
                            choice_text, probs_dict.get(member), scale_options,
                            persona["respid"], member, multi=False,
                        )
                    state[member] = choice_text
                    explanations_dict[member] = ans.explanation
                    # `scale_order` is already indices into the canonical scale: grids read
                    # their options from `get_choice_options_list` and scales are never masked.
                    orders_dict[member] = list(scale_order)
                    history_parts.append(f"{item_labels[idx - 1]}: {choice_text}")

                # ONE combined history turn for the whole grid
                conversation_history.append((stem_text, "; ".join(history_parts)))

                if getattr(variation, "subscription_tier", None):
                    tier = variation.subscription_tier
            except Exception as e:
                print(f"  Warning: Failed to process grid {grid_group}: {e}")
                if error_recorder:
                    error_recorder.record_failure(
                        persona["respid"], grid_group, "question", e
                    )
                for member in members_to_rate:
                    state[member] = "Error"
                    explanations_dict[member] = f"Failed: {str(e)}"
                conversation_history.append((stem_text, "Error"))
            continue

        # A grid member reached on its own -- only possible with `batch_grids=False`, since the
        # combined call above consumes every member of a due group. Its `mask_by`, if any, is the
        # same ROW filter the combined call applies, so it is read the same way and lands in the
        # same state: `None` under "Skipped (masked out)", which validation already drops. Without
        # this the row would be asked with the full scale, because `get_options` deliberately
        # leaves a grid member's options unmasked -- this is where the row decision lives.
        if question_mapper.get_grid_group(next_q) is not None:
            _, masked = question_router.filter_grid_members([next_q], state)
            if masked:
                state[next_q] = None
                explanations_dict[next_q] = "Skipped (masked out)"
                continue

        question_text = _fill_stem(question_mapper.get_question_text(next_q), persona, next_q)
        base_options = question_router.get_options(next_q, state)  # Dynamic options (masking/piping)
        # Unmasked, unshuffled option list — the frame `orders_dict` indices are relative to.
        canonical_options = question_mapper.get_choice_options_list(next_q)
        question_type = question_mapper.get_question_type(next_q)
        shuffle = question_mapper.get_shuffle_options(next_q)

        # Open-ended questions: free-text LLM response (no option list)
        if question_type == "open_ended":
            history_str = _history()
            ResponseModel = create_open_ended_response_model(
                n_variations=1, subscription_tiers=subscription_tiers
            )
            structured_llm = apply_langchain_retry(
                llm.with_structured_output(ResponseModel, method=structured_output_method(model)), max_retries=max_retries,
                on_retry=error_recorder.retry_hook if error_recorder else None,
            )
            chain = prompt | structured_llm
            inputs = {
                **persona["demographics"],
                "question": question_text,
                "options": "(Open-ended — write your answer as free text)",
                "conversation_history": history_str,
                "request_id": _request_id(next_q),
            }
            try:
                response = _invoke_llm(next_q, chain, inputs)
                variation = response.variations[0]
                answer = variation.answer.strip()
                state[next_q] = answer
                conversation_history.append((question_text, answer))
                explanations_dict[next_q] = variation.explanation
                if hasattr(variation, "subscription_tier") and variation.subscription_tier:
                    tier = variation.subscription_tier
            except Exception as e:
                print(f"  Warning: Failed to process {next_q}: {e}")
                if error_recorder:
                    error_recorder.record_failure(
                        persona["respid"], next_q, "question", e
                    )
                state[next_q] = "Error"
                conversation_history.append((question_text, "Error"))
                explanations_dict[next_q] = f"Failed: {str(e)}"
            continue

        # Handle edge case: masking filtered out all options.
        # Treat as skipped (routed out) — never substitute the ground truth, or validation
        # would compare ground truth against itself and report a false match.
        if len(base_options) == 0:
            state[next_q] = None  # Sentinel: validation loop drops None (main.py:253)
            explanations_dict[next_q] = "Skipped (no masked options)"
            continue

        elif len(base_options) == 1:
            # Single option - auto-select without LLM call
            answer = base_options[0] if question_type == "single" else [base_options[0]]
            state[next_q] = answer
            conversation_history.append((question_text, answer))
            explanations_dict[next_q] = "Auto-selected (only one masked option)"
            orders_dict[next_q] = _canonical_slot_indices(base_options, canonical_options)
            continue

        # Build conversation history string
        history_str = _history()

        # Option shuffling (per-question opt-in via shuffle_options in mapping).
        # Anchors ("None of the above", "Other, please specify") stay pinned at the end only
        # when the config sets preserve_anchors.
        if shuffle:
            option_order = _shuffled_option_order(
                base_options, rng, _anchors_for(next_q)
            )
            options = [base_options[idx] for idx in option_order]
        else:
            options = base_options
            option_order = list(range(len(options)))

        # Questions with an "Other, please specify" option get an optional generated
        # other_text field, stored under the oe_field for downstream piping.
        oe_field = question_mapper.get_oe_field(next_q)

        # Create structured output model (n_variations=1 for stateful mode)
        if question_type == "single":
            ResponseModel = create_multi_variation_single_choice_model(
                len(options), n_variations=1, subscription_tiers=subscription_tiers,
                include_other_text=oe_field is not None,
                response_mode=response_mode,
                enforce_prob_length=enforce_prob_length,
            )
        elif question_type == "multi":
            # Where checkboxes are all [min 1]; require at least one selection so an
            # empty answer can't collapse a downstream mask to zero options.
            ResponseModel = create_multi_variation_multi_choice_model(
                len(options), n_variations=1, subscription_tiers=subscription_tiers,
                include_other_text=oe_field is not None,
                require_selection=True,
                response_mode=response_mode,
                enforce_prob_length=enforce_prob_length,
            )
        else:
            print(f"  Warning: Unsupported question type '{question_type}' for {next_q}, skipping")
            state[next_q] = None
            explanations_dict[next_q] = f"Skipped (unsupported type: {question_type})"
            continue

        structured_llm = apply_langchain_retry(
            llm.with_structured_output(ResponseModel, method=structured_output_method(model)), max_retries=max_retries,
            on_retry=error_recorder.retry_hook if error_recorder else None,
        )
        chain = prompt | structured_llm

        # Build prompt inputs with demographics
        # Demographics unpacked directly - surveys have different fields, prompts handle gracefully
        inputs = {
            **persona["demographics"],
            "question": question_text,
            "options": format_options_numbered(options),
            "conversation_history": history_str,
            "request_id": _request_id(next_q),
        }

        # LLM call
        try:
            response = _invoke_llm(next_q, chain, inputs)
            variation = response.variations[0]  # Only 1 variation in stateful mode

            # Extract answer
            if question_type == "single":
                answer = _extract_single_choice(variation, option_order, base_options)
            else:
                answer = _extract_multi_choice(variation, option_order, base_options)

            if _elicits_option_probabilities(response_mode):
                probs_dict[next_q] = _extract_option_probabilities(
                    variation, option_order, base_options
                )
            if response_mode == "weighted_draw":
                # Ahead of `state`/`conversation_history` on purpose: under `memory_mode: full` the
                # history IS the persona's state, so remembering the committed answer while
                # recording the drawn one would make the rest of the walk incoherent. The oe_field
                # block below reads the same `answer`, so a drawn "Other" pipes like a chosen one.
                answer = _weighted_draw_answer(
                    answer, probs_dict.get(next_q), base_options,
                    persona["respid"], next_q, multi=question_type != "single",
                )

            # Update state and history
            state[next_q] = answer
            conversation_history.append((question_text, answer))
            explanations_dict[next_q] = variation.explanation
            orders_dict[next_q] = _canonical_slot_indices(options, canonical_options)

            # Store generated "Other" free text under the oe_field for piping (Q31 etc.).
            # Only when the Other option was actually selected and text was produced.
            if oe_field:
                other_text = getattr(variation, "other_text", None)
                other_label = question_mapper.get_other_option_text(next_q)
                answer_list = answer if isinstance(answer, list) else [answer]
                if other_text and (other_label is None or other_label in answer_list):
                    state[oe_field] = other_text.strip()

            # Update tier if present
            if hasattr(variation, 'subscription_tier') and variation.subscription_tier:
                tier = variation.subscription_tier

        except Exception as e:
            print(f"  Warning: Failed to process {next_q}: {e}")
            if error_recorder:
                error_recorder.record_failure(
                    persona["respid"], next_q, "question", e
                )
            # Add error sentinel and continue
            error_answer = "Error" if question_type == "single" else ["Error"]
            state[next_q] = error_answer
            conversation_history.append((question_text, error_answer))
            explanations_dict[next_q] = f"Failed: {str(e)}"

    return state, explanations_dict, tier, probs_dict, orders_dict


def run_stateful_survey_for_all_personas(
    personas: List[Dict[str, Any]],
    question_list: List[str],
    question_mapper,
    question_router,
    survey_prompt_template: str,
    model: str = None,
    temperature: float = 0.7,
    subscription_tiers: Optional[List[str]] = None,
    include_request_id: bool = True,
    max_concurrency: Optional[int] = None,
    max_retries: Optional[int] = None,
    preserve_anchors: bool = False,
    chain_own_answers: bool = True,
    batch_grids: bool = True,
    prompt_cache_key_by_respid: bool = False,
    token_recorder: Optional[TokenUsageRecorder] = None,
    response_mode: ResponseMode = "hard_choice",
) -> Tuple[
    List[Dict[str, Any]],
    List[Dict[str, str]],
    List[Optional[str]],
    List[Dict[str, Optional[Dict[str, float]]]],
    List[Dict[str, Optional[List[str]]]],
    List[dict],
]:
    """Run stateful survey for all personas (parallel persona-walks via LangChain .batch()).

    Args:
        personas: List of persona dicts
        question_list: Ordered list of question IDs
        question_mapper: QuestionMapper instance
        question_router: QuestionRouter instance
        survey_prompt_template: Prompt template
        model, temperature: LLM settings
        subscription_tiers: Optional tier list
        max_concurrency: Thread-pool cap for concurrent persona-walks (None = LangChain default)
        max_retries: retry count applied via apply_langchain_retry() (SDK retries disabled; None = env LLM_MAX_RETRIES/default)
        preserve_anchors: Pin each question's `anchor_options` last instead of shuffling them in
        chain_own_answers: Feed a persona's own answers back into later prompts (default True)
        batch_grids: Combine a question's `grid_group` siblings into one call (default True)
        prompt_cache_key_by_respid: Send `prompt_cache_key` = respid so the provider keeps a walk's
            calls on the deployment holding its cached prefix (default False; a cost knob only)
        token_recorder: Optional TokenUsageRecorder. Must be **owned by the caller**, not created
            here: the checkpointed path calls this function once per cohort, so a recorder created
            internally would reset and report only the last cohort's tokens.

    Returns:
        (all_states, all_explanations, all_tiers)
        - all_states: List[Dict[str, Any]] - one state dict per persona
        - all_explanations: List[Dict[str, str]] - one explanation dict per persona
        - all_tiers: List[Optional[str]] - one tier per persona
        - all_probs: List[Dict[str, Optional[Dict[str, float]]]] - one probs dict per persona
        - all_orders: List[Dict[str, Optional[List[int]]]] - one option-order dict per persona
        - error_records: List[dict] - structured failure records for the run
    """
    concurrency_label = max_concurrency if max_concurrency is not None else "default"
    print(f"\n[INFO] Running stateful survey (per-persona mode, max_concurrency={concurrency_label})")
    print(f"  Personas: {len(personas)}")
    print(f"  Questions: {len(question_list)}")
    print(f"  Routing rules: {len(question_router.routing_rules)}")

    recorder = RunErrorRecorder()

    def _run_one(persona: Dict[str, Any]):
        return run_stateful_survey(
            persona, question_list, question_mapper, question_router,
            survey_prompt_template, model, temperature, subscription_tiers,
            include_request_id=include_request_id,
            max_retries=max_retries,
            error_recorder=recorder,
            preserve_anchors=preserve_anchors,
            chain_own_answers=chain_own_answers,
            batch_grids=batch_grids,
            prompt_cache_key_by_respid=prompt_cache_key_by_respid,
            response_mode=response_mode,
        )

    batch_config: Dict[str, Any] = {}
    if max_concurrency is not None:
        batch_config["max_concurrency"] = max_concurrency
    # Print a progress line every `interval` completed persona-walks. .batch() is unchunked,
    # so this is a completion counter (not a true wave); tying interval to max_concurrency makes
    # each line read like "one pool's-worth done".
    progress_interval = max_concurrency if max_concurrency is not None else 8
    batch_config["callbacks"] = [
        ProgressHandler(total=len(personas), interval=progress_interval),
    ]
    if token_recorder is not None:
        # LangChain propagates config callbacks into nested runnable invocations, so this one handler
        # reaches every LLM call inside every persona-walk without touching the call sites.
        batch_config["callbacks"].append(token_recorder)

    results = RunnableLambda(_run_one).batch(
        personas,
        config=batch_config,
        return_exceptions=True,
    )

    all_states: List[Dict[str, Any]] = []
    all_explanations: List[Dict[str, str]] = []
    all_tiers: List[Optional[str]] = []
    all_probs: List[Dict[str, Optional[Dict[str, float]]]] = []
    all_orders: List[Dict[str, Optional[List[int]]]] = []

    for i, result in enumerate(results):
        respid = personas[i]["respid"]
        if isinstance(result, Exception):
            print(f"  Warning: Persona {i + 1}/{len(personas)} ({respid}) failed: {result}")
            recorder.record_failure(respid, None, "persona", result)
            all_states.append({})
            all_explanations.append({"__persona_error__": str(result)})
            all_tiers.append(None)
            all_probs.append({})
            all_orders.append({})
            continue

        state, explanations, tier, probs, orders = result
        all_states.append(state)
        all_explanations.append(explanations)
        all_tiers.append(tier)
        all_probs.append(probs)
        all_orders.append(orders)

    print(f"\n[OK] Stateful survey complete for all {len(personas)} personas")
    print_error_summary(recorder)
    return all_states, all_explanations, all_tiers, all_probs, all_orders, recorder.records
