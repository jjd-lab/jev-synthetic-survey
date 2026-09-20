# What is in `reports/`

Scored output. Every figure quoted in the write-up comes from one of these files, and each one is
reproducible from the runs in [`runs/`](../runs/) with the command shown.

These files record where they were scored from, and that path is stale in every one of them: it
names `outputs/`, this repo's gitignored working directory, from before the runs were arranged for
publication. The `individual_signal_*` files carry it in a `source` field, the `paper_accuracy_*`
files in their top-level key. The same runs now ship under `runs/gpt41_panel_n2058/`, and the
tables below map each file to the run it came from.

## The comparison that decides the verdict

| File | Arms | Scored from |
|---|---|---|
| `score_with_noul.json` | Jev Noul, Jev Choice, GPT-4.1 probabilities | `runs/jev_vs_gpt41_n300/{jev_noul,jev_choice,gpt41_probs}.jsonl` |
| `score_all_arms.json` | Jev Choice, GPT-4.1 probabilities, GPT-4.1 hard answer | `runs/jev_vs_gpt41_n300/{jev_choice,gpt41_probs,gpt41_hard}.jsonl` |
| `score_jc_vs_ac.json` | Jev Choice, GPT-4.1 hard answer | `runs/jev_vs_gpt41_n300/{jev_choice,gpt41_hard}.jsonl` |
| `score_with_described.json` | Jev Choice described, Jev Choice, GPT-4.1 probabilities | `runs/jev_vs_gpt41_n300/{jev_choice_described,jev_choice,gpt41_probs}.jsonl` |
| `score_nc_vs_ac_n2058.json` | Jev Noul, GPT-4.1 hard answer, **all 2,058 respondents** | `runs/jev_vs_gpt41_n2058/jev_noul.jsonl.gz`, `gpt41_hard.jsonl` |

```bash
python scripts/twin2k/prob_scoring.py score \
    --arm jev_noul=runs/jev_vs_gpt41_n300/jev_noul.jsonl \
    --arm jev=runs/jev_vs_gpt41_n300/jev_choice.jsonl \
    --arm bc=runs/jev_vs_gpt41_n300/gpt41_probs.jsonl \
    --bootstrap 1000 --seed 20260919 --ece-bins 10 --out /tmp/check.json
```

The `--arm` labels are part of the output: they become the keys in the JSON, so changing them
changes the file. The labels above are the ones the shipped reports were scored with.

Every statistic reproduces. Two fields will not match byte for byte: each arm's `path`, which
records where the file was read from, and occasionally the last digit of a p-value, which moves
with the platform's floating-point rounding. Verified for `score_with_noul.json` and
`score_all_arms.json`: of several thousand values, only the three `path` strings and
one p-value's final digit differed.

## The full-panel GPT-4.1 runs

`arm1` in these filenames is the demographics-stateless arm, named before the arms were.

| File | Arm | Scored from |
|---|---|---|
| `paper_accuracy_full_arm1.json`, `individual_signal_full_arm1.json` | demographics, stateless | `runs/gpt41_panel_n2058/demographics_stateless/` |
| `paper_accuracy_full_chained.json`, `individual_signal_full_chained.json` | demographics, stateful | `runs/gpt41_panel_n2058/demographics_stateful/` |
| `paper_accuracy_full_prior_answers.json`, `individual_signal_full_prior_answers.json` | prior answers, stateless | `runs/gpt41_panel_n2058/prior_answers_stateless/` |
| `task_deep_dive_full.md` | all three | the same workbooks, per task |

```bash
# --json is what writes the file; without it both scripts only print.
python scripts/twin2k/paper_accuracy.py --ceiling \
    --details runs/gpt41_panel_n2058/demographics_stateless/respondent_details_20260904_091556.xlsx \
    --json /tmp/paper_accuracy_full_arm1.json
python scripts/twin2k/individual_signal.py \
    --details runs/gpt41_panel_n2058/demographics_stateless/respondent_details_20260904_091556.xlsx \
    --summary runs/gpt41_panel_n2058/demographics_stateless/validation_summary_20260904_091556.xlsx \
    --json /tmp/individual_signal_full_arm1.json
```

`--ceiling` is needed to reproduce the `ceiling` block the shipped `paper_accuracy_*` files carry,
and it reads the raw wave files, so run `fetch_twin2k.py` first. The top-level key in those files
is built from the run folder's name, so re-scoring now yields `demographics_stateless (...)` where
the shipped file says `demographics_only (...)`: the folder was renamed after they were written.
The contents under that key are unchanged.

`paper_accuracy_full_prior_answers.json` is also the anchor for the scorer's own test: the
leave-one-out and accuracy figures in it must reproduce exactly from the shipped workbook, which
is what `tests/unit/test_twin2k_prob_scoring.py` checks.

## Not reproducible from this repo

`paper_accuracy_matched50.json` was scored from a 50-respondent matched subset whose workbooks are
not shipped (`respondent_details_demographics_only_matched50.xlsx`,
`respondent_details_chained_matched50.xlsx`, and a superseded prior-answers run). It is kept
because the write-up quotes it, but it cannot be re-run here.

Back to [the repo overview](../README.md), [the write-up](../docs/README.md), or
[`runs/README.md`](../runs/README.md) for the raw per-cell files these were scored from.
