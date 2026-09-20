"""Tests for the Jev probe: does it ask Twin exactly what the gpt-4.1 runner asks?

The JC-vs-BC comparison only measures the MODEL if the two arms differ in nothing else, so the
load-bearing test here is `TestWalkFidelity`: it runs the REAL `run_stateful_survey` against the
real 108-question Twin mapping with a fake LLM, and asserts the probe's independently planned walk
produces the same questions in the same order with the same option permutations. Anything less
(re-deriving the expected permutation in the test) would only prove the probe agrees with itself.

The rest guard the things that would silently corrupt a run rather than fail it: the public-data
refusal, the `--chain` cross-check, and the client's refusal to repair a malformed vector.
"""

import json
import random
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from scripts.twin2k.jev_client import (
    JevClient,
    JevError,
    classify_status,
)
from scripts.twin2k.probe_jev import (
    STATE_END,
    STATE_START,
    assert_public_data_config,
    build_state_template,
    completed_respids,
    effective_chaining,
    plan_walk,
    render_state,
    walk_persona,
)
from src.core.config_loader import load_survey_config
from src.core.question_router import QuestionRouter
from src.data import QuestionMapper
from src.data.question_mapper import CONDITION_PREFIX

REPO_ROOT = Path(__file__).resolve().parents[2]
TWIN_DIR = REPO_ROOT / "configs" / "twin2k"
CHAINED_CONFIG = TWIN_DIR / "twin2k_survey_config_chained.yaml"
BASELINE_CONFIG = TWIN_DIR / "twin2k_survey_config.yaml"
PRIOR_ANSWERS_CONFIG = TWIN_DIR / "twin2k_survey_config_prior_answers.yaml"


# --------------------------------------------------------------------------
# Fixtures: the real mapping and router, but a synthetic persona.
#
# Deliberately no CSV. The walk's branching lives in the MAPPING (the 65/43 shuffle split, the 7
# grid groups, the 13 between-subject groups), so loading 761 columns and seven parquet chunks
# would add ~30s per test without exercising anything the mapping does not already carry.
# --------------------------------------------------------------------------
@pytest.fixture(scope="module")
def twin():
    config = load_survey_config(str(CHAINED_CONFIG))
    mapper = QuestionMapper(
        config.survey.data_source.demographic_mapping,
        config.survey.data_source.question_mapping,
        data_format=config.survey.data_source.data_format,
    )
    router = QuestionRouter(getattr(config, "routing_rules", None), mapper)
    question_list = [q.id for q in config.survey.questions]
    return SimpleNamespace(
        config=config, mapper=mapper, router=router, question_list=question_list
    )


def _condition_assignments(twin, pick_second=False):
    """One arm per between-subject group, as the stateful runner seeds from the persona."""
    arms = {}
    for qid in twin.question_list:
        group = twin.mapper.get_condition_group(qid)
        if group is None:
            continue
        arms.setdefault(group, []).append(twin.mapper.get_condition_arm(qid))
    return {
        CONDITION_PREFIX + group: seen[1 if pick_second and len(seen) > 1 else 0]
        for group, seen in arms.items()
    }


def _persona(twin, respid="1234", pick_second=False):
    return {
        "respid": respid,
        # The real prompt names 14 fields; anything absent renders "" via `_fill_inputs`, which is
        # what the runner does for a respondent with an empty field.
        "demographics": {"age": "35-44", "sex": "Female", "party": "Independent"},
        "screener_profile": {},
        "screener_summary": "",
        "ground_truth": {},
        # All 40 pricing stems carry `{stem_value}`; `_fill_stem` raises without these.
        "stem_values": {f"QID9_{i}": f"{i}.49" for i in range(1, 41)},
        "condition_assignments": _condition_assignments(twin, pick_second),
    }


class _Args:
    """Stand-in for the argparse namespace `walk_persona` reads."""

    def __init__(self, **kw):
        self.arm = "jev_chained"
        self.chain = True
        self.primitive = "choice"
        self.repeat_tag = "r1"
        self.order_salt = ""
        self.__dict__.update(kw)


# --------------------------------------------------------------------------
# The fidelity test
# --------------------------------------------------------------------------
class TestWalkFidelity:
    """`plan_walk` must reproduce `run_stateful_survey`'s walk exactly."""

    def _runner_walk(self, twin, persona):
        """Run the real stateful runner with a fake LLM; return its (state, orders).

        `choice: 1` means "the first option I was shown", which is also what `plan_walk` assumes
        while planning — so the two walks commit the same answer at every step and stay in
        lockstep. Any divergence is a real difference in the walk, not in the answers.
        """
        from langchain_core.runnables import RunnableLambda

        from src.core import survey_runner_excel as runner

        def _stub(_structured_llm, **_kwargs):
            return RunnableLambda(
                lambda _prompt: SimpleNamespace(
                    variations=[SimpleNamespace(choice=1, explanation="canned")]
                )
            )

        with patch.object(runner, "apply_langchain_retry", _stub):
            state, _expl, _tier, _probs, orders = runner.run_stateful_survey(
                dict(persona),
                list(twin.question_list),
                twin.mapper,
                twin.router,
                twin.config.survey_prompt,
                model="azure/gpt-4.1",
                max_retries=0,
                # Exactly the BC arm's settings: one call per cell, chaining on, no anchors.
                batch_grids=False,
                chain_own_answers=True,
                preserve_anchors=False,
                include_request_id=False,
            )
        return state, orders

    def test_same_questions_in_the_same_order(self, twin):
        persona = _persona(twin)
        _state, orders = self._runner_walk(twin, persona)
        planned = [qid for qid, _q, _o, _auto in
                   plan_walk(persona, twin.question_list, twin.mapper, twin.router, "")]
        assert planned == list(orders), (
            "the probe asks a different set or order of questions than the runner"
        )
        # Guard against a vacuous pass: Twin gates 48 of its 108 columns by arm.
        assert 60 < len(planned) < 108, f"expected ~82 asked cells, planned {len(planned)}"

    def test_same_option_permutation_on_every_cell(self, twin):
        """The per-persona RNG stream, replayed.

        `orders_dict[qid][i]` is the canonical index of the option shown in slot i, which is
        exactly what the probe's presented order encodes -- so this compares the two streams cell
        by cell rather than trusting that both call `_shuffled_option_order`.
        """
        persona = _persona(twin)
        _state, orders = self._runner_walk(twin, persona)
        shuffled = 0
        for qid, _text, options, _auto in plan_walk(
            persona, twin.question_list, twin.mapper, twin.router, ""
        ):
            canonical = twin.mapper.get_choice_options_list(qid)
            assert orders[qid] == [canonical.index(opt) for opt in options], (
                f"{qid}: probe showed {options}, runner showed slots {orders[qid]}"
            )
            if orders[qid] != sorted(orders[qid]):
                shuffled += 1
        # Only 65 of 108 questions set `shuffle_options`; if none of the asked ones actually came
        # back permuted the assertion above would hold trivially for the wrong reason.
        assert shuffled > 10, f"only {shuffled} cells were permuted — fixture is near-vacuous"

    def test_ordinal_questions_keep_scale_order(self, twin):
        """43 of the 108 are ordinal scales with `shuffle_options: false`.

        They are the reason the RNG cannot be advanced once per asked question: a per-cell draw
        would consume the stream on cells the runner never draws for.
        """
        persona = _persona(twin)
        unshuffled = [
            qid for qid, _t, options, _a in plan_walk(
                persona, twin.question_list, twin.mapper, twin.router, ""
            )
            if not twin.mapper.get_shuffle_options(qid)
            and options == twin.mapper.get_choice_options_list(qid)
        ]
        assert len(unshuffled) > 20, "expected the ordinal block to keep canonical order"

    def test_a_per_cell_seed_would_not_match(self, twin):
        """The error this guards against, stated as a test.

        The reviewed plan originally prescribed `random.Random(f"{respid}|{qid}|order")` per cell.
        If that produced the same permutations as the runner's single per-persona stream, none of
        the care above would matter -- so assert it genuinely does not.
        """
        persona = _persona(twin)
        planned = plan_walk(persona, twin.question_list, twin.mapper, twin.router, "")
        from src.core.survey_runner_excel import _shuffled_option_order

        mismatches = 0
        for qid, _text, options, _auto in planned:
            if not twin.mapper.get_shuffle_options(qid):
                continue
            base = twin.mapper.get_choice_options_list(qid)
            per_cell = _shuffled_option_order(
                base, random.Random(f"{persona['respid']}|{qid}|order"), ()
            )
            if [base[i] for i in per_cell] != options:
                mismatches += 1
        assert mismatches > 5, "a per-cell seed must not coincide with the runner's stream"

    def test_between_subject_arms_diverge_with_the_assignment(self, twin):
        """A twin is asked only the arm its human counterpart was randomized into."""
        first = {qid for qid, *_ in plan_walk(
            _persona(twin, pick_second=False), twin.question_list, twin.mapper, twin.router, "")}
        second = {qid for qid, *_ in plan_walk(
            _persona(twin, pick_second=True), twin.question_list, twin.mapper, twin.router, "")}
        assert first != second, "condition assignment did not change which cells are asked"
        # The 60 unconditional columns must be in both.
        unconditional = {q for q in twin.question_list
                         if twin.mapper.get_condition_group(q) is None}
        assert unconditional <= first and unconditional <= second


# --------------------------------------------------------------------------
# State rendering
# --------------------------------------------------------------------------
class TestStateRendering:
    def test_state_is_the_prompt_minus_answer_style_and_the_question(self, twin):
        template = build_state_template(twin.config.survey_prompt)
        assert template.startswith(STATE_START)
        assert STATE_END not in template
        assert "<answer_style>" not in template, "text-generation styling must not reach Jev"
        assert "Return your answer with" not in template
        for marker in ("<persona>", "<conversation_history>", "Demographics:"):
            assert marker in template

    def test_demographics_and_history_reach_the_state(self, twin):
        persona = _persona(twin)
        template = build_state_template(twin.config.survey_prompt)
        state = render_state(template, persona, [("Did you buy it?", "Yes, I would purchase")])
        assert "35-44" in state and "Independent" in state
        assert "Did you buy it?" in state and "Yes, I would purchase" in state

    def test_missing_demographic_renders_empty_not_an_error(self, twin):
        """Matches `_fill_inputs`: a respondent with no value for a field is not a failure."""
        persona = _persona(twin)
        persona["demographics"] = {"age": "35-44"}
        state = render_state(build_state_template(twin.config.survey_prompt), persona, [])
        assert "{income}" not in state and "{religion}" not in state

    def test_unchained_state_carries_no_answers(self, twin):
        template = build_state_template(twin.config.survey_prompt)
        empty = render_state(template, _persona(twin), [])
        chained = render_state(template, _persona(twin), [("Q", "A")])
        assert "A" not in empty.split("<conversation_history>")[1].split(
            "</conversation_history>")[0]
        assert len(chained) > len(empty)

    def test_a_moved_marker_fails_loudly(self):
        with pytest.raises(SystemExit):
            build_state_template("no markers here")
        with pytest.raises(SystemExit):
            build_state_template(f"{STATE_START} {STATE_START} {STATE_END}")

    def test_the_piped_price_reaches_the_question(self, twin):
        """The 40 pricing stems are respondent-specific; a run that sent `{stem_value}` would
        still parse and still score, so this is the failure that has to be impossible."""
        persona = _persona(twin)
        priced = [(qid, text) for qid, text, _o, _a in plan_walk(
            persona, twin.question_list, twin.mapper, twin.router, "") if qid.startswith("QID9_")]
        assert priced, "fixture: no pricing questions were asked"
        for qid, text in priced:
            assert "{stem_value}" not in text
            assert persona["stem_values"][qid] in text

    def test_a_missing_price_aborts_rather_than_sending_a_placeholder(self, twin):
        persona = _persona(twin)
        persona["stem_values"] = {}
        with pytest.raises(KeyError):
            plan_walk(persona, twin.question_list, twin.mapper, twin.router, "")


# --------------------------------------------------------------------------
# Chaining, walk-abort and resume
# --------------------------------------------------------------------------
class _FakeClient:
    """Answers every cell with its first option (or a fixed `noul`), or raises at a cell index."""

    def __init__(self, fail_at=None, kind="transient", noul=0.75):
        self.fail_at = fail_at
        self.kind = kind
        self.noul = noul
        self.states = []
        self.asked = []

    def ask_choice(self, state, question, options):
        if self.fail_at is not None and len(self.states) == self.fail_at:
            raise JevError(self.kind, "boom")
        self.states.append(state)
        self.asked.append(("choice", options))
        return {"probs": {opt: 1.0 if i == 0 else 0.0 for i, opt in enumerate(options)},
                "choice": options[0], "confidence": 1.0, "model": "jev-1.13.0",
                "input_tokens": 10, "latency_ms": 5}

    def ask_noul(self, state, question, target, other):
        if self.fail_at is not None and len(self.states) == self.fail_at:
            raise JevError(self.kind, "boom")
        self.states.append(state)
        self.asked.append(("noul", [target, other]))
        return {"probs": {target: self.noul, other: 1.0 - self.noul},
                "choice": target if self.noul >= 0.5 else other, "confidence": None,
                "noul": self.noul, "noul_target": target, "model": "jev-1.13.0",
                "input_tokens": 10, "latency_ms": 5}


class TestChainingAndAbort:
    def test_history_length_equals_walk_position(self, twin):
        persona = _persona(twin)
        client = _FakeClient()
        rows, error = walk_persona(client, persona, twin.question_list, twin.mapper,
                                   twin.router, build_state_template(twin.config.survey_prompt),
                                   _Args())
        assert error is None
        assert [r["history_len"] for r in rows] == list(range(len(rows)))

    def test_each_state_carries_the_previous_answers(self, twin):
        persona = _persona(twin)
        client = _FakeClient()
        walk_persona(client, persona, twin.question_list, twin.mapper, twin.router,
                     build_state_template(twin.config.survey_prompt), _Args())
        # Cell t's state must contain the t-1 earlier answers and no more, which shows up as a
        # monotonically growing history block.
        lengths = [len(s) for s in client.states]
        assert lengths == sorted(lengths)
        assert lengths[-1] > lengths[0], "chained state never grew"

    def test_without_chain_every_state_is_identical(self, twin):
        """`--chain` must gate the WALK, not only cross-check the config.

        It used to do only the cross-check, so `jev_order_probe` -- specified as the UNCHAINED
        instrument arm -- accumulated a history anyway and shipped 2,040 cells whose input grew
        653 -> 6,645 tokens across the walk. Nothing downstream could catch it: chaining shows up
        only inside the state string, which is not recorded per cell. The byte-equality assertion
        below is the property that was missing; `history_len` alone would still have read 0..n.
        """
        client = _FakeClient()
        rows, error = walk_persona(client, _persona(twin), twin.question_list, twin.mapper,
                                   twin.router, build_state_template(twin.config.survey_prompt),
                                   _Args(chain=False, arm="jev_order_probe"))
        assert error is None
        assert {r["history_len"] for r in rows} == {0}
        assert len(set(client.states)) == 1, "an unchained walk sent more than one distinct state"

    def test_a_failed_cell_writes_no_rows_at_all(self, twin):
        """Not "the rows before the failure" -- the whole persona. Under chaining a truncated
        history is a different prompt for every later cell, so a partial walk is not comparable."""
        persona = _persona(twin)
        rows, error = walk_persona(_FakeClient(fail_at=5), persona, twin.question_list,
                                   twin.mapper, twin.router,
                                   build_state_template(twin.config.survey_prompt), _Args())
        assert error is not None and error["kind"] == "transient"
        assert len(rows) == 5, "rows are returned for the caller to discard, not to write"

    def test_resume_reads_done_markers_only(self, tmp_path):
        path = tmp_path / "out.jsonl"
        path.write_text("\n".join(json.dumps(r) for r in [
            {"arm": "a", "respid": "1", "qid": "Q1", "probs": {}},          # a cell, not a marker
            {"arm": "a", "respid": "2", "done": True, "repeat_tag": "r1", "order_salt": ""},
            {"arm": "a", "respid": "3", "aborted": True, "repeat_tag": "r1", "order_salt": ""},
            {"arm": "b", "respid": "4", "done": True, "repeat_tag": "r1", "order_salt": ""},
            {"arm": "a", "respid": "5", "done": True, "repeat_tag": "r2", "order_salt": ""},
        ]) + "\n", encoding="utf-8")
        done = completed_respids(path, "a", "r1", "")
        assert done == {"2"}, "only a matching done marker counts as complete"

    def test_resume_on_a_missing_file_is_empty(self, tmp_path):
        assert completed_respids(tmp_path / "nope.jsonl", "a", "r1", "") == set()

    def test_order_salt_changes_the_permutation(self, twin):
        persona = _persona(twin)
        plain = plan_walk(persona, twin.question_list, twin.mapper, twin.router, "")
        salted = plan_walk(persona, twin.question_list, twin.mapper, twin.router, "s2")
        assert [q for q, *_ in plain] == [q for q, *_ in salted], "salt must not change WHICH cells"
        assert any(a[2] != b[2] for a, b in zip(plain, salted)), "salt did not reorder anything"


# --------------------------------------------------------------------------
# The Noul primitive
#
# `--primitive noul` exists to answer one question: JC beat gpt-4.1 on the 43 multiclass columns and
# lost the 65 binary ones, and the vendor documents yes/no items as where `Choice` and `Noul`
# disagree. That only isolates the primitive if EVERYTHING else stays at JC's values -- same cells,
# same option permutations, same history -- which is what these tests pin.
# --------------------------------------------------------------------------
def _asked_rows(rows):
    """Rows that cost a call, in call order -- so they line up with `_FakeClient.asked`/`.states`."""
    return [r for r in rows if r["elicitation"] in ("noul", "choice")]


class TestNoulPrimitive:
    def _walk(self, twin, **kw):
        client = _FakeClient(**kw)
        rows, error = walk_persona(client, _persona(twin), twin.question_list, twin.mapper,
                                   twin.router, build_state_template(twin.config.survey_prompt),
                                   _Args(primitive="noul", arm="jev_noul_chained"))
        assert error is None
        return client, rows

    def test_only_the_two_option_columns_become_noul(self, twin):
        """A Noul decides one condition, so it cannot express a 5-option scale. Those columns must
        stay on Choice -- otherwise the arm changes two things at once and measures neither."""
        client, rows = self._walk(twin)
        asked = _asked_rows(rows)
        assert asked and len(asked) == len(client.asked)
        for (kind, _sent), row in zip(client.asked, asked):
            assert kind == ("noul" if len(row["presented_order"]) == 2 else "choice")
        kinds = {kind for kind, _ in client.asked}
        assert kinds == {"noul", "choice"}, f"expected both primitives in one walk, got {kinds}"

    def test_the_walk_is_identical_to_the_choice_arm(self, twin):
        """Same qids, same presented order, same count. The two arms are paired cell by cell, so
        any difference here would unpair the comparison the arm exists to make."""
        _client, noul_rows = self._walk(twin)
        client = _FakeClient()
        choice_rows, _ = walk_persona(client, _persona(twin), twin.question_list, twin.mapper,
                                      twin.router,
                                      build_state_template(twin.config.survey_prompt), _Args())
        assert [r["qid"] for r in noul_rows] == [r["qid"] for r in choice_rows]
        assert [r["presented_order"] for r in noul_rows] == [
            r["presented_order"] for r in choice_rows]

    def test_the_condition_names_the_first_presented_option(self, twin):
        """Not the first CANONICAL one. The per-persona RNG already permutes these 65 columns, so
        taking the presented side randomises which way the yes/no is phrased -- a fixed side would
        bake any statement-vs-negation asymmetry into every cell of a column."""
        _client, rows = self._walk(twin)
        binary = [r for r in rows if r.get("elicitation") == "noul"]
        assert binary, "fixture: no binary column was asked"
        for row in binary:
            assert row["noul_target"] == row["presented_order"][0]

    def test_the_target_side_varies_between_respondents(self, twin):
        """The randomisation above has to actually bite, or the asymmetry is unmeasurable."""
        targets = []
        for respid in ("1234", "5678"):
            client = _FakeClient()
            rows, _ = walk_persona(client, _persona(twin, respid=respid), twin.question_list,
                                   twin.mapper, twin.router,
                                   build_state_template(twin.config.survey_prompt),
                                   _Args(primitive="noul"))
            targets.append({r["qid"]: r["noul_target"]
                            for r in rows if r.get("elicitation") == "noul"})
        shared = set(targets[0]) & set(targets[1])
        assert any(targets[0][q] != targets[1][q] for q in shared), \
            "every respondent got the same side of every condition"

    def test_the_derived_vector_and_committed_side(self, twin):
        _client, rows = self._walk(twin, noul=0.2)
        for row in (r for r in rows if r.get("elicitation") == "noul"):
            assert sum(row["probs"].values()) == pytest.approx(1.0)
            assert row["probs"][row["noul_target"]] == pytest.approx(0.2)
            # Below the threshold, so the committed answer is the OTHER side -- computed here, not
            # stated by the model, which is the one thing this arm cannot hold identical to JC.
            assert row["choice"] == row["presented_order"][1]
            assert row["confidence"] is None

    def test_choice_cells_carry_no_noul_fields(self, twin):
        """`elicitation` is what the scorer reads; a stray `noul` on a Choice row would make a
        multiclass cell look like it came from the primitive under test."""
        _client, rows = self._walk(twin)
        for row in (r for r in rows if r.get("elicitation") == "choice"):
            assert "noul" not in row and "noul_target" not in row

    def test_the_chained_history_carries_the_thresholded_answer(self, twin):
        """Under chaining the state IS the measurement, so the committed side must reach it."""
        client, rows = self._walk(twin, noul=0.2)
        asked = _asked_rows(rows)
        first = next(i for i, r in enumerate(asked) if r["elicitation"] == "noul")
        assert asked[first]["choice"] in client.states[first + 1]


# --------------------------------------------------------------------------
# Guards: public data, and the --chain cross-check
# --------------------------------------------------------------------------
class TestGuards:
    def test_twin_config_is_accepted(self):
        config = load_survey_config(str(CHAINED_CONFIG))
        assert_public_data_config(CHAINED_CONFIG, config)  # must not raise

    @pytest.mark.parametrize("config_path", sorted(
        p for p in REPO_ROOT.glob("configs/*/*survey_config*.yaml") if "twin2k" not in p.parts
    ))
    def test_every_non_twin_survey_config_is_refused(self, config_path):
        """Enumerated from the repo, not hardcoded: a non-Twin config added later is covered
        automatically. This repo ships only twin2k configs, so the parameter set is empty today
        and pytest skips it -- which is why the two tests below assert the same invariant
        WITHOUT depending on repo contents. Keep all three: this one catches a config someone
        adds, those catch the guard itself regressing."""
        config = load_survey_config(str(config_path))
        with pytest.raises(SystemExit, match="REFUSED"):
            assert_public_data_config(config_path, config)

    def test_a_config_outside_the_twin_dir_is_refused(self, tmp_path):
        """The path half of the guard, asserted without needing a non-Twin config to exist.

        Byte-identical content to the accepted config -- only its location differs -- so this
        pins the check to the directory and nothing else.
        """
        elsewhere = tmp_path / CHAINED_CONFIG.name
        elsewhere.write_bytes(CHAINED_CONFIG.read_bytes())
        config = load_survey_config(str(elsewhere))
        with pytest.raises(SystemExit, match="REFUSED"):
            assert_public_data_config(elsewhere, config)

    def test_a_twin_named_config_pointed_at_other_data_is_refused(self, tmp_path):
        """The data half. A config in the right directory whose rows are NOT the public dataset
        must still be refused -- the docstring on `assert_public_data_config` calls this out as
        the case the path check alone would miss.
        """
        config = load_survey_config(str(CHAINED_CONFIG))
        config.survey.data_source.excel_file = str(tmp_path / "somewhere_else.xlsx")
        with pytest.raises(SystemExit, match="REFUSED"):
            assert_public_data_config(CHAINED_CONFIG, config)

    def test_a_twin_config_pointed_at_other_data_is_refused(self, twin, tmp_path):
        """The config path proves the arm is Twin's; only the data path proves the ROWS are."""
        config = load_survey_config(str(CHAINED_CONFIG))
        config.survey.data_source.excel_file = "data/elsewhere/some_panel.csv"
        with pytest.raises(SystemExit, match="REFUSED"):
            assert_public_data_config(CHAINED_CONFIG, config)

    def test_effective_chaining_reads_both_flags(self):
        """`prior_answers` runs on the stateful path for the prompt cache and then cancels the
        chaining, so `memory_mode` alone misreads it."""
        assert effective_chaining(load_survey_config(str(CHAINED_CONFIG))) is True
        assert effective_chaining(load_survey_config(str(BASELINE_CONFIG))) is False
        assert effective_chaining(load_survey_config(str(PRIOR_ANSWERS_CONFIG))) is False


# --------------------------------------------------------------------------
# The client's wire contract
# --------------------------------------------------------------------------
class TestJevClient:
    def _client(self):
        return JevClient("test-key-not-real")

    def test_payload_shape_matches_the_documented_api(self):
        payload = self._client().build_payload("some state", "Buy it?", ["Yes", "No"])
        assert payload["model"] == "jev-1.13.0", "pin the version, never an alias"
        assert payload["state"] == "some state"
        question = payload["questions"]["q"]
        assert question["type"] == "choice"
        assert question["instructions"] == "Buy it?"
        # criteria is an OBJECT keyed by label, with null descriptions: the survey's own option
        # text is the label, and inventing rubric text would be a prompt gpt-4.1 never saw.
        assert question["criteria"] == {"Yes": None, "No": None}

    def test_duplicate_option_labels_are_refused(self):
        """`criteria` is a JSON object, so two identical labels would collapse to one key and the
        response would be missing an option we believe we asked about."""
        with pytest.raises(JevError, match="duplicate"):
            self._client().build_payload("s", "q", ["Yes", "Yes"])

    def test_empty_and_oversized_option_sets_are_refused(self):
        with pytest.raises(JevError):
            self._client().build_payload("s", "q", [])
        with pytest.raises(JevError, match="255"):
            self._client().build_payload("s", "q", [str(i) for i in range(256)])

    @pytest.mark.parametrize("status,kind", [
        (429, "rate_limit"), (529, "transient"), (500, "transient"), (503, "transient"),
        (401, "auth"), (403, "auth"), (404, "bad_response"),
    ])
    def test_status_classification(self, status, kind):
        assert classify_status(status, "") == kind

    def test_over_length_is_not_confused_with_a_malformed_body(self):
        """Both arrive as 422. An over-long state means STOP (truncating history would change the
        arm); a malformed body is a bug here. They must not collapse into one kind."""
        assert classify_status(422, "state exceeds 32000 tokens") == "context_length"
        assert classify_status(422, "field 'criteria' is required") == "bad_response"

    def _parse(self, body, options=("Yes", "No")):
        response = SimpleNamespace(json=lambda: body, text=json.dumps(body))
        return self._client()._parse(response, list(options), 0.01)

    def test_a_good_response_is_flattened(self):
        out = self._parse({
            "model": "jev-1.13.0",
            "answers": {"q": {"choice": "Yes", "probabilities": {"Yes": 0.7, "No": 0.3},
                              "confidence": 0.8}},
            "usage": {"input_tokens": 120, "output_tokens": 4},
        })
        assert out["probs"] == {"Yes": 0.7, "No": 0.3}
        assert out["choice"] == "Yes" and out["confidence"] == 0.8
        assert out["model"] == "jev-1.13.0" and out["input_tokens"] == 120

    def test_the_answering_version_is_recorded_not_the_requested_one(self):
        """An alias silently moving under us is exactly what this catches."""
        out = self._parse({
            "model": "jev-1.14.0",
            "answers": {"q": {"choice": "Yes", "probabilities": {"Yes": 1.0, "No": 0.0}}},
        })
        assert out["model"] == "jev-1.14.0"

    @pytest.mark.parametrize("probs", [
        {"Yes": 0.7},                            # missing an option
        {"Yes": 0.5, "No": 0.3, "Maybe": 0.2},   # an option we never sent
        {"yes": 0.7, "no": 0.3},                 # case-mismatched labels
    ])
    def test_a_mismatched_vector_is_never_repaired(self, probs):
        """A repaired vector is indistinguishable from a real one downstream, so it must raise."""
        with pytest.raises(JevError, match="probability keys"):
            self._parse({"answers": {"q": {"choice": "Yes", "probabilities": probs}}})

    def test_a_choice_outside_the_options_raises(self):
        with pytest.raises(JevError, match="not one of the options"):
            self._parse({"answers": {"q": {"choice": "Maybe",
                                           "probabilities": {"Yes": 0.5, "No": 0.5}}}})

    def test_raw_probabilities_are_not_normalised(self):
        """How far a source's vector is from summing to 1 is a finding the scorer reports -- Jev's
        docs promise 1, gpt-4.1's verbalized vectors demonstrably do not."""
        out = self._parse({"answers": {"q": {"choice": "Yes",
                                             "probabilities": {"Yes": 0.6, "No": 0.6}}}})
        assert sum(out["probs"].values()) == pytest.approx(1.2)

    def test_a_non_json_body_raises(self):
        def _boom():
            raise ValueError("not json")
        response = SimpleNamespace(json=_boom, text="<html>502</html>")
        with pytest.raises(JevError, match="not JSON"):
            self._client()._parse(response, ["Yes", "No"], 0.01)

    def test_a_missing_key_is_an_auth_error_not_a_crash(self):
        with pytest.raises(JevError, match="auth"):
            JevClient("")

    # ---- the Noul primitive, per /primitives/noul.md ----
    def test_noul_payload_shape_matches_the_documented_api(self):
        payload = self._client().build_noul_payload("some state", "Buy it?", "Yes", "No")
        question = payload["questions"]["q"]
        assert question["type"] == "noul"
        # The stem verbatim, then one line naming the side asked about. Everything before that line
        # is byte-identical to what the Choice arm sent.
        assert question["instructions"] == 'Buy it?\n\nDoes this respondent answer "Yes"?'
        # `true`/`false` slots, not option-keyed -- and carrying the survey's own text, no rubric.
        assert question["criteria"] == {"true": "Yes", "false": "No"}

    def test_a_noul_against_itself_is_refused(self):
        with pytest.raises(JevError, match="target equals other"):
            self._client().build_noul_payload("s", "q", "Yes", "Yes")

    def _parse_noul(self, body, target="Yes", other="No"):
        response = SimpleNamespace(json=lambda: body, text=json.dumps(body))
        return self._client()._parse_noul(response, target, other, 0.01)

    def test_one_number_becomes_the_two_option_vector(self):
        out = self._parse_noul({
            "model": "jev-1.13.0",
            "answers": {"q": {"type": "noul", "noul": 0.87}},
            "usage": {"input_tokens": 120},
        })
        assert out["probs"] == {"Yes": 0.87, "No": pytest.approx(0.13)}
        assert out["choice"] == "Yes" and out["noul"] == 0.87 and out["noul_target"] == "Yes"
        # Noul has no confidence value at all; recording 1.0 or the probability would invent one.
        assert out["confidence"] is None
        assert out["model"] == "jev-1.13.0" and out["input_tokens"] == 120

    def test_an_exact_half_resolves_to_the_target_not_to_dict_order(self):
        """Dict-order tie-breaking is what made the choice-vs-argmax count differ between runs."""
        assert self._parse_noul({"answers": {"q": {"noul": 0.5}}})["choice"] == "Yes"

    @pytest.mark.parametrize("value", [1.4, -0.01])
    def test_a_probability_outside_the_unit_interval_raises(self, value):
        """The complement `1 - p` assumes P(yes). Clamping would turn a response nobody understands
        into a plausible-looking vector."""
        with pytest.raises(JevError, match="outside"):
            self._parse_noul({"answers": {"q": {"noul": value}}})

    def test_a_missing_or_non_numeric_noul_raises(self):
        with pytest.raises(JevError, match="no `noul` value"):
            self._parse_noul({"answers": {"q": {"type": "noul"}}})
        with pytest.raises(JevError, match="non-numeric"):
            self._parse_noul({"answers": {"q": {"noul": "very likely"}}})
