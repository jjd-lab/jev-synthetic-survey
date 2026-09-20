"""Config loader for Excel-based survey validation"""

import json
import os

import yaml
from pydantic import BaseModel
from typing import Any, List, Optional, Literal, Dict


class PreprocessConfig(BaseModel):
    """Optional raw-data preprocessor applied before respondents are built.

    Points at a ``df -> df`` callable by dotted path (e.g. a survey-specific
    module under ``src/data/preprocessors/``). Surveys that need no transform
    that need none simply omit the ``preprocess`` block and the loader is a no-op.
    """
    callable: str  # Dotted path, e.g. "src.data.preprocessors.twin2k.preprocess"
    params: Optional[Dict[str, Any]] = None  # Extra kwargs passed to the callable


class DataSourceConfig(BaseModel):
    """Data source configuration for Excel-based surveys"""
    excel_file: str
    demographic_mapping: str  # Maps demographics (CSV columns or screener questions)
    question_mapping: str  # Maps survey questions (validation questions)
    sheet_name: Optional[str] = None
    max_rows: Optional[int] = None
    # "coded": answers are numeric codes in columns named by qid
    # "text": answers are raw text in columns named "<qid>: <question text>" (Twin-2K-500)
    data_format: Literal["coded", "text"] = "coded"
    preprocess: Optional[PreprocessConfig] = None  # Optional raw-CSV transform; omit for no-op


class QuestionConfig(BaseModel):
    """Single question configuration"""
    id: str
    type: str = "single"  # "single" or "multi"


class SkipIfRule(BaseModel):
    """Skip to target question if source matches condition"""
    source_question: str  # Question to check
    skip_on: List[str]  # Answer values that trigger skip (e.g., ["No", "Don't know"])
    skip_to: str  # Target question to jump to


class ShowIfRule(BaseModel):
    """Show question only if source matches condition (OR logic)"""
    source_question: str  # Question to check
    any_of: List[str]  # Show if any of these answers selected (OR logic)


class MaskByRule(BaseModel):
    """Dynamic option list based on prior answer"""
    source_question: str  # Question whose answers become this question's options
    filter_type: Literal["include_selected", "exclude_selected"]  # Include or exclude logic


class RoutingRule(BaseModel):
    """Conditional routing logic for a question"""
    question_id: str  # Question this rule applies to
    skip_if: Optional[SkipIfRule] = None  # Skip logic
    show_if: Optional[ShowIfRule] = None  # Conditional display
    mask_by: Optional[MaskByRule] = None  # Dynamic options
    pipe_from: Optional[str] = None  # OE field to pipe text from (e.g., "Q30.A24.OE")


class SurveyConfig(BaseModel):
    """Main survey configuration"""
    name: str
    data_source: DataSourceConfig
    questions: List[QuestionConfig]


class PersonaConfig(BaseModel):
    """Persona generation configuration"""
    source: str = "excel"


class LLMConfig(BaseModel):
    """LLM settings"""
    model: str = "azure/gpt-4.1"
    temperature: float = 0.7
    persona_temperature: Optional[float] = None
    survey_temperature: Optional[float] = None
    # Fixed at 1. The walk asks each cell once; the batched runner that fanned out into
    # several variations per persona was removed. Stated as a validated field rather than
    # dropped so a config asking for 4 fails here instead of silently getting 1.
    n_variations: Literal[1] = 1
    # The only concurrency knob. .batch() uses a rolling pool, so this caps in-flight calls without
    # the synchronization barrier the old `batch_size` chunk loop imposed. None = LangChain default
    # pool of min(32, cpu_count + 4). A leftover `batch_size:` key in an old config is inert
    # (pydantic ignores extras), so archived run configs keep loading.
    max_concurrency: Optional[int] = None
    max_retries: Optional[int] = None
    subscription_tiers: Optional[List[str]] = None

    def get_persona_temperature(self) -> float:
        """Get temperature for persona generation (factual summarization)"""
        return self.persona_temperature if self.persona_temperature is not None else 0.3

    def get_survey_temperature(self) -> float:
        """Get temperature for survey responses (varied)"""
        return self.survey_temperature if self.survey_temperature is not None else self.temperature


class ExecutionConfig(BaseModel):
    """Execution settings"""
    save_output: bool = True
    output_dir: str = "outputs"


class FullSurveyConfig(BaseModel):
    """Complete survey configuration"""
    survey: SurveyConfig
    personas: PersonaConfig
    survey_prompt: str
    llm: LLMConfig = LLMConfig()
    execution: ExecutionConfig = ExecutionConfig()

    # Fields for the stateful path
    # Every arm is a per-persona walk. The batched, question-major path was removed once no arm
    # used it: `chain_own_answers: false` gives the same elicitation on this path, and only this
    # path reaches `response_mode`, per-cell option orders and cache pinning. Kept as a field, and
    # still required to say "full", so an older config fails loudly instead of quietly running a
    # different experiment.
    memory_mode: Literal["full"] = "full"
    include_request_id: bool = False  # Prepend a per-call UUID to the prompt (dedup buster). Default
    # False (stateful: sequential per-persona, every prompt already unique, so the UUID only defeats
    # prefix caching). Set True for stateless batch + n_variations, which keeps identical
    # (persona, question) calls from collapsing to one cached completion).
    chain_own_answers: bool = True  # Feed a persona's own answers back into later prompts. Only read
    # True = the chained arms' behaviour. False
    # keeps the prompt constant across a walk, which is how the twin2k `prior_answers` arm gets
    # respondent-major prefix caching while still eliciting exactly like the stateless `baseline` arm.
    batch_grids: bool = True  # Combine a question's `grid_group` siblings into one LLM call. Only
    # read on the stateful path. True = today's behaviour. False asks each member individually, which
    # is what the stateless runner does -- set it when a stateful arm has to stay comparable to a
    # stateless one, and to separate grid batching from answer chaining as a cause of an effect.
    prompt_cache_key_by_respid: bool = False  # Send OpenAI's `prompt_cache_key` set to the respid, so
    # the provider routes all of one respondent's calls to the deployment holding their cached prefix.
    # Only read on the stateful path. Measured need: the provider fans out across deployments and a
    # cache entry lives only on the one that wrote it, so a walk's calls miss a warm prefix purely by
    # landing elsewhere -- which is what drags the hit rate from 92.5% at one walk in flight to 54.6%
    # at 32. A routing hint, not a cache setting: it cannot create or extend an entry, so the worst
    # case is that the provider ignores it. Off by default because it changes no answer, only the bill,
    # and every arm should opt in on its own measurement.
    preserve_anchors: bool = False  # Pin `anchor_options` (mapping JSON) to the end of the shuffled
    # option list instead of letting them float. Default False = uniform shuffle over all options.
    # Opt-in because it changes prompt option order, so results are not comparable across the flip;
    # tracked as the predecessor project's `positional:preserve_anchors` arm.
    response_mode: Literal["hard_choice", "choice_plus_confidence", "verbalized_probs", "weighted_draw"] = "hard_choice"
    # `response_mode` is how a choice is elicited. `hard_choice` = pick one option (default, and
    # every pre-ELICIT arm).
    # `verbalized_probs` = also emit a probability per option (ELICIT_V10), which is what the
    # `<qid>_probs` export column and the downstream soft metric read; the committed `choice` field
    # still supplies `_synthetic`, so hard metrics are unaffected.
    # `weighted_draw` (ELICIT_V11) elicits identically to `verbalized_probs` and changes only the
    # commit rule: `_synthetic` becomes a DRAW from that vector -- one option from the simplex for
    # single-choice, one Bernoulli per option for multi (the multi vector is independent inclusion
    # marginals, not a distribution). Seeded per (respid, question_id), and the drawn answer is what
    # enters `conversation_history`. Unlike `verbalized_probs` this changes `_synthetic`, so it is
    # not comparable to a `hard_choice` run except as the intervention under test; report D-1 (mean
    # options selected) beside the metric, since the draw changes how many boxes get ticked.
    # `choice_plus_confidence` is registered but NOT implemented -- the runner has no branch for it,
    # so setting it today elicits exactly like `hard_choice`, silently.
    persona_cache_path: Optional[str] = None  # Explicit shared cache; omit for persona-changing runs.
    demographic_mapping: Optional[Dict[str, str]] = None  # Maps demo keys to CSV columns
    routing_rules: Optional[List[RoutingRule]] = None  # Conditional logic (skip, show-if, mask, pipe)
    min_n_for_gating: int = 50  # Valid-respondent floor below which `collapse` and `blind_spot` are
    # reported but never FLAGGED (an entropy ratio over a handful of draws cannot separate collapse
    # from sampling noise). Default matches `MIN_N_FOR_GATING` in response_validator.py.
    # Per-survey because it is a reporting policy, not a law.
    # Raising it is the honest use — lowering it manufactures flags rather than restoring a guardrail.


def validate_routing_rules(config: FullSurveyConfig) -> None:
    """Validate routing rules reference valid questions

    Args:
        config: Loaded survey configuration

    Raises:
        ValueError: If routing rules reference invalid questions or have circular dependencies
    """
    if not config.routing_rules:
        return  # No routing rules to validate

    # Build set of valid question IDs
    question_ids = {q.id for q in config.survey.questions}

    # Guard against duplicate rule ids: rules are indexed by question_id (last wins),
    # so a duplicate silently drops a rule (e.g. Q45 skip_if lost behind show_if).
    seen_rule_ids = set()
    for rule in config.routing_rules:
        if rule.question_id in seen_rule_ids:
            raise ValueError(
                f"Duplicate routing rule for question '{rule.question_id}'. "
                f"Merge them into one rule (skip_if/show_if/mask_by/pipe_from can coexist)."
            )
        seen_rule_ids.add(rule.question_id)

    # Track skip chains to detect circular dependencies
    skip_graph = {}  # {source_q: target_q}

    for rule in config.routing_rules:
        # Validate question_id exists
        if rule.question_id not in question_ids:
            raise ValueError(
                f"Routing rule references unknown question: {rule.question_id}\n"
                f"Valid questions: {sorted(question_ids)}"
            )

        # Validate skip_if references
        if rule.skip_if:
            if rule.skip_if.source_question not in question_ids:
                raise ValueError(
                    f"Routing rule {rule.question_id}: skip_if references unknown question {rule.skip_if.source_question}"
                )
            if rule.skip_if.skip_to not in question_ids:
                raise ValueError(
                    f"Routing rule {rule.question_id}: skip_to target {rule.skip_if.skip_to} not found"
                )
            skip_graph[rule.question_id] = rule.skip_if.skip_to

        # Validate show_if references
        if rule.show_if:
            if rule.show_if.source_question not in question_ids:
                raise ValueError(
                    f"Routing rule {rule.question_id}: show_if references unknown question {rule.show_if.source_question}"
                )

        # Validate mask_by references
        if rule.mask_by:
            if rule.mask_by.source_question not in question_ids:
                raise ValueError(
                    f"Routing rule {rule.question_id}: mask_by references unknown question {rule.mask_by.source_question}"
                )

    # Check for circular skip dependencies (simple cycle detection)
    # This prevents Q1 -> Q2 -> Q1 loops
    for start_q in skip_graph:
        visited = set()
        current = start_q
        while current in skip_graph:
            if current in visited:
                raise ValueError(
                    f"Circular skip dependency detected: {' -> '.join(visited)} -> {current}"
                )
            visited.add(current)
            current = skip_graph[current]


def load_survey_config(config_path: str) -> FullSurveyConfig:
    """Load and validate survey configuration from YAML/JSON"""
    if not os.path.exists(config_path):
        raise FileNotFoundError(
            f"Config file not found: {config_path}\n"
            f"Expected absolute path or path relative to current directory.\n"
            f"Example configs available in: configs/twin2k/demographics_stateless.yaml"
        )

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            if config_path.endswith('.yaml') or config_path.endswith('.yml'):
                data = yaml.safe_load(f)
            else:
                data = json.load(f)
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML syntax in config file: {e}")
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON syntax in config file: {e}")

    try:
        config = FullSurveyConfig(**data)
        validate_routing_rules(config)
        return config
    except Exception as e:
        raise ValueError(f"Config validation failed: {e}\nCheck config schema in README.md")
