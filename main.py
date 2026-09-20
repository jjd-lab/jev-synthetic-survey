"""
Synthetic Survey Validation Pipeline

Validates synthetic survey responses against real respondent data from Excel.

Usage:
    python main.py --config configs/twin2k/twin2k_survey_config.yaml
    python main.py --config configs/twin2k/twin2k_survey_config.yaml --sample 100
    python main.py --config configs/twin2k/twin2k_survey_config.yaml --questions QID9_1,QID9_2
"""
import argparse
import logging
import os
from collections import Counter
from datetime import datetime
from src.core.config_loader import load_survey_config
from src.data import QuestionMapper, ExcelSurveyLoader
from src.core.persona_from_excel import generate_personas_from_respondents, display_sample_personas
from src.core.persona_cache import load_personas_from_excel, save_personas_to_excel, get_persona_cache_path
from src.core.survey_runner_excel import run_survey_for_question
from src.validation.response_validator import (
    MIN_N_FOR_GATING,
    ValidationResult,
    individual_baseline_name,
)
from src.validation.validation_pairs import replicate_ground_truth


def validate_question_responses(
    question_id: str,
    question_type: str,
    synthetic_responses: list,
    ground_truth_responses: list,
    subscription_tiers: list,
    persona_indices: list,
    personas: list,
    question_mapper,
    min_n_for_gating: int = MIN_N_FOR_GATING,
) -> ValidationResult:
    """
    Common validation logic for both stateful and stateless modes.

    Args:
        question_id: Question identifier
        question_type: Question type (single/multi)
        synthetic_responses: List of synthetic answers
        ground_truth_responses: List of ground truth answers (aligned with synthetic)
        subscription_tiers: List of subscription tiers
        persona_indices: List of persona indices (for segmentation)
        personas: Full list of personas
        question_mapper: QuestionMapper instance
        min_n_for_gating: Valid-respondent floor below which `collapse`/`blind_spot` are
            reported but not flagged (config's `min_n_for_gating`).

    Returns:
        ValidationResult with calculated metrics and segments, or None if the
        question is excluded from validation (e.g. open-ended: no defensible
        distributional metric at n=1).
    """
    # Open-ended questions are excluded from validation (no defensible metric).
    if question_type == "open_ended":
        return None

    # Filter valid pairs (exclude None ground truth and Error responses)
    valid_pairs = []
    for i, (synth, gt) in enumerate(zip(synthetic_responses, ground_truth_responses)):
        if gt is not None and synth not in ["Error", ["Error"]]:
            valid_pairs.append((synth, gt, subscription_tiers[i], persona_indices[i]))

    if not valid_pairs:
        return None

    synthetic_filtered, ground_truth_filtered, _, final_persona_indices = zip(*valid_pairs)
    synthetic_filtered = list(synthetic_filtered)
    ground_truth_filtered = list(ground_truth_filtered)
    final_persona_indices = list(final_persona_indices)

    # Calculate validation metrics
    result = ValidationResult(question_id, question_type, min_n_for_gating=min_n_for_gating)
    result.synthetic = synthetic_filtered
    result.ground_truth = ground_truth_filtered

    all_options = question_mapper.get_choice_options_list(question_id)
    ordered_scale = question_mapper.get_ordered_scale(question_id)
    result.calculate_overall(all_options=all_options, ordered_scale=ordered_scale)

    # Calculate segmentation
    personas_with_gt = [personas[i] for i in final_persona_indices]
    if personas_with_gt:
        for demographic_key in personas_with_gt[0]["demographics"].keys():
            segment_values = [personas[i]["demographics"].get(demographic_key) for i in final_persona_indices]
            result.calculate_segments(demographic_key, segment_values)

    return result


def validate_stateful_results(
    all_states: list,
    all_explanations: list,
    all_tiers: list,
    questions_to_validate: list,
    personas: list,
    question_mapper,
    min_n_for_gating: int = MIN_N_FOR_GATING,
    all_orders: list = None,
    all_probs: list = None,
):
    """Convert stateful per-persona results to per-question format and validate.

    Shared by the single-shot run and the batched/resumed run so the conversion + validation
    logic lives in exactly one place. Positional alignment holds by construction:
    all_states[i] / all_explanations[i] / all_tiers[i] correspond to personas[i].
    When `all_orders` is passed, all_orders[i] is the per-question presented-option order for
    persona i; when `all_probs` is passed, all_probs[i] is that persona's per-question
    option->probability map (only populated under `response_mode: verbalized_probs` or
    `weighted_draw`).

    Returns:
        (validation_results, all_responses_by_question, all_explanations_by_question,
         all_subscription_tiers_by_question, all_persona_indices_by_question,
         all_variation_ids_by_question, open_ended_question_ids,
         all_option_orders_by_question, all_probs_by_question)
    """
    validation_results = {}
    all_responses_by_question = {}
    all_explanations_by_question = {}
    all_subscription_tiers_by_question = {}
    all_persona_indices_by_question = {}
    all_variation_ids_by_question = {}
    all_option_orders_by_question = {}
    all_probs_by_question = {}
    open_ended_question_ids = []  # open-ended questions have no metric but are still exported

    for idx, question_config in enumerate(questions_to_validate, 1):
        question_id = question_config.id

        PipelineDisplay.section(f"Question {idx}/{len(questions_to_validate)}: {question_id}")

        # Extract answers for this question across all personas
        synthetic_responses = [state.get(question_id) for state in all_states]
        explanations = [exp_dict.get(question_id, "") for exp_dict in all_explanations]
        order_cells = (
            [order_dict.get(question_id) for order_dict in all_orders]
            if all_orders is not None else None
        )
        prob_cells = (
            [prob_dict.get(question_id) for prob_dict in all_probs]
            if all_probs is not None else None
        )
        subscription_tiers = all_tiers
        persona_indices = list(range(len(personas)))
        variation_ids = [0] * len(personas)  # n_variations=1, so all are variation 0

        # Filter out None (question not answered due to routing)
        valid_responses = []
        valid_explanations = []
        valid_orders = []
        valid_probs = []
        valid_tiers = []
        valid_persona_indices = []
        valid_variation_ids = []

        for i, response in enumerate(synthetic_responses):
            if response is not None:
                valid_responses.append(response)
                valid_explanations.append(explanations[i])
                if order_cells is not None:
                    valid_orders.append(order_cells[i])
                if prob_cells is not None:
                    valid_probs.append(prob_cells[i])
                valid_tiers.append(subscription_tiers[i])
                valid_persona_indices.append(persona_indices[i])
                valid_variation_ids.append(variation_ids[i])

        print(f"  Answered by {len(valid_responses)}/{len(personas)} personas (routing applied)")

        # Store for later export
        all_responses_by_question[question_id] = valid_responses
        all_explanations_by_question[question_id] = valid_explanations
        if order_cells is not None:
            all_option_orders_by_question[question_id] = valid_orders
        if prob_cells is not None:
            all_probs_by_question[question_id] = valid_probs
        all_subscription_tiers_by_question[question_id] = valid_tiers
        all_persona_indices_by_question[question_id] = valid_persona_indices
        all_variation_ids_by_question[question_id] = valid_variation_ids

        # Get question type and ground truth
        question_type = question_mapper.get_question_type(question_id)
        if question_type == "open_ended":
            # Excluded from validation metrics, but still rendered in respondent_details.
            open_ended_question_ids.append(question_id)
        ground_truth_list = [personas[i]["ground_truth"].get(question_id) for i in valid_persona_indices]

        # Validate using common logic (open-ended is excluded inside, returns None)
        result = validate_question_responses(
            question_id=question_id,
            question_type=question_type,
            synthetic_responses=valid_responses,
            ground_truth_responses=ground_truth_list,
            subscription_tiers=valid_tiers,
            persona_indices=valid_persona_indices,
            personas=personas,
            question_mapper=question_mapper,
            min_n_for_gating=min_n_for_gating,
        )

        if result is None:
            print(f"[WARN] No valid pairs for {question_id}, skipping")
            continue

        print(
            f"[OK] {result.distributional_metric_name}={result.distributional_metric:.3f} "
            f"| {individual_baseline_name(result.metric_bucket)}="
            f"{result.individual_baseline:.3f} "
            f"(n_valid={result.n_valid}, n_failed={result.n_failed})"
        )

        # Print segmentation keys
        if result.segment_results:
            for demographic_key in result.segment_results.keys():
                print(f"  Segmented by {demographic_key}")

        validation_results[question_id] = result

    return (
        validation_results,
        all_responses_by_question,
        all_explanations_by_question,
        all_subscription_tiers_by_question,
        all_persona_indices_by_question,
        all_variation_ids_by_question,
        open_ended_question_ids,
        all_option_orders_by_question,
        all_probs_by_question,
    )


from src.validation.excel_exporter import export_all_results
from src.utils.llm_factory import budget_halt_reason
from src.utils.progress import (
    TokenUsageRecorder,
    print_token_summary,
    write_error_jsonl,
    write_token_json,
)

logger = logging.getLogger(__name__)


class PipelineDisplay:
    """Display formatting for pipeline output"""
    WIDTH = 80

    @staticmethod
    def header(text, char="="):
        print(f"\n{char * PipelineDisplay.WIDTH}")
        print(text.center(PipelineDisplay.WIDTH))
        print(char * PipelineDisplay.WIDTH)

    @staticmethod
    def section(text):
        print(f"\n{'-' * PipelineDisplay.WIDTH}")
        print(text)
        print("-" * PipelineDisplay.WIDTH)


def run_excel_validation_pipeline(config_path: str,
                                   sample_size: int = None,
                                   question_ids: list = None,
                                   use_cached_personas: bool = True,
                                   checkpoint_dir: str = None,
                                   run_id: str = None,
                                   resume: bool = False):
    """Run complete Excel validation pipeline.

    Checkpoint args (both modes; the unit differs because the runners differ):
        checkpoint_dir: base dir for checkpoints; enables resumable execution
        run_id: identifier for this checkpoint run (subdir under checkpoint_dir/)
        resume: skip work already saved to the checkpoint dir

    Stateful runs checkpoint one batch per full concurrency wave (batch size =
    llm.max_concurrency) and resume per persona. Stateless runs checkpoint one file per question
    and resume per (question, respid) cell, since a stateless cell has no conversation history and
    is independently re-runnable.
    """
    PipelineDisplay.header("EXCEL VALIDATION PIPELINE")
    print(f"Loading config: {config_path}")

    try:
        config = load_survey_config(config_path)
    except Exception as e:
        print(f"[ERROR] Failed to load config: {e}")
        return None

    print(f"\n[OK] Configuration loaded")
    print(f"  Survey: {config.survey.name}")
    print(f"  Data Source: {config.survey.data_source.excel_file}")
    print(f"  Questions: {len(config.survey.questions)}")

    output_dir = config.execution.output_dir
    os.makedirs(output_dir, exist_ok=True)

    PipelineDisplay.header("STEP 1: LOADING DATA", "-")

    try:
        question_mapper = QuestionMapper(
            config.survey.data_source.demographic_mapping,
            config.survey.data_source.question_mapping,
            data_format=config.survey.data_source.data_format
        )
        question_mapper.validate_question_types(config.survey.questions)

        loader = ExcelSurveyLoader(
            config.survey.data_source.excel_file,
            question_mapper,
            preprocess=config.survey.data_source.preprocess
        )

        effective_sample = sample_size if sample_size is not None else config.survey.data_source.max_rows
        respondents = loader.load_respondents(
            sheet_name=config.survey.data_source.sheet_name,
            max_rows=effective_sample
        )

        print(f"[OK] Loaded {len(respondents)} respondents")

    except Exception as e:
        print(f"[ERROR] Failed to load data: {e}")
        logger.exception("Failed to load data")
        return None

    PipelineDisplay.header("STEP 2: LOADING/GENERATING PERSONAS", "-")

    personas = None
    # SECURITY-REVIEW: Configured paths control local cache reads/writes; survey configs are
    # trusted operator input and must not be accepted from untrusted users.
    persona_cache_path = get_persona_cache_path(output_dir, config.persona_cache_path)

    if use_cached_personas:
        personas = load_personas_from_excel(persona_cache_path, respondents)

    if personas is None:
        try:
            personas = generate_personas_from_respondents(
                respondents,
                screener_summarization_prompt=config.personas.screener_summarization_prompt,
                model=config.llm.model,
                temperature=config.llm.get_persona_temperature(),
                max_concurrency=config.llm.max_concurrency,
                max_retries=config.llm.max_retries,
            )

            print(f"[OK] Generated {len(personas)} personas")
            save_personas_to_excel(personas, persona_cache_path)

        except Exception as e:
            print(f"[ERROR] Failed to generate personas: {e}")
            logger.exception("Failed to generate personas")
            return None

    display_sample_personas(personas, n=3)

    PipelineDisplay.header("STEP 3: VALIDATING RESPONSES", "-")

    questions_to_validate = (
        [q for q in config.survey.questions if q.id in question_ids]
        if question_ids
        else config.survey.questions
    )

    print(f"Validating {len(questions_to_validate)} questions...\n")

    # Determine survey mode
    memory_mode = getattr(config, 'memory_mode', 'stateless')
    print(f"[INFO] Survey mode: {memory_mode}")

    validation_results = {}
    all_responses_by_question = {}
    all_explanations_by_question = {}
    all_subscription_tiers_by_question = {}
    all_persona_indices_by_question = {}
    all_variation_ids_by_question = {}
    all_option_orders_by_question = {}  # populated by stateful validation; empty for stateless
    all_probs_by_question = {}  # only under response_mode: verbalized_probs / weighted_draw
    open_ended_question_ids = []  # populated by stateful validation; empty for stateless runs
    error_records = []
    failed_persona_indices = set()
    # Set to the spend-cap reason when a run stops short, so the closing summary says "HALTED"
    # instead of "COMPLETE" -- a partial panel that reads as finished is the failure this guards.
    budget_halted = None
    # Owned here, not by the runner: the checkpointed stateful path calls the runner once per cohort,
    # so a recorder created down there would report only the last cohort. Stays empty on the
    # stateless path, which is not wired to it (nothing there has a cacheable prefix to measure).
    token_recorder = TokenUsageRecorder()

    # One router for BOTH modes: stateful uses the full walk (skip/show-if/mask/pipe), stateless
    # uses only `is_asked` to honor between-subject arm assignments. Building it once keeps the
    # arm gate defined in a single place instead of once per mode.
    from src.core.question_router import QuestionRouter
    router = QuestionRouter(getattr(config, 'routing_rules', None), question_mapper)

    # Branch based on memory mode
    if memory_mode == "full":
        # ===== STATEFUL MODE =====
        print("[INFO] Using stateful mode (per-persona sequential with routing)")

        from src.core.survey_runner_excel import run_stateful_survey_for_all_personas

        question_list = [q.id for q in config.survey.questions]

        def _run_cohort(cohort_personas):
            """Run the stateful survey over one cohort of personas (unchanged runner)."""
            return run_stateful_survey_for_all_personas(
                cohort_personas,
                question_list,
                question_mapper,
                router,
                config.survey_prompt,
                model=config.llm.model,
                temperature=config.llm.get_survey_temperature(),
                subscription_tiers=config.llm.subscription_tiers,
                include_request_id=config.include_request_id,
                max_concurrency=config.llm.max_concurrency,
                max_retries=config.llm.max_retries,
                preserve_anchors=config.preserve_anchors,
                chain_own_answers=config.chain_own_answers,
                batch_grids=config.batch_grids,
                prompt_cache_key_by_respid=config.prompt_cache_key_by_respid,
                response_mode=config.response_mode,
                token_recorder=token_recorder,
            )

        if checkpoint_dir:
            # ----- Batched, resumable execution -----
            from src.utils import survey_checkpoint as ckpt

            # One checkpoint batch per full concurrency wave.
            effective_batch = config.llm.max_concurrency or len(personas)
            run_dir = ckpt.init_run_dir(checkpoint_dir, run_id)
            manifest = ckpt.load_manifest(run_dir)
            # Mirror of the stateless branch's guard. Reachable now that a survey can move between
            # the two paths: `prior_answers` left a question-scoped dir behind. Without this the
            # `batches` count below is 0, so a stateful run appends its own keys beside the
            # existing `questions` — and `rerun_failed` dispatches on which key is present, so it
            # would repair a mixed dir with the wrong unit.
            if manifest.get("questions") or manifest.get("completed_pairs"):
                raise RuntimeError(
                    f"Checkpoint dir '{run_dir}' holds a stateless, per-question checkpoint; a "
                    f"stateful run checkpoints per persona and cannot share it. Use a new "
                    f"--run-id."
                )
            existing_batches = len(manifest.get("batches", []))

            if existing_batches and not resume:
                raise RuntimeError(
                    f"Checkpoint dir '{run_dir}' already has {existing_batches} batch(es). "
                    f"Re-run with --resume to continue it, or use a new --run-id / delete the "
                    f"dir to start fresh. Refusing to mix a fresh run into existing batches."
                )

            done = ckpt.completed_respids(run_dir) if resume else set()
            if resume and done:
                print(f"[INFO] Resuming: {len(done)} personas already checkpointed, skipping them")

            pending = [(i, p) for i, p in enumerate(personas)
                       if ckpt.norm_respid(p["respid"]) not in done]
            print(f"[INFO] Checkpointed run: {len(pending)} pending, cohort_size={effective_batch}, "
                  f"run_dir={run_dir}")

            for offset in range(0, len(pending), effective_batch):
                chunk = pending[offset:offset + effective_batch]
                batch_num = existing_batches + (offset // effective_batch) + 1
                PipelineDisplay.section(
                    f"Batch {batch_num}: personas {chunk[0][0]}..{chunk[-1][0]} ({len(chunk)})"
                )
                cohort = [p for _, p in chunk]
                c_states, c_expl, c_tiers, c_probs, c_orders, c_errors = _run_cohort(cohort)

                # Bucket each cohort error record under its persona by respid. The bucket is
                # only a storage container — each record carries its own respid — so any record
                # that fails to match a persona (None/type-drifted respid) is appended to the
                # first record's bucket rather than dropped, keeping the flattened error set
                # identical to a single-shot run's recorder.records.
                records = []
                attributed = set()
                for (global_idx, persona), state, expl, tier, probs, orders in zip(
                    chunk, c_states, c_expl, c_tiers, c_probs, c_orders,
                ):
                    respid = ckpt.norm_respid(persona["respid"])
                    err_recs = []
                    for i, r in enumerate(c_errors):
                        if ckpt.norm_respid(r.get("respid")) == respid:
                            err_recs.append(r)
                            attributed.add(i)
                    records.append({
                        "respid": respid,
                        "global_index": global_idx,
                        # A failed cell inside a finished walk is a failed walk too. `status` is what
                        # save_batch reads to decide "complete", so consulting only
                        # `__persona_error__` marked such a persona done and left its `LLM Error`
                        # cells behind a manifest that no --resume would revisit -- the stateless
                        # flavour never marks a failed cell complete, and this is that same contract.
                        # The re-run repeats the whole walk (a stateful cell cannot be spliced), so
                        # expect a little drift in the persona's other answers; measured at 12 cells
                        # of 108x2 when repairing 2 filtered cells in the twin2k chained arm.
                        "status": "aborted" if ("__persona_error__" in expl or err_recs) else "ok",
                        "state": state,
                        "explanations": expl,
                        "tier": tier,
                        "orders": orders,
                        "probs": probs,
                        "error_records": err_recs,
                    })
                leftover = [r for i, r in enumerate(c_errors) if i not in attributed]
                if leftover:
                    records[0]["error_records"].extend(leftover)
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                ckpt.save_batch(run_dir, batch_num, records, timestamp=ts)
                print(f"  [checkpoint] saved batch {batch_num} ({len(records)} personas)")

                # A spend cap has latched (llm_factory): every remaining call would fail without
                # reaching the API. Stop here rather than churning the rest of the panel into
                # aborted personas and one error record per cell, and report the day's token
                # spend on the way out -- that summary is the reason to look at this exit.
                halted = budget_halt_reason()
                if halted is not None:
                    print(
                        f"\n[BUDGET] Stopped after batch {batch_num}: {halted}\n"
                        f"[BUDGET] Personas that finished are checkpointed in {run_dir}. Re-run the "
                        f"same command with --resume once the cap resets; only personas not marked "
                        f"complete are re-run (a stateful cell cannot be spliced, so an "
                        f"interrupted persona repeats its whole walk)."
                    )
                    halt_summary = token_recorder.summary()
                    if halt_summary:
                        halt_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                        print_token_summary(
                            halt_summary, write_token_json(halt_summary, output_dir, halt_ts)
                        )
                    return None

            # Reconstruct the full result set from all checkpoints, in global_index order.
            all_records = ckpt.load_all_batches(run_dir)
            # Fail loud: export is positionally index-aligned to personas.
            got_indices = [r["global_index"] for r in all_records]
            if got_indices != list(range(len(personas))):
                raise RuntimeError(
                    f"Checkpoint integrity check failed: reconstructed {len(all_records)} "
                    f"personas with indices != 0..{len(personas) - 1}. Refusing to export "
                    f"mispaired data. Re-run with --resume to fill gaps."
                )
            all_states = [r["state"] for r in all_records]
            all_explanations = [r["explanations"] for r in all_records]
            all_tiers = [r["tier"] for r in all_records]
            all_orders = [r.get("orders", {}) for r in all_records]
            # `.get` with a default: batches written before `probs` was checkpointed carry no such
            # key, and a pre-change checkpoint dir must stay resumable.
            all_probs = [r.get("probs", {}) for r in all_records]
            error_records = [er for r in all_records for er in r.get("error_records", [])]
        else:
            # ----- Single-shot execution (unchanged behavior) -----
            all_states, all_explanations, all_tiers, all_probs, all_orders, error_records = (
                _run_cohort(personas)
            )
            # The whole panel runs as one `.batch()` here, so there is no batch boundary to stop
            # at -- by the time we know the cap latched, the personas after it are already
            # aborted. Say so anyway: otherwise a panel of "LLM Error" cells looks like a model
            # or prompt problem instead of a spend cap, which is the wrong thing to go debug.
            budget_halted = budget_halt_reason()
            if budget_halted is not None:
                print(
                    f"\n[BUDGET] A spend cap latched mid-run: {budget_halted}\n"
                    f"[BUDGET] Personas after that point are aborted and this run is not "
                    f"checkpointed, so nothing is resumable. Re-run with --checkpoint-dir once "
                    f"the cap resets."
                )

        failed_persona_indices = {
            i for i, exp_dict in enumerate(all_explanations) if "__persona_error__" in exp_dict
        }

        # Convert stateful results to per-question format for validation
        PipelineDisplay.section("Converting stateful results to validation format")

        (
            validation_results,
            all_responses_by_question,
            all_explanations_by_question,
            all_subscription_tiers_by_question,
            all_persona_indices_by_question,
            all_variation_ids_by_question,
            open_ended_question_ids,
            all_option_orders_by_question,
            all_probs_by_question,
        ) = validate_stateful_results(
            all_states,
            all_explanations,
            all_tiers,
            questions_to_validate,
            personas,
            question_mapper,
            min_n_for_gating=config.min_n_for_gating,
            all_orders=all_orders,
            all_probs=all_probs,
        )

    else:
        # ===== STATELESS MODE =====
        print("[INFO] Using stateless mode (batch processing, no routing)")

        from src.utils import survey_checkpoint as ckpt
        from src.utils.progress import RunErrorRecorder, print_error_summary

        # One recorder for the whole run: the runner records each failed (respid, question) in
        # place, so a transient error becomes a line in run_errors_*.jsonl instead of a silent
        # "Error" cell that only shows up as a dip in n_valid.
        recorder = RunErrorRecorder()

        # Question-scoped checkpointing. Inert unless --checkpoint-dir is passed, so callers and
        # other non-checkpointed stateless runs keep exactly their current control flow.
        run_dir = None
        done = {}
        if checkpoint_dir:
            run_dir = ckpt.init_run_dir(checkpoint_dir, run_id)
            manifest = ckpt.load_manifest(run_dir)
            # A run dir carries one flavour only — readers (and rerun_failed) dispatch on which
            # manifest key is present, so a mixed dir would be repaired with the wrong unit.
            if manifest.get("batches") or manifest.get("completed_respids"):
                raise RuntimeError(
                    f"Checkpoint dir '{run_dir}' holds a stateful, per-persona checkpoint; a "
                    f"stateless run checkpoints per question and cannot share it. Use a new "
                    f"--run-id."
                )
            existing = manifest.get("questions", {})
            if existing and not resume:
                raise RuntimeError(
                    f"Checkpoint dir '{run_dir}' already has {len(existing)} question(s). "
                    f"Re-run with --resume to continue it, or use a new --run-id / delete the "
                    f"dir to start fresh. Refusing to mix a fresh run into existing questions."
                )
            done = ckpt.completed_pairs(run_dir) if resume else {}
            if done:
                n_cells = sum(len(v) for v in done.values())
                print(f"[INFO] Resuming: {n_cells} cell(s) across {len(done)} question(s) "
                      f"already checkpointed, skipping them")
            print(f"[INFO] Checkpointed run: run_dir={run_dir}")

            # Resume and repair both join on respid, so a duplicate would silently claim another
            # persona's answers. Fail before spending a single call.
            all_respids = [ckpt.norm_respid(p["respid"]) for p in personas]
            if len(set(all_respids)) != len(all_respids):
                raise RuntimeError(
                    "Checkpointing requires unique respids, but this panel has duplicates. "
                    "Refusing to checkpoint: resume matches saved answers by respid."
                )

        for idx, question_config in enumerate(questions_to_validate, 1):
            question_id = question_config.id

            # Same spend-cap exit as the stateful cohort loop, at the unit this path checkpoints:
            # one question. Checked at the top of the body, not the bottom, because a halted
            # question fails validation and takes the `except ... continue` below -- a bottom
            # check would be skipped by exactly the iteration that latched. Every remaining call
            # would fail without reaching the API, so stop instead of churning the rest of the
            # panel into "Error" cells and one error record per cell.
            budget_halted = budget_halt_reason()
            if budget_halted is not None:
                print(
                    f"\n[BUDGET] Stopped before question {idx}/{len(questions_to_validate)} "
                    f"({question_id}): {budget_halted}"
                )
                if run_dir:
                    print(
                        f"[BUDGET] Questions that finished are checkpointed in {run_dir}. Re-run "
                        f"the same command with --resume once the cap resets; only cells not "
                        f"marked complete are re-run."
                    )
                else:
                    print(
                        "[BUDGET] This run is not checkpointed, so the questions below are not "
                        "saved. Re-run with --checkpoint-dir once the cap resets."
                    )
                break

            PipelineDisplay.section(f"Question {idx}/{len(questions_to_validate)}: {question_id}")

            try:
                # Between-subject arms: ask only the personas assigned this arm. `asked_idx` maps
                # positions in `asked` back to `personas`, which the exporter and segmentation
                # both index -- so the remap after the run is load-bearing, not cosmetic.
                # Identity for every question with no `condition_group`.
                asked_idx = [
                    i for i, p in enumerate(personas)
                    if router.is_asked(question_id, p.get("condition_assignments", {}))
                ]
                if not asked_idx:
                    print(f"[WARN] {question_id}: no persona is assigned this arm, skipping")
                    continue
                if len(asked_idx) < len(personas):
                    print(f"  Condition arm: asking {len(asked_idx)}/{len(personas)} personas")
                asked = [personas[i] for i in asked_idx]

                # Resume skips the cells already on disk for this question; without a checkpoint
                # `pending_idx is asked_idx` and everything below is the single-run path.
                done_respids = done.get(question_id, set())
                pending_idx = (
                    [i for i in asked_idx
                     if ckpt.norm_respid(personas[i]["respid"]) not in done_respids]
                    if done_respids else asked_idx
                )
                if done_respids:
                    print(f"  Resume: {len(pending_idx)}/{len(asked_idx)} personas still pending")

                if pending_idx:
                    (fresh_responses, fresh_explanations, fresh_tiers, fresh_persona_indices,
                     fresh_variation_ids, question_type) = run_survey_for_question(
                        [personas[i] for i in pending_idx],
                        question_id,
                        question_mapper,
                        config.survey_prompt,
                        model=config.llm.model,
                        temperature=config.llm.get_survey_temperature(),
                        n_variations=config.llm.n_variations,
                        subscription_tiers=config.llm.subscription_tiers,
                        max_concurrency=config.llm.max_concurrency,
                        max_retries=config.llm.max_retries,
                        preserve_anchors=config.preserve_anchors,
                        error_recorder=recorder,
                    )
                else:
                    print("  Resume: fully checkpointed, no calls needed")
                    fresh_responses, fresh_explanations, fresh_tiers = [], [], []
                    fresh_persona_indices, fresh_variation_ids = [], []
                    question_type = (
                        ckpt.question_type_for(run_dir, question_id)
                        or question_mapper.get_question_type(question_id)
                    )

                # Fresh rows are joined positionally (`fresh_persona_indices` index into
                # `pending_idx`), never by respid — that keeps the no-checkpoint path identical to
                # a straight lift. Only the checkpoint join uses respid.
                rows_by_persona = {}
                for k, pos in enumerate(fresh_persona_indices):
                    rows_by_persona.setdefault(pending_idx[pos], []).append({
                        "respid": ckpt.norm_respid(personas[pending_idx[pos]]["respid"]),
                        "response": fresh_responses[k],
                        "explanation": fresh_explanations[k],
                        "tier": fresh_tiers[k],
                        "variation_id": fresh_variation_ids[k],
                    })
                if done_respids:
                    saved_rows = {}
                    for row in ckpt.load_question(run_dir, question_id):
                        saved_rows.setdefault(ckpt.norm_respid(row["respid"]), []).append(row)
                    for i in asked_idx:
                        if i in rows_by_persona:
                            continue
                        rid = ckpt.norm_respid(personas[i]["respid"])
                        if rid not in saved_rows:
                            raise RuntimeError(
                                f"Checkpoint gap for {question_id}: respid {rid} is marked "
                                f"completed in the manifest but has no rows on disk. Refusing to "
                                f"export a hole; delete the run dir and re-run this question."
                            )
                        rows_by_persona[i] = saved_rows[rid]

                # Merge in canonical `asked_idx` order, so the output ordering is "per persona,
                # n_variations each" over the full asked panel — what replicate_ground_truth
                # below assumes — whether a row came from this run or a checkpoint.
                synthetic_responses, explanations, subscription_tiers = [], [], []
                persona_indices, variation_ids, merged_rows = [], [], []
                for i in asked_idx:
                    if i not in rows_by_persona:
                        raise RuntimeError(
                            f"{question_id}: no rows for asked persona index {i} "
                            f"(respid {personas[i]['respid']}). Refusing to export a panel that "
                            f"silently drops a persona."
                        )
                    for row in rows_by_persona[i]:
                        synthetic_responses.append(row["response"])
                        explanations.append(row["explanation"])
                        subscription_tiers.append(row["tier"])
                        persona_indices.append(i)
                        variation_ids.append(row["variation_id"])
                        merged_rows.append(row)

                if run_dir is not None:
                    ckpt.save_question(
                        run_dir, question_id, merged_rows,
                        question_type=question_type,
                        timestamp=datetime.now().strftime("%Y%m%d_%H%M%S"),
                    )
                    print(f"  [checkpoint] saved {question_id} ({len(merged_rows)} rows)")

                all_responses_by_question[question_id] = synthetic_responses
                all_explanations_by_question[question_id] = explanations
                all_subscription_tiers_by_question[question_id] = subscription_tiers
                all_persona_indices_by_question[question_id] = persona_indices
                all_variation_ids_by_question[question_id] = variation_ids

                all_tier_counts = Counter(subscription_tiers)
                print(f"  Subscription tier distribution (all variations): {dict(all_tier_counts)}")

                # Replicate ground truth for multi-variation comparison. Over `asked`, not
                # `personas`: it must match `_run_survey_multi_var`'s output ordering (per
                # persona, `n_variations` each), which ran on `asked`.
                ground_truth_responses_replicated = replicate_ground_truth(
                    asked, question_id, config.llm.n_variations
                )

                print(f"  Validating with all {config.llm.n_variations} variations: {len(synthetic_responses)} total responses")

                # Validate using common logic
                result = validate_question_responses(
                    question_id=question_id,
                    question_type=question_type,
                    synthetic_responses=synthetic_responses,
                    ground_truth_responses=ground_truth_responses_replicated,
                    subscription_tiers=subscription_tiers,
                    persona_indices=persona_indices,
                    personas=personas,
                    question_mapper=question_mapper,
                    min_n_for_gating=config.min_n_for_gating,
                )

                if result is None:
                    print(f"[WARN] No valid pairs for {question_id}, skipping")
                    continue

                print(
                    f"[OK] {result.distributional_metric_name}={result.distributional_metric:.3f} "
                    f"| {individual_baseline_name(result.metric_bucket)}="
                    f"{result.individual_baseline:.3f} "
                    f"(n_valid={result.n_valid}, n_failed={result.n_failed})"
                )

                # Print segmentation keys
                if result.segment_results:
                    for demographic_key in result.segment_results.keys():
                        print(f"  Segmented by {demographic_key}")

                validation_results[question_id] = result

            except Exception as e:
                print(f"[ERROR] Failed to validate {question_id}: {e}")
                logger.exception("Failed to validate %s", question_id)
                # Record it so a question lost wholesale shows up in run_errors_*.jsonl rather
                # than only as a missing column in the summary.
                recorder.record_failure(None, question_id, "question", e)
                continue

        error_records = recorder.records
        print_error_summary(recorder)

    token_summary = token_recorder.summary()

    timestamp = None
    if config.execution.save_output or error_records or token_summary:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if error_records:
            error_jsonl = write_error_jsonl(error_records, output_dir, timestamp)
            if error_jsonl:
                print(f"[OK] Error log saved to: {error_jsonl}")
        if token_summary:
            print_token_summary(token_summary, write_token_json(token_summary, output_dir, timestamp))

    if config.execution.save_output:
        PipelineDisplay.header("STEP 4: SAVING RESULTS", "-")

        try:
            detail_excel, summary_excel = export_all_results(
                personas,
                validation_results,
                output_dir,
                timestamp,
                all_responses_by_question,
                all_explanations_by_question,
                all_subscription_tiers_by_question,
                all_persona_indices_by_question,
                all_variation_ids_by_question,
                include_screener=config.personas.screener_summarization_prompt is not None,
                include_tiers=bool(config.llm.subscription_tiers),
                failed_persona_indices=failed_persona_indices,
                open_ended_question_ids=open_ended_question_ids,
                all_option_orders_by_question=(
                    all_option_orders_by_question if memory_mode == "full" else None
                ),
                # Gated on the mode, not on emptiness: passing this on a hard_choice run would add
                # an all-None `<qid>_probs` column to every baseline export and break the anchor
                # guarantee report.py rests on (a pre-D-5 run must score byte-identically).
                # `weighted_draw` elicits the same vector and needs the column even more: it is the
                # only record of what `_synthetic` was drawn from.
                all_probs_by_question=(
                    all_probs_by_question
                    if config.response_mode in ("verbalized_probs", "weighted_draw") else None
                ),
            )
            print(f"[OK] Detailed Excel saved to: {detail_excel}")
            print(f"[OK] Summary Excel saved to: {summary_excel}")

        except Exception as e:
            print(f"[ERROR] Failed to save Excel results: {e}")
            logger.exception("Failed to save Excel results")
    else:
        print("\n[INFO] save_output is false — skipping Excel export")

    PipelineDisplay.header(
        "PIPELINE HALTED (SPEND CAP)" if budget_halted else "PIPELINE COMPLETE", "="
    )

    print("\nSummary:")
    print(f"  Respondents Processed: {len(respondents)}")
    print(f"  Personas Generated: {len(personas)}")
    print(f"  Questions Validated: {len(validation_results)} of {len(questions_to_validate)}")
    if budget_halted:
        # The numbers above are real but partial. Say why here so the export is not read as a
        # finished panel.
        print(f"  INCOMPLETE -- spend cap latched: {budget_halted}")

    if validation_results:
        avg_dist = sum(r.distributional_metric for r in validation_results.values()) / len(validation_results)
        print(f"  Average Distributional Metric: {avg_dist:.3f}")

    if config.execution.save_output:
        print("\nOutput Files:")
        print(f"  {output_dir}/respondent_details_*.xlsx  (One-to-one respondent mapping)")
        print(f"  {output_dir}/validation_summary_*.xlsx  (Validation metrics & segments)")

    print("\n" + "="*80 + "\n")

    if budget_halted:
        # `main()` maps a None return to exit 1, which is the whole point: a halted run must not
        # report success to whatever launched it, however much of the panel got exported above.
        # The checkpointed stateful loop already returns None the same way.
        return None

    return validation_results


def main():
    logging.basicConfig(level=logging.ERROR)

    parser = argparse.ArgumentParser(
        description="Validate synthetic survey responses against Excel ground truth",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py --config configs/excel_validation.yaml --questions MU1
  python main.py --config configs/excel_validation.yaml --questions MU2
  python main.py --config configs/excel_validation.yaml --no-cache
  python main.py --config configs/excel_validation.yaml --sample 100
        """
    )

    parser.add_argument("--config", required=True, help="Path to config YAML file")
    parser.add_argument("--sample", type=int, help="Limit to first N respondents (for testing)")
    parser.add_argument("--questions", help="Comma-separated list of question IDs to validate (e.g., MU1,MU2)")
    parser.add_argument("--no-cache", action="store_true", help="Skip persona cache and always regenerate personas")
    parser.add_argument("--checkpoint-dir", help="Enable resumable runs; base dir for checkpoints. Stateful mode checkpoints per batch of personas (batch size = llm.max_concurrency); stateless mode checkpoints per question and resumes per (question, respid) cell.")
    parser.add_argument("--run-id", help="Checkpoint run identifier (subdir under <checkpoint-dir>/); defaults to the config filename stem")
    parser.add_argument("--resume", action="store_true", help="Skip work already saved in the checkpoint dir (personas in stateful mode, (question, respid) cells in stateless mode)")

    args = parser.parse_args()

    # --resume / --run-id only do anything with --checkpoint-dir; fail loud rather than
    # silently running a full single-shot re-run when the user expected to resume.
    if not args.checkpoint_dir and (args.resume or args.run_id):
        parser.error("--resume and --run-id require --checkpoint-dir")

    # Default run-id to the config filename stem (deterministic, so --resume finds the same dir).
    run_id = args.run_id or os.path.splitext(os.path.basename(args.config))[0]

    question_ids = None
    if args.questions:
        question_ids = [q.strip() for q in args.questions.split(",")]

    results = run_excel_validation_pipeline(
        config_path=args.config,
        sample_size=args.sample,
        question_ids=question_ids,
        use_cached_personas=not args.no_cache,
        checkpoint_dir=args.checkpoint_dir,
        run_id=run_id,
        resume=args.resume,
    )

    if results is None:
        print("\n[ERROR] Pipeline failed. Check errors above.")
        return 1
    print("\n[OK] Pipeline completed successfully!")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
