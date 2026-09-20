"""Question routing engine for conditional survey logic

This module implements the QuestionRouter class which handles:
- Skip logic: Jump to target question based on prior answer
- Show-if logic: Only show question if condition met
- Masking: Dynamic option lists based on prior answers
- Piping: Inject OE text into options

State format: {question_id: answer_text}
- Single-choice: {"Q2": "Yes"}
- Multi-choice: {"Q3": ["Cable/satellite", "Streaming service"]}
- Open-ended: {"Q30.A24.OE": "Sci-fi thriller"}
"""

from typing import List, Dict, Any, Optional
from src.data.question_mapper import CONDITION_PREFIX, QuestionMapper, _QUALTRICS_SUFFIX_RE
from src.core.config_loader import RoutingRule


def _normalize_answer_for_match(answer: Any) -> str:
    """Normalize answer text for routing comparisons."""
    return _QUALTRICS_SUFFIX_RE.sub("", str(answer).strip())


def _answer_matches_any(answer: Any, candidates: List[str]) -> bool:
    """Return True if answer (single or multi) matches any candidate value."""
    if answer is None:
        return False

    normalized_candidates = {_normalize_answer_for_match(c) for c in candidates}

    if isinstance(answer, list):
        for item in answer:
            if item in candidates:
                return True
            if _normalize_answer_for_match(item) in normalized_candidates:
                return True
        return False

    if answer in candidates:
        return True
    return _normalize_answer_for_match(answer) in normalized_candidates


class QuestionRouter:
    """Routes survey questions based on respondent state and conditional logic"""

    def __init__(self, routing_rules: Optional[List[RoutingRule]], question_mapper: QuestionMapper):
        """Initialize question router with routing rules and question mapper

        Args:
            routing_rules: List of conditional routing rules from config (can be None for stateless surveys)
            question_mapper: Reference to mapper for question metadata
        """
        self.mapper = question_mapper
        self.routing_rules = routing_rules or []

        # Index rules by question_id for O(1) lookup
        self.rules_by_question = {rule.question_id: rule for rule in self.routing_rules}

    def is_asked(self, question_id: str, state: Dict[str, Any]) -> bool:
        """False only when `question_id` is in a between-subject condition group whose assigned
        arm is a different one.

        Conditioning is a routing check like `skip_if`/`show_if`, but sourced from the question
        mapping rather than a config rule: the arms are a property of the instrument, so
        duplicating them as rules would mean two places to keep in agreement. The assignment
        arrives via `state` under `CONDITION_PREFIX` keys (seeded by the stateful runner from the
        persona) so this reads state exactly like the other checks do.

        Inert for surveys with no condition groups: `get_condition_group` returns None for every
        question, so this is unconditionally True and both run modes behave as before.
        """
        group = self.mapper.get_condition_group(question_id)
        if group is None:
            return True
        return state.get(CONDITION_PREFIX + group) == self.mapper.get_condition_arm(question_id)

    def next_question(self, state: Dict[str, Any], question_list: List[str]) -> Optional[str]:
        """Determine next question to ask based on current state

        Algorithm:
        1. Iterate through question_list in order
        2. For each question:
           a. If already answered (in state), skip to next
           a2. If it belongs to a condition group this respondent was not assigned, skip it
           b. Check skip_if rule:
              - If skip condition met, jump to skip_to target
              - Continue iteration from skip_to position
           c. Check show_if rule:
              - If condition NOT met, skip this question
           d. Return first question that passes all checks
        3. If no questions remain, return None (survey complete)

        Args:
            state: Current respondent state (flat dict with text values)
            question_list: Ordered list of question IDs from config

        Returns:
            Next question ID to ask, or None if survey complete
        """
        i = 0
        while i < len(question_list):
            q_id = question_list[i]

            # Skip if already answered
            if q_id in state:
                i += 1
                continue

            # Skip the arms of a between-subject condition group this respondent wasn't
            # assigned. Checked BEFORE skip_if: a question that was never shown must not fire
            # its own routing rule either. `question_list` stays shared and unfiltered, so the
            # `question_list.index(skip_to)` lookups below always resolve.
            if not self.is_asked(q_id, state):
                i += 1
                continue

            # Check skip_if rule
            rule = self.rules_by_question.get(q_id)
            if rule and rule.skip_if:
                source_answer = state.get(rule.skip_if.source_question)

                # Handle multi-select source (answer is list)
                if isinstance(source_answer, list):
                    # Check if ANY selected option triggers skip
                    if _answer_matches_any(source_answer, rule.skip_if.skip_on):
                        # Skip to target question
                        try:
                            i = question_list.index(rule.skip_if.skip_to)
                        except ValueError:
                            # Skip target not found, end survey
                            return None
                        continue
                else:
                    # Single-select: check if answer matches skip_on
                    if _answer_matches_any(source_answer, rule.skip_if.skip_on):
                        # Skip to target question
                        try:
                            i = question_list.index(rule.skip_if.skip_to)
                        except ValueError:
                            # Skip target not found, end survey
                            return None
                        continue

            # Check show_if rule
            if rule and rule.show_if:
                source_answer = state.get(rule.show_if.source_question)

                # If source not answered yet, skip this question (condition not met)
                if source_answer is None:
                    i += 1
                    continue

                # Handle multi-select source (answer is list)
                if isinstance(source_answer, list):
                    # Check if ANY selected option matches any_of condition
                    if not _answer_matches_any(source_answer, rule.show_if.any_of):
                        i += 1
                        continue
                else:
                    # Single-select: check if answer matches any_of
                    if not _answer_matches_any(source_answer, rule.show_if.any_of):
                        i += 1
                        continue

            # Question passes all checks
            return q_id

        # No more questions
        return None

    def get_options(self, question_id: str, state: Dict[str, Any]) -> List[str]:
        """Get dynamic option list for a question based on current state

        Algorithm:
        1. Get base options from mapper
        2. Check mask_by rule, unless the question is a grid member (see below):
           - include_selected: filter to keep only options selected in source_question
           - exclude_selected: filter to remove options selected in source_question
        3. Check pipe_from rule: if OE non-empty, append to options
        4. Return final list

        Args:
            question_id: Question ID
            state: Current respondent state

        Returns:
            List of option texts (can be masked or include piped text)
        """
        # Start with base options
        base_options = self.mapper.get_choice_options_list(question_id)

        rule = self.rules_by_question.get(question_id)
        if not rule:
            return base_options

        # Apply masking -- but never to a grid member. `mask_by` on one of those is a ROW filter
        # ("rate this row only if its `grid_label` was selected"), which `filter_grid_members`
        # reads; the option list it would filter here is the shared rating scale, whose points are
        # never named in the source answer, so it would keep NOTHING and blank the whole grid. The
        # combined call already renders the scale unmasked (`get_choice_options_list`), so unmasked
        # is what a grid member's options are -- in either path.
        if rule.mask_by and self.mapper.get_grid_group(question_id) is None:
            source_answer = state.get(rule.mask_by.source_question, [])

            # Normalize to list
            if not isinstance(source_answer, list):
                source_answer = [source_answer] if source_answer else []

            if rule.mask_by.filter_type == "include_selected":
                # Only show options selected in source question
                options = [opt for opt in base_options if opt in source_answer]
            else:  # exclude_selected
                # Show all options EXCEPT those selected in source question
                options = [opt for opt in base_options if opt not in source_answer]
        else:
            options = base_options

        # Apply piping: SUBSTITUTE the placeholder "Other" option with the generated
        # free text (not append — appending duplicated the placeholder). The placeholder
        # is the choice text of the OE's parent option (e.g. Q30.A24.OE -> Q30.A24 ->
        # "Some other genre (please specify)").
        if rule.pipe_from:
            piped_text = state.get(rule.pipe_from, "")
            if piped_text:
                parent_option_key = rule.pipe_from[:-3] if rule.pipe_from.endswith(".OE") else rule.pipe_from
                placeholder = self.mapper.get_option_text_by_key(parent_option_key)
                if placeholder and placeholder in options:
                    options = [piped_text if opt == placeholder else opt for opt in options]
                else:
                    # Placeholder not in (masked) options — append so the generated
                    # genre is still offered.
                    options = options + [piped_text]

        return options

    def filter_grid_members(
        self, members: List[str], state: Dict[str, Any]
    ) -> tuple[List[str], List[str]]:
        """Split grid members into those to rate vs masked-out (not asked).

        For grid items with ``mask_by`` + ``include_selected``, a member is rated
        only when its ``grid_label`` appears in the source question's answer.
        """
        to_rate: List[str] = []
        skipped: List[str] = []

        for member in members:
            rule = self.rules_by_question.get(member)
            if not rule or not rule.mask_by:
                to_rate.append(member)
                continue

            label = self.mapper.get_grid_label(member)
            source_answer = state.get(rule.mask_by.source_question, [])
            if not isinstance(source_answer, list):
                source_answer = [source_answer] if source_answer else []

            selected = _answer_matches_any(label, source_answer)

            if rule.mask_by.filter_type == "include_selected":
                if selected:
                    to_rate.append(member)
                else:
                    skipped.append(member)
            else:
                if selected:
                    skipped.append(member)
                else:
                    to_rate.append(member)

        return to_rate, skipped
