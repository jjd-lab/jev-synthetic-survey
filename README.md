# Jev on a synthetic survey: does a native probability vector beat a verbalized one?

We asked a decision-only model, TypeSafe's [Jev](https://typesafe.ai) `jev-1.13.0`, and `gpt-4.1` to
play the same 300 survey respondents on the public
[Twin-2K-500](https://huggingface.co/datasets/LLM-Digital-Twin/Twin-2K-500) benchmark. That is 108
questions, 16 behavioral-economics tasks, and 24,596 answered cells per arm. Jev returns a
probability vector natively. We asked `gpt-4.1` to write one out.

We fixed two tests in writing before collecting any data. Both failed.

The full write-up is in [`docs/`](docs/README.md), split into a
[survey track](docs/README.md#survey-track) for what transfers to any model on this benchmark and a
[Jev track](docs/README.md#jev-track) for the verdict on this one.

**Where to go from here.** This page is the summary; each row below is the thing itself.

| If you want | Go to |
|---|---|
| to have never thought about synthetic survey respondents | [New to this?](#new-to-this-start-here), just below |
| the result, all five arms, one table | [All five arms](#all-five-arms) |
| the write-up, paper style, with every caveat | [`docs/`](docs/README.md) |
| to re-derive every number yourself, no account needed | [Reproduce it](#reproduce-it) |
| the raw per-cell answers, model beside human | [`runs/`](runs/README.md) |
| the scored reports behind each figure | [`reports/`](reports/README.md) |
| the code: scorer, Jev probe, survey engine | [`scripts/twin2k/`](scripts/twin2k/README.md), [`src/`](src/) |

---

## New to this? Start here

**What a synthetic survey respondent is.** A language model asked to fill in a questionnaire as if
it were a particular person. You give it some facts about a real human, it answers questions that
human also answered, and you compare the two. The appeal is that real panels are slow and
expensive, so a model that could stand in for one would let you pretest a survey before fielding
it. Whether it can is an open question, and this repo is one measurement of it.

**The data is not ours, and neither is the benchmark design.** Everything here runs on
[Twin-2K-500](https://huggingface.co/datasets/LLM-Digital-Twin/Twin-2K-500), built for this exact
question by Toubia et al. (*Twin-2K-500*, [arXiv 2505.17479](https://arxiv.org/abs/2505.17479),
CC BY 4.0). They surveyed 2,058 US adults on Prolific across four waves in February 2025, over 500
questions each, then held one block out: a battery of classic behavioral-economics tasks. The rest
of a person's answers is what you may use to build their twin. The held-out block is the exam. We
did not collect any of it and we do not redistribute it;
[`fetch_twin2k.py`](scripts/twin2k/fetch_twin2k.py) downloads it from the authors.

**What a run does here.** For each of 300 respondents, build a persona out of their 14 demographic
items, walk that persona through 108 of the held-out questions one at a time, and record what the
model answered beside what the human actually answered. One pass over all 300 people is an **arm**.
Five arms ship in this repo and they differ only in which model was asked, and how.

**What is being compared.** Two ways of getting a probability out of a model. Jev is decision-only:
it writes no prose and returns a number per option natively, because that is all it is built to do.
`gpt-4.1` is a general chat model, so we asked it to write those same numbers out in words. The
question is whether the native vector beats the verbalized one.

**Why the tables below lead with a distribution gap instead of accuracy.** Nobody can predict how
one individual answers a trick question. The humans themselves only reproduce their own earlier
answer 81.68% of the time, and every arm here scores below a baseline that ignores the persona
entirely. What a survey is actually for is the population number, the share who picked option A. So
the metric that decides things is how far an arm's *distribution* of answers sits from the humans',
and an arm can win that while losing per-person accuracy.

[The dataset and the instrument](docs/survey/01-dataset-and-instrument.md) has the full design and
the three different ways this dataset's questions can be counted.
[The metrics page](docs/survey/02-metrics.md) defines every number below.

---

## The verdict is reject

The test that decides it asked whether Jev's native vector beats a verbalized one in **both** halves
of the instrument. It does not. Jev loses the yes/no half, 0.1985 against `gpt-4.1`'s 0.1789, so the
recommendation is unchanged: stay with verbalized probabilities and soft aggregation.

The second test, on calibration, also failed, and for all four arms at once. That one is a statement
about demographics-only grounding rather than about any model.
[Details and both tests in full](docs/jev/02-planned-comparison.md).

## All five arms

Accuracy is last in this table on purpose. A synthetic panel earns its keep when the *distribution*
it produces matches the population's, so the first two columns are the ones the verdict turns on:
how far an arm's answer distribution sits from the humans' on the 65 two-option questions (soft
TVD), and how far it sits on the 43 questions whose options are ordered (soft Wasserstein-1). Lower
is better everywhere except the last column.

| Arm | distribution gap | ordinal gap | calibration (ECE) | Brier | accuracy | cost |
|---|---|---|---|---|---|---|
| Jev `Choice` (the registered arm) | 0.1985 | 0.6864 | 0.2029 | 0.7550 | 67.59% | $4.01 |
| Jev `Choice` + option descriptions | 0.1985 | 0.6822 | 0.2032 | 0.7553 | 67.51% | $4.03 |
| Jev `Noul` | **0.1530** | **0.6812** | **0.1472** | **0.7385** | 67.28% | $4.02 |
| `gpt-4.1` probabilities | 0.1789 | 0.7272 | 0.2393 | 0.8108 | 64.78% | ~$136 |
| `gpt-4.1` hard answer | 0.2037 | 0.6987 | 0.3741 | 1.1664 | **69.32%** | not measured |

300 respondents, 108 columns, 24,596 cells in every arm, equal weight per task. Three things the
table will mislead you about if you read it alone:

- **The hard-answer arm has no probability vector.** Its ECE and Brier score a one-hot spike, so
  they measure the absence of a distribution rather than the quality of one. It is in the table
  because it is the arm that wins accuracy, which is the whole point about accuracy. It was
  extracted from a larger panel run rather than collected on its own, so it has no separate cost.
- **The arm that wins accuracy is last on the distribution gap, on calibration and on Brier.** All
  five sit below the persona-blind leave-one-out floor of 73.59%, so none of them predicts an
  individual. The distribution columns are where the arms actually separate.
- **The descriptions arm changed 40 of the 108 columns**, the pricing block, because the
  description is derived from the option label and most labels yield none. The other 68 columns got
  a byte-identical payload, which is the control that proves the run was clean rather than a
  result. [What it did and did not move](docs/jev/06-option-descriptions.md).

## Asking the same question a different way closed most of the gap

We asked Jev every yes/no question as a `Choice`, meaning pick one of two options. That was the
wrong form, and it cost more than the whole gap we were trying to measure.

Re-asking those same 65 columns as a `Noul`, a single probability that the answer is yes with no
options offered, changes the result at the same price and with no loss of accuracy.

| | `Choice` | `Noul` |
|---|---|---|
| distribution gap (soft TVD, 65 two-option columns) | 0.1985 | 0.1530 |
| calibration error (ECE) | 0.2029 | 0.1472 |
| accuracy | 67.59% | 67.28% |
| cost | $4.01 | $4.02 |

The mechanism is saturation. Asked as a `Choice`, Jev put a probability of exactly zero on one of
the two options in 16.6% of two-option cells. Asked as a `Noul`, it did that in 0.0%. On the same
cell and the same label the two forms disagree by a mean of 0.13, so they are not variants of each
other.

If you take one thing from this repo, take this: on this model, never ask a yes/no question as a
two-option choice. [The follow-up in full](docs/jev/03-noul-follow-up.md).

That arm does not overturn the verdict and was never eligible to. We fixed the test on the `Choice`
arm and built `Noul` afterwards, having seen the result. Against `gpt-4.1` it wins on the
aggregation this codebase uses, 0.1530 against 0.1789, and loses the per-column test that was fixed
in advance at p=0.9995. One task holds 40 of the 65 two-option columns, and that weighting choice
accounts for the entire disagreement between the two answers.

## Where Jev is better

The verdict is a conjunction, so losing one half of it is not the same as losing outright. Measured:

- It wins the 43 ordinal questions on the ordinal distribution gap, 0.6864 against 0.7272, better in
  26 of 43 columns at p=0.031. That advantage carries its all-cell Brier win, 0.7550 against 0.8108.
- It costs about 34 times less. $4.01 measured against roughly $136 inferred from `gpt-4.1` list
  rates, because Jev bills input only and its output is free.
- It answers about ten times faster per call, 0.26 s measured across all 24,596 cells against
  roughly 2.7 s inferred for `gpt-4.1`. The two arms' wall clocks look close only because they ran
  at different concurrency, so do not read those as a speed comparison.
- It produced no errors and no aborted walks in either of its two arms, 24,596 cells each.
- It tracks price more tightly than the respondents themselves do. The pricing block pipes a
  randomized price into each stem, and Jev's purchase probability follows it at r = −0.55 against
  the humans' −0.33, in 40 of 40 columns.

## Where it is worse

Jev loses the yes/no half, and most of that is the pricing block. We first wrote this up as
TypeSafe's documented "not a calculator" weakness. That was wrong. Measuring it gives a more useful
answer: the arithmetic is fine and the decision boundary is not.

| over the 40 pricing columns | Jev `Choice` | Jev `Noul` | gpt-4.1 | humans |
|---|---|---|---|---|
| corr(price, P(yes)) | −0.551 | −0.522 | −0.488 | −0.333 |
| mean P(yes) | 0.601 | 0.591 | 0.343 | 0.416 |
| signed bias | +0.185 | +0.175 | −0.073 | |
| columns biased high | 36/40 | 37/40 | 10/40 | |

The bias is near-constant, +0.185 asking as a `Choice` and +0.175 as a `Noul`, and on the `Noul`
arm it accounts for 95% of that arm's entire pricing error. Jev predicts a purchase far more often
than these respondents reported making one. Re-committing at a shifted threshold recovers 5.89
points of `Choice` pricing accuracy and 8.45 of `Noul`'s, while giving `gpt-4.1` 0.03 points, which
says the ranking is sound and only the operating point is wrong. That threshold is fitted in-sample,
so it bounds the failure rather than scoring it.
[Details](docs/jev/04-price-sensitivity.md).

## A result that is not about Jev

Asking `gpt-4.1` for a probability distribution cost 4.42 points of committed accuracy against
asking it to pick an answer, 64.90% versus 69.32%. The obvious confound is that the probability arm
also unbatched its grids. The entire loss sits in the 15 tasks where grid batching is not in play,
and the one block that was unbatched improved by 0.89 points, so the cause is the elicitation rather
than the batching.

If you ask a model to verbalize its uncertainty, expect its committed answer to move. We measured
that on one model and one instrument; treat it as a hypothesis worth checking on yours rather than
as a settled law. [Details](docs/survey/04-elicitation-effects.md).

## Limits

**The instrument.** Twin-2K-500's holdout is a cognitive-bias battery while the grounding is
personality and economic-preference content, so the test is out-of-domain by construction. Its
questions are built so that answers should not track who you are.

**The sample.** 2,058 Prolific US adults, four waves, February 2025 (Toubia et al.,
[arXiv 2505.17479](https://arxiv.org/abs/2505.17479)). Not population-representative, US-only,
public since 2025, and built from classic replications, so contamination applies to every arm
equally. Our 300 are the first 300 rows and are older, whiter and more conservative than the panel.
Read the between-arm comparisons and do not read any absolute number.

**This evaluation.** 300 of 2,058 respondents. 108 of 126 holdout columns, because 18 sliders and
free-numeric items have no option list to decode against. One pinned model version. Two-option and
ordinal questions only, with multi-select untested.

**Individual-level prediction.** Every arm scores below a persona-blind leave-one-out majority
baseline of 73.59%. A demographics-grounded synthetic respondent is usable for a population's
distribution and not for predicting a specific person. That is the standing state of this field
rather than a result about Jev.

One number puts the rest in proportion: humans agree with their own earlier answers only 81.68% of
the time. [All limitations](docs/survey/05-limitations.md).

## Reproduce it

Python 3.11 or newer. Every run behind the verdict is in this repo, and scoring needs nothing
downloaded and no account.

```bash
pip install -r requirements.txt

python scripts/twin2k/prob_scoring.py score \
    --arm jev_noul=runs/jev_vs_gpt41_n300/jev_noul.jsonl \
    --arm jev=runs/jev_vs_gpt41_n300/jev_choice.jsonl \
    --arm bc=runs/jev_vs_gpt41_n300/gpt41_probs.jsonl \
    --bootstrap 1000 --seed 20260919 --ece-bins 10 \
    --out /tmp/check.json
```

That reproduces [`reports/score_with_noul.json`](reports/score_with_noul.json). Every number quoted
above comes out of it. Two fields will not match byte for byte: each arm's `path`, which records
where the file was read from and in the shipped report still names the working directory the run was
scored in, and occasionally the last digit of a p-value, which moves with the platform's
floating-point rounding.

[`runs/jev_vs_gpt41_n300/`](runs/jev_vs_gpt41_n300/) holds the five arms as plain JSONL, one record
per respondent and question cell, carrying the probability vector, the committed answer, the human's
answer, the option order as presented, and the model version. Each arm is 24,596 cells and the five
come to 70 MB, small enough to ship here rather than from a dataset host. The 2,058-respondent
arms ship as plain JSONL too, except for the one file past GitHub's 100 MB limit: the scorer also
reads `.jsonl.gz`, which is how `jev_noul` is stored at 115 MB raw.
[`runs/README.md`](runs/README.md) maps every file to the claim it supports.

The price diagnostic also needs the dataset itself, for the per-respondent piped prices.

```bash
python scripts/twin2k/fetch_twin2k.py            # Twin-2K-500, CC BY 4.0
python scripts/twin2k/price_sensitivity.py \
    --arm jev_choice=runs/jev_vs_gpt41_n300/jev_choice.jsonl \
    --arm jev_noul=runs/jev_vs_gpt41_n300/jev_noul.jsonl \
    --arm gpt41_probs=runs/jev_vs_gpt41_n300/gpt41_probs.jsonl
```

What each step costs, measured on a 2023 laptop:

| Step | Needs | Time | Cost |
|---|---|---|---|
| score the three arms above | nothing downloaded, no account | 1m 45s | free |
| `pytest` | nothing | 22s, 398 tests, no network | free |
| `fetch_twin2k.py` | 205 MB of disk | a few minutes on a home connection | free |
| the price diagnostic, once fetched | the dataset | under a second | free |
| a new 300-respondent Jev arm | `TYPESAFE_API_KEY` | 6 to 8 min at 16 walks | about $4 |
| a new 300-respondent `gpt-4.1` arm | `API_KEY` | about 22 min at 50 walks | about $136 at list rates |

The two run costs are the whole reason the comparison is interesting: they buy the same 24,596
cells. Jev bills input only at $0.042 per million tokens with output free, which is where the
34-fold gap comes from. The `gpt-4.1` figure is inferred from list rates rather than billed
through, so read it as an order of magnitude. `probe_jev.py --dry-run` prints the exact Jev cost
before anything is sent.

The two wall clocks are **not** a like-for-like speed comparison, and nothing here should be read
as one. The arms ran at different concurrency, 16 in-flight walks against 50, so the Jev figure is
the slower setting rather than the slower model. Per call Jev is the faster of the two by roughly
an order of magnitude: its records carry `latency_ms` and average **0.26 s** over all 24,596 cells,
while the `gpt-4.1` arm was converted from workbooks and kept no per-call timing, so its rate can
only be inferred from wall clock at about 2.7 s. Jev's walk is latency-bound with no measurable
overhead on top, so its wall clock scales down with concurrency: raising `--concurrency` is the
whole lever.

## Credentials

Only needed to run a **new** arm. Scoring the shipped runs needs none.

```bash
cp .env.example .env
```

| Variable | For | Notes |
|---|---|---|
| `TYPESAFE_API_KEY` | Jev | the probe also accepts `JEV_KEY` |
| `API_BASE_URL`, `API_KEY` | the `gpt-4.1` comparator | any OpenAI-compatible endpoint |

[`.env.example`](.env.example) documents the optional settings. The table above has what a full arm
costs and how long it takes.

The configs ship a plain `gpt-4.1`, so `.env.example` as written runs against stock OpenAI. Every
number in this repo was collected through a hosted OpenAI-compatible endpoint, and the model id is
the only thing that differs. It is sent verbatim as the model, so at such an endpoint the provider
prefix *is* the routing key. To reproduce the shipped runs, restore that prefix along with its
`API_BASE_URL`.
What it does not change is structured output: `structured_output_method` branches only on a
`bedrock/` prefix, so both ids take the same hard-enforced `json_schema` path the probability arm
depends on.

On a personal key, lower `max_concurrency` in the YAML (50 in three arms, 32 in
`prior_answers_stateless`) to 8-16 — a slot holds a whole persona-walk, not one call, and a
personal account's rate limit is far below a shared endpoint's.

## Run a new arm

```bash
python scripts/twin2k/probe_jev.py --arm my_run --chain --primitive noul --sample 300
python main.py --config configs/twin2k/gpt41_probs.yaml \
    --checkpoint-dir outputs/twin2k/checkpoints --resume
```

To collect only the respondents an earlier run did not reach, both runners take the panel from the
top and skip what is already done. The Jev probe resumes from its own output, per persona, keyed on
`--arm` + `--repeat-tag` + `--order-salt` + whether `--describe-criteria` was set:

```bash
python scripts/twin2k/probe_jev.py --arm jev_noul_chained --chain --primitive noul \
    --sample 2058 --out <the arm's existing .jsonl>   # prints "300 already complete, 1758 to run"
```

`main.py` has no such marker, so it takes the window explicitly — `--sample 2058 --skip 300` is
respondents 301-2058. Option order is seeded per respid
([`survey_runner_excel.py`](src/core/survey_runner_excel.py)), so those cells are identical to the
same rows of a full run.

Give a skipped run its **own `--run-id`**. A checkpoint record is keyed by its position in the
run's persona list, so position 0 is respondent 1 in a full run and respondent 301 under
`--skip 300`; sharing a dir would make the export drop one of every colliding pair. The run dir
records the window it was built for and refuses a mismatch, so this fails loudly rather than
quietly. Convert each run's workbook to per-cell JSONL with
[`prob_scoring.py convert`](scripts/twin2k/prob_scoring.py), then concatenate the two files. The
scorer keys on respid and qid, so order across the join does not matter.

The Jev probe refuses to load a config outside `configs/twin2k/`, and refuses any endpoint that is
not TypeSafe. Twin-2K-500 is the only data cleared to be sent there, and the code and the tests
enforce that rather than convention.

## What we would do next

1. **Re-run the distribution test with `Noul`** as the registered elicitation, and fix the
   aggregation rule in advance. That choice accounts for the entire disagreement in the result
   above.
2. **More respondents.** 48 between-subject columns draw only 16 to 25 respondents at this sample
   size, which is where the per-column test is noisiest.

Describing the options was the obvious first candidate and has since been run, pre-registered, and
[it changes nothing](docs/jev/06-option-descriptions.md): the pricing bias moved +0.185 to +0.183
and the gap did not move at all. That closes the objection that `Choice` was merely
under-specified.

[The full list](docs/jev/05-what-this-licenses.md#what-to-run-next).

## Author's take

Everything above is measured. This part is opinion, kept separate on purpose.

I think Jev is a strong option and I would use it. It costs about 34 times less, it produced no
errors in 24,596 cells, it wins the ordinal half outright, and the yes/no half it lost closes almost
entirely once you stop asking those questions the wrong way. The reject stands and I am not going to
soften it. Given `gpt-4.1`'s input and a `Choice` on every yes/no item, Jev did not win. But that
comparison held the prompt fixed to be fair to the model, which means it left every one of
TypeSafe's own prompting options untouched. The one we changed afterwards moved the losing half by
more than the whole deficit, and I expect the others to matter too.

I would use it today for ordinal-scale marginals under cost pressure, with `Noul` for anything
yes/no.

## Contents

| | |
|---|---|
| [`docs/`](docs/README.md) | the write-up: the survey track, the Jev track, and the question inventory |
| [`runs/`](runs/README.md) | the raw per-cell output of every arm, and what each file supports |
| [`reports/`](reports/README.md) | the scored reports behind every figure, and how to regenerate them |
| [`scripts/twin2k/`](scripts/twin2k/README.md) | the scorer, the Jev probe, the price diagnostic, and the config builders |
| [`configs/twin2k/`](configs/twin2k/) | the arm configurations, one per run |
| [`src/`](src/), [`main.py`](main.py) | the survey engine the `gpt-4.1` arms run on |
| [`tests/`](tests/) | `pytest`, offline, no network |

`src/` and `main.py` are adapted from a private survey-simulation codebase, which is why they carry
machinery this evaluation does not exercise.

## How to cite

> Jev on a synthetic survey: does a native probability vector beat a verbalized one? 2026.

Add the repository URL when citing; this copy does not record one.

The dataset is not ours. Cite it as Toubia, O., et al. *Twin-2K-500*,
[arXiv 2505.17479](https://arxiv.org/abs/2505.17479).

## License

Code and write-up are [MIT](LICENSE).

Twin-2K-500 is CC BY 4.0 and is not redistributed here; `fetch_twin2k.py` downloads it from the
source. The files under [`runs/`](runs/) are derived outputs that carry that dataset's human answers
alongside each model answer, and are redistributed under the same CC BY 4.0 terms with attribution
to its authors.
