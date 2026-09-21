# Pricing is a boundary problem, not an arithmetic one

The largest single effect measured in this work. It is also the one place where a claim written
down in advance turned out to be right about the symptom and wrong about the cause.

## Question

Forty of the 108 columns are one task: a purchase question with a randomized price piped into each
respondent's question stem. TypeSafe documents Jev as weak on numeric representations, "not a
calculator", so the expectation fixed in advance was that this block would sink it.

Jev is indeed far worse here, 9.18 accuracy points below GPT-4.1 hard answer on pricing against
1.34 points on the other 15 tasks. Is that because it cannot read the number?

## Setup

A diagnostic over the runs already collected, not a new run. It needs the dataset itself, for the
per-respondent piped prices, which the scoring path does not.

Runs: the four arms in `runs/jev_vs_gpt41_n300/`, restricted to the 40 pricing columns.

## Metrics

For each pricing column, the correlation between the price piped into the stem and the probability
the arm assigns to "yes", compared against the same correlation computed on the real human
answers. Then the mean probability of yes, and its signed difference from the humans'.

## Results

| over the 40 pricing columns | Jev Choice | Jev Noul | GPT-4.1 probs | humans |
|---|---|---|---|---|
| correlation(piped price, P(yes)) | −0.551 | −0.522 | −0.488 | −0.333 |
| negative in | 40/40 | 40/40 | 40/40 | 40/40 |
| mean P(yes) | 0.601 | 0.591 | 0.343 | 0.416 |
| signed bias against humans | +0.185 | +0.175 | −0.073 | |
| columns biased high | 36/40 | 37/40 | 10/40 | |

Jev reads the price, and reads it harder than the humans do. Its price response is stronger
than the real respondents' in all 40 columns. What it gets wrong is the level: a near-constant
offset of +0.175 on Jev Noul, which is 95% of that arm's entire pricing distribution gap of 0.185.
It is not noise, not per-column idiosyncrasy, and not a failure to process the number. Jev thinks
people buy things; mostly they do not.

Re-committing at a shifted threshold instead of 0.5 recovers 8.45 points of Jev Noul's pricing
accuracy (52.57% to 61.02% at a threshold of 0.79) and 5.89 points of Jev Choice's, while giving
GPT-4.1 probabilities 0.03 points: its boundary is already where it should be.

## Interpretation

The ranking is sound and only the operating point is wrong. That is a much more tractable failure
than an inability to handle numbers, and it points at a specific, untried lever.

Jev was given the options as bare labels with no descriptions, so on a two-option pricing column it
sees "Yes" and "No" and all the meaning sits in the question stem. TypeSafe's documentation says
option descriptions exist to separate the options from each other. A near-constant offset in *what
counts as yes* is exactly the kind of framing problem a description can address and a calculator
cannot. That lever moves from "untested" to the one this evidence implicates.

A calibration layer fit on held-out columns would likely recover most of this block. That is a
different product from Jev, and it would have to be fixed in advance and scored out of sample
to mean anything.

## Caveats

- **The recovered accuracy is an in-sample upper bound, not an achievable score.** The threshold is
  chosen on the same cells it is then scored on. It bounds the size of the failure rather than
  measuring a fix.
- The diagnostic covers one pricing block on one instrument.

## Reproduce

```bash
python scripts/twin2k/fetch_twin2k.py            # Twin-2K-500, CC BY 4.0
python scripts/twin2k/price_sensitivity.py \
    --arm jev_choice=runs/jev_vs_gpt41_n300/jev_choice.jsonl \
    --arm jev_noul=runs/jev_vs_gpt41_n300/jev_noul.jsonl \
    --arm gpt41_probs=runs/jev_vs_gpt41_n300/gpt41_probs.jsonl
```

Reproduces the table above. The `--arm` labels are free text and become the column headings.

Back to [the Jev track](../README.md#jev-track), or on to
[what this licenses](08-what-this-licenses.md).
