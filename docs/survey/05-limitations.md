# Limitations of this benchmark and this setup

These apply to any model run on this instrument, including the ones evaluated in the Jev track.
Model-specific caveats live with their own experiments.

## The instrument is out of domain by construction

Twin-2K-500's holdout is a cognitive-bias battery, while the persona content it gives you is
personality and economic-preference material. The questions are designed so that the answer should
*not* track who you are: that is what makes them tests of bias rather than of taste.

This has a direct consequence for calibration. Calibration error failed in all four arms of the
Jev comparison, at 0.2029, 0.2393, 0.3741 and 0.1472, and the best of those still sits above the
0.10 failure band. Some of that is a statement about this instrument rather than about any model
running on it.

If you want to know whether simulated respondents can reproduce a *preference* distribution, this
benchmark is the wrong one. It answers a harder and narrower question.

## The sample is not the population

2,058 Prolific US adults, four waves, February 2025 (Toubia et al.,
[arXiv 2505.17479](https://arxiv.org/abs/2505.17479)). It is not population-representative, and it
is US-only.

It has also been public since 2025, and its tasks are classic behavioral-economics replications
that appear throughout the literature any modern model was trained on. Contamination is therefore
real, and it applies to every arm equally. Read between-arm comparisons; do not read any absolute
number as a measurement of how well simulated respondents match humans in general.

## Subsampling is by position, not at random

The runner's `--sample N` takes the first N rows in file order. Respondent id order in this dataset
correlates with demographics: in the 300-respondent runs, the first 300 rows are older, whiter and
more conservative than the full panel, and the share aged 18 to 29 rises monotonically across the
file, from 9.3% in the first 300 rows to 30.2% in the last 258.

Paired comparisons within the same respondents are unaffected. Absolute levels are not, and a
subsample's numbers should never be read against the full panel's. The figures are in
[runs/README.md](../../runs/README.md).

## Coverage of the instrument is partial

108 of the 126 holdout columns are scored. The other 18 are sliders and free-numeric items with no
option list to decode an answer against. Only two-option and ordinal questions are exercised; no
scored column in this instrument accepts more than one answer, so multi-select support is untested
by everything here.

## Individual prediction is beyond all of it

Every arm measured scores below a persona-blind leave-one-out majority baseline of 73.59%: that is,
below simply predicting whatever the other respondents answered. A demographics-grounded simulated
respondent is usable for a population's distribution and not for predicting a specific person.

That is the standing state of this field rather than a result about any one model, and richer
grounding is what moves it; see [the grounding panel](03-grounding-panel.md).

One number puts the rest in proportion. Humans agree with their own earlier answers only 81.68% of
the time, so that, not 100%, is the ceiling any simulated respondent is working against.

## The models are not deterministic

Two identical runs of the same arm differ. For Jev, measured over 2,040 comparable cells, the mean
per-cell distribution gap between two runs is 0.055 and the top answer flips 7.5% of the time.
Scaled to 300 respondents, the column-level noise floor is roughly 0.006.

That 0.055 is an upper bound, and a later run measured a tighter one. The described-`Choice` arm
sends 25 two-option columns a byte-identical payload, so their movement is pure nondeterminism with
no path dependence mixed in: **0.011 per cell**, about five times smaller. Prefer it when asking
whether an effect clears the noise, and treat anything previously dismissed against 0.055 as worth
a second look.

Any difference smaller than that floor is not a result. Both the run-to-run figure and the
option-order figure it is compared against are upper bounds: the arm intended to isolate them
carried its own history forward by mistake, so path dependence inflates both. The comparison
between them survives, since the same mechanism inflates each.
