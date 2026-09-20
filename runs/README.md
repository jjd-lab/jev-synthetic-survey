# What is in `runs/`

Two experiments on the same instrument, the panel first. Each folder holds the output as the
runner wrote it; `reports/` holds what was scored from it.

Twin-2K-500 itself is not here. It is CC BY 4.0 (Toubia et al.,
[arXiv 2505.17479](https://arxiv.org/abs/2505.17479)) and `scripts/twin2k/fetch_twin2k.py`
downloads it. The files below are derived outputs and carry that dataset's human answers
alongside each model answer, so they are redistributed under the same CC BY 4.0 terms, with
attribution to the dataset authors.

## `jev_vs_gpt41_n300/`: the comparison the verdict rests on

Four arms, 300 respondents, the same 108 questions, every model seeing its own earlier answers.

| File | Arm | What was asked |
|---|---|---|
| `jev_choice.jsonl.gz` | Jev Choice | pick among the listed options |
| `jev_noul.jsonl.gz` | Jev Noul | one probability of "yes", options not offered (built after seeing the Choice result) |
| `gpt41_probs.jsonl.gz` | GPT-4.1 probabilities | state a probability per option |
| `gpt41_hard.jsonl.gz` | GPT-4.1 hard answer | pick one option (not a separate run, see below) |
| `respondents_300.txt` | | the respondent ids, in the order the runner walked them |

All four arms hold 24,596 answer cells: 300 respondents against the same 108 questions, minus the
cells no respondent was asked. One record per cell, holding the probability vector, the committed
answer, the human's answer, the option order as presented, and the model version. The two Jev
files carry 300 further records with `done: true` rather than a `qid`, one per respondent, marking
that the walk finished. The `arm` field inside each record keeps its original run name
(`jev_chained`, `gpt41_probs_chained`, `gpt41_hard_chained`, `jev_noul_chained`) because the scored
reports key off it.

`gpt41_probs_source/` holds the workbooks the GPT-4.1 probabilities arm was converted from.

**The hard-answer arm is not its own run.** `gpt41_hard.jsonl.gz` is the first 300 respondents of
the `demographics_stateful` panel run below, extracted: all 24,596 cells carry identical answers,
checked cell by cell. So it shares that arm's settings, including batched grids, which is one of
the two ways it differs from the probabilities arm. Only three models were ever run against these
300 respondents: Jev twice, and GPT-4.1 once for probabilities.

### The 300 are the first 300 rows, and they are not representative of the panel

`--sample 300` takes the first N respondents in file order. Respondent id order in Twin-2K-500
correlates with age, so the first 300 are older and more conservative than the full 2,058:

| | first 300 | all 2,058 |
|---|---|---|
| aged 18–29 | 9.3% | 18.9% |
| White | 76.0% | 66.1% |
| Republican | 34.0% | 26.2% |
| Very conservative | 12.0% | 6.7% |
| Retired | 18.0% | 11.9% |

The share aged 18–29 climbs monotonically across the file, from 9.3% in rows 1–300 to 30.2% in
rows 1801–2058, so this is a property of the ordering, not a coincidence of the draw.

What this does and does not affect: every claim in the write-up is a **paired** comparison between
arms on these same 300 respondents, and pairing is what the bootstrap resamples, so the verdict is
unaffected. Absolute levels are not: accuracy and calibration numbers here describe this slice,
not the US adult population, and should not be read against the full-panel numbers below. The
leave-one-out floor the n=300 arms are judged against is computed on these same 300 for that
reason.

## `gpt41_panel_n2058/`: what persona content buys you

GPT-4.1 over the whole panel, three arms varying two things one at a time: what the persona
contains, and whether the model sees its own earlier answers.

| Folder | Persona holds | Sees its own earlier answers |
|---|---|---|
| `demographics_stateless/` | 14 demographics | no |
| `demographics_stateful/` | 14 demographics | yes |
| `prior_answers_stateless/` | 14 demographics + 620 past answers | no |

There is no prior-answers + stateful cell: on top of 620 real prior answers the model's own
earlier answers add near-zero information, and it is by far the slowest path.

Each folder holds the respondent-level workbook, the validation summary, and the persona cache it
ran from. `prior_answers_stateless/` also holds `cells.jsonl.gz` (168,768 cells, all 2,058
respondents) and the per-resumption token records. That arm ran across several days under a daily
spend cap.

`content_filter_errors/` holds the cells Azure's content filter refused, from two superseded runs.
They are kept because the filter deletes specific respondents deterministically rather than at
random, which is a limitation of the panel arms rather than an incident.

## Reading a run back

```bash
python scripts/twin2k/prob_scoring.py score \
    --arm jev=runs/jev_vs_gpt41_n300/jev_choice.jsonl.gz \
    --arm bc=runs/jev_vs_gpt41_n300/gpt41_probs.jsonl.gz \
    --bootstrap 1000 --seed 20260919 --ece-bins 10 --out /tmp/check.json
```

`reports/README.md` maps each scored report back to the runs it came from.
