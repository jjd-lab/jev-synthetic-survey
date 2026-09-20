# Reproducing the runs

Every artifact under [`runs/`](../runs/), with the command that produced it. Scoring those runs into
`reports/` is a separate step, covered in [`reports/README.md`](../reports/README.md).

Nothing here overwrites a published file. `main.py` and `probe_jev.py` write to `outputs/`, which is
gitignored; the shipped runs were copied into `runs/` deliberately after the fact.

## Prerequisites

```bash
pip install -r requirements.txt
python scripts/twin2k/fetch_twin2k.py     # Twin-2K-500, CC BY 4.0; data/ is gitignored
cp .env.example .env                      # then fill in the keys below
```

| Variable | Needed for |
|---|---|
| `API_BASE_URL`, `API_KEY` | the four GPT-4.1 arms (`main.py`) |
| `TYPESAFE_API_KEY`, or `JEV_KEY` | the four Jev arms (`probe_jev.py`) |

On a personal key, lower `max_concurrency` in the config YAML — 50 in three arms, 32 in
`prior_answers_stateless` — to 8-16. A concurrency slot holds a whole persona walk, not one call.

## The GPT-4.1 panel

2,058 respondents, 108 columns, one config per arm. Each writes to its config's `output_dir`.

| Run | Config | Distinguishing setting |
|---|---|---|
| [`runs/gpt41_panel_n2058/demographics_stateless/`](../runs/gpt41_panel_n2058/demographics_stateless/) | `demographics_stateless.yaml` | `chain_own_answers: false`, `batch_grids: false` |
| [`runs/gpt41_panel_n2058/demographics_stateful/`](../runs/gpt41_panel_n2058/demographics_stateful/) | `demographics_stateful.yaml` | `chain_own_answers: true`, `batch_grids: true` |
| [`runs/gpt41_panel_n2058/prior_answers_stateless/`](../runs/gpt41_panel_n2058/prior_answers_stateless/) | `prior_answers_stateless.yaml` | persona carries 620 prior answers, not 14 demographics |

```bash
python main.py --config configs/twin2k/demographics_stateless.yaml
```

For a run you expect to interrupt, add checkpointing. The prior-answers arm was collected this way
across six sessions under a daily spend cap, which is why it ships six `run_tokens_*.json` files:

```bash
python main.py --config configs/twin2k/prior_answers_stateless.yaml \
    --checkpoint-dir outputs/twin2k/checkpoints --resume
```

`main.py` has no completion marker, so a partial re-run takes its window explicitly:
`--sample 2058 --skip 300` is respondents 301-2058. Option order is seeded per respid, so those
cells are identical to the same rows of a full run.

## The n=300 probability arm

```bash
python main.py --config configs/twin2k/gpt41_probs.yaml --sample 300
```

That writes workbooks, matching [`runs/jev_vs_gpt41_n300/gpt41_probs/`](../runs/jev_vs_gpt41_n300/gpt41_probs/).
Converting them to the scored per-cell JSONL is a second step:

```bash
python scripts/twin2k/prob_scoring.py convert \
    --details outputs/twin2k/gpt41_probs/respondent_details_<timestamp>.xlsx \
    --arm gpt41_probs_chained --out /tmp/gpt41_probs.jsonl \
    --sample 300 --respid-order runs/jev_vs_gpt41_n300/respondents_300.txt
```

`--respid-order` matters: without it `--sample` falls back to spreadsheet row order, which is not
the loader's order, and the arms stop being paired respondent for respondent.

## The Jev arms

All four read `demographics_stateful.yaml` for the persona, question mapping and prompt, and pick
the elicitation from flags. Sharing the config is what makes the Jev and GPT-4.1 arms comparable:
the model and the way it is asked are the only differences.

| Run | `--arm` | Flags beyond `--chain` |
|---|---|---|
| `runs/jev_vs_gpt41_n300/jev_choice.jsonl` | `jev_chained` | none |
| `runs/jev_vs_gpt41_n300/jev_choice_described.jsonl` | `jev_choice_described` | `--describe-criteria` |
| `runs/jev_vs_gpt41_n300/jev_noul.jsonl` | `jev_noul_chained` | `--primitive noul` |
| `runs/jev_vs_gpt41_n2058/jev_noul.jsonl.gz` | `jev_noul_chained` | `--primitive noul --sample 2058` |

```bash
python scripts/twin2k/probe_jev.py \
    --config configs/twin2k/demographics_stateful.yaml \
    --arm jev_noul_chained --chain --primitive noul --sample 300 \
    --persona-cache runs/gpt41_panel_n2058/demographics_stateful/persona_cache.xlsx \
    --out /tmp/jev_noul.jsonl
```

Passing `--persona-cache` reuses the shipped personas. Without it the probe derives a cache path
from the config's `output_dir` and regenerates them, which costs calls and will not match cell for
cell.

`--dry-run` prints the exact cost before anything is sent.

The probe resumes from its own output, per persona, keyed on `--arm` plus `--repeat-tag`,
`--order-salt` and whether `--describe-criteria` was set. Pointing `--out` at an existing file
continues it:

```bash
python scripts/twin2k/probe_jev.py --config configs/twin2k/demographics_stateful.yaml \
    --arm jev_noul_chained --chain --primitive noul --sample 2058 \
    --out runs/jev_vs_gpt41_n2058/jev_noul.jsonl   # "300 already complete, 1758 to run"
```

## The hard-answer extractions

Neither `gpt41_hard.jsonl` is a run. Both are the `demographics_stateful` panel run read back per
cell, so they inherit that arm's settings, batched grids included, and their `probs` field is
`null` on every record.

```bash
python scripts/twin2k/prob_scoring.py convert \
    --details runs/gpt41_panel_n2058/demographics_stateful/respondent_details_20260904_131620.xlsx \
    --arm gpt41_hard_chained --out /tmp/gpt41_hard.jsonl \
    --sample 300 --respid-order runs/jev_vs_gpt41_n300/respondents_300.txt
```

Drop `--sample` and `--respid-order` for the 2,058-respondent version.

## What a re-run will not match

- **Filenames.** Both runners stamp the run's finish time into `respondent_details_*`,
  `validation_summary_*` and `run_tokens_*`.
- **Individual answers.** Every arm ran at temperature 0.7. Option order is seeded per respid and so
  is stable, but the answers themselves are not deterministic.
- **The `arm` field.** It records the `--arm` label you pass, and the scored reports key off it. The
  labels in the table above are the ones the shipped files carry.

## Recorded cost

Measured for the n=300 arms: Jev Choice $4.01, Jev Choice described $4.03, Jev Noul $4.02, GPT-4.1
probabilities roughly $136 inferred from list pricing. The hard-answer arm has no cost of its own,
being an extraction.

The full-panel arms have no recorded dollar figure. Their token counts are in each run's
`run_tokens_*.json`.

Back to [the repo overview](../README.md), [the write-up](README.md), or
[`runs/README.md`](../runs/README.md).
