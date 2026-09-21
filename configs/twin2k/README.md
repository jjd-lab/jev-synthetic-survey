# `configs/twin2k/`

Four configs, one per GPT-4.1 arm. Each one is a complete survey definition: the question mapping,
the persona mapping, the prompt, and the handful of settings that make it a distinct arm. They are
identical apart from the settings in the table below, because three of them are generated from the
baseline by [`build_twin2k_variants.py`](../../scripts/twin2k/build_twin2k_variants.py) so the
shared prompt cannot drift between arms.

## Config to run to report

| Config | What makes it its own arm | Run it produced | Reports scored from it |
|---|---|---|---|
| `demographics_stateless.yaml` | `chain_own_answers: false`, `batch_grids: false` | [`runs/gpt41_panel_n2058/demographics_stateless/`](../../runs/gpt41_panel_n2058/demographics_stateless/) | `reports/gpt41_panel_n2058/paper_accuracy_full_arm1.json`, `individual_signal_full_arm1.json` |
| `demographics_stateful.yaml` | `chain_own_answers: true`, `batch_grids: true` | [`runs/gpt41_panel_n2058/demographics_stateful/`](../../runs/gpt41_panel_n2058/demographics_stateful/) | `reports/gpt41_panel_n2058/paper_accuracy_full_chained.json`, `individual_signal_full_chained.json` |
| `prior_answers_stateless.yaml` | persona carries 620 prior answers, not just the 14 demographics | [`runs/gpt41_panel_n2058/prior_answers_stateless/`](../../runs/gpt41_panel_n2058/prior_answers_stateless/) | `reports/gpt41_panel_n2058/paper_accuracy_full_prior_answers.json`, `individual_signal_full_prior_answers.json` |
| `gpt41_probs.yaml` | `response_mode: verbalized_probs`, grids unbatched | [`runs/jev_vs_gpt41_n300/gpt41_probs/`](../../runs/jev_vs_gpt41_n300/gpt41_probs/), converted to `gpt41_probs.jsonl` | `score_with_noul`, `score_all_arms`, `score_jc_vs_ac`, `score_with_described`, and the n=300 half of the verdict |

The report filenames and keys, `arm1` included, are decoded in [the glossary](../../docs/README.md#names-used-throughout).
[`reports/README.md`](../../reports/README.md) maps every report back to its run and gives the
command that regenerates it.

## Two arms have no config of their own

**The Jev arms.** `jev_choice`, `jev_noul` and `jev_choice_described` are not run by `main.py` and
have no config file. [`probe_jev.py`](../../scripts/twin2k/probe_jev.py) reads
`demographics_stateful.yaml` for the persona, the question mapping and the prompt, then chooses the
elicitation from its own flags (`--primitive`, `--chain`, `--describe-criteria`). That is deliberate:
sharing the config is what makes the Jev arms and the GPT-4.1 arms comparable, since the only thing
that differs is the model and how it was asked.

**GPT-4.1 hard answer.** Both `gpt41_hard.jsonl` files are extractions from the
`demographics_stateful` run rather than runs of their own, so they inherit that config exactly,
batched grids included.

## Two things that trip people up

**`output_dir` is not where the shipped runs live.** Every config writes to `outputs/twin2k/...`,
which is gitignored working space. The runs behind the published numbers were moved to `runs/` and
arranged by experiment. A new run writes to `outputs/`; nothing overwrites `runs/`.

**`max_rows: 50` is a smoke run, not the real arm.** Every config ships that way so a bare checkout
does something small and cheap. The published arms were collected with `--sample` overriding it,
2,058 for the panel arms and 300 for the comparison. `--sample` also matters for `--skip`, which
offsets *into* the `--sample` window rather than into the file.

## The generated files beside them

The `.json` mappings in this directory are generated, not written by hand, and the three builders
that own them refuse stray arguments so a stray `--help` cannot rewrite them. See
[`scripts/twin2k/README.md`](../../scripts/twin2k/README.md).

Back to [the repo overview](../../README.md), or to [the write-up](../../docs/README.md).
