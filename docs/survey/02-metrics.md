# The metrics, defined once

Both tracks of this write-up read the same numbers. This page defines them, states which direction
is good, and states the one aggregation rule that every headline figure in the repo uses. Nothing
here is specific to a model.

## Three levels, and why a model can pass one and fail another

A survey answer can be right or wrong at three different scales, and this repo measures all three
because an arm can be excellent at one while useless at the next.

| Level | The question it answers | Metrics | Defined in |
|---|---|---|---|
| **Population** | Across everyone, does the spread of answers match? | distribution gap, ordinal gap, Brier, calibration, entropy ratio, collapsed columns | this page |
| **Segment** | Do demographic groups differ from each other the way real ones do? | separation ratio, segment fidelity | [06 Segment diversity](06-segment-diversity.md) |
| **Individual** | Is the right *person* given the right answer? | rank correlation, accuracy against the persona-blind floor, blind spots | this page |

The population and individual levels are what this repo is built to measure, and what every
criterion is stated in. The segment level is a secondary diagnostic: it is reported
where it changes a conclusion and not otherwise, because on this instrument the human signal
between demographic groups barely clears its own noise floor.

They are independent in both directions, which is the reason to keep them apart:

- An arm can match the population marginal **exactly** and still hand every demographic group the
  same distribution. Every crosstab then comes out empty while the headline number looks perfect.
- An arm can sit close to the humans **inside** every segment and still understate how far the
  segments are from each other. Being right about each group's level and right about the gaps
  between groups are different properties.
- Every arm in this repo is measurably useful at the population level and measurably useless at the
  individual level, and no amount of the first buys the second.

Read any single number on this page as an answer to one of those three questions, never to the
survey as a whole.

## The unit of measurement: a cell

**A cell is one respondent answering one question.** 300 respondents against 108 questions, minus the
cells no respondent was asked, is 24,596 cells. Every model in this repo answers every cell it is
given, and every metric below is built from cells: either by scoring them one at a time (accuracy,
Brier, calibration) or by pooling a column's cells into a distribution and comparing that to the
humans' (the distribution gaps).

A model may answer a cell in two ways, and the distinction runs through everything else:

- a **probability vector** over the question's options, which is what a distributional metric reads;
- a **committed answer**, one option, which is what an accuracy metric reads.

Some arms produce both. Where they disagree, the page says which one it is reading.

## The two column buckets

The 108 scored columns split cleanly in two, and the split has two sets of names for one thing:

| Bucket | Columns | Options per column | Metrics read on it |
|---|---|---|---|
| **two-option** (also: nominal, binary) | 65 | exactly 2 | distribution gap, calibration error, Murphy decomposition, binary Brier |
| **multi-option** (also: ordinal, multiclass) | 43 | 5 (16 columns), 6 (13), 7 (10), 10 (3), 4 (1) | ordinal distribution gap, top-label calibration error |

The ordered-scale flag is true on exactly the 43 columns with more than two options, verified against
the run files rather than assumed, so "65 nominal", "65 binary" and "the 65 two-option columns" all
name the same set.

**"Multi-option" means one answer out of more than two, not more than one answer.** No scored column
in this instrument is multi-select.

## Population level: distribution gap (soft TVD), on the two-option columns

For one column, take the human answers and the model's answers and compare the two distributions
over that column's options. The total variation distance is half the sum of absolute differences:

```
distance = 0.5 * sum over options of |human share − model share|
```

0 means the two panels are identical, 1 means they are maximally different. Lower is better.

**"Soft" is about how the model's distribution is built.** Rather than counting which option each
simulated respondent committed to, the model's predicted share for a column is the average of its
per-cell probability vectors across respondents. A model that answers "70% yes" for every one of 300
respondents contributes a 70/30 column marginal, where a committed-answer count would contribute
100/0. Two other commit rules are computed alongside it and reported in the same report files: the
model's most likely option per cell, and a weighted random draw per cell using the same seed the
live runner would have used. Soft aggregation is the expected value of the weighted draw, so any gap
between the two is Monte Carlo error rather than a difference in elicitation.

After first use this page and the others call it **the distribution gap**.

## Population level: ordinal distribution gap (soft Wasserstein-1), on the multi-option columns

On an ordered scale, missing by one scale point is not the same mistake as missing by four, and the
distribution gap above cannot tell them apart. The Wasserstein-1 distance can: it is the sum of the
absolute differences between the two cumulative distributions, measured in scale positions.

```
distance = sum over scale points of |human cumulative share − model cumulative share|
```

Lower is better. It is built from the same soft marginals as the distribution gap.

The two gaps are never averaged together. One is bounded by 1 and the other is in scale
positions, so a mean over both is a number with no unit. Every comparison in this repo is made
within a bucket for the same reason.

After first use: **the ordinal distribution gap**.

## Calibration error (ECE)

Expected calibration error asks whether a stated probability means what it says. Sort every cell's
forecast into bins by the probability the model gave; within a bin, compare the mean forecast to the
fraction of those cells the model actually got right; weight each bin by how many cells it holds.

```
calibration error = sum over bins of (bin share) * |mean forecast in bin − observed rate in bin|
```

0 is perfect, and lower is better. On the 65 two-option columns the forecast read is the probability
of the first canonical option; on the 43 multi-option columns it is the probability the model put on
its own top label, which asks "is the option I was most sure of right as often as I said".

Two implementation choices matter for reading any calibration number:

Bin layout is reported twice. The default is 10 equal-width bins, the reliability-diagram
convention. Equal-width bins leave most cells in one or two bins when a model is confident, which
can hide a miscalibration or invent one, so an equal-count cross-check is always reported beside it.
A verdict that flips between the two is not a verdict. What that looks like in practice, on the
four arms of the model comparison:

| pooled calibration error | 10 equal-width bins | equal-count bins | move |
|---|---|---|---|
| Jev Choice | 0.2532 | 0.2517 | 0.0015 |
| GPT-4.1 probabilities | 0.2270 | 0.2278 | 0.0008 |
| Jev Noul | 0.1837 | 0.1837 | 0.0000 |
| GPT-4.1 hard answer | 0.3456 | 0.0627 | 0.2829 |

The first three are stable and mean what they say. The last one collapses, because an arm that only
ever states 0% or 100% occupies just the two extreme bins, so its calibration number is a
restatement of "this arm has no distribution" rather than a calibration result.

The headline is equal-task-weighted, not pooled, for the reason in the aggregation section
below; the pooled figure is reported beside it, and a large gap between the two is itself a finding.

After first use: **the calibration error**.

## Brier score

Per cell: subtract the human's answer, written as a one-hot vector, from the model's forecast,
square each element, and sum. A forecast of `[0.6, 0.3, 0.1]` against a human who chose the second
option scores `0.6² + 0.7² + 0.1² = 0.86`.

The range is 0 to 2. Sure and right scores 0, "no opinion" (`[0.5, 0.5]`) scores 0.5, and sure and
wrong scores 2. Lower is better. Confident error is punished far harder than doubt, which is why an
arm can be the most accurate of a set and still score worst on Brier: an arm that only ever commits,
with no probabilities, has every miss cost the full 2.

An arm with no probability vector is scored as a one-hot forecast. That is the honest reading and the
only one that makes such an arm scoreable at all, but it means any Brier or calibration number
against it measures "has a distribution at all" rather than the quality of one.

Log loss is reported alongside Brier. It needs a floor, because a single zero-probability cell makes
an arm's score infinite and reports nothing about the other 25,000 cells; the count of cells where
the model gave the human's actual answer a probability of zero is reported separately instead.

## The Murphy decomposition

Brier on a two-option column decomposes into three terms:

```
Brier = reliability − resolution + uncertainty
```

- **reliability** (lower is better): how far the stated probabilities sit from the outcomes that
  followed them. This is the calibration term.
- **resolution** (higher is better): how far the model's bins pull away from the base rate. This is
  the sharpness term, the part that says the model is discriminating between people rather than
  repeating the average.
- **uncertainty**: a property of the column, not the model. It is the base rate times one minus the
  base rate, and no forecaster can change it.

An arm can lose on both terms at once, which is a stronger statement than losing on Brier alone.

**Restricted to the two-option columns on purpose.** The decomposition is a statement about a scalar
forecast of a binary event; extending it to a 7-point scale needs a choice of which event, and any
such choice would make the three terms incomparable to the literature the words come from.

**Read the terms as components, not as an exact partition.** With 10 equal-width bins over continuous
forecasts the three terms overshoot the true pooled binary Brier by a within-bin variance term, which
was measured here at +0.0013, +0.0006 and −0.000 for Jev Choice, GPT-4.1 probabilities and GPT-4.1
hard answer. That residual is about 25 times smaller than the between-arm gap it is used to
describe, so the ranking holds, but the reliability term is not a clean calibration figure at that
resolution.

## Accuracy, and which answer it reads

The accuracy metric is the dataset paper's own, reimplemented so that arms here can be set beside
the paper's table:

- **exact match** on a two-option item;
- `1 − |deviation| / range` otherwise, where **range is the number of options minus one**, so
  deviation is measured in scale positions. On a 5-point item the worst possible answer scores 0 and
  an adjacent one scores 0.75.
- averaged within a column, then within a task, then across the 16 equally weighted tasks.

Higher is better. All 65 two-option columns take the exact-match branch and all 43 multi-option
columns carry an ordered option list, so they all take the graded branch. An unordered column with
more than two options would be a mapping error and raises rather than being scored as though its
option order meant something.

**Argmax-committed against stated choice.** A model that returns both a probability vector and a
chosen option can disagree with itself: the vector and the choice are separate schema fields, the
choice is generated after the vector, and no code links them. So accuracy can be computed two ways,
from the largest entry of the model's own vector or from the option it named. In the model
comparison, Jev Choice named an option strictly below its own maximum in 40 cells (0.16%) and GPT-4.1
probabilities in 189 (0.77%); either rule moves accuracy by about 0.1 point.

The repo's default is **argmax-committed**, computed from the vector, because it is defined for every
arm. The one place the stated choice is used instead is where the question being asked is
specifically what an arm *committed to*, which is the subject of
[04 Elicitation effects](04-elicitation-effects.md).

## The leave-one-out majority floor

An accuracy figure is not interpretable on its own, because a predictor that never looks at the
person can win on any skewed column. So every accuracy report carries a floor: answer each column
with the modal label of the **other** respondents, ignoring the persona entirely. A simulated
respondent that cannot beat it is not reading the individual, however close its raw score sits to a
published table.

**Read the edge against this floor, not the headline.**

The leave-one-out form (each respondent scored against the mode of the other n−1) is used rather
than the in-sample mode, because the in-sample mode is fitted to the very labels it is scored
against, and at small samples the inflation is large enough to invert a conclusion. Measured on a
50-respondent run, one arm's edge was +0.50 against leave-one-out, −1.08 against the in-sample mode,
and −1.70 against the true modal answer of all 2,058 humans: three defensible baselines, two
different signs. The three converge as the sample grows, so the ambiguity is a small-sample artifact
rather than a choice to argue about.

Values on this instrument: **73.27%** over the full 2,058-respondent panel, **73.59%** over the
300-respondent slice. The human test-retest ceiling beats the same floor by **+8.41 points**, so that
is the headroom real individual signal is worth here.

A column needs at least two scorable respondents to enter a report, because leave-one-out has nothing
to predict a lone respondent from, and accuracy and floor must be averaged over the same columns or
the edge subtracts two means taken over different sets. Such columns are counted, not silently
dropped.

## Individual level: rank correlation with the human

Accuracy answers "how often is the answer right", which a persona-blind predictor can win on any
skewed column. The complementary question is **does the model rank the right people high?** Within
one column, correlate the model's answer position against the human's across respondents. A model
that reproduces a column's distribution but assigns it randomly across people scores about 0 here
while still scoring well on accuracy.

Spearman rather than Pearson, because the multi-option columns are 4 to 7 point scales where only
order is meaningful; on a two-option column Spearman equals the phi coefficient, so one statistic
covers both buckets. A column where the model gave every respondent the same answer has zero
variance and **no defined correlation**; those columns are counted, not scored as 0, because "no
signal measurable" and "signal measured as none" are different claims.

**The 40 pricing columns need a control, and without it they dominate the headline.** Each product's
price is randomized per respondent and the model is shown the same price its human saw, so model and
human agree partly because both react to the price, with no knowledge of the person involved. Those
columns are therefore reported as a partial Spearman holding price rank fixed. Measured on the
full demographics-only panel the raw correlation is +0.301 and the price-controlled one is +0.048:
six sevenths of it was the price.

The partial correlation is a shortcut for stratifying by price, and it earns that shortcut: it was
checked against a within-price-decile correlation pooled by size (+0.058 over 267 bins) and a
Mantel-Haenszel odds ratio over all 13,851 exact-price groups (1.398, p<0.0001, n=82,320 cells). All
three agree that the price-controlled signal is real, small, and near +0.05. If a future arm's
partial correlation diverges from the decile-pooled one, distrust the partial: it means the model's
price response stopped being monotone.

## Population level: entropy ratio, collapsed columns, and blind spots

Accuracy and distribution gaps can both look acceptable while the model answers a column far more
uniformly than the humans did. Three diagnostics catch that.

**Entropy ratio** is the entropy of the model's predicted distribution over the entropy of the
humans', normalized by the log of the option count so that columns with different numbers of options
compare. 1.0 is human-level diversity. Below 1 is the collapse that a model repeating one answer
produces; above 1 is a model hedging where the humans were decided.

**A collapsed column** is one where every simulated respondent committed to the same option. Nothing
can move on such a column, so a collapsed task's edge against the floor is a construction rather than
an agreement, and cross-arm comparisons that include one are reading a constant.

**A blind spot** is an option at least **5%** of humans used that the model gave less than **1%** of
the time. It is reported separately from the distance metrics because it barely moves a distribution
gap when the missed option is small, and because which answer went missing is the whole content of
the finding: an abandoned end of a rating scale and an unpicked middle option are different defects
with different fixes.

The blind-spot and collapse flags are gated at 50 valid respondents per column. Below that they
read as "not computed", not as "clear". That gate is what makes the 48 between-subject condition
columns a plumbing proof rather than a result at small sample sizes.

## The aggregation rule: equal weight per task

**Column mean, then task mean, then an unweighted mean across the 16 tasks.** Never a mean over
pooled cells.

The reason is blunt: **40 of the 108 columns are the pricing study**, so a cell-pooled or
column-pooled figure is 37% one experiment. Averaging within task first is also exactly how the
dataset's paper aggregates its 17 tasks, so this is the paper-faithful reading rather than a
workaround for a local problem.

Two consequences a reader has to hold on to:

- **Pricing is always reported separately as well.** Every headline comes with a pricing-excluded
  twin. If the two disagree in sign, that split is the finding.
- **Task weighting and column weighting can point opposite ways, and both can be correct.** One task
  holds 40 of the 65 two-option columns, so equal task weighting gives each of the 25 non-pricing
  two-option columns roughly eight times the weight it gets per column. Any test fixed in advance has
  to fix which of the two it reads, in advance.

## Two rules about uncertainty

Bootstrap over respondents, never over cells. Roughly 84 cells come from one respondent and are
correlated, so resampling cells would understate an interval several-fold. Arm differences resample
the *same* respondents, which is what makes a paired margin readable. The shipped reports use 1,000
resamples at seed 20260919.

Raw vectors go in, and are normalized only at the point of use. How far a source's probability
vector is from summing to 1 is itself a result, so the raw sum is reported as a distribution rather
than quietly repaired upstream.

## Direction summary

| Metric | Direction |
|---|---|
| distribution gap (soft TVD) | lower is better, 0 is identical |
| ordinal distribution gap (soft Wasserstein-1) | lower is better |
| calibration error (ECE) | lower is better |
| Brier, log loss | lower is better |
| Murphy reliability | lower is better |
| Murphy resolution | higher is better |
| accuracy | higher is better, read as an edge against the floor |
| entropy ratio | 1.0 is human-level; below is collapse, above is hedging |
| collapsed columns, blind spots | fewer is better |
| separation ratio (segment) | 1.0 matches real group differences; below flattens, above caricatures |
| segment fidelity | lower is better, 0 is identical within a group |

The last two are defined in [06 Segment diversity](06-segment-diversity.md) rather than here,
because they need the noise floor to be readable and that machinery belongs with the result.

## Where the code is

| Metric | Implementation |
|---|---|
| distribution gaps, calibration, Brier, Murphy, bootstrap | [`scripts/twin2k/prob_scoring.py`](../../scripts/twin2k/prob_scoring.py) |
| accuracy and the leave-one-out floor | [`scripts/twin2k/paper_accuracy.py`](../../scripts/twin2k/paper_accuracy.py) |
| per-task correlation with the human, and the price control | [`scripts/twin2k/individual_signal.py`](../../scripts/twin2k/individual_signal.py) |
| the distance functions and the blind-spot rule | [`src/validation/response_validator.py`](../../src/validation/response_validator.py) |

The scorer has an external anchor rather than only unit tests: run over the full-panel prior-answers
arm it must reproduce that arm's recorded 72.92% accuracy and 73.27% leave-one-out floor, and the
ceiling path must land on 81.68%. These formulae are all short enough to look right while being
wrong, and those recorded numbers are what pin them.

[`reports/README.md`](../../reports/README.md) maps each scored report back to the run it came from
and the command that regenerates it.
