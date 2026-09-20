# Re-asking the yes/no questions a different way

**This arm was built after seeing Jev lose the two-option half of the planned comparison.** It is
a follow-up, not a test fixed in advance, and it cannot change [the verdict](02-planned-comparison.md).
It does explain a large part of it. Read every number here as what it is: a hypothesis formed
after looking at the data, then measured.

## Question

Jev's `Choice` primitive picks among the options offered and its probabilities are relative to
that set. Its `Noul` primitive returns one absolute probability that a statement is true. TypeSafe's
own documentation says the two diverge most sharply on yes/no items, and gives an example where an
equivalent pair scores 0.22 one way and 0.01 the other, and where a statement plus its negation sum
to 1.19.

Every one of the 65 two-option columns had been asked as a `Choice`. So: does asking them as a
`Noul` instead close the gap?

## Setup

Jev Noul re-asks the 65 two-option columns as `Noul` and holds everything else at the planned
arm's values: the same 300 respondents, the same persona cache, the same stateful walk, the same
per-respondent option-order random seed, the same pinned `jev-1.13.0`, and the 43 multi-option
columns still asked as `Choice`. Every shared cell carries the same presented option order. Set
equality asserted on respondent ids and cell keys, not counts. 24,596 cells (15,896 `Noul`, 8,700
`Choice`), zero aborted walks, $4.02.

The added condition is one line appended to the question stem, `Does this respondent answer
"{target}"?`, with everything before it byte-identical to what the planned arm sent, and phrased so
that high means yes, as TypeSafe advises. The target is **the first presented option**, so the
per-respondent randomization that permuted the options also varies which side each respondent is
asked about. That is what makes the coherence check below visible across a column instead of baked
into every cell of it.

A `Noul` returns one number and no label, so two fields the other arms state are derived here: the
vector is `{target: p, other: 1 - p}`, and the committed answer is `p >= 0.5`. Both matter when
reading its numbers. The check that vectors sum to 1 is vacuous on its two-option half, since they
do so by construction rather than by the model's doing, and this is the one arm whose committed
answer cannot disagree with its own vector.

Runs: `runs/jev_vs_gpt41_n300/jev_noul.jsonl.gz`.

## Metrics

Defined in [the metrics page](../survey/02-metrics.md). Unchanged from the planned comparison.

## Results

### Against Jev Choice, the entire two-option gap closes and accuracy does not pay for it

| paired, 108 shared columns / 300 shared respondents (lower is better) | delta | 95% CI | Wilcoxon |
|---|---|---|---|
| distribution gap, 65 two-option | −0.0454 | [−0.0564, −0.0328] | p=0.0000, better in 49/65 columns |
| ordinal distribution gap, 43 | −0.0052 | [−0.0098, +0.0004] | p=0.0537 |
| Brier, all cells | −0.0165 | [−0.0203, −0.0127] | p=0.0000 |

The two-option distribution gap goes from 0.1985 to 0.1530, which is more than twice the 0.0196
deficit that lost the planned comparison. Every calibration measure moves with it: calibration
error from 0.2029 to 0.1472, Murphy reliability from 0.0759 to 0.0385, two-option Brier from
0.3052 to 0.2671, log loss from 1.6439 to 1.5486, cells giving the human's answer zero probability
from 1,681 to 1,069, entropy ratio from 0.8497 to 0.9467.

**Accuracy is unchanged**, 67.59% to 67.28%, a third of a point. The change in elicitation bought
calibration without trading away hit rate. A 5-respondent trial run beforehand had suggested a 3.4
point accuracy cost; that did not survive at 300 respondents and was noise.

### The mechanism is saturation

On the 15,896 shared two-option cells, Jev Choice put a probability of *exactly zero* on one option
in 16.6% of them. Jev Noul did so in 0.0%: its scale never reaches the endpoints. A zero on the
human's actual answer costs the full 2 in Brier and is unbounded in log loss, so removing that one
behavior accounts for most of the gain.

The two primitives are not cosmetic variants of each other. On the same cell, for the same label,
they differ by a mean of 0.1301.

The multi-option delta is a control rather than a result. Those 43 columns were asked identically
in both arms, so their −0.0052 bounds the combined effect of Jev's run-to-run noise and a perturbed
history, since this arm commits a thresholded answer where the other committed a stated one. At
p=0.0537 it is the right order of magnitude for noise, and it is a second independent sighting of
the reproducibility floor measured elsewhere.

### Against GPT-4.1, the aggregation decides, and the test still fails

| distribution gap, 65 two-option columns | Jev Noul | GPT-4.1 probs | delta | CI | per-column test |
|---|---|---|---|---|---|
| equal weight per task (this repo's rule) | 0.1530 | 0.1789 | −0.0259 | [−0.0459, −0.0053] | |
| per column, unweighted | 0.1747 | 0.1177 | +0.0570 | | Jev better in 21/65, Wilcoxon **p=0.9995** |

Both rows are correct and they point opposite ways. The repo aggregates by averaging within a
column, then within a task, then equally across the 16 tasks, and one task holds 40 of the 65
two-option columns. Task weighting therefore gives each of the 25 non-pricing columns roughly eight
times the weight it gets per column.

The test fixed in advance is the per-column Wilcoxon within each half, so **the distribution test
still fails against GPT-4.1**, now for a different reason than Jev Choice's. Jev Choice lost on both
aggregations; Jev Noul wins the task-weighted one and loses the per-column one. The scorer prints a
passing flag for this pair, but that flag reads the sign of the delta only and is looser than the
registered rule. The registered rule governs.

Per column, `Noul` closes proportionally more of the gap where no price is piped into the stem, so
the numeric weakness survives the change of primitive:

| distribution gap per column, unweighted | n | Jev Choice | Jev Noul | GPT-4.1 probs |
|---|---|---|---|---|
| all two-option | 65 | 0.2235 | 0.1747 | 0.1177 |
| pricing | 40 | 0.2246 | 0.1848 | 0.1074 |
| non-pricing | 25 | 0.2219 | 0.1586 | 0.1342 |

Jev Noul beats Jev Choice on 26 of 40 pricing columns and 23 of 25 non-pricing ones, and it breaks
the coincidental tie noted in the planned comparison: 0.1467 against 0.1932 for both other arms.

### A statement and its negation are incoherent, by an order of magnitude less than TypeSafe's example

Because the condition names whichever option was presented first, every one of the 65 columns was
asked about side A for some respondents and side B for others. A coherent forecaster would give
P(A) + P(B) = 1 on the column's marginal.

| implied P(A) + P(B) over 65 columns | value |
|---|---|
| mean | 0.9950 |
| median | 0.9883 |
| range | 0.8654 to 1.0838 |
| mean deviation from 1, unsigned | 0.0234 |
| columns more than 2 standard errors from 1 | 29 of 65 (median abs z 1.58, max 49.37) |

There is no systematic inflation: the mean sits within half a point of 1. But individual columns
are incoherent by 2.3 points on average, and 29 of them significantly so. That is real and worth
knowing, and it is an order of magnitude smaller than the 0.19 in TypeSafe's own illustration.

One confound cannot be removed from this design: the target side is also the first-presented side,
so this figure carries any presentation-order effect along with the primitive's incoherence. A
separate probe bounds the order component at 0.017 or less in column-marginal terms, so it is small
but not zero.

## Interpretation

The single most useful thing measured in this work is not about the verdict at all:

> Never ask Jev a yes/no question as a `Choice`.

That one substitution is worth more on the two-option half than the entire gap the planned
comparison was trying to measure, at the same cost, with no accuracy penalty. It generalizes as far
as the mechanism does: a `Choice` is relative to the options offered, and on a two-option item that
relativity is what produces the saturation at exactly zero.

It also sharpens what the verdict means. The comparison gave Jev the input GPT-4.1 got, which is
what made it a comparison of models rather than of prompting. Every prompting lever TypeSafe
documents was therefore left untouched, and the first one pulled afterwards moved the losing half a
long way. Expect the others to matter too.

## Caveats

- **Post hoc.** Built after seeing the result it explains. It cannot carry a test fixed in advance,
  and the fair version of this experiment is a fresh run with `Noul` registered as the elicitation
  and the aggregation rule fixed beforehand. That distance between the two aggregations is exactly
  the gap the registration would have to close.
- **It does not rescue Jev on the registered test.** It fails the same per-column rule against
  GPT-4.1.
- **The coherence figure carries a presentation-order component** that this design cannot separate.
- All caveats of [the planned comparison](02-planned-comparison.md) apply unchanged.

## Reproduce

```bash
python scripts/twin2k/prob_scoring.py score \
    --arm jev_noul=runs/jev_vs_gpt41_n300/jev_noul.jsonl.gz \
    --arm jev=runs/jev_vs_gpt41_n300/jev_choice.jsonl.gz \
    --arm bc=runs/jev_vs_gpt41_n300/gpt41_probs.jsonl.gz \
    --bootstrap 1000 --seed 20260919 --ece-bins 10 --out /tmp/check.json
```

Writes the equivalent of [`reports/score_with_noul.json`](../../reports/score_with_noul.json).
