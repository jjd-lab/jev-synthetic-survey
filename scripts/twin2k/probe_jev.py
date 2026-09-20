"""Walk Twin-2K-500 personas through Jev, recording a probability vector per cell.

The Jev Choice arm of the Jev-vs-gpt-4.1 comparison. The question is narrow: gpt-4.1 under
`response_mode: verbalized_probs` is ASKED to state a distribution over the options; Jev returns one
natively. Does the native vector fit the human marginals better than the verbalized one, in the
setting a production survey actually runs -- stateful, demographics-only, chaining its own answers?

For that comparison to mean anything, the two arms must differ in the MODEL and nothing else. So
this does not build its own prompt: it reuses the runner's own helpers (`_fill_stem`,
`render_history`, `_shuffled_option_order`) and mirrors `run_stateful_survey`'s walk step for step,
including the parts that are easy to get wrong:

  * Only 65 of Twin's 108 questions set `shuffle_options` (the nominal ones; the 43 ordinal keep
    scale order). The per-persona RNG is seeded ONCE, at `str(respid)`, and advanced only on a
    shuffled question -- so replaying it requires walking every question in order, not just the
    shuffled ones. Draw it per cell instead and both arms get different option orders, silently
    unpairing the comparison.
  * History carries the FILLED stem, not the raw one (`survey_runner_excel.py:1235`), which matters
    on the 40 pricing questions whose `{stem_value}` is randomized per respondent.
  * The 48 between-subject columns are gated by `is_asked` off `persona["condition_assignments"]`,
    so each twin is asked only the arm its human counterpart was randomized into.

Differences from the runner, both deliberate:
  * `<answer_style>` and the "Return your answer with:" block are dropped. They exist to constrain a
    generated `explanation` and to ask for a numbered choice; Jev generates no text and answers with
    a label. Keeping them would be prompt text the model cannot act on.
  * A failed cell ABORTS that persona's walk rather than writing "Error" and continuing. Under
    chaining the history IS the state, so one poisoned turn changes every later vector -- the
    runner's behaviour is right for a checkpointed production run and wrong for a measurement.

PUBLIC DATA ONLY. This is the one path in the repo that sends prompts outside the hosted endpoint,
on a personal key. `assert_public_data_config` refuses any config that is not Twin's, before a
respondent is loaded or a request is built, so a mistyped `--config` cannot send a persona from
any other dataset to TypeSafe.

`--primitive noul` re-asks the 65 two-option columns as a yes/no condition, holding the walk, the
option permutations, the history and the model fixed. It is the follow-up JC's own result asks for:
JC beat gpt-4.1 on the 43 multiclass columns and lost the 65 binary ones, and the vendor documents
yes/no as precisely where `Choice` and `Noul` diverge. If the gap closes, C3 measured the
elicitation and not the model.

Usage:
    python scripts/twin2k/probe_jev.py --arm jev_chained --chain \\
        --config configs/twin2k/demographics_stateful.yaml \\
        --persona-cache runs/gpt41_panel_n2058/demographics_stateful/persona_cache.xlsx \\
        --sample 300 --out outputs/twin2k/jev/jev_choice.jsonl
"""

import argparse
import json
import random
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.twin2k.jev_client import (  # noqa: E402
    derive_description,
    CONTEXT_BUDGET_STATE_AND_QUESTION,
    CONTEXT_BUDGET_TOTAL,
    MODEL,
    RATE_IN_PER_TOKEN,
    JevClient,
    JevError,
    approx_tokens,
    check_endpoint_is_typesafe,
    load_key,
)
from src.core.config_loader import load_survey_config  # noqa: E402
from src.core.persona_cache import load_personas_from_excel  # noqa: E402
from src.core.question_router import QuestionRouter  # noqa: E402
from src.core.survey_runner_excel import (  # noqa: E402
    _fill_stem,
    _shuffled_option_order,
    render_history,
)
from src.data import ExcelSurveyLoader, QuestionMapper  # noqa: E402

# The state handed to Jev is the prompt from here up to (not including) here.
STATE_START = "<survey_context>"
STATE_END = "<current_question>"

# Only Twin-2K-500 is CC BY 4.0 and cleared to leave the provider.
PUBLIC_CONFIG_DIR = REPO_ROOT / "configs" / "twin2k"
PUBLIC_DATA_DIR = REPO_ROOT / "data" / "twin2k500"


class _Blank(dict):
    """Missing prompt placeholder -> empty string, matching the runner's `_fill_inputs`.

    A respondent with no `children` value must render as "" rather than raising, exactly as it
    does in the real run.
    """

    def __missing__(self, key):  # noqa: D105
        return ""


def assert_public_data_config(config_path: Path, config) -> None:
    """Fail closed unless this is Twin's config reading Twin's data.

    Both halves are needed: the config path proves the ARM is Twin's, the data path proves the
    ROWS are. A twin2k-named config pointed at some other CSV would pass the first check alone.
    """
    resolved = config_path.resolve()
    if resolved.parent != PUBLIC_CONFIG_DIR.resolve():
        raise SystemExit(
            f"REFUSED: {resolved} is not in {PUBLIC_CONFIG_DIR}.\n"
            "Jev is reached on a personal key outside the hosted endpoint, so only "
            "Twin-2K-500 (CC BY 4.0) may be sent -- it is the only data cleared for it."
        )
    excel = (REPO_ROOT / config.survey.data_source.excel_file).resolve()
    if PUBLIC_DATA_DIR.resolve() not in excel.parents:
        raise SystemExit(
            f"REFUSED: data source {excel} is not under {PUBLIC_DATA_DIR}."
        )


def effective_chaining(config) -> bool:
    """Whether this config actually chains the model's own answers.

    Reading `memory_mode` alone gets `prior_answers` wrong: it runs on the stateful path for the
    prompt cache and then sets `chain_own_answers: false` to cancel the chaining, so it looks
    chained and is not.
    """
    return getattr(config, "memory_mode", "full") == "full" and bool(
        getattr(config, "chain_own_answers", True)
    )


def build_state_template(survey_prompt: str) -> str:
    """The slice of the survey prompt that becomes Jev's `state`.

    Asserts each marker appears exactly once: if the template is reworded so that a marker moves
    or doubles, this must fail rather than quietly send a truncated persona.
    """
    for marker in (STATE_START, STATE_END):
        found = survey_prompt.count(marker)
        if found != 1:
            raise SystemExit(f"survey_prompt contains {marker!r} {found} times, expected exactly 1")
    start = survey_prompt.index(STATE_START)
    end = survey_prompt.index(STATE_END)
    return survey_prompt[start:end].rstrip()


def render_state(state_template: str, persona: dict, own_answers) -> str:
    """Fill the state template for one cell. `own_answers` is empty when not chaining."""
    fields = _Blank(persona["demographics"])
    fields["conversation_history"] = render_history(persona, own_answers)
    return state_template.format_map(fields)


def plan_walk(persona: dict, question_list, mapper, router, order_salt: str):
    """Replay the runner's walk offline: the (qid, filled stem, options) sequence, in order.

    This is the whole fidelity argument of the probe, so it is a pure function -- no network, no
    model -- and a unit test asserts its option permutations equal the runner's own RNG stream.

    `batch_grids` is false on both arms by construction, so the runner's combined-grid branch is
    not mirrored; a grid member is an ordinary question whose row mask is still read (:1225).
    """
    walk_state = dict(persona.get("condition_assignments", {}))
    # Seeded exactly as the runner seeds it (:1028). The salt is for the order-sensitivity probe
    # only; empty means byte-identical to the runner's stream, which is what pairs JC with BC.
    seed = f"{persona['respid']}|{order_salt}" if order_salt else str(persona["respid"])
    rng = random.Random(seed)
    cells = []

    while True:
        next_q = router.next_question(walk_state, question_list)
        if next_q is None:
            break

        if mapper.get_grid_group(next_q) is not None:
            _, masked = router.filter_grid_members([next_q], walk_state)
            if masked:
                walk_state[next_q] = None
                continue

        question_text = _fill_stem(mapper.get_question_text(next_q), persona, next_q)
        base_options = router.get_options(next_q, walk_state)

        if not base_options:
            walk_state[next_q] = None
            continue
        if len(base_options) == 1:
            # Auto-selected without a call, as the runner does -- and notably WITHOUT advancing
            # the rng, which is why this branch is mirrored even though Twin never reaches it
            # (no question carries `mask_by`, so options are never filtered down to one).
            walk_state[next_q] = base_options[0]
            cells.append((next_q, question_text, base_options, True))
            continue

        if mapper.get_shuffle_options(next_q):
            # `_anchors_for` is `()` here: `preserve_anchors` is false on every twin2k config and
            # all 108 questions carry `anchor_options: null`, so there is nothing to pin.
            order = _shuffled_option_order(base_options, rng, ())
            options = [base_options[idx] for idx in order]
        else:
            options = list(base_options)

        cells.append((next_q, question_text, options, False))
        # Answer with the first option so the walk keeps advancing. Only the SEQUENCE and the
        # permutations are being planned here; the real answers replace this during the live walk,
        # and nothing in `next_question`/`is_asked` for Twin depends on an answer's value (no
        # `show_if`, no `mask_by`, no `pipe_from` anywhere in the mapping).
        walk_state[next_q] = options[0]

    return cells


def walk_persona(client, persona, question_list, mapper, router, state_template, args):
    """Ask one persona every question it is due, in order. Returns (rows, error).

    Rows are buffered and returned rather than streamed: on a chained arm a mid-walk failure
    leaves a truncated history, and a half-written persona would be indistinguishable on resume
    from a complete one.
    """
    plan = plan_walk(persona, question_list, mapper, router, args.order_salt)
    own_answers: list = []
    rows = []

    for qid, question_text, options, auto in plan:
        ground_truth = (persona.get("ground_truth") or {}).get(qid)
        row = {
            "arm": args.arm,
            "respid": str(persona["respid"]),
            "qid": qid,
            # Canonical order, so ordinal distance is computable downstream and the presented
            # permutation never leaks into scoring.
            "options": mapper.get_choice_options_list(qid),
            "human": ground_truth,
            "presented_order": options,
            "history_len": len(own_answers),
            "repeat_tag": args.repeat_tag,
            "order_salt": args.order_salt,
            "error": None,
        }

        if auto:
            # Only one option survived masking, so there is nothing to ask. Recorded as a
            # degenerate vector rather than dropped, so cell counts still reconcile.
            row.update({"probs": {options[0]: 1.0}, "choice": options[0], "confidence": 1.0,
                        "model": None, "elicitation": "auto_single_option", "latency_ms": 0,
                        "input_tokens": 0})
            rows.append(row)
            if args.chain:
                own_answers.append((question_text, options[0]))
            continue

        state = render_state(state_template, persona, own_answers)
        # A Noul decides one yes/no condition, so it only applies where the column HAS two options.
        # The 43 multiclass columns stay `Choice` under `--primitive noul`, which is what makes the
        # arm a clean swap on the 65 binary columns: same walk, same RNG stream, same history
        # composition as JC, one primitive different on the half JC loses.
        as_noul = args.primitive == "noul" and len(options) == 2
        try:
            if as_noul:
                # `options[0]` is the first PRESENTED option, so which side the condition names is
                # randomised per respondent by the same per-persona RNG that permuted JC's options.
                # A fixed side would bake any statement-vs-negation asymmetry into every cell of a
                # column; randomising it averages the asymmetry out and makes it measurable.
                answer = client.ask_noul(state, question_text, options[0], options[1])
            else:
                # `descriptions` is None unless --describe-criteria, and `derive_description`
                # returns None for any label it cannot restate. Both paths send `criteria`
                # values of null, byte-identical to the undescribed arms, so every column the
                # rule does not reach is a true control rather than an approximate one.
                # Two-option columns only. The plan targets the yes/no boundary -- "where does
                # 'yes' begin" -- and fixes the 43 multi-option columns as a control. The rule
                # also derives labels on three ordered scales (QID157, QID158, QID291, whose
                # options read "I would ..." / "I favor program A"), and describing those would
                # both widen the manipulation past the boundary question and shrink the control
                # set the criteria are read against.
                descriptions = (
                    {option: derive_description(option) for option in options}
                    if args.describe_criteria and len(options) == 2 else None
                )
                answer = client.ask_choice(state, question_text, options, descriptions)
        except JevError as exc:
            # Abort the walk. Every later cell's state would carry the gap.
            return rows, {"qid": qid, "kind": exc.kind, "message": str(exc)[:300]}

        row.update({
            "probs": answer["probs"], "choice": answer["choice"],
            "confidence": answer["confidence"], "model": answer["model"],
            "elicitation": "noul" if as_noul else "choice",
            "latency_ms": answer["latency_ms"],
            "input_tokens": answer["input_tokens"],
        })
        if as_noul:
            # The raw number and the side it was asked about. `probs` alone cannot recover the
            # target once p == 0.5, and the target is what the asymmetry check groups by.
            row["noul"] = answer["noul"]
            row["noul_target"] = answer["noul_target"]
        rows.append(row)
        # The model's own `choice` enters the history -- never a draw. A draw-committing walk is a
        # different arm (it cannot be replayed offline), and both arms must chain the same way.
        #
        # `args.chain` GATES this, and must: it used to only cross-check the config, so an unchained
        # arm still accumulated a history, still rendered it into `state`, and still reported a
        # rising `history_len` -- the first order_probe run grew from 653 to 6,645 input tokens
        # across the walk and was silently a second chained arm. Nothing downstream could see it,
        # because an unchained run and a chained one differ only inside the state string.
        if args.chain:
            own_answers.append((question_text, answer["choice"]))

    return rows, None


def completed_respids(path: Path, arm: str, repeat_tag: str, order_salt: str) -> set:
    """Respids whose walk finished, from a `done` marker -- not from the presence of cell rows.

    A marker is what makes resume safe: an aborted persona also has rows on disk (it does not,
    since rows are buffered, but a crash mid-write could leave some), and only the marker says the
    walk ran to the end.
    """
    if not path.exists():
        return set()
    done = set()
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if (row.get("done") and row.get("arm") == arm
                    and row.get("repeat_tag") == repeat_tag
                    and row.get("order_salt") == order_salt):
                done.add(str(row["respid"]))
    return done


def dry_run(personas, question_list, mapper, router, state_template, args) -> int:
    """Render every prompt and report the token budget, without calling anything.

    The chained arm's LAST question carries the whole history, so the longest prompt is what
    decides whether the arm fits at all -- the plan's Phase 3 gate. Reported against the
    documented 32k state+question cap, not the 64k total, since that is the binding one here.
    """
    worst = (0, None, None)
    total_tokens = 0
    for persona in personas:
        plan = plan_walk(persona, question_list, mapper, router, args.order_salt)
        own_answers = []
        for qid, question_text, options, auto in plan:
            if auto:
                own_answers.append((question_text, options[0]))
                continue
            state = render_state(state_template, persona, own_answers)
            # `criteria` is billed on both sides: the option text as keys, and under
            # --describe-criteria the derived descriptions as values. Both belong in the estimate,
            # or the flag looks free.
            described = "".join(
                derive_description(option) or "" for option in options
            ) if args.describe_criteria and len(options) == 2 else ""
            tokens = approx_tokens(state) + approx_tokens(question_text) + approx_tokens(
                "".join(options)
            ) + approx_tokens(described)
            total_tokens += tokens
            if tokens > worst[0]:
                worst = (tokens, persona["respid"], qid)
            if args.chain:
                own_answers.append((question_text, options[0]))

    cells = sum(
        len(plan_walk(p, question_list, mapper, router, args.order_salt)) for p in personas
    )
    print(f"\n{len(personas)} personas, {cells} cells "
          f"({cells / max(len(personas), 1):.1f} per persona)")
    print(f"longest prompt ~{worst[0]:,} tokens (respid {worst[1]}, {worst[2]}) "
          f"vs {CONTEXT_BUDGET_STATE_AND_QUESTION:,} cap for state+question "
          f"(total request cap {CONTEXT_BUDGET_TOTAL:,})")
    print(f"~{total_tokens:,} input tokens -> ~${total_tokens * RATE_IN_PER_TOKEN:.2f} at "
          f"${RATE_IN_PER_TOKEN * 1e6:.3f}/Mtok (input-only; output is free)")
    print("NOTE: the estimate is chars/4 and EXCLUDES Jev's fixed per-request overhead, measured "
          "at ~300 tokens on a one-sentence state — add ~300 x n_cells.")
    if worst[0] > CONTEXT_BUDGET_STATE_AND_QUESTION:
        print("\nFAIL: over the documented cap. STOP — do not truncate history to fit; that "
              "changes the arm. See the plan's Phase 3 gate.")
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", required=True,
                       help="Must be a configs/twin2k/ config — public data only.")
    parser.add_argument("--arm", required=True, help="Label recorded on every row, e.g. jev_chained")
    parser.add_argument("--out", required=True, help="JSONL, appended to; resume reads it back.")
    parser.add_argument("--persona-cache", default=None,
                       help="Existing persona cache. Required in practice: regenerating personas "
                            "needs the provider and would break the same-persona control.")
    parser.add_argument("--describe-criteria", action="store_true",
                       help="Send a derived description per option, where the rule reaches one. "
                            "On the shipped instrument that is the 40 pricing columns and nothing "
                            "else; see docs/jev/06-option-descriptions.md.")
    parser.add_argument("--primitive", choices=("choice", "noul"), default="choice",
                       help="`noul` asks the 65 two-option columns as a yes/no condition instead "
                            "of a Choice, and leaves the 43 multiclass columns on Choice. Tests "
                            "the vendor's own claim that the two primitives disagree on yes/no "
                            "items; everything else stays identical to the Choice arm.")
    parser.add_argument("--chain", action="store_true",
                       help="Feed the twin its own earlier answers. Cross-checked against the "
                            "config's EFFECTIVE chaining; a mismatch is refused.")
    parser.add_argument("--sample", type=int, default=None,
                       help="First N respondents in loader order. Defaults to the config's max_rows.")
    parser.add_argument("--questions", default=None,
                       help="Comma-separated qid subset, for smoke runs only. Changes the walk and "
                            "so the RNG stream — results are NOT comparable to a full run.")
    parser.add_argument("--concurrency", type=int, default=8,
                       help="Personas in flight. Cells within a persona are strictly sequential. "
                            "The account ceiling is 1,200 req/min, so ~20 threads at ~1s/call "
                            "already saturates it; more only buys 429s.")
    parser.add_argument("--repeat-tag", default="r1",
                       help="Distinguishes a repeat of the same cells, for the determinism probe.")
    parser.add_argument("--order-salt", default="",
                       help="Perturbs the option-order RNG seed. Empty reproduces the runner's own "
                            "stream exactly — leave it empty for any arm being compared to BC.")
    parser.add_argument("--dry-run", action="store_true",
                       help="Render prompts, report tokens and cost, call nothing.")
    parser.add_argument("--model", default=MODEL, help="Pinned version; avoid aliases.")
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.exists():
        raise SystemExit(f"config not found: {config_path}")
    config = load_survey_config(str(config_path))
    # FIRST, before a respondent is loaded or a request is built.
    assert_public_data_config(config_path, config)

    chains = effective_chaining(config)
    if args.chain != chains:
        raise SystemExit(
            f"REFUSED: --chain={args.chain} but {config_path.name} effectively chains={chains} "
            f"(memory_mode={getattr(config, 'memory_mode', None)!r}, "
            f"chain_own_answers={getattr(config, 'chain_own_answers', None)!r}).\n"
            "Pass --chain only for a config that really feeds the model its own answers."
        )

    mapper = QuestionMapper(
        config.survey.data_source.demographic_mapping,
        config.survey.data_source.question_mapping,
        data_format=config.survey.data_source.data_format,
    )
    mapper.validate_question_types(config.survey.questions)
    loader = ExcelSurveyLoader(
        config.survey.data_source.excel_file, mapper,
        preprocess=config.survey.data_source.preprocess,
    )
    respondents = loader.load_respondents(
        sheet_name=config.survey.data_source.sheet_name,
        max_rows=args.sample if args.sample is not None else config.survey.data_source.max_rows,
    )
    print(f"[OK] {len(respondents)} respondents")

    cache_path = args.persona_cache or ""
    personas = load_personas_from_excel(cache_path, respondents) if cache_path else None
    if personas is None:
        raise SystemExit(
            f"REFUSED: no usable persona cache at {cache_path!r}. Regenerating personas needs the "
            "provider and would break the same-persona control against the gpt-4.1 arms. Point "
            "--persona-cache at the arm's existing cache."
        )
    print(f"[OK] {len(personas)} personas from cache")

    router = QuestionRouter(getattr(config, "routing_rules", None), mapper)
    question_list = [q.id for q in config.survey.questions]
    if args.questions:
        wanted = {q.strip() for q in args.questions.split(",") if q.strip()}
        unknown = wanted - set(question_list)
        if unknown:
            raise SystemExit(f"--questions names unknown qids: {sorted(unknown)}")
        question_list = [q for q in question_list if q in wanted]
        print(f"[warn] --questions restricts the walk to {len(question_list)} questions; the RNG "
              "stream and history differ from a full run, so this is a smoke run only.")

    state_template = build_state_template(config.survey_prompt)

    if args.dry_run:
        return dry_run(personas, question_list, mapper, router, state_template, args)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    done = completed_respids(out_path, args.arm, args.repeat_tag, args.order_salt)
    todo = [p for p in personas if str(p["respid"]) not in done]
    print(f"[OK] {len(done)} personas already complete, {len(todo)} to run")
    if not todo:
        return 0

    key = load_key()
    write_lock = threading.Lock()
    # `requests.Session` is not documented as thread-safe, so a client is per-thread rather than
    # shared across the pool.
    local = threading.local()
    counters = {"done": 0, "aborted": 0, "cells": 0, "tokens": 0, "noul": 0}

    def run_one(persona):
        client = getattr(local, "client", None)
        if client is None:
            client = local.client = JevClient(key, model=args.model)
            check_endpoint_is_typesafe(client.endpoint)
        rows, error = walk_persona(
            client, persona, question_list, mapper, router, state_template, args
        )
        respid = str(persona["respid"])
        if error is None:
            payload = rows + [{"arm": args.arm, "respid": respid, "done": True,
                               "repeat_tag": args.repeat_tag, "order_salt": args.order_salt,
                               "n_cells": len(rows)}]
        else:
            # Nothing but the marker: a partial walk's cells are not comparable, and keeping them
            # would let a later resume double-count the persona.
            payload = [{"arm": args.arm, "respid": respid, "aborted": True,
                        "repeat_tag": args.repeat_tag, "order_salt": args.order_salt,
                        "error": error}]
        with write_lock:
            with open(out_path, "a", encoding="utf-8") as handle:
                for row in payload:
                    handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            if error is None:
                counters["done"] += 1
                counters["cells"] += len(rows)
                counters["tokens"] += sum(r.get("input_tokens") or 0 for r in rows)
                counters["noul"] += sum(1 for r in rows if r.get("elicitation") == "noul")
            else:
                counters["aborted"] += 1
            n = counters["done"] + counters["aborted"]
            if n % 10 == 0 or n == len(todo):
                print(f"[progress] {n}/{len(todo)} personas  "
                      f"{counters['cells']} cells  {counters['aborted']} aborted  "
                      f"~${counters['tokens'] * RATE_IN_PER_TOKEN:.2f}", flush=True)
        if error is not None:
            print(f"  [abort] respid {respid} at {error['qid']}: "
                  f"{error['kind']} — {error['message']}", flush=True)

    print(f"Running {args.arm} (chain={args.chain}, primitive={args.primitive}) on "
          f"{len(todo)} personas, concurrency {args.concurrency}, model {args.model}")
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        list(pool.map(run_one, todo))

    print(f"\n{counters['done']} personas complete, {counters['aborted']} aborted, "
          f"{counters['cells']} cells written to {out_path}")
    if args.primitive == "noul":
        print(f"{counters['noul']} of {counters['cells']} cells asked as Noul "
              f"({counters['cells'] - counters['noul']} multiclass cells stayed on Choice)")
    print(f"billed ~{counters['tokens']:,} input tokens -> "
          f"~${counters['tokens'] * RATE_IN_PER_TOKEN:.2f}")
    if counters["aborted"]:
        print("Re-run the same command to retry the aborted personas (resume is per persona).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
