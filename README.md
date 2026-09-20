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

---

## The verdict is reject

The test that decides it asked whether Jev's native vector beats a verbalized one in **both** halves
of the instrument. It does not. Jev loses the yes/no half, 0.1985 against `gpt-4.1`'s 0.1789, so the
recommendation is unchanged: stay with verbalized probabilities and soft aggregation.

The second test, on calibration, also failed, and for all four arms at once. That one is a statement
about demographics-only grounding rather than about any model.
[Details and both tests in full](docs/jev/02-planned-comparison.md).

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
  rates, because Jev bills input only and its output is free. Wall clock was comparable.
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
    --arm jev_noul=runs/jev_vs_gpt41_n300/jev_noul.jsonl.gz \
    --arm jev=runs/jev_vs_gpt41_n300/jev_choice.jsonl.gz \
    --arm bc=runs/jev_vs_gpt41_n300/gpt41_probs.jsonl.gz \
    --bootstrap 1000 --seed 20260919 --ece-bins 10 \
    --out /tmp/check.json
```

That reproduces [`reports/score_with_noul.json`](reports/score_with_noul.json). Every number quoted
above comes out of it. Two fields will not match byte for byte: each arm's `path`, which records
where the file was read from and in the shipped report still names the working directory the run was
scored in, and occasionally the last digit of a p-value, which moves with the platform's
floating-point rounding.

[`runs/jev_vs_gpt41_n300/`](runs/jev_vs_gpt41_n300/) holds the four arms of that comparison as
gzipped JSONL, one record per respondent and question cell, carrying the probability vector, the
committed answer, the human's answer, the option order as presented, and the model version. Each arm
is 24,596 cells; the four are 3.1 MB gzipped against 56.7 MB raw, which is why they ship here rather
than from a dataset host. The scorer reads either form.
[`runs/README.md`](runs/README.md) maps every file to the claim it supports.

The price diagnostic also needs the dataset itself, for the per-respondent piped prices.

```bash
python scripts/twin2k/fetch_twin2k.py            # Twin-2K-500, CC BY 4.0
python scripts/twin2k/price_sensitivity.py \
    --arm jev_choice=runs/jev_vs_gpt41_n300/jev_choice.jsonl.gz \
    --arm jev_noul=runs/jev_vs_gpt41_n300/jev_noul.jsonl.gz \
    --arm gpt41_probs=runs/jev_vs_gpt41_n300/gpt41_probs.jsonl.gz
```

## Credentials

Only needed to run a **new** arm. Scoring the shipped runs needs none.

```bash
cp .env.example .env
```

| Variable | For | Notes |
|---|---|---|
| `TYPESAFE_API_KEY` | Jev | the probe also accepts `JEV_KEY` |
| `API_BASE_URL`, `API_KEY` | the `gpt-4.1` comparator | any OpenAI-compatible endpoint |

[`.env.example`](.env.example) documents the optional settings. A full 300-respondent Jev arm cost
$4.01; the `gpt-4.1` comparator arm is inferred at roughly $136.

## Run a new arm

```bash
python scripts/twin2k/probe_jev.py --arm my_run --chain --primitive noul --sample 300
python main.py --config configs/twin2k/gpt41_probs.yaml \
    --checkpoint-dir outputs/twin2k/checkpoints --resume
```

The Jev probe refuses to load a config outside `configs/twin2k/`, and refuses any endpoint that is
not TypeSafe. Twin-2K-500 is the only data cleared to be sent there, and the code and the tests
enforce that rather than convention.

## What we would do next

1. **Describe the options.** Jev currently sees bare `"Yes"` and `"No"` labels, with all the meaning
   sitting in the prose stem. A constant offset in what counts as yes is what a description should
   move, and it is the cheapest experiment left at about $4.
2. **Re-run the distribution test with `Noul`** as the registered elicitation, and fix the
   aggregation rule in advance. That choice accounts for the entire disagreement in the result
   above.
3. **More respondents.** 48 between-subject columns draw only 16 to 25 respondents at this sample
   size, which is where the per-column test is noisiest.

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
| [`scripts/twin2k/`](scripts/twin2k/) | the Jev client, the probe, the scorer, and the price diagnostic |
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
