"""Export detailed validation results to Excel with one-to-one respondent mapping"""

import json
import pandas as pd
from typing import List, Dict, Optional, Set
from src.validation.response_validator import ValidationResult


def _format_ground_truth(ground_truth, question_type: str):
    """Render a ground-truth value for the detail sheet, one rule for every path.

    Multi-select ground truth is a list, and the early-return paths used to write it raw while
    the normal path joined it — so one column carried two encodings (`Q13` etc. came out as
    `['a', 'b']`), decided by whether the *synthetic* side was routed out. `single` ground truth
    is already scalar and `open_ended` is free text that a ", ".join would split into characters,
    so both pass through untouched.
    """
    if question_type in ("single", "open_ended"):
        return ground_truth
    return ", ".join(ground_truth) if isinstance(ground_truth, list) else str(ground_truth)


def _set_question_columns(
    row: dict,
    question_id: str,
    result: ValidationResult,
    ground_truth,
    persona_idx: int,
    variation_id: int,
    all_responses_by_question: Optional[Dict[str, List]],
    all_explanations_by_question: Optional[Dict[str, List[str]]],
    all_subscription_tiers_by_question: Optional[Dict[str, List[str]]],
    all_persona_indices_by_question: Optional[Dict[str, List[int]]],
    all_variation_ids_by_question: Optional[Dict[str, List[int]]],
    all_probs_by_question: Optional[Dict[str, List]] = None,
    include_tiers: bool = True,
    failed_persona_indices: Optional[Set[int]] = None,
    all_option_orders_by_question: Optional[Dict[str, List]] = None,
) -> None:
    """Populate per-question columns on a respondent detail row."""
    prefix = question_id

    if ground_truth is None:
        row[f'{prefix}_synthetic'] = None
        row[f'{prefix}_ground_truth'] = None
        row[f'{prefix}_explanation'] = None
        if all_probs_by_question is not None:
            row[f'{prefix}_probs'] = None
        if all_option_orders_by_question is not None:
            row[f'{prefix}_option_order'] = None
        if include_tiers:
            row[f'{prefix}_subscription_tier'] = None
        return

    if not all_persona_indices_by_question or question_id not in all_persona_indices_by_question:
        row[f'{prefix}_synthetic'] = "N/A"
        row[f'{prefix}_ground_truth'] = _format_ground_truth(ground_truth, result.question_type)
        row[f'{prefix}_explanation'] = "N/A"
        if include_tiers:
            row[f'{prefix}_subscription_tier'] = "N/A"
        return

    persona_indices = all_persona_indices_by_question[question_id]
    variation_ids = all_variation_ids_by_question[question_id]
    responses = all_responses_by_question[question_id]
    explanations = all_explanations_by_question.get(question_id, [])
    tiers = all_subscription_tiers_by_question.get(question_id, [])

    response_idx = next(
        (
            idx
            for idx, (p_idx, v_id) in enumerate(zip(persona_indices, variation_ids))
            if p_idx == persona_idx and v_id == variation_id
        ),
        None,
    )

    if response_idx is None or response_idx >= len(responses):
        # Persona has ground truth but no synthetic response: the survey never asked
        # this question (routing skip / grid mask), not a genuine LLM error.
        if persona_idx in (failed_persona_indices or set()):
            row[f'{prefix}_synthetic'] = "Persona aborted"
        else:
            row[f'{prefix}_synthetic'] = "Skipped (not routed)"
        row[f'{prefix}_ground_truth'] = _format_ground_truth(ground_truth, result.question_type)
        row[f'{prefix}_explanation'] = None
        if all_probs_by_question is not None:
            row[f'{prefix}_probs'] = None
        if all_option_orders_by_question is not None:
            row[f'{prefix}_option_order'] = None
        if include_tiers:
            row[f'{prefix}_subscription_tier'] = None
        return

    synthetic_response = responses[response_idx]

    if result.question_type == "single":
        # Display label for a genuine LLM failure (sentinel "Error"); distinct from
        # "Skipped (not routed)". n_failed is computed upstream from the raw sentinel.
        row[f'{prefix}_synthetic'] = (
            "LLM Error" if synthetic_response == "Error" else synthetic_response
        )
    elif result.question_type == "open_ended":
        # Free text: keep the string as-is (don't ", ".join it into characters).
        row[f'{prefix}_synthetic'] = (
            "LLM Error" if synthetic_response == "Error" else synthetic_response
        )
    else:
        if synthetic_response == ["Error"]:
            synthetic_str = "LLM Error"
        else:
            synthetic_str = ", ".join(synthetic_response) if isinstance(synthetic_response, list) else str(synthetic_response)
        row[f'{prefix}_synthetic'] = synthetic_str

    row[f'{prefix}_ground_truth'] = _format_ground_truth(ground_truth, result.question_type)

    row[f'{prefix}_explanation'] = (
        explanations[response_idx] if response_idx < len(explanations) else "N/A"
    )
    if all_probs_by_question is not None:
        probs_list = all_probs_by_question.get(question_id, [])
        prob_val = probs_list[response_idx] if response_idx < len(probs_list) else None
        row[f'{prefix}_probs'] = (
            json.dumps(prob_val, ensure_ascii=False) if isinstance(prob_val, dict) else None
        )
    if all_option_orders_by_question is not None:
        orders_list = all_option_orders_by_question.get(question_id, [])
        order_val = orders_list[response_idx] if response_idx < len(orders_list) else None
        row[f'{prefix}_option_order'] = (
            json.dumps(order_val, ensure_ascii=False) if isinstance(order_val, list) else None
        )
    if include_tiers:
        row[f'{prefix}_subscription_tier'] = (
            tiers[response_idx] if response_idx < len(tiers) else "N/A"
        )


def generate_respondent_detail_excel(
    personas: List[dict],
    validation_results: Dict[str, ValidationResult],
    output_path: str,
    all_responses_by_question: Optional[Dict[str, List]] = None,
    all_explanations_by_question: Optional[Dict[str, List[str]]] = None,
    all_subscription_tiers_by_question: Optional[Dict[str, List[str]]] = None,
    all_persona_indices_by_question: Optional[Dict[str, List[int]]] = None,
    all_variation_ids_by_question: Optional[Dict[str, List[int]]] = None,
    all_probs_by_question: Optional[Dict[str, List]] = None,
    include_tiers: bool = True,
    failed_persona_indices: Optional[Set[int]] = None,
    open_ended_question_ids: Optional[List[str]] = None,
    all_option_orders_by_question: Optional[Dict[str, List]] = None,
):
    """Generate Excel file with ALL variations per respondent

    Creates an Excel file where each row represents ONE variation of a respondent:
    - If n_variations=2, each respondent gets 2 rows
    - Respondent ID + variation_id identify each row uniquely
    - Demographics (age, income, family_type, etc.)
    - For each survey question:
        - Synthetic response (for this variation)
        - Ground truth response (same for all variations)
        - Choice explanation
        - Subscription tier (only when include_tiers)

    Args:
        personas: List of persona dictionaries
        validation_results: Dictionary of {question_id: ValidationResult}
        output_path: Path to save Excel file
        all_responses_by_question: Dict of {question_id: list of ALL synthetic responses (all variations)}
        all_explanations_by_question: Dict of {question_id: list of ALL explanations}
        all_subscription_tiers_by_question: Dict of {question_id: list of ALL subscription tiers}
        all_persona_indices_by_question: Dict of {question_id: list of persona indices}
        all_variation_ids_by_question: Dict of {question_id: list of variation IDs}
        include_tiers: Emit per-question subscription_tier columns (opt-in prompt feature)
    """
    print("\nGenerating detailed respondent Excel report (with all variations)...")

    # Open-ended questions have no ValidationResult (no metric), so they're absent from
    # validation_results and would be dropped from the sheet. Render them with a stand-in
    # result carrying only the question type; response/ground-truth data is already retained.
    extra_results = {
        qid: ValidationResult(qid, "open_ended")
        for qid in (open_ended_question_ids or [])
        if qid not in validation_results
    }
    detail_results = {**validation_results, **extra_results}

    # Determine total number of rows (personas × variations)
    if all_variation_ids_by_question:
        first_question_id = next(iter(all_variation_ids_by_question))
        total_variations = len(all_variation_ids_by_question[first_question_id])
        n_personas = len(personas)
        n_variations_per_persona = total_variations // n_personas if n_personas > 0 else 1
        if n_variations_per_persona < 1:
            n_variations_per_persona = 1
        print(f"Processing {n_personas} respondents × {n_variations_per_persona} variations = {total_variations} total rows")
    else:
        print(f"Processing {len(personas)} respondents (no variation data)")
        n_variations_per_persona = 1

    # Build data rows - one row per (persona, variation) pair
    rows = []

    for persona_idx, persona in enumerate(personas):
        for variation_id in range(n_variations_per_persona):
            row = {
                'respid': persona['respid'],
                'response_id': persona['response_id'],
                'variation_id': variation_id,
            }

            # Add demographics as separate columns
            for demo_key, demo_value in persona['demographics'].items():
                row[f'demo_{demo_key}'] = demo_value

            # Add persona information

            for question_id, result in detail_results.items():
                _set_question_columns(
                    row,
                    question_id,
                    result,
                    persona['ground_truth'].get(question_id),
                    persona_idx,
                    variation_id,
                    all_responses_by_question,
                    all_explanations_by_question,
                    all_subscription_tiers_by_question,
                    all_persona_indices_by_question,
                    all_variation_ids_by_question,
                    all_probs_by_question=all_probs_by_question,
                    all_option_orders_by_question=all_option_orders_by_question,
                    include_tiers=include_tiers,
                    failed_persona_indices=failed_persona_indices,
                )

            rows.append(row)

    df = pd.DataFrame(rows)

    # Reorder columns for better readability
    # Start with ID columns (including variation_id), then demographics, then persona info, then questions
    id_cols = ['respid', 'response_id', 'variation_id']
    demo_cols = [col for col in df.columns if col.startswith('demo_')]
    persona_cols = []

    # Question columns in order
    question_cols = []
    for question_id in detail_results.keys():
        question_cols.append(f'{question_id}_synthetic')
        question_cols.append(f'{question_id}_ground_truth')
        question_cols.append(f'{question_id}_explanation')
        if all_probs_by_question is not None:
            question_cols.append(f'{question_id}_probs')
        if all_option_orders_by_question is not None:
            question_cols.append(f'{question_id}_option_order')
        if include_tiers:
            question_cols.append(f'{question_id}_subscription_tier')

    # Reorder
    ordered_cols = id_cols + demo_cols + persona_cols + question_cols
    existing_cols = [col for col in ordered_cols if col in df.columns]
    if existing_cols:
        df = df[existing_cols]

    # Save to Excel with formatting
    from openpyxl.utils import get_column_letter

    with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Respondent Details', index=False)

        worksheet = writer.sheets['Respondent Details']

        # Auto-adjust column widths
        for idx, col in enumerate(df.columns, 1):
            col_max = df[col].fillna("").astype(str).map(len).max()
            max_length = max(0 if pd.isna(col_max) else int(col_max), len(col))
            # Cap at 80 characters for readability
            adjusted_width = min(max_length + 2, 80)
            worksheet.column_dimensions[get_column_letter(idx)].width = adjusted_width

        # Freeze first row
        worksheet.freeze_panes = 'A2'

    return output_path


def generate_summary_excel(
    validation_results: Dict[str, ValidationResult],
    output_path: str
):
    """Generate summary Excel with validation metrics

    Creates a summary sheet with:
    - One distributional metric + one individual metric per question
    - Per-segment distributional metric (one sheet per demographic)

    Args:
        validation_results: Dictionary of {question_id: ValidationResult}
        output_path: Path to save Excel file
    """
    print("\nGenerating summary validation Excel...")

    # Overall summary
    #
    # Entropy columns are appended AFTER individual_baseline so existing column positions don't
    # move: two downstream scorers in the predecessor project both read this sheet, by
    # name. Values are read off the ValidationResult — no formula here, exactly as with
    # distributional_metric.
    #
    # Six columns, not the eleven `ValidationResult` carries. The other five are omitted from the
    # SHEET only (`to_dict` and that project's scorecard keep all eleven) because a reader can
    # reconstruct each from a column already present, and a wide sheet costs more than the
    # keystrokes save:
    #   entropy_kind  = "setwise" if metric_bucket == "multi" else "optionwise"
    #   entropy_thin  = n_valid < 50   (and kl_thin, which is the same predicate)
    #   entropy_gap   = h_syn - h_hum
    #   n_sets_hum / top_set_share — blank on every non-multi row
    # `h_ceiling` is the one that stays despite looking derivable: set-wise and option-wise
    # entropies sit on different scales, so it is what makes h_syn comparable across questions at
    # all, and it is the exact quantity `analysis.py` got wrong. `n_sets_syn` stays because "1500
    # personas produced 5 distinct answer sets" is the most legible evidence of collapse here.
    summary_rows = []
    for question_id, result in validation_results.items():
        summary_rows.append({
            'question_id': question_id,
            'question_type': result.question_type,
            'metric_bucket': result.metric_bucket,
            'sample_size': result.n,
            'n_valid': result.n_valid,
            'n_failed': result.n_failed,
            'distributional_metric': result.distributional_metric,
            'distributional_metric_name': result.distributional_metric_name,
            'individual_baseline': result.individual_baseline,
            'h_syn': result.h_syn,
            'h_hum': result.h_hum,
            'h_ceiling': result.h_ceiling,
            'entropy_ratio': result.entropy_ratio,
            'collapse': result.collapse,
            'n_sets_syn': result.n_sets_syn,
            'kl':               result.kl,
            'blind_spot':       result.blind_spot,
            'blind_spot_worst': result.blind_spot_worst,
        })

    summary_df = pd.DataFrame(summary_rows)

    # Segment analysis (one sheet per demographic) — distributional metric only
    segment_dfs = {}

    for question_id, result in validation_results.items():
        for segment_name, segment_data in result.segment_results.items():
            if segment_name not in segment_dfs:
                segment_dfs[segment_name] = []

            for segment_value, stats in segment_data.items():
                segment_dfs[segment_name].append({
                    'question_id': question_id,
                    'segment_value': segment_value,
                    'sample_size': stats['n'],
                    'distributional_metric': stats['distributional_metric'],
                    'distributional_metric_name': stats['distributional_metric_name'],
                    # Entropy per segment: the distributional metric cannot see a segment whose
                    # personas all answered identically. No collapse flag — segment n is usually
                    # under the gating cut, and sample_size is right here to read it against.
                    'h_syn': stats.get('h_syn'),
                    'h_hum': stats.get('h_hum'),
                    'entropy_ratio': stats.get('entropy_ratio'),
                    # No kl_thin, for the same reason as the collapse flag: it is exactly
                    # `sample_size < 50`, and sample_size is right here to read it against.
                    'kl':               stats.get('kl'),
                    'blind_spot':       stats.get('blind_spot'),
                    'blind_spot_worst': stats.get('blind_spot_worst'),
                })

    # Write to Excel
    with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
        # Overall summary (one distributional + one individual metric per question)
        summary_df.to_excel(writer, sheet_name='Overall Summary', index=False)

        # Segment distributional-metric sheets
        for segment_name, rows in segment_dfs.items():
            segment_df = pd.DataFrame(rows)
            sheet_name = f'By {segment_name.title()}'[:31]  # Excel sheet name limit
            segment_df.to_excel(writer, sheet_name=sheet_name, index=False)

    return output_path


def export_all_results(
    personas: List[dict],
    validation_results: Dict[str, ValidationResult],
    output_dir: str,
    timestamp: str,
    all_responses_by_question: Optional[Dict[str, List]] = None,
    all_explanations_by_question: Optional[Dict[str, List[str]]] = None,
    all_subscription_tiers_by_question: Optional[Dict[str, List[str]]] = None,
    all_persona_indices_by_question: Optional[Dict[str, List[int]]] = None,
    all_variation_ids_by_question: Optional[Dict[str, List[int]]] = None,
    all_probs_by_question: Optional[Dict[str, List]] = None,
    all_option_orders_by_question: Optional[Dict[str, List]] = None,
    include_tiers: bool = True,
    failed_persona_indices: Optional[Set[int]] = None,
    open_ended_question_ids: Optional[List[str]] = None,
):
    """Export both detailed and summary Excel files

    Args:
        personas: List of persona dictionaries
        validation_results: Dictionary of validation results
        output_dir: Output directory
        timestamp: Timestamp string for filenames
        all_responses_by_question: Dict of {question_id: list of ALL synthetic responses}
        all_explanations_by_question: Dict of {question_id: list of ALL explanations}
        all_subscription_tiers_by_question: Dict of {question_id: list of ALL subscription tiers}
        all_persona_indices_by_question: Dict of {question_id: list of persona indices}
        all_variation_ids_by_question: Dict of {question_id: list of variation IDs}
        include_tiers: Emit per-question subscription_tier columns (opt-in)
        open_ended_question_ids: Open-ended question ids to render in the detail sheet.
            They have no ValidationResult (no metric) so they'd otherwise be omitted; the
            summary sheet is unaffected.

    Returns:
        Tuple of (detail_path, summary_path)
    """
    detail_path = f"{output_dir}/respondent_details_{timestamp}.xlsx"
    summary_path = f"{output_dir}/validation_summary_{timestamp}.xlsx"

    generate_respondent_detail_excel(
        personas,
        validation_results,
        detail_path,
        all_responses_by_question,
        all_explanations_by_question,
        all_subscription_tiers_by_question,
        all_persona_indices_by_question,
        all_variation_ids_by_question,
        all_probs_by_question=all_probs_by_question,
        all_option_orders_by_question=all_option_orders_by_question,
        include_tiers=include_tiers,
        failed_persona_indices=failed_persona_indices,
        open_ended_question_ids=open_ended_question_ids,
    )
    generate_summary_excel(validation_results, summary_path)

    return detail_path, summary_path
