"""Unit tests for QuestionRouter

Tests all routing patterns:
- Skip logic (skip_if)
- Show-if logic (show_if) with single-select and multi-select sources
- Masking (mask_by) with include_selected and exclude_selected
- Piping (pipe_from)
- No routing rules (sequential iteration)
"""

import pytest
from src.core.question_router import QuestionRouter
from src.core.config_loader import RoutingRule, SkipIfRule, ShowIfRule, MaskByRule


class MockQuestionMapper:
    """Mock QuestionMapper for testing"""

    def __init__(self, questions_with_options, option_texts=None, conditions=None,
                 grid_groups=None):
        """
        Args:
            questions_with_options: Dict of {question_id: [option_texts]}
            option_texts: Dict of {option_key: placeholder_text} for pipe substitution
            conditions: Dict of {question_id: (condition_group, condition_arm)}. Omitted for
                every survey without between-subject arms, which is what makes the router's
                arm gate inert for surveys with no between-subject design.
            grid_groups: Dict of {question_id: grid_group}. Omitted by every test here, which
                is what makes `mask_by` read as an option mask rather than a row mask.
        """
        self.questions = questions_with_options
        self.option_texts = option_texts or {}
        self.conditions = conditions or {}
        self.grid_groups = grid_groups or {}

    def get_choice_options_list(self, question_id: str):
        return self.questions.get(question_id, [])

    def get_option_text_by_key(self, option_key: str):
        return self.option_texts.get(option_key)

    def get_grid_group(self, question_id: str):
        """None for every question here: these rules are option masks, not row masks.

        `get_options` asks this to tell the two meanings of `mask_by` apart, so the double has to
        answer it. A grid member's row mask is covered by the grid tests, against
        the real mapper and a real grid.
        """
        return self.grid_groups.get(question_id)

    def get_grid_label(self, question_id: str):
        return question_id

    def get_condition_group(self, question_id: str):
        return self.conditions.get(question_id, (None, None))[0]

    def get_condition_arm(self, question_id: str):
        return self.conditions.get(question_id, (None, None))[1]


def test_skip_logic_fires():
    """Test skip_if rule: Q2=No → skip to Q5"""
    mapper = MockQuestionMapper({})
    rules = [
        RoutingRule(
            question_id="Q3",
            skip_if=SkipIfRule(source_question="Q2", skip_on=["No"], skip_to="Q5")
        )
    ]
    router = QuestionRouter(rules, mapper)

    state = {"Q2": "No"}
    question_list = ["Q1", "Q2", "Q3", "Q4", "Q5"]

    # Q1, Q2 already answered → next should be Q5 (skip Q3, Q4)
    state["Q1"] = "Some answer"
    next_q = router.next_question(state, question_list)
    assert next_q == "Q5", f"Expected Q5, got {next_q}"


def test_skip_logic_no_fire():
    """Test skip_if rule: Q2=Yes → no skip, show Q3"""
    mapper = MockQuestionMapper({})
    rules = [
        RoutingRule(
            question_id="Q3",
            skip_if=SkipIfRule(source_question="Q2", skip_on=["No"], skip_to="Q5")
        )
    ]
    router = QuestionRouter(rules, mapper)

    state = {"Q1": "Some answer", "Q2": "Yes"}
    question_list = ["Q1", "Q2", "Q3", "Q4", "Q5"]

    next_q = router.next_question(state, question_list)
    assert next_q == "Q3", f"Expected Q3, got {next_q}"


def test_show_if_single_select_match():
    """Test show_if with single-select source: Q3=StreamingApp → Q4 shown"""
    mapper = MockQuestionMapper({})
    rules = [
        RoutingRule(
            question_id="Q4",
            show_if=ShowIfRule(source_question="Q3", any_of=["StreamingApp", "SportsApp"])
        )
    ]
    router = QuestionRouter(rules, mapper)

    state = {"Q1": "Answer", "Q2": "Answer", "Q3": "StreamingApp"}
    question_list = ["Q1", "Q2", "Q3", "Q4", "Q5"]

    next_q = router.next_question(state, question_list)
    assert next_q == "Q4", f"Expected Q4, got {next_q}"


def test_show_if_single_select_no_match():
    """Test show_if with single-select source: Q3=Cable → Q4 skipped"""
    mapper = MockQuestionMapper({})
    rules = [
        RoutingRule(
            question_id="Q4",
            show_if=ShowIfRule(source_question="Q3", any_of=["StreamingApp", "SportsApp"])
        )
    ]
    router = QuestionRouter(rules, mapper)

    state = {"Q1": "Answer", "Q2": "Answer", "Q3": "Cable"}
    question_list = ["Q1", "Q2", "Q3", "Q4", "Q5"]

    next_q = router.next_question(state, question_list)
    assert next_q == "Q5", f"Expected Q5 (Q4 skipped), got {next_q}"


def test_show_if_multi_select_match():
    """Test show_if with multi-select source: Q3 has ANY of [A2, A3, A4] → Q4 shown"""
    mapper = MockQuestionMapper({})
    rules = [
        RoutingRule(
            question_id="Q4",
            show_if=ShowIfRule(source_question="Q3", any_of=["Q3.A2", "Q3.A3", "Q3.A4"])
        )
    ]
    router = QuestionRouter(rules, mapper)

    state = {
        "Q1": "Answer",
        "Q2": "Answer",
        "Q3": ["Q3.A1", "Q3.A3"]  # Multi-select: has A3 which matches
    }
    question_list = ["Q1", "Q2", "Q3", "Q4", "Q5"]

    next_q = router.next_question(state, question_list)
    assert next_q == "Q4", f"Expected Q4, got {next_q}"


def test_show_if_multi_select_no_match():
    """Test show_if with multi-select source: Q3 has none of [A2, A3, A4] → Q4 skipped"""
    mapper = MockQuestionMapper({})
    rules = [
        RoutingRule(
            question_id="Q4",
            show_if=ShowIfRule(source_question="Q3", any_of=["Q3.A2", "Q3.A3", "Q3.A4"])
        )
    ]
    router = QuestionRouter(rules, mapper)

    state = {
        "Q1": "Answer",
        "Q2": "Answer",
        "Q3": ["Q3.A1", "Q3.A5"]  # Multi-select: no match
    }
    question_list = ["Q1", "Q2", "Q3", "Q4", "Q5"]

    next_q = router.next_question(state, question_list)
    assert next_q == "Q5", f"Expected Q5 (Q4 skipped), got {next_q}"


def test_masking_include_selected():
    """Test mask_by include_selected: Q9 options = Q8 selected platforms"""
    mapper = MockQuestionMapper({
        "Q9": ["Platform1", "Platform2", "Platform3", "Platform4"]
    })
    rules = [
        RoutingRule(
            question_id="Q9",
            mask_by=MaskByRule(source_question="Q8", filter_type="include_selected")
        )
    ]
    router = QuestionRouter(rules, mapper)

    state = {"Q8": ["Platform1", "Platform3"]}

    options = router.get_options("Q9", state)
    assert options == ["Platform1", "Platform3"], f"Expected [Platform1, Platform3], got {options}"


def test_masking_leaves_a_grid_member_unmasked():
    """On a grid member `mask_by` is a ROW filter, so it must not touch the option list.

    Same rule and same state as the test above, with one difference: Q9 is now a member of a grid.
    Its options are a shared rating scale, whose points are never named in the source answer — so
    masking them keeps NOTHING and blanks the row. `filter_grid_members` is what reads the rule for
    a grid, and the combined call renders this scale unmasked, so unmasked is the right answer here.
    """
    scale = ["Never", "Sometimes", "Often"]
    mapper = MockQuestionMapper({"Q9::youtube": scale}, grid_groups={"Q9::youtube": "Q9"})
    rules = [
        RoutingRule(
            question_id="Q9::youtube",
            mask_by=MaskByRule(source_question="Q8", filter_type="include_selected")
        )
    ]
    router = QuestionRouter(rules, mapper)

    options = router.get_options("Q9::youtube", {"Q8": ["YouTube"]})
    assert options == scale, f"Expected the full scale, got {options}"
    # And the masked-out case is a row decision, not an empty option list.
    assert router.get_options("Q9::youtube", {}) == scale


def test_masking_include_selected_empty_source():
    """Test mask_by include_selected: Q8 not answered → Q9 options empty"""
    mapper = MockQuestionMapper({
        "Q9": ["Platform1", "Platform2", "Platform3"]
    })
    rules = [
        RoutingRule(
            question_id="Q9",
            mask_by=MaskByRule(source_question="Q8", filter_type="include_selected")
        )
    ]
    router = QuestionRouter(rules, mapper)

    state = {}  # Q8 not answered

    options = router.get_options("Q9", state)
    assert options == [], f"Expected empty list, got {options}"


def test_masking_exclude_selected():
    """Test mask_by exclude_selected: Q32 options = all genres EXCEPT Q30 selections"""
    mapper = MockQuestionMapper({
        "Q32": ["Genre1", "Genre2", "Genre3", "Genre4"]
    })
    rules = [
        RoutingRule(
            question_id="Q32",
            mask_by=MaskByRule(source_question="Q30", filter_type="exclude_selected")
        )
    ]
    router = QuestionRouter(rules, mapper)

    state = {"Q30": ["Genre1", "Genre3"]}

    options = router.get_options("Q32", state)
    assert options == ["Genre2", "Genre4"], f"Expected [Genre2, Genre4], got {options}"


def test_masking_exclude_selected_empty_source():
    """Test mask_by exclude_selected: Q30 not answered → Q32 shows all options"""
    mapper = MockQuestionMapper({
        "Q32": ["Genre1", "Genre2", "Genre3"]
    })
    rules = [
        RoutingRule(
            question_id="Q32",
            mask_by=MaskByRule(source_question="Q30", filter_type="exclude_selected")
        )
    ]
    router = QuestionRouter(rules, mapper)

    state = {}  # Q30 not answered

    options = router.get_options("Q32", state)
    assert options == ["Genre1", "Genre2", "Genre3"], f"Expected all options, got {options}"


# Test 6: Piping (substitutes the placeholder "Other" option, no duplicate)
def test_piping_with_text():
    """Test pipe_from: Q31's placeholder option is REPLACED by the generated OE text."""
    mapper = MockQuestionMapper(
        {"Q31": ["StandardGenre1", "StandardGenre2", "Some other genre (please specify)"]},
        option_texts={"Q30.A24": "Some other genre (please specify)"},
    )
    rules = [
        RoutingRule(
            question_id="Q31",
            pipe_from="Q30.A24.OE"
        )
    ]
    router = QuestionRouter(rules, mapper)

    state = {"Q30.A24.OE": "Custom Sci-Fi"}

    options = router.get_options("Q31", state)
    # Placeholder substituted, not appended (no duplicate placeholder).
    assert options == ["StandardGenre1", "StandardGenre2", "Custom Sci-Fi"], f"Expected substitution, got {options}"


def test_piping_empty_source():
    """Test pipe_from: Q30.A24.OE empty → Q31 options unchanged"""
    mapper = MockQuestionMapper({
        "Q31": ["StandardGenre1", "StandardGenre2"]
    })
    rules = [
        RoutingRule(
            question_id="Q31",
            pipe_from="Q30.A24.OE"
        )
    ]
    router = QuestionRouter(rules, mapper)

    state = {"Q30.A24.OE": ""}  # Empty OE

    options = router.get_options("Q31", state)
    assert options == ["StandardGenre1", "StandardGenre2"], f"Expected no piping, got {options}"


def test_piping_missing_source():
    """Test pipe_from: Q30.A24.OE not in state → Q31 options unchanged"""
    mapper = MockQuestionMapper({
        "Q31": ["StandardGenre1", "StandardGenre2"]
    })
    rules = [
        RoutingRule(
            question_id="Q31",
            pipe_from="Q30.A24.OE"
        )
    ]
    router = QuestionRouter(rules, mapper)

    state = {}  # Q30.A24.OE not answered

    options = router.get_options("Q31", state)
    assert options == ["StandardGenre1", "StandardGenre2"], f"Expected no piping, got {options}"


def test_no_routing_rules():
    """Test router with no rules: sequential iteration"""
    mapper = MockQuestionMapper({})
    rules = []
    router = QuestionRouter(rules, mapper)

    state = {"Q1": "Answer", "Q2": "Answer"}
    question_list = ["Q1", "Q2", "Q3", "Q4", "Q5"]

    next_q = router.next_question(state, question_list)
    assert next_q == "Q3", f"Expected Q3, got {next_q}"


def test_no_more_questions():
    """Test router returns None when all questions answered"""
    mapper = MockQuestionMapper({})
    rules = []
    router = QuestionRouter(rules, mapper)

    state = {"Q1": "Answer", "Q2": "Answer", "Q3": "Answer"}
    question_list = ["Q1", "Q2", "Q3"]

    next_q = router.next_question(state, question_list)
    assert next_q is None, f"Expected None (survey complete), got {next_q}"


# Test 8: Combined masking + piping (mask keeps the placeholder, pipe substitutes it)
def test_masking_and_piping_combined():
    """Test mask_by + pipe_from: Q31 masked by Q30, placeholder replaced by generated OE."""
    placeholder = "Some other genre (please specify)"
    mapper = MockQuestionMapper(
        {"Q31": ["Genre1", "Genre2", "Genre3", placeholder]},
        option_texts={"Q30.A24": placeholder},
    )
    rules = [
        RoutingRule(
            question_id="Q31",
            mask_by=MaskByRule(source_question="Q30", filter_type="include_selected"),
            pipe_from="Q30.A24.OE"
        )
    ]
    router = QuestionRouter(rules, mapper)

    state = {
        # Q30 selected Genre1, Genre3, AND the "Other" option (so it survives the mask).
        "Q30": ["Genre1", "Genre3", placeholder],
        "Q30.A24.OE": "Custom Genre"
    }

    options = router.get_options("Q31", state)
    # Masked to [Genre1, Genre3, placeholder]; placeholder substituted with "Custom Genre".
    assert options == ["Genre1", "Genre3", "Custom Genre"], f"Expected masked + substituted, got {options}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
