# Jev on a synthetic survey: does a native probability vector beat a verbalized one?

We asked a decision-only model, TypeSafe's [Jev](https://typesafe.ai) `jev-1.13.0`, and `gpt-4.1` to
play the same 300 survey respondents on the public
[Twin-2K-500](https://huggingface.co/datasets/LLM-Digital-Twin/Twin-2K-500) benchmark. That is 108
questions, 16 behavioural-economics tasks, and 24,596 answered cells per arm. Jev returns a
calibrated probability vector natively. We asked `gpt-4.1` to write one out.

We fixed two criteria in writing before collecting any data. One of them failed.

---

## Asking the same question a different way closed most of the gap

We asked Jev every yes/no question as a `Choice`, meaning pick one of two options. That was the wrong
form, and it cost more than the whole gap we were trying to measure.

Re-asking those same 65 columns as a `Noul`, a single probability that the answer is yes with no
options offered, changes the result at the same price and with no loss of accuracy.

| | `Choice` | `Noul` |
|---|---|---|
| distributional error (soft TVD, 65 binary columns) | 0.1985 | 0.1530 |
| calibration error (ECE) | 0.2029 | 0.1472 |
| accuracy | 67.59% | 67.28% |
| cost | $4.01 | $4.02 |

The mechanism is saturation. Asked as a `Choice`, Jev put a probability of exactly zero on one of the
two options in 16.6% of binary cells. Asked as a `Noul`, it did that in 0.0%. On the same cell and
the same label the two forms disagree by a mean of 0.13, so they are not variants of each other.

If you take one thing from this repo, take this. Never ask a decision model a yes/no question as a
two-option choice.

## The pre-registered verdict is reject

C3 asked whether Jev's native vector beats a verbalized one in both column buckets. It does not. Jev
loses the nominal half, 0.1985 against `gpt-4.1`'s 0.1789, so the recommendation is unchanged. Stay
with verbalized probabilities and soft aggregation.

The `Noul` arm does not overturn that and was never eligible to. We registered C3 on the `Choice` arm
and built `Noul` afterwards, having seen the result. Against `gpt-4.1` it wins on the aggregation
this codebase uses, 0.1530 against 0.1789, and loses the pre-registered per-column test at p=0.9995.
One task holds 40 of the 65 binary columns, and that weighting choice accounts for the entire
disagreement between the two answers. Both numbers are in [FINDINGS.md](FINDINGS.md).

## Where Jev is better

The verdict is a conjunction, so losing one half of it is not the same as losing outright. Measured:

- It wins the 43 ordinal questions on Wasserstein-1, 0.6864 against 0.7272, better in 26 of 43
  columns at p=0.031. That advantage carries its all-cell multiclass Brier win, 0.7550 against 0.8108.
- It costs about 34 times less. $4.01 measured against roughly $136 inferred from `gpt-4.1` list
  rates, because Jev bills input only and its output is free. Wall clock was comparable.
- It produced no errors and no aborted walks in 24,596 cells, across four separate arms.
- It reads numbers better than people do. The pricing block pipes a randomized price into each stem,
  and Jev's purchase probability tracks that price more tightly than the real humans' answers do,
  r = −0.55 against −0.33, in 40 of 40 columns.

## Where it is worse

Jev loses the binary half, and most of that is the pricing block. We first wrote this up as the
vendor's documented "not a calculator" weakness. That was wrong. Measuring it gives a more useful
answer, which is that the arithmetic is fine and the decision boundary is not.

| over the 40 pricing columns | Jev `Choice` | Jev `Noul` | gpt-4.1 | humans |
|---|---|---|---|---|
| corr(price, P(yes)) | −0.551 | −0.522 | −0.488 | −0.333 |
| mean P(yes) | 0.601 | 0.591 | 0.343 | 0.416 |
| signed bias | +0.185 | +0.175 | −0.073 | |
| columns biased high | 36/40 | 37/40 | 10/40 | |

The bias is a near-constant +0.175, which accounts for 95% of that arm's entire pricing error. Jev
predicts a purchase far more often than these respondents reported making one. Re-committing at a
shifted threshold recovers 8.45 points of its pricing accuracy and gives `gpt-4.1` 0.03 points, which
says the ranking is sound and only the operating point is wrong. That threshold is fitted in-sample,
so it bounds the failure rather than scoring it. Reproduce it with
[`price_sensitivity.py`](scripts/twin2k/price_sensitivity.py).

## A result that is not about Jev

Asking `gpt-4.1` for a probability distribution cost 4.42 points of committed accuracy against asking
it to pick an answer, 64.90% versus 69.32%. The obvious confound is that the probability arm also
unbatched its grids. The entire loss sits in the 15 tasks where grid batching is not in play, and the
one block that was unbatched improved by 0.89 points, so the cause is the elicitation rather than the
batching.

If you ask a model to verbalize its uncertainty, expect its committed answer to move. That applies
well beyond this experiment.

## Limits

**The instrument.** Twin-2K-500's holdout is a cognitive-bias battery while the grounding is
personality and economic-preference content, so the test is out-of-domain by construction. Its
questions are built so that answers should not track who you are. Calibration failed in all four
arms, at 0.2029, 0.2393, 0.3741, and 0.1472 for `Noul`. The best of those still sits above the 0.10
failure band, and that is partly a statement about this instrument rather than about any model
running on it.

**The sample.** 2,058 Prolific US adults, four waves, February 2025 (Toubia et al.,
[arXiv 2505.17479](https://arxiv.org/abs/2505.17479)). It is not population-representative, it is
US-only, it has been public since 2025, and it is built from classic behavioural-economics
replications, so contamination applies to every arm equally. Read the between-arm comparisons and do
not read any absolute number.

**This evaluation.** 300 of 2,058 respondents. 108 of 126 holdout columns, because 18 sliders and
free-numeric items have no option list to decode against. One pinned model version. Binary and
ordinal questions only, with multi-select untested. One number puts the rest in proportion. Humans
agree with their own earlier answers only 81.68% of the time.

**Individual-level prediction.** Every arm scores below a persona-blind leave-one-out majority
baseline of 73.59%. A demographics-grounded synthetic respondent is usable for a population's
distribution and not for predicting a specific person. That is the standing state of this field
rather than a result about Jev.

## Reproduce it

Every per-arm run is in this repo. There is nothing to download and no account to create.

```bash
pip install -r requirements.txt

python scripts/twin2k/prob_scoring.py score \
    --arm jev_noul=runs/jev_noul_chained.jsonl.gz \
    --arm jev=runs/jev_chained.jsonl.gz \
    --arm bc=runs/bc_probs_chained.jsonl.gz \
    --bootstrap 1000 --seed 20260919 --ece-bins 10 \
    --out /tmp/check.json
```

That reproduces [`reports/score_with_noul.json`](reports/score_with_noul.json) exactly. Every number
quoted above and in [FINDINGS.md](FINDINGS.md) comes out of it.

[`runs/`](runs/) holds all five arms as gzipped JSONL, one record per respondent and question cell,
carrying the probability vector, the committed answer, the human's answer, the option order as
presented, and the model version. There are 24,596 cells per arm and 5.8 MB for all five. They
compress to about 6%, which is why they ship here rather than from a dataset host.

The price diagnostic also needs the dataset itself, for the per-respondent piped prices.

```bash
python scripts/twin2k/fetch_twin2k.py            # Twin-2K-500, CC BY 4.0
python scripts/twin2k/price_sensitivity.py \
    --arm JC=runs/jev_chained.jsonl.gz \
    --arm NC=runs/jev_noul_chained.jsonl.gz \
    --arm BC=runs/bc_probs_chained.jsonl.gz
```

## Run a new arm

```bash
cp .env.example .env     # TYPESAFE_API_KEY for Jev; API_BASE_URL + API_KEY for the comparator
python scripts/twin2k/probe_jev.py --arm my_run --chain --primitive noul --sample 300
python main.py --config configs/twin2k/twin2k_survey_config_probs_chained.yaml --resume
```

The comparator runs through any OpenAI-compatible endpoint. The Jev probe refuses to load a config
outside `configs/twin2k/`, and refuses any endpoint that is not TypeSafe. Twin-2K-500 is the only
data cleared to be sent there, and the code and the tests enforce that rather than convention.

## What we would do next

1. **Describe the `criteria`.** Jev currently sees bare `"Yes"` and `"No"` labels, with all the
   meaning sitting in the prose stem. A constant offset in what counts as yes is what a description
   should move, and it is the cheapest experiment left at about $4.
2. **Re-register C3 with `Noul`.** Use it as the elicitation, and fix the aggregation rule in
   advance. That choice accounts for the entire disagreement in the result above.
3. **More respondents.** 48 between-subject columns draw only 16 to 25 respondents at this sample
   size, which is where the per-column test is noisiest.

## Author's take

Everything above is measured. This part is opinion, kept separate on purpose.

I think Jev is a strong option and I would use it. It costs about 34 times less, it produced no
errors in 24,596 cells, it wins the ordinal half outright, and the binary half it lost closes almost
entirely once you stop asking yes/no questions the wrong way. The pre-registered reject stands and I
am not going to soften it. Given `gpt-4.1`'s input and a `Choice` on every binary item, Jev did not
win. But that comparison held the prompt fixed to be fair to the model, which means it left every one
of the vendor's own prompting options untouched. The one we changed afterwards moved the losing half
by more than the whole deficit, and I expect the others to matter too.

I would use it today for ordinal-scale marginals under cost pressure, with `Noul` for anything binary.

## Contents

| | |
|---|---|
| [FINDINGS.md](FINDINGS.md) | the full write-up, with every number, every caveat, and the pre-registration |
| [`reports/`](reports/) | the scored reports behind every figure quoted here |
| [`runs/`](runs/) | the raw per-cell output of all five arms, gzipped |
| [`scripts/twin2k/`](scripts/twin2k/) | the Jev client, the probe, the scorer, and the price diagnostic |
| [`docs/`](docs/) | the arm design, the instrument, and the structured-output failure modes |

Licensed MIT. Twin-2K-500 is CC BY 4.0 and is not redistributed here. `fetch_twin2k.py` downloads it
from the source.
