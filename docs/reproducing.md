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
`prior_answers_stateless` — to 8-16. A concurrency slot holds a whole persona walk, not one call,
and a personal account's rate limit is far below a shared endpoint's.

[`.env.example`](../.env.example) documents the optional settings. The configs ship a plain
`gpt-4.1`, so `.env.example` as written runs against stock OpenAI. Every GPT-4.1 number in this repo
was collected through a hosted OpenAI-compatible endpoint, and the model id is the only thing that
differs: it is sent verbatim as the model, so at such an endpoint the provider prefix *is* the
routing key. To reproduce the shipped runs, restore that prefix along with its `API_BASE_URL`.
Structured output does not change: `structured_output_method` branches only on a `bedrock/` prefix,
so both ids take the same hard-enforced `json_schema` path the probability arm depends on.

Scoring the shipped runs needs none of this: no key, no download. That command is in the
[README](../README.md#reproduce-it), and the rest are in [`reports/README.md`](../reports/README.md).

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
`--sample 2058 --skip 300` is respondents 301-2058. Option order is seeded per respid
([`survey_runner_excel.py`](../src/core/survey_runner_excel.py)), so those cells are identical to
the same rows of a full run.

Give a skipped run its **own `--run-id`**. A checkpoint record is keyed by its position in the run's
persona list, so position 0 is respondent 1 in a full run and respondent 301 under `--skip 300`;
sharing a directory would make the export drop one of every colliding pair. The run directory
records the window it was built for and refuses a mismatch, so this fails loudly rather than
quietly. Convert each run's workbook to per-cell JSONL with
[`prob_scoring.py convert`](../scripts/twin2k/prob_scoring.py), then concatenate the two files. The
scorer keys on respid and qid, so order across the join does not matter.

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

The probe refuses to load a config outside `configs/twin2k/`, and refuses any endpoint that is not
TypeSafe. Twin-2K-500 is the only data cleared to be sent there, and the code and the tests enforce
that rather than convention.

## The grounding arm

One arm, stateless, grounded in 620 prior answers instead of 14 demographics. It reads a different
config and a different persona cache from the four above, which is the whole point: the persona is
byte-identical to the one the GPT-4.1 prior-answers arm saw.

```bash
python scripts/twin2k/probe_jev.py \
    --config configs/twin2k/prior_answers_stateless.yaml \
    --arm jev_noul_prior_answers --primitive noul --sample 300 \
    --persona-cache runs/gpt41_panel_n2058/prior_answers_stateless/persona_cache.xlsx \
    --concurrency 8 \
    --out runs/jev_grounding_n300/jev_prior_answers.jsonl
```

No `--chain`: the arm is stateless by design, matching its GPT-4.1 counterpart. Concurrency 8 rather
than 16 — at 16 the first pass lost 8 personas to rate limits on a 21k-token state, and re-running
the same command cleared all 8 in 35 seconds. $24.40 and 17m 25s in total. Written up in
[06 Grounding](jev/06-grounding.md).

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

## The price diagnostic

The one analysis that needs the dataset itself, for the per-respondent piped prices. It prints its
figures and writes no report, so the numbers on [the price page](jev/04-price-sensitivity.md) come
from running it:

```bash
python scripts/twin2k/price_sensitivity.py \
    --arm jev_choice=runs/jev_vs_gpt41_n300/jev_choice.jsonl \
    --arm jev_noul=runs/jev_vs_gpt41_n300/jev_noul.jsonl \
    --arm gpt41_probs=runs/jev_vs_gpt41_n300/gpt41_probs.jsonl
```

## What a re-run will not match

- **Filenames.** Both runners stamp the run's finish time into `respondent_details_*`,
  `validation_summary_*` and `run_tokens_*`.
- **Individual answers.** Every arm ran at temperature 0.7. Option order is seeded per respid and so
  is stable, but the answers themselves are not deterministic.
- **The `arm` field.** It records the `--arm` label you pass, and the scored reports key off it. The
  labels in the table above are the ones the shipped files carry.

## Recorded cost

Measured for the n=300 arms: Jev Choice $4.01, Jev Choice described $4.03, Jev Noul $4.02, Jev on
prior-answers grounding $24.40, GPT-4.1 probabilities roughly $136 inferred from list pricing. The
hard-answer arm has no cost of its own, being an extraction.

A Jev arm's cost is its input tokens and nothing else — output is free and the rate is flat — so
the spread between those figures is entirely prompt length:

| | Tokens per cell | Cost |
|---|---|---|
| persona and question alone, unchained | 670 | about $0.69 |
| chained, averaged over a 108-question walk (Jev Noul) | 3,891 | $4.02 measured |
| 620 prior answers in the persona, unchained | 23,624 | $24.40 measured |

`--dry-run` prints the estimate before anything is sent, and excludes a fixed per-request overhead
of roughly 300 tokens per cell, which is why the billed figure lands slightly above it.

The full-panel arms have no recorded dollar figure. Their token counts are in each run's
`run_tokens_*.json`.

What each step costs, measured on a 2023 laptop:

| Step | Needs | Time | Cost |
|---|---|---|---|
| score the three headline arms | nothing downloaded, no account | 1m 45s | free |
| `pytest` | nothing | under a minute, no network | free |
| `fetch_twin2k.py` | 205 MB of disk | a few minutes on a home connection | free |
| the price diagnostic, once fetched | the dataset | under a second | free |
| a new 300-respondent Jev arm | `TYPESAFE_API_KEY` | 6 to 8 min at 16 walks | about $4 |
| a new 300-respondent GPT-4.1 arm | `API_KEY` | about 22 min at 50 walks | about $136 at list rates |

The two run costs buy the same 24,596 cells. Jev bills input only at $0.042 per million tokens with
output free, which is where the 34-fold gap comes from. The GPT-4.1 figure is inferred from list
rates rather than billed through, so read it as an order of magnitude.

The two wall clocks are **not** a like-for-like speed comparison. The arms ran at different
concurrency, 16 in-flight walks against 50, so the Jev figure is the slower setting rather than the
slower model. Per call Jev is the faster of the two by roughly an order of magnitude: its records
carry `latency_ms` and average **0.26 s** over all 24,596 cells, while the GPT-4.1 arm was converted
from workbooks and kept no per-call timing, so its rate can only be inferred from wall clock at
about 2.7 s. Jev's walk is latency-bound with no measurable overhead on top, so its wall clock
scales down with concurrency: raising `--concurrency` is the whole lever.

[`runs/jev_vs_gpt41_n300/`](../runs/jev_vs_gpt41_n300/) holds the five comparison arms as plain
JSONL, 70 MB in all. The 2,058-respondent arms ship as plain JSONL too, except for the one file past
GitHub's 100 MB limit: the scorer also reads `.jsonl.gz`, which is how `jev_noul` is stored at
115 MB raw.

Back to [the repo overview](../README.md), [the write-up](README.md), or
[`runs/README.md`](../runs/README.md).
