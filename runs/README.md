# What is in `runs/`

Two experiments on the same instrument, the panel first. Each folder holds the output as the
runner wrote it; `reports/` holds what was scored from it.

Twin-2K-500 itself is not here. It is CC BY 4.0 (Toubia et al.,
[arXiv 2505.17479](https://arxiv.org/abs/2505.17479)) and `scripts/twin2k/fetch_twin2k.py`
downloads it. The files below are derived outputs and carry that dataset's human answers
alongside each model answer, so they are redistributed under the same CC BY 4.0 terms, with
attribution to the dataset authors.

## `jev_vs_gpt41_n300/`: the comparison the verdict rests on

Five arms, 300 respondents, the same 108 questions, every model seeing its own earlier answers.

| File | Arm | What was asked |
|---|---|---|
| `jev_choice.jsonl` | Jev Choice | pick among the listed options |
| `jev_choice_described.jsonl` | Jev Choice described | the same, with a derived description per option on the 40 pricing columns (built after seeing the Choice result) |
| `jev_noul.jsonl` | Jev Noul | one probability of "yes", options not offered (built after seeing the Choice result) |
| `gpt41_probs.jsonl` | GPT-4.1 probabilities | state a probability per option |
| `gpt41_hard.jsonl` | GPT-4.1 hard answer | pick one option (not a separate run, see below) |
| `respondents_300.txt` | | the respondent ids, in the order the runner walked them |

All five arms hold 24,596 answer cells: 300 respondents against the same 108 questions, minus the
cells no respondent was asked. One record per cell, holding the probability vector, the committed
answer, the human's answer, the option order as presented, and the model version. The three Jev
files carry 300 further records with `done: true` rather than a `qid`, one per respondent, marking
that the walk finished. The `arm` field inside each record keeps its original run name
(`jev_chained`, `gpt41_probs_chained`, `gpt41_hard_chained`, `jev_noul_chained`,
`jev_choice_described`) because the scored reports key off it.

`gpt41_probs_source/` holds the workbooks the GPT-4.1 probabilities arm was converted from.

These five ship uncompressed, at about 15 MB each. Git zlib-compresses blobs anyway, so an
already-gzipped file costs it slightly more to store than the plain text, and a `.jsonl` can be
grepped and read on the web without a decompression step. The 2,058-respondent arms follow the
same rule: `jev_vs_gpt41_n2058/gpt41_hard.jsonl` ships plain at 68 MB, and
`prior_answers_stateless/cells.jsonl` at 67 MB. One file has no choice: `jev_noul.jsonl.gz` is
115 MB raw, past the 100 MB file limit GitHub refuses a push over, so there compression is not a
preference.

**The hard-answer arm is not its own run.** `gpt41_hard.jsonl` is the first 300 respondents of
the `demographics_stateful` panel run below, extracted: all 24,596 cells carry identical answers,
checked cell by cell. So it shares that arm's settings, including batched grids, which is one of
the two ways it differs from the probabilities arm. Only four runs ever touched these 300
respondents: Jev three times, and GPT-4.1 once for probabilities.

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
ran from. `prior_answers_stateless/` also holds `cells.jsonl` (168,768 cells, all 2,058
respondents) and the per-resumption token records. That arm ran across several days under a daily
spend cap.

## `jev_vs_gpt41_n2058/`: the same two models over the whole panel

The n=300 comparison above, rerun across every respondent. Two arms, all 2,058 people, **168,768
answer cells each**, which is the same per-respondent count as the n=300 arms: 108 questions minus
the ones no given respondent was asked, since 48 of the 108 columns are between-subject.

| File | Arm | What was asked |
|---|---|---|
| `jev_noul.jsonl.gz` | Jev Noul | one probability of "yes", options not offered |
| `gpt41_hard.jsonl` | GPT-4.1 hard answer | pick one option, no probabilities (extracted, not its own run) |

The Jev arm ran as `jev_noul_chained` on `jev-1.13.0` against the `demographics_stateful` persona
cache, and finished clean: 2,058 `done: true` markers, one per respondent, and zero error records.

**The hard-answer arm is again an extraction, not a run.** It is the `demographics_stateful` panel
run read back per cell, so it carries that arm's settings including batched grids. Its `probs`
field is `null` on every record, so it supports accuracy comparisons and nothing distributional.
The n=300 `gpt41_hard.jsonl` is a strict subset of it: all 24,596 of those cells appear here with
identical committed answers, checked cell by cell.

The hard-answer arm ships as a plain `.jsonl` like the n=300 arms and like
`prior_answers_stateless/cells.jsonl`, at 68 MB. `jev_noul.jsonl.gz` is the one file in the repo
that is gzipped, and not by preference: at 115 MB raw it is past the 100 MB limit GitHub refuses a
push over. `prob_scoring.py` reads `.jsonl` and `.jsonl.gz` without being told which.

[`reports/score_nc_vs_ac_n2058.json`](../reports/score_nc_vs_ac_n2058.json) scores the pair. Its
main use is as a check on the n=300 slice, and the slice holds up: Jev Noul moves from 0.1530 to
0.1523 on the distribution gap, 0.1472 to 0.1418 on calibration, and 67.28% to 67.64% on accuracy
across a 6.9-fold increase in respondents, despite those 300 being demographically unrepresentative
of the panel.

It is **not** a model comparison, for the same reason the n=300 hard arm is not one: with `probs`
null on every cell, GPT-4.1's soft scores are computed against a one-hot spike, which measures
whether it has a distribution and not how good one is. The ordinal gap is where that bites, and it
is why 0.6507 against Jev's 0.6766 should not be read as GPT-4.1 winning the ordinal half. The
verdict continues to rest on the n=300 comparison, where both models answered under the same
elicitation and both produced a real vector.

## Reading a run back

```bash
python scripts/twin2k/prob_scoring.py score \
    --arm jev=runs/jev_vs_gpt41_n300/jev_choice.jsonl \
    --arm bc=runs/jev_vs_gpt41_n300/gpt41_probs.jsonl \
    --bootstrap 1000 --seed 20260919 --ece-bins 10 --out /tmp/check.json
```

[`reports/README.md`](../reports/README.md) maps each scored report back to the runs it came from.

Back to [the repo overview](../README.md), or to [the write-up](../docs/README.md) for what these
runs were collected to answer.
