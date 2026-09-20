"""Derive the Twin variant configs from the baseline, so the shared prompt can't drift.

Runs on the same 108 questions and the same respondents, varying what the persona CONTAINS,
whether the model SEES ITS OWN earlier answers, and how a choice is ELICITED, one factor at a time:

    config file                                     persona holds        sees own answers
    twin2k_survey_config.yaml                       14 demographics      no   (baseline)
    twin2k_survey_config_prior_answers.yaml         + 620 prior Q&A      no
    twin2k_survey_config_chained.yaml               14 demographics      yes
    twin2k_survey_config_probs_chained.yaml         14 demographics      yes, elicited as a vector

Reading them: prior_answers minus baseline = what the respondent's own past answers are
worth. chained minus baseline = what letting the model see its earlier answers is worth.
probs_chained minus chained = what asking for a distribution instead of an answer costs or buys,
and it is the comparator the Jev probe is read against.
Every reading assumes the four differ in NOTHING else -- and the framework has no config
inheritance, so hand-maintained copies of a 60-line prompt would make a one-file edit both
easy and invisible. This copies the baseline's text (comments included) and substitutes only
what an arm is DEFINED by -- the mapping path, the memory mode, the runner flags that cancel
memory mode's side effects, the concurrency cap those imply, and the output directory -- then
asserts each fired.

An arm's runner settings belong in this table, not in the generated file. They look like
per-file tuning and so invite a hand-edit, but a hand-edit survives only until the next
regeneration silently reverts it: `prior_answers` carried four such settings for a while, and
regenerating would have turned it back into a stateless near-duplicate of the baseline.

There is no prior_answers x chained cell: on top of 620 real prior answers, the model's own
earlier answers add near-zero information, and it is the slowest path (`memory_mode: full`
walks each persona through ~82 sequential questions instead of batching — 60 asked of
everyone plus the arms this respondent drew).

Re-run after ANY edit to twin2k_survey_config.yaml. Generated files are overwritten.

Usage:  .venv\\Scripts\\python.exe scripts/twin2k/build_twin2k_variants.py
"""

import sys
from pathlib import Path

BASELINE = Path("configs/twin2k/twin2k_survey_config.yaml")

DEMOGRAPHIC_MAPPING = 'demographic_mapping: "configs/twin2k/twin2k_demographic_mapping.json"'
PERSONA_MAPPING = 'demographic_mapping: "configs/twin2k/twin2k_demographic_mapping_persona.json"'
NO_CHAINING = 'memory_mode: "stateless"'
CHAINING = 'memory_mode: "full"'
BASELINE_OUTPUT = 'output_dir: "outputs/twin2k/demographics_only"'

# Always FIND one whole line, never a multi-line block: this file is LF today and CRLF after a
# fresh checkout on Windows, so a multi-line needle misses silently. The REPLACE side may be a
# list of lines, which `build_variant` joins with the newline it sniffs off the baseline -- that
# is how a variant adds lines the baseline does not have.
#
# The baseline's two concurrency-comment lines and its cap are named because BOTH variants rewrite
# them, so one baseline edit does not have to be chased through two tables.
CAP_COMMENT_1 = "  # The only concurrency knob: .batch() caps in-flight calls with a rolling pool, so this is the"
CAP_COMMENT_2 = "  # number of (persona, question) calls in flight at once for this question."
CAP_VALUE = "max_concurrency: 100"

# The cap means different things either side of memory_mode, so chaining the model forces it down
# with the same edit -- carrying it here is what keeps the two from drifting apart by hand.
CHAINED_CAP = [
    (CAP_COMMENT_1,
     "  # Stateful slots hold a whole persona-walk, so this is 50 concurrent walks, not 50 calls."),
    (CAP_COMMENT_2,
     "  # 50 is this pipeline's proven-stable value; c=100 stalled the provider on that same path."),
    (CAP_VALUE, "max_concurrency: 50"),
]

# `prior_answers` runs on the STATEFUL path, for the cache rather than for chaining, and then
# cancels everything else `memory_mode: full` would change so the arm still differs from `baseline`
# in exactly one respect: the prior answers. Four settings carry that, and every one of them lived
# as a hand-edit to the generated file until now -- which is the failure this script exists to
# prevent, and which would have reverted the arm to stateless on the next regeneration.
PRIOR_ANSWERS_STATEFUL = [
    (CAP_COMMENT_1,
     [
         "  # The only concurrency knob: .batch() caps in-flight units with a rolling pool. This arm is",
         "  # respondent-major, so a slot is a whole persona-walk (~82 sequential calls), NOT a single call.",
         "  # It USED TO double as a cost knob: the prompt-cache hit rate fell as walks in flight rose --",
         "  # 92.5% at c=1, 89.3% at c=2, 54.6% at c=32, 50.5% at c=50 -- and a miss bills 4x. The cause was",
         "  # provider routing, not prefix eviction (32 concurrent calls on ONE shared prefix, with nothing to",
         "  # evict, still hit only 53%: scripts/twin2k/probe_cache_routing.py). `prompt_cache_key_by_respid`",
     ]),
    (CAP_COMMENT_2,
     [
         "  # below fixes it at the source, so c=32 now holds 92.3% -- the c=1 rate. Raise this for speed",
         "  # alone; do NOT lower it for cost without re-measuring, because that curve no longer exists.",
         "  # It is also the checkpoint cohort size, so it bounds what a mid-cohort spend cap can waste.",
     ]),
    (CAP_VALUE, "max_concurrency: 32"),
    ("# Batched path: one LLM call per (persona, question), no answer chaining. Twin needs no",
     [
         "# Respondent-major for COST, not for chaining. This arm's ~20,275-token prior-answer block is",
         "# identical on all 108 of a respondent's calls, and OpenAI's automatic prompt caching serves a",
         "# repeated prefix at 1/4 the input rate — but only if the calls arrive close together. The stateless",
         "# runner is question-major (one pass over the whole panel per question), so a respondent's next call",
     ]),
    ("# routing, so chaining is the only thing `full` adds — which is what the `_chained` run",
     [
         "# comes after 2,057 competing 20k prefixes; the stateful runner walks one respondent's questions",
         "# back-to-back. Measured hit rates: 26/30 question-major vs 30/30 respondent-major, and only the",
         "# latter is scale-invariant. Probe: scripts/twin2k/probe_prompt_cache.py.",
         "#",
     ]),
    ("# isolates.",
     [
         "# The two flags below cancel everything ELSE `full` would change, so elicitation still matches the",
         "# stateless `baseline` arm and the grounding-ladder comparison holds. Without them this would",
         "# silently become a different experiment, not a cheaper run of the same one.",
     ]),
    (NO_CHAINING,
     [
         "memory_mode: \"full\"",
         "",
         "# No answer chaining — that is what the `_chained` arm isolates, and this arm must differ from",
         "# `baseline` in exactly one respect: the prior answers. Also keeps the prompt constant across the",
         "# walk, so the cache serves the whole history block.",
         "chain_own_answers: false",
         "",
         "# Ask each grid member individually, as the stateless runner does. Left true, the 7 grid groups would",
         "# collapse 40 of 108 questions into 7 calls — ~30% cheaper, but a different elicitation from",
         "# `baseline` on those 40 columns.",
         "batch_grids: false",
     ]),
    ("include_request_id: false",
     [
         "include_request_id: false",
         "",
         "# Keep each respondent's 82 calls on one deployment. The provider load-balances across at least two,",
         "# and a cache entry lives only on the deployment that wrote it, so half this arm's calls were missing",
         "# a warm prefix purely by landing elsewhere. Measured over 638 walks (52,502 calls) at c=32: the",
         "# hit rate goes 54.6% -> 92.3% and the bill $2.24 -> $1.19/walk, i.e. concurrency now costs",
         "# nothing -- 92.5% is also what c=1 gives, so this recovers the whole gap rather than part of it.",
         "# Per-respondent, not one global key: prefixes differ per respondent, so a shared key would crowd",
         "# them onto one deployment. Changes cost, never answers -- the key is not part of the prompt.",
         "prompt_cache_key_by_respid: true",
     ]),
]

# `probs_chained` is `chained` asked for a DISTRIBUTION instead of an answer, and is the comparator
# for the Jev probe (`scripts/twin2k/probe_jev.py`): Jev's native probability vector against gpt-4.1
# verbalizing one. That comparison only measures the model if the two arms differ in nothing else,
# which is what the two extra flags buy -- `batch_grids: false` matches the probe's one-call-per-cell
# walk, and the shared persona cache keeps the twins themselves identical.
PROBS_CHAINED = [
    (NO_CHAINING,
     [
         "memory_mode: \"full\"",
         "",
         "# Ask each grid member individually, as the Jev probe does. Left true, the 7 grid groups would",
         "# collapse 40 of the 108 columns into 7 calls -- a different elicitation from the probe on 37% of",
         "# the instrument. And a grid writes ONE combined history turn, so the damage would not stay in",
         "# those 40: every later cell's history would differ too. This is the deliberate departure from",
         "# `chained`, which leaves the default true -- so `chained` is a loose sanity check here, not a",
         "# second comparator.",
         "batch_grids: false",
         "",
         "# The point of the arm: gpt-4.1 ASKED to state a distribution, against a model whose native",
         "# output is one. Everything else matches `chained` -- same prompt, same walk, and the answer",
         "# entering the history is still the model's own `choice`, never a draw from the vector.",
         "response_mode: \"verbalized_probs\"",
     ]),
    ("include_request_id: false",
     [
         "include_request_id: false",
         "",
         "# Reuse `chained`'s cache so this arm and the Jev probe walk the SAME 300 twins; the comparison",
         "# is about elicitation, not about personas. Omitted, `get_persona_cache_path` derives the path",
         "# from this arm's own `output_dir`, finds no cache, and regenerates all 300 through the provider.",
         "persona_cache_path: \"outputs/twin2k/chained/persona_cache.xlsx\"",
     ]),
]

# (name, one-line description, [(find, replace), ...])
VARIANTS = [
    ("prior_answers",
     "the respondent's own past answers in the persona — the paper's published twin (71.72%)",
     [(DEMOGRAPHIC_MAPPING, PERSONA_MAPPING), *PRIOR_ANSWERS_STATEFUL]),
    ("chained",
     "demographics only, but the model sees its own earlier answers — not in the paper",
     [(NO_CHAINING, CHAINING), *CHAINED_CAP]),
    ("probs_chained",
     "chained, but asked for a probability vector — the comparator for the Jev probe",
     [*PROBS_CHAINED, *CHAINED_CAP]),
]

BASELINE_HEADER = "# Twin-2K-500 — BASELINE: demographics only, no answer chaining"
BANNER = "# GENERATED by scripts/twin2k/build_twin2k_variants.py — edit the baseline, then re-run."


def build_variant(source: str, name: str, summary: str, substitutions: list) -> str:
    """Apply one variant's substitutions to the baseline text, failing loudly on a miss."""
    # Sniffed once up front because every substitution that ADDS lines needs it: the baseline's
    # newline depends on how git checked it out (LF here, CRLF on a fresh Windows clone), and a
    # literal "\n" would plant a lone LF among CRLF lines. os.linesep describes the platform
    # rather than the file being copied, so it is the wrong question to ask.
    newline = "\r\n" if "\r\n" in source else "\n"
    text = source
    for find, replace in substitutions:
        if find not in text:
            raise SystemExit(
                f"{name}: {BASELINE} no longer contains {find!r} — the substitution would "
                f"silently produce a duplicate of the baseline."
            )
        # A list replacement is a block that stands in for ONE baseline line. Joining it here is
        # what lets the find side stay a single line, and so stay newline-blind.
        text = text.replace(find, newline.join(replace) if isinstance(replace, list) else replace)
    text = text.replace(
        BASELINE_HEADER, f"# Twin-2K-500 — {name.upper()}: {summary}{newline}{BANNER}"
    )
    return text.replace(BASELINE_OUTPUT, f'output_dir: "outputs/twin2k/{name}"')


def main() -> int:
    if not BASELINE.exists():
        raise FileNotFoundError(f"{BASELINE} not found — run from the repo root")
    # newline="" both ways: the baseline's line endings depend on how git checked it out (LF
    # here, CRLF on a fresh Windows clone), and normalising them would make every line of the
    # derived files differ from it — defeating the point of generating.
    # Explicit open() because Path.read_text gained `newline` only in 3.13.
    with open(BASELINE, encoding="utf-8", newline="") as handle:
        source = handle.read()
    for token in (BASELINE_HEADER, BASELINE_OUTPUT):
        if token not in source:
            raise SystemExit(f"{BASELINE} is missing the expected line {token!r}")

    for name, summary, substitutions in VARIANTS:
        out_path = BASELINE.with_name(f"twin2k_survey_config_{name}.yaml")
        with open(out_path, "w", encoding="utf-8", newline="") as handle:
            handle.write(build_variant(source, name, summary, substitutions))
        print(f"wrote {out_path}\n    {summary}")

    print(f"\nAll derived from {BASELINE}; re-run after editing it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
