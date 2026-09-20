"""Unit tests for survey_runner dynamic Pydantic models."""

import json

import pytest
from pydantic import ValidationError

from src.core.config_loader import FullSurveyConfig
from src.core.survey_runner_excel import (
    _CHOICE_RESPONSE_FORMAT,
    _choice_response_format,
    _default_subscription_tier,
    _extract_option_probabilities,
    _field_names_in_order,
    _weighted_draw_answer,
    create_grid_response_model,
    create_multi_variation_multi_choice_model,
    create_multi_variation_single_choice_model,
)


def _inner_variation_fields(model):
    variation_list = model.model_fields["variations"].annotation
    return variation_list.__args__[0].model_fields


def _array_length_constraints(model):
    """Length keywords the emitted JSON schema carries for `option_probabilities`.

    Read from `model_json_schema()` rather than the Pydantic field, because the schema is
    what the provider constrained-decodes against -- the field metadata could carry a
    constraint that never reaches the wire.
    """
    defs = model.model_json_schema().get("$defs", {})
    matches = [
        d["properties"]["option_probabilities"]
        for d in defs.values()
        if "option_probabilities" in d.get("properties", {})
    ]
    assert len(matches) == 1, f"expected 1 option_probabilities field, found {len(matches)}"
    return {k: v for k, v in matches[0].items() if k in ("minItems", "maxItems")}


@pytest.mark.unit
class TestSurveyRunnerModels:
    def test_with_tiers_has_subscription_field(self):
        model = create_multi_variation_single_choice_model(4, 3, ["Monthly Plan", "No Plan"])
        fields = _inner_variation_fields(model)
        assert "subscription_tier" in fields
        assert "choice" in fields

    def test_without_tiers_omits_subscription_field(self):
        model = create_multi_variation_single_choice_model(4, 1, None)
        fields = _inner_variation_fields(model)
        assert "subscription_tier" not in fields

    def test_multi_choice_without_tiers(self):
        model = create_multi_variation_multi_choice_model(5, 2, None)
        fields = _inner_variation_fields(model)
        assert "choices" in fields
        assert "subscription_tier" not in fields

    def test_multi_choice_require_selection_rejects_empty(self):
        """With require_selection=True ([min 1] checkboxes), an empty selection fails."""
        model = create_multi_variation_multi_choice_model(5, 1, None, require_selection=True)
        with pytest.raises(ValidationError):
            model(variations=[{"choices": [], "explanation": "none"}])
        ok = model(variations=[{"choices": [1], "explanation": "one"}])
        assert ok.variations[0].choices == [1]

    def test_multi_choice_allows_empty_by_default(self):
        model = create_multi_variation_multi_choice_model(5, 1, None)
        ok = model(variations=[{"choices": [], "explanation": "none apply"}])
        assert ok.variations[0].choices == []

    def test_default_subscription_tier_prefers_no_plan(self):
        assert _default_subscription_tier(["Monthly Plan", "No Plan"]) == "No Plan"

    def test_default_subscription_tier_first_when_no_plan_absent(self):
        assert _default_subscription_tier(["Monthly Plan", "Annual Plan"]) == "Monthly Plan"


@pytest.mark.unit
class TestHardChoiceRegression:
    """Pin flag-off behavior before response_mode implementation (Phase 0b)."""

    def test_hard_choice_single_has_no_option_probabilities(self):
        model = create_multi_variation_single_choice_model(4, 1, None)
        fields = _inner_variation_fields(model)
        assert "option_probabilities" not in fields
        assert list(fields.keys())[0] == "choice"

    def test_hard_choice_multi_field_order(self):
        model = create_multi_variation_multi_choice_model(5, 1, None)
        names = list(_inner_variation_fields(model).keys())
        assert names.index("choices") < names.index("explanation")


@pytest.mark.unit
class TestHardChoiceHasNoProbabilitySurface:
    """No elicitation mode may leak a probability surface into the `hard_choice` default.

    G5 rests on a pre-D-5 run rescoring byte-identically, which holds only if the default path
    sends the provider exactly what it sent before any of this existed. `TestHardChoiceRegression`
    checks two shapes by field name; this sweeps every shape the runner builds -- including grids
    and the 24/25-option questions where exp-006 actually lost cells -- and greps the serialised
    schema, so a probability field cannot arrive under a new name or nested in a `$def`.

    `choice_plus_confidence` is swept too: it is an accepted value with no runner branch, so it
    must stay indistinguishable from `hard_choice` rather than half-implemented.
    """

    SILENT_MODES = ("hard_choice", "choice_plus_confidence")

    @pytest.mark.parametrize("response_mode", SILENT_MODES)
    @pytest.mark.parametrize("n_options", [2, 3, 5, 24, 25])
    def test_flat_schemas_carry_no_probability_field(self, response_mode, n_options):
        for factory in (
            create_multi_variation_single_choice_model,
            create_multi_variation_multi_choice_model,
        ):
            for tiers in (None, ["Monthly Plan", "No Plan"]):
                schema = factory(
                    n_options, 1, tiers, response_mode=response_mode, enforce_prob_length=True
                ).model_json_schema()
                assert "probabilit" not in json.dumps(schema).lower()

    @pytest.mark.parametrize("response_mode", SILENT_MODES)
    def test_grid_schemas_carry_no_probability_field(self, response_mode):
        for n_questions in (1, 2, 4):
            schema = create_grid_response_model(
                n_questions, 25, 1, None, response_mode=response_mode, enforce_prob_length=True
            ).model_json_schema()
            assert "probabilit" not in json.dumps(schema).lower()

    @pytest.mark.parametrize("response_mode", SILENT_MODES)
    def test_prompt_never_asks_for_a_vector(self, response_mode):
        assert _choice_response_format(response_mode) == _CHOICE_RESPONSE_FORMAT

    def test_the_default_is_the_silent_one(self):
        """A config that omits `response_mode` must elicit no probabilities at all."""
        assert FullSurveyConfig(
            survey={
                "name": "x",
                "data_source": {
                    "excel_file": "x",
                    "demographic_mapping": "x",
                    "question_mapping": "x",
                },
                "questions": [],
            },
            personas={},
            survey_prompt="x",
        ).response_mode == "hard_choice"


@pytest.mark.unit
class TestVerbalizedProbsModels:
    def test_verbalized_probs_field_order_single(self):
        model = create_multi_variation_single_choice_model(4, 1, None, response_mode="verbalized_probs")
        names = _field_names_in_order(_inner_variation_fields(model))
        assert names.index("option_probabilities") < names.index("choice")
        assert names.index("choice") < names.index("explanation")

    def test_verbalized_probs_field_order_multi(self):
        model = create_multi_variation_multi_choice_model(5, 1, None, response_mode="verbalized_probs")
        names = _field_names_in_order(_inner_variation_fields(model))
        assert names.index("option_probabilities") < names.index("choices")

    def test_verbalized_probs_grid_item_field_order(self):
        grid = create_grid_response_model(2, 3, 1, None, response_mode="verbalized_probs")
        item_fields = grid.model_fields["variations"].annotation.__args__[0].model_fields[
            "grid_answers"
        ].annotation.__args__[0].model_fields
        names = _field_names_in_order(item_fields)
        assert names.index("option_probabilities") < names.index("choice")

    def test_prob_length_declared_in_schema_when_enforced(self):
        """The length must ride in the JSON schema, not only in the field description.

        exp-006 lost 7 cells to this: under `json_schema` the provider constrained-decodes
        the schema, the schema said nothing about length, and a 25th number on a 24-option
        question then failed client-side validation -- taking a valid choice down with it.
        """
        model = create_multi_variation_single_choice_model(
            24, 1, None, response_mode="verbalized_probs", enforce_prob_length=True
        )
        assert _array_length_constraints(model) == {"minItems": 24, "maxItems": 24}

    def test_prob_length_absent_from_schema_when_not_enforced(self):
        """Bedrock/`function_calling` rejects array `maxItems`, so that path stays silent."""
        model = create_multi_variation_single_choice_model(
            3, 1, None, response_mode="verbalized_probs"
        )
        assert _array_length_constraints(model) == {}

    def test_grid_prob_length_declared_in_schema_when_enforced(self):
        grid = create_grid_response_model(
            2, 5, 1, None, response_mode="verbalized_probs", enforce_prob_length=True
        )
        assert _array_length_constraints(grid) == {"minItems": 5, "maxItems": 5}

    def test_wrong_length_costs_only_the_probs_cell(self):
        """A miscount must no longer raise: the answer is worth more than the vector.

        On the unenforced path the model can still emit a short list, and
        `_extract_option_probabilities` drops it -- leaving choice and explanation intact.
        """
        model = create_multi_variation_single_choice_model(
            3, 1, None, response_mode="verbalized_probs"
        )
        ok = model(variations=[{
            "option_probabilities": [0.5, 0.5],
            "choice": 1,
            "explanation": "too short",
        }])
        variation = ok.variations[0]
        assert variation.choice == 1
        assert _extract_option_probabilities(variation, [0, 1, 2], ["A", "B", "C"]) is None

    def test_non_normalized_vector_accepted(self):
        model = create_multi_variation_single_choice_model(3, 1, None, response_mode="verbalized_probs")
        ok = model(variations=[{
            "option_probabilities": [0.2, 0.2, 0.2],
            "choice": 1,
            "explanation": "sum not 1",
        }])
        assert ok.variations[0].option_probabilities == [0.2, 0.2, 0.2]

    def test_map_back_to_canonical_labels(self):
        class _Var:
            option_probabilities = [0.1, 0.8, 0.1]

        options = ["A", "B", "C"]
        option_order = [2, 0, 1]
        mapped = _extract_option_probabilities(_Var(), option_order, options)
        assert mapped == {"A": 0.8, "B": 0.1, "C": 0.1}


@pytest.mark.unit
class TestWeightedDrawSchema:
    """`weighted_draw` must elicit *identically* to `verbalized_probs`.

    The two arms differ only in the commit rule, so any schema or prompt difference would
    confound exp-007 against exp-006. Asserted rather than assumed, because both modes reach
    the schema through the same `response_mode` parameter and it would be easy to wire one and
    not the other -- which is the bug that left `weighted_draw` a silent no-op.
    """

    @pytest.mark.parametrize(
        "factory,choice_field",
        [
            (create_multi_variation_single_choice_model, "choice"),
            (create_multi_variation_multi_choice_model, "choices"),
        ],
    )
    def test_schema_matches_verbalized_probs(self, factory, choice_field):
        drawn = factory(4, 1, None, response_mode="weighted_draw")
        verbalized = factory(4, 1, None, response_mode="verbalized_probs")
        assert drawn.model_json_schema() == verbalized.model_json_schema()
        names = _field_names_in_order(_inner_variation_fields(drawn))
        assert names.index("option_probabilities") < names.index(choice_field)

    def test_grid_schema_matches_verbalized_probs(self):
        drawn = create_grid_response_model(2, 5, 1, None, response_mode="weighted_draw")
        verbalized = create_grid_response_model(2, 5, 1, None, response_mode="verbalized_probs")
        assert drawn.model_json_schema() == verbalized.model_json_schema()

    def test_prob_length_still_enforced_per_provider(self):
        model = create_multi_variation_single_choice_model(
            24, 1, None, response_mode="weighted_draw", enforce_prob_length=True
        )
        assert _array_length_constraints(model) == {"minItems": 24, "maxItems": 24}

    def test_prompt_asks_for_the_vector(self):
        """Without the vector in the prompt there is nothing to draw from."""
        assert _choice_response_format("weighted_draw") == _choice_response_format(
            "verbalized_probs"
        )
        assert _choice_response_format("hard_choice") == _CHOICE_RESPONSE_FORMAT
        assert "option_probabilities" in _choice_response_format("weighted_draw")


@pytest.mark.unit
class TestWeightedDrawAnswer:
    OPTIONS = ["A", "B", "C"]

    def test_single_draws_from_the_simplex_not_the_commit(self):
        """The drawn answer comes from the vector, so a zero-probability commit is discarded."""
        drawn = _weighted_draw_answer(
            "C", {"A": 1.0, "B": 0.0, "C": 0.0}, self.OPTIONS, "185772161.0", "Q16", multi=False
        )
        assert drawn == "A"

    def test_single_normalises_a_non_normalised_vector(self):
        """exp-006 accepts vectors that do not sum to 1, so the draw cannot assume they do."""
        drawn = _weighted_draw_answer(
            "C", {"A": 0.2, "B": 0.0, "C": 0.0}, self.OPTIONS, "1", "Q16", multi=False
        )
        assert drawn == "A"

    def test_single_respects_the_weights_over_many_respondents(self):
        """The whole point of the arm: `_synthetic` is distributed like the model's own vector."""
        probs = {"A": 0.7, "B": 0.3, "C": 0.0}
        picks = [
            _weighted_draw_answer("A", probs, self.OPTIONS, str(i), "Q16", multi=False)
            for i in range(2000)
        ]
        assert "C" not in picks
        assert 0.65 < picks.count("A") / len(picks) < 0.75

    def test_multi_is_one_bernoulli_per_option(self):
        """The multi vector is independent inclusion marginals, NOT a distribution: raw sum mean
        2.11 on exp-006's panel. A simplex draw would tick exactly one box and destroy the count."""
        drawn = _weighted_draw_answer(
            ["A"], {"A": 1.0, "B": 1.0, "C": 0.0}, self.OPTIONS, "1", "Q30", multi=True
        )
        assert drawn == ["A", "B"]

    def test_multi_marginals_are_reproduced_independently(self):
        probs = {"A": 0.9, "B": 0.5, "C": 0.1}
        draws = [
            _weighted_draw_answer(["A"], probs, self.OPTIONS, str(i), "Q30", multi=True)
            for i in range(2000)
        ]
        rates = {opt: sum(opt in d for d in draws) / len(draws) for opt in self.OPTIONS}
        for opt, expected in probs.items():
            assert abs(rates[opt] - expected) < 0.05, f"{opt}: {rates[opt]} vs {expected}"

    def test_multi_never_returns_an_empty_selection(self):
        """Where checkboxes are all [min 1] and later questions are masked, an empty
        answer can collapse a later question's option list to nothing."""
        drawn = _weighted_draw_answer(
            ["A"], {"A": 0.4, "B": 0.3, "C": 0.2}, self.OPTIONS, "seed-with-no-hits", "Q30",
            multi=True,
        )
        assert drawn
        for respid in range(500):
            assert _weighted_draw_answer(
                ["A"], {"A": 0.01, "B": 0.01, "C": 0.01}, self.OPTIONS, str(respid), "Q30",
                multi=True,
            ), "an all-miss draw must fall back to the most likely option"

    def test_missing_vector_keeps_the_committed_answer(self):
        """A wrong-length vector is already dropped to None upstream; the answer survives it."""
        for probs in (None, {}):
            assert _weighted_draw_answer(
                "B", probs, self.OPTIONS, "1", "Q16", multi=False
            ) == "B"
            assert _weighted_draw_answer(
                ["B"], probs, self.OPTIONS, "1", "Q30", multi=True
            ) == ["B"]

    def test_all_zero_vector_keeps_the_committed_answer(self):
        zeros = {"A": 0.0, "B": 0.0, "C": 0.0}
        assert _weighted_draw_answer("B", zeros, self.OPTIONS, "1", "Q16", multi=False) == "B"
        assert _weighted_draw_answer(["B"], zeros, self.OPTIONS, "1", "Q30", multi=True) == ["B"]

    def test_negative_values_cannot_flip_the_draw(self):
        drawn = _weighted_draw_answer(
            "C", {"A": 1.0, "B": -5.0, "C": 0.0}, self.OPTIONS, "1", "Q16", multi=False
        )
        assert drawn == "A"

    def test_seeded_per_respid_and_question(self):
        """Reproducibility is the gate: an unseeded draw makes a scored run unrepeatable.

        Keyed on (respid, question_id) rather than taken from the persona's shuffle RNG, so the
        presented option order stays byte-identical to every other arm.
        """
        probs = {"A": 0.34, "B": 0.33, "C": 0.33}
        first = [
            _weighted_draw_answer("A", probs, self.OPTIONS, "185772161.0", f"Q{q}", multi=False)
            for q in range(40)
        ]
        again = [
            _weighted_draw_answer("A", probs, self.OPTIONS, "185772161.0", f"Q{q}", multi=False)
            for q in range(40)
        ]
        other = [
            _weighted_draw_answer("A", probs, self.OPTIONS, "185772162.0", f"Q{q}", multi=False)
            for q in range(40)
        ]
        assert first == again
        assert first != other
        assert len(set(first)) > 1, "one respondent must not draw the same option every question"

    def test_draw_ignores_the_presented_option_order(self):
        """`_extract_option_probabilities` keys the vector by canonical label but inserts it in
        PRESENTED order, so iterating the dict instead of `options` would make one respondent's
        draw depend on their shuffle -- and two personas with identical vectors would diverge."""
        as_shown_to_persona_a = {"C": 0.0, "A": 0.5, "B": 0.5}
        as_shown_to_persona_b = {"B": 0.5, "C": 0.0, "A": 0.5}
        for multi, committed in ((False, "A"), (True, ["A"])):
            a = _weighted_draw_answer(
                committed, as_shown_to_persona_a, self.OPTIONS, "7", "Q16", multi=multi
            )
            b = _weighted_draw_answer(
                committed, as_shown_to_persona_b, self.OPTIONS, "7", "Q16", multi=multi
            )
            assert a == b
