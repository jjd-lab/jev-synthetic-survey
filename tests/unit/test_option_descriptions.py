"""The described-`Choice` arm's manipulation, pinned to the rule fixed before the run.

`docs/jev/06-option-descriptions-plan.md` fixes three things these tests exist to hold the code to:

  1. descriptions are derived from the label, never written, so there is no wording to tune;
  2. the rule reaches exactly the 40 pricing columns on the shipped instrument, and falls through
     everywhere else rather than inventing text;
  3. every column it does not reach receives a payload byte-identical to the undescribed arms, so
     the 25 other two-option columns and the 43 multi-option ones are true controls.

(3) is the load-bearing one. If a control column's payload differed at all, a move there could not
be read as evidence that the run was unclean.
"""

import json
from pathlib import Path

import pytest

from scripts.twin2k.jev_client import QUESTION_KEY, JevClient, derive_description

REPO_ROOT = Path(__file__).resolve().parents[2]
MAPPING = REPO_ROOT / "configs" / "twin2k" / "twin2k_question_mapping.json"

PRICING = ["Yes, I would purchase the product", "No, I would not purchase the product"]
BARE = ["more", "fewer"]


def _client() -> JevClient:
    return JevClient("k" * 20)


@pytest.mark.unit
class TestTheRule:
    def test_a_first_person_label_is_restated_in_the_third_person(self):
        assert derive_description("Yes, I would purchase the product") == (
            "This respondent would purchase the product, "
            "for the situation described in the question."
        )

    def test_the_negation_is_carried_through_rather_than_dropped(self):
        described = derive_description("No, I would not purchase the product")
        assert "would not purchase" in described

    @pytest.mark.parametrize("label", ["more", "fewer", "the small tray", "Strongly oppose", ""])
    def test_a_label_it_cannot_restate_falls_through(self, label):
        """No fallback. Inventing wording here would be a second, unstated manipulation."""
        assert derive_description(label) is None

    def test_it_adds_no_word_that_was_not_already_there(self):
        """The description may only reorder and frame; every content word comes from the label."""
        described = derive_description("Yes, I would purchase the product")
        for word in ("purchase", "the", "product", "would"):
            assert word in described
        assert "price" not in described and "buy" not in described


@pytest.mark.unit
class TestTheScopeOnTheShippedInstrument:
    def _two_option_columns(self):
        mapping = json.loads(MAPPING.read_text(encoding="utf-8"))
        return {
            qid: list(entry["choices"].values())
            for qid, entry in mapping.items()
            if len(entry["choices"]) == 2
        }

    def test_the_rule_reaches_exactly_the_forty_pricing_columns(self):
        reached = {
            qid for qid, options in self._two_option_columns().items()
            if all(derive_description(option) is not None for option in options)
        }
        assert len(reached) == 40
        assert all(qid.startswith("QID9_") for qid in reached)

    def test_the_other_twenty_five_two_option_columns_are_controls(self):
        columns = self._two_option_columns()
        assert len(columns) == 65
        untouched = {
            qid for qid, options in columns.items()
            if all(derive_description(option) is None for option in options)
        }
        assert len(untouched) == 25


@pytest.mark.unit
class TestTheArmsScope:
    """What the probe actually describes, counted over the whole instrument."""

    def _counts(self):
        mapping = json.loads(MAPPING.read_text(encoding="utf-8"))
        client = _client()
        described = controls_two = controls_multi = 0
        for entry in mapping.values():
            options = list(entry["choices"].values())
            # The probe's rule: two-option columns only.
            descriptions = (
                {o: derive_description(o) for o in options} if len(options) == 2 else None
            )
            plain = client.build_payload("s", "q", options)
            sent = client.build_payload("s", "q", options, descriptions)
            if json.dumps(sent, sort_keys=True) != json.dumps(plain, sort_keys=True):
                described += 1
            elif len(options) == 2:
                controls_two += 1
            else:
                controls_multi += 1
        return described, controls_two, controls_multi

    def test_the_split_is_the_one_the_plan_fixed(self):
        assert self._counts() == (40, 25, 43)

    def test_the_ordered_scales_the_rule_touches_are_left_as_controls(self):
        """QID157/158/291 read "I favor program A" and would derive, but have no yes/no boundary."""
        mapping = json.loads(MAPPING.read_text(encoding="utf-8"))
        for qid in ("QID157", "QID158", "QID291"):
            options = list(mapping[qid]["choices"].values())
            assert len(options) > 2
            assert all(derive_description(o) is not None for o in options)


@pytest.mark.unit
class TestTheControlsGetAnIdenticalPayload:
    def test_a_column_the_rule_misses_is_byte_identical_to_the_undescribed_arm(self):
        client = _client()
        undescribed = client.build_payload("state", "q", BARE)
        described = client.build_payload(
            "state", "q", BARE, {o: derive_description(o) for o in BARE}
        )
        assert json.dumps(described, sort_keys=True) == json.dumps(undescribed, sort_keys=True)

    def test_a_pricing_column_does_change(self):
        """The counterpart: the manipulation has to actually reach the arm it targets."""
        client = _client()
        undescribed = client.build_payload("state", "q", PRICING)
        described = client.build_payload(
            "state", "q", PRICING, {o: derive_description(o) for o in PRICING}
        )
        assert described != undescribed
        criteria = described["questions"][QUESTION_KEY]["criteria"]
        assert all(value is not None for value in criteria.values())

    def test_the_default_payload_is_unchanged_by_the_new_parameter(self):
        """The shipped arms must not move because this parameter now exists."""
        client = _client()
        assert client.build_payload("s", "q", PRICING) == {
            "state": "s",
            "model": client.model,
            "questions": {
                QUESTION_KEY: {
                    "type": "choice",
                    "instructions": "q",
                    "criteria": {PRICING[0]: None, PRICING[1]: None},
                },
            },
        }
