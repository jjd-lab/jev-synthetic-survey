"""Derive the Twin variant configs from the baseline, so the shared prompt can't drift.

Runs on the same 108 questions and the same respondents, varying what the persona CONTAINS,
whether the model SEES ITS OWN earlier answers, and how a choice is ELICITED, one factor at a time:

    config file                       persona holds        sees own answers
    demographics_stateless.yaml       14 demographics      no   (baseline)
    prior_answers_stateless.yaml      + 620 prior Q&A      no
    demographics_stateful.yaml        14 demographics      yes
    gpt41_probs.yaml                  14 demographics      yes, elicited as a vector

Reading them: prior answers minus baseline = what the respondent's own past answers are
worth. stateful minus baseline = what letting the model see its earlier answers is worth.
gpt41_probs minus stateful = what asking for a distribution instead of an answer costs or buys,
and it is the comparator the Jev probe is read against.
Every reading assumes the four differ in NOTHING else -- and the framework has no config
inheritance, so hand-maintained copies of a 60-line prompt would make a one-file edit both
easy and invisible. This copies the baseline's text (comments included) and substitutes only
what an arm is DEFINED by -- the mapping path, the memory mode, the runner flags that cancel
memory mode's side effects, the concurrency cap those imply, and the output directory -- then
asserts each fired.

An arm's runner settings belong in this table, not in the generated file. They look like
per-file tuning and so invite a hand-edit, but a hand-edit survives only until the next
regeneration silently reverts it: `prior_answers_stateless` carried four such settings for a while, and
regenerating would have turned it back into a stateless near-duplicate of the baseline.

There is no prior_answers x chained cell: on top of 620 real prior answers, the model's own
earlier answers add near-zero information, and it is the slowest path (`memory_mode: full`
walks each persona through ~82 sequential questions instead of batching — 60 asked of
everyone plus the arms this respondent drew).

Re-run after ANY edit to demographics_stateless.yaml. Generated files are overwritten.

Usage:  python scripts/twin2k/build_twin2k_variants.py
"""

import sys
from pathlib import Path

BASELINE = Path("configs/twin2k/demographics_stateless.yaml")

DEMOGRAPHIC_MAPPING = 'demographic_mapping: "configs/twin2k/twin2k_demographic_mapping.json"'
PERSONA_MAPPING = 'demographic_mapping: "configs/twin2k/twin2k_demographic_mapping_persona.json"'
BASELINE_OUTPUT = 'output_dir: "outputs/twin2k/demographics_stateless"'

# Always FIND one whole line, never a multi-line block: this file is LF today and CRLF after a
# fresh checkout on Windows, so a multi-line needle misses silently. The REPLACE side may be a
# list of lines, which `build_variant` joins with the newline it sniffs off the baseline -- that
# is how a variant adds lines the baseline does not have.
#
# The baseline's two concurrency-comment lines and its cap are named because BOTH variants rewrite
# them, so one baseline edit does not have to be chased through two tables.
CAP_COMMENT_1 = "  # The only concurrency knob. A slot holds a whole persona-walk (~82 sequential calls), not a"
CAP_COMMENT_2 = "  # single call, so this is 50 concurrent walks. 50 is this pipeline's proven-stable value;"
CAP_COMMENT_3 = "  # c=100 stalled that endpoint on the same path."
CAP_VALUE = "max_concurrency: 50"

# Every arm is a respondent-major walk now; the baseline is the one that does not chain. So a
# variant says only what it changes about the walk, and the two flags the baseline sets to false
# are the tokens the chaining arms flip.
NO_CHAIN_COMMENT = "# Never show the model its own earlier answers. That is the difference this arm is"
NO_CHAIN_COMMENT_2 = "# defined by, and `demographics_stateful` is the same config with this set true."
NO_CHAIN = "chain_own_answers: false"
NO_BATCH_COMMENT = "# Ask each grid member individually. Left true, the 7 grid groups would collapse 40 of the"
NO_BATCH_COMMENT_2 = "# 108 questions into 7 calls, a different elicitation on 37% of the instrument."
NO_BATCH = "batch_grids: false"

# `prior_answers_stateless` differs from the baseline in ONE respect: what the persona contains.
# It inherits the baseline's no-chaining, per-member-grid walk unchanged, and adds cache pinning
# because its ~20,275-token persona block is what makes a warm prefix worth routing for.
PRIOR_ANSWERS_STATEFUL = [
    (DEMOGRAPHIC_MAPPING, PERSONA_MAPPING),
    ("include_request_id: false",
     [
         "include_request_id: false",
         "",
         "# Keep each respondent's 82 calls on one deployment. The provider load-balances across at least",
         "# two, and a cache entry lives only on the deployment that wrote it, so half this arm's calls",
         "# were missing a warm prefix purely by landing elsewhere. Measured over 638 walks (52,502",
         "# calls) at c=32: the hit rate goes 54.6% -> 92.3% and the bill $2.24 -> $1.19/walk. Changes",
         "# cost, never answers -- the key is not part of the prompt.",
         "prompt_cache_key_by_respid: true",
     ]),
    (CAP_COMMENT_1,
     "  # Slots hold a whole persona-walk, so this is 32 concurrent walks, not 32 calls. Lower than"),
    (CAP_COMMENT_2,
     "  # the others: it is also the checkpoint cohort size, bounding what a spend cap can waste."),
    (CAP_COMMENT_3,
     "  # Raise it for speed alone; lowering it for cost no longer buys anything."),
    (CAP_VALUE, "max_concurrency: 32"),
]

# `demographics_stateful` is the baseline with chaining switched on. That one flag is the whole
# arm: it is what isolates "the model sees its own earlier answers" from everything else.
CHAINED = [
    (NO_CHAIN_COMMENT,
     "# Feed the model its own earlier answers. This single flag is what separates this arm from"),
    (NO_CHAIN_COMMENT_2, "# the baseline, which is otherwise the identical walk."),
    (NO_CHAIN, "chain_own_answers: true"),
    (NO_BATCH_COMMENT,
     "# Grids batched, as the runner does by default: the 7 grid groups become 7 calls covering"),
    (NO_BATCH_COMMENT_2,
     "# 40 of the 108 questions, the one way this arm departs from the baseline's elicitation."),
    (NO_BATCH, "batch_grids: true"),
]

# `gpt41_probs` is `demographics_stateful` asked for a DISTRIBUTION instead of an answer, and is
# the comparator for the Jev probe (`scripts/twin2k/probe_jev.py`): Jev's native probability vector
# against gpt-4.1 verbalizing one. That comparison only measures the model if the two arms differ
# in nothing else, which is what keeping the baseline's per-member grids buys -- it matches the
# probe's one-call-per-cell walk -- while the shared persona cache keeps the twins identical.
PROBS_CHAINED = [
    (NO_CHAIN_COMMENT,
     "# Chained, like `demographics_stateful`: the answer entering the history is still the"),
    (NO_CHAIN_COMMENT_2, "# model's own `choice`, never a draw from the vector."),
    (NO_CHAIN, "chain_own_answers: true"),
    (NO_BATCH_COMMENT,
     "# Grids stay per-member, as the Jev probe asks them. Batched, the 7 grid groups would"),
    (NO_BATCH_COMMENT_2,
     "# collapse 40 of the 108 columns into 7 calls, and a grid writes ONE combined history turn."),
    (NO_BATCH,
     [
         "batch_grids: false",
         "",
         "# The point of the arm: gpt-4.1 ASKED to state a distribution, against a model whose native",
         "# output is one.",
         "response_mode: \"verbalized_probs\"",
     ]),
    ("include_request_id: false",
     [
         "include_request_id: false",
         "",
         "# Reuse the stateful demographics arm's cache so this arm and the Jev probe walk the SAME",
         "# 300 twins; the comparison is about elicitation, not about personas. This is the copy that",
         "# ships in runs/, so a fresh clone reuses it instead of regenerating 300 personas through the",
         "# provider. Omitted, `get_persona_cache_path` derives a path from this arm's own `output_dir`.",
         "persona_cache_path: \"runs/gpt41_panel_n2058/demographics_stateful/persona_cache.xlsx\"",
     ]),
]

VARIANTS = [
    ("prior_answers_stateless",
     "the respondent's own past answers in the persona — the paper's published twin (71.72%)",
     PRIOR_ANSWERS_STATEFUL),
    ("demographics_stateful",
     "demographics only, but the model sees its own earlier answers — not in the paper",
     CHAINED),
    ("gpt41_probs",
     "chained, but asked for a probability vector — the comparator for the Jev probe",
     PROBS_CHAINED),
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



def _refuse_arguments(what_it_writes: str) -> None:
    """Exit rather than rebuild when given any argument.

    These builders take no options and overwrite tracked files, so a typo, a stray flag, or a
    `--help` reflex used to run a full regeneration and report success. Fail closed instead.
    """
    if sys.argv[1:]:
        raise SystemExit(
            f"{Path(sys.argv[0]).name} takes no arguments. It {what_it_writes}.\n"
            f"Run it with no arguments to regenerate."
        )


def main() -> int:
    _refuse_arguments("regenerates the three derived configs under configs/twin2k/ from the "
                      "baseline config")
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
        out_path = BASELINE.with_name(f"{name}.yaml")
        with open(out_path, "w", encoding="utf-8", newline="") as handle:
            handle.write(build_variant(source, name, summary, substitutions))
        print(f"wrote {out_path}\n    {summary}")

    print(f"\nAll derived from {BASELINE}; re-run after editing it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
