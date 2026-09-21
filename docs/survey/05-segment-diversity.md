# Does a synthetic panel reproduce the differences between groups?

Every other metric in this repo asks whether an arm matches the population as a whole. That is not
what survey data is usually for. A survey gets broken out by age, by party, by region, and an arm
can match the overall marginal perfectly while giving every group the same answer. The marginal
will not notice. This page measures the thing the marginal misses.

## Question

**Do the demographic segments of a synthetic panel differ from each other the way real ones do?**

The failure this is looking for is flattening: a model that ignores the persona produces segments
that are identical, so every crosstab comes out empty. The opposite failure is caricature: a model
that reads the persona too hard produces segments further apart than the real ones, so every
crosstab comes out overstated. Both are wrong, and a distributional metric computed on the pooled
panel is blind to each.

## Metrics

For one demographic variable and one scored column, split the respondents into segments, drop any
with fewer than 50 people, and compute each segment's answer distribution twice: once from the
humans, once from the arm's own forecasts averaged over that segment's members.

| | |
|---|---|
| **separation** | mean pairwise total variation between the segments' distributions |
| **noise floor** | the same quantity with the segment labels shuffled, averaged over 20 shuffles |
| **separation ratio** | the arm's separation over the humans' |
| **segment fidelity** | mean total variation between the arm and the humans *within* a segment |

Aggregated equal-weight-per-task, like every other headline here. Separation and fidelity are
different questions: an arm can sit close to the humans inside each segment and still flatten the
gaps between them.

**The noise floor is what makes any of this readable.** Two segments differ partly because their
members differ and partly because each segment's rate is estimated from finitely many people. Only
the first is signal and only the first is reproducible. Shuffling the labels destroys the signal and
keeps the sampling error, so it measures the second directly.

## Results

All 2,058 respondents, 108 columns
([`reports/jev_vs_gpt41_n2058/segment_diversity_n2058.json`](../../reports/jev_vs_gpt41_n2058/segment_diversity_n2058.json)):

"Jev Noul" is `Noul` on the 65 two-option columns and `Choice` on the 43 multi-option ones; a
`Noul` takes a yes/no condition and cannot be asked of a multi-option column.

| Variable | humans | noise floor | Jev Noul | ratio | GPT-4.1 hard | ratio |
|---|---|---|---|---|---|---|
| political views | 0.1146 | 0.0654 | 0.1405 | 1.23 | 0.3074 | **2.68** |
| party | 0.0887 | 0.0552 | 0.1193 | 1.35 | 0.2547 | **2.87** |
| sex | 0.0809 | 0.0380 | 0.0239 | **0.30** | 0.0561 | 0.69 |
| age | 0.0851 | 0.0577 | 0.0340 | **0.40** | 0.0934 | 1.10 |
| race | 0.1104 | 0.0814 | 0.0259 | **0.23** | 0.0753 | 0.68 |
| education | 0.0820 | 0.0654 | 0.0267 | 0.33 | 0.0673 | 0.82 |
| religion | 0.1013 | 0.0709 | 0.0522 | 0.52 | 0.1238 | 1.22 |
| employment | 0.0944 | 0.0759 | 0.0331 | 0.35 | 0.0856 | 0.91 |
| income | 0.0673 | 0.0610 | 0.0398 | 0.59 | 0.0803 | 1.19 |
| region | 0.0609 | 0.0577 | 0.0171 | 0.28 | 0.0466 | 0.77 |

Citizenship is absent because 2,054 of 2,058 respondents are citizens, so the second segment never
reaches 50 people. Marital status and household size behave like income and are omitted for space.

The same measurement on the 300-respondent arms, where **every arm is soft**, so nothing about the
comparison depends on elicitation
([`reports/jev_vs_gpt41_n300/segment_diversity_n300.json`](../../reports/jev_vs_gpt41_n300/segment_diversity_n300.json)):

| Variable | Jev Choice | Jev Noul | GPT-4.1 probabilities |
|---|---|---|---|
| political views | 0.83 | 0.82 | **1.56** |
| party | 0.86 | 0.87 | **1.79** |
| sex | 0.28 | 0.25 | 0.41 |
| age | 0.31 | 0.31 | 0.57 |

## By task

The variable table averages each arm over all 16 tasks, which hides how uneven the flattening is.
Split the same measurement the other way — by task, averaged over the 11 non-political demographics,
ordered by how far the humans clear the shuffle floor:

| Task | humans | noise floor | Jev Noul | GPT-4.1 hard |
|---|---|---|---|---|
| Omission bias | 0.0957 | 0.0535 | 0.22 | 0.84 |
| False consensus | 0.0980 | 0.0585 | **1.27** | 1.30 |
| Dominator neglect | 0.0647 | 0.0272 | **0.06** | 0.71 |
| Allais paradox | 0.0738 | 0.0406 | **0.09** | 0.61 |
| Less is more | 0.1286 | 0.0958 | 0.18 | 0.87 |
| Nonseparability | 0.0906 | 0.0669 | 0.85 | 1.04 |
| WTA/WTP (Thaler) | 0.1420 | 0.1207 | 0.19 | 1.00 |
| Pricing | 0.0496 | 0.0318 | 0.92 | 1.19 |
| Outcome bias | 0.0968 | 0.0820 | **0.06** | 0.36 |
| Probability matching | 0.0481 | 0.0343 | **0.03** | 0.21 |
| Linda (conjunction) | 0.0993 | 0.0856 | 0.25 | 0.55 |
| Proportion dominance | 0.1037 | 0.0926 | 0.63 | **1.46** |
| Anchoring | 0.0420 | 0.0319 | 0.15 | **0.00** |
| Absolute vs relative saving | 0.0474 | 0.0375 | 0.41 | **1.58** |
| Asian disease | 0.0921 | 0.0898 | 0.18 | **1.47** |
| Myside bias | 0.0918 | 0.0912 | 0.71 | **1.59** |

The last two rows sit essentially on the floor, +0.0023 and +0.0006, so nothing should be read into
either arm's ratio there.

**A by-variable median hides a by-task collapse.** The Jev arm reads 0.40 by variable and 0.21 by
task, because the variable figure averages four tasks where the ratio is 0.03 to 0.09 — the persona
changing essentially nothing — against the three where it holds. Any arm can carry that shape, so a
by-variable number alone should not be taken as evidence that a panel supports crosstabs. What it
means for Jev is in [jev/07](../jev/07-segment-diversity.md).

**GPT-4.1's median is 0.93, and that number is an average of opposite errors.** It overshoots on
proportion dominance, absolute versus relative saving and the Asian disease problem, and collapses
on probability matching (0.21) and outcome bias (0.36).

**On anchoring it is a constant function.** Its separation is exactly 0.0000, on all 13 demographic
variables, because it gave the same answer to every respondent on all four anchoring columns:
1002/1002 `more` on QID163, 1056/1056 `fewer` on QID165, 1049/1049 `more` on QID167, 1009/1009
`less` on QID169. That is 4,116 cells with no variation of any kind — not flattened segments but no
per-respondent response at all. The variable-level table cannot show this, because averaging one
dead task into fifteen live ones leaves a healthy-looking 1.10 on age.

## Interpretation

**This instrument carries much less demographic signal than it looks like.** Human separation clears
the shuffle floor by very little: +0.0032 on region, +0.0063 on income, +0.0166 on education.
That is the holdout doing what it was designed to do. Twin-2K-500 holds out a cognitive-bias
battery, and those questions are built so that answers should *not* track who you are. So for most
variables in the table there is barely a group difference to reproduce, and a low ratio there is not
much of an accusation. The variables worth reading are the ones with real excess: political views
(+0.0493), sex (+0.0429), party (+0.0335), religion (+0.0304), race (+0.0290), age (+0.0274).

**GPT-4.1 exaggerates political segments and tracks the rest.** It runs 2.87 on party and 2.68 on
political views, spreading Republicans and Democrats roughly two and a half times further apart than
they actually are on a battery that is not about politics, while sitting at 0.68 to 1.10 on race,
sex and age. Caricature is the more dangerous of the two failures: a crosstab built on it would
report a polarization that is not in the data.

**Separation and fidelity are different questions, and an arm can win one while losing the other.**
Within segments the Jev arm is closer to the humans on every variable, 0.229 to 0.257 against 0.287
to 0.376, while separating them far less. Both follow from sitting near the pooled marginal: the arm
that hedges harder lands closer to it and spreads less. Reading either number alone gets the
instrument wrong.

What this measurement says about Jev specifically — the verdict, the by-task collapse and the
elicitation-confound check — is in [jev/07 Segment diversity](../jev/07-segment-diversity.md).

## Caveats

- **The noise floor is large relative to the signal**, often more than half of the human figure.
  Both the human and the model number carry it, so every ratio in the table is pulled toward 1
  and the true flattening is worse than 0.23 to 0.59 suggests. `separation_ratio_excess_null` in
  the JSON nets it out, and is unstable exactly where the excess is small, which is why the table
  above reports the raw ratio and the floor beside it rather than the netted one.
- **One-hot arms spread wider for free.** GPT-4.1 hard's n=2058 separation is inflated by
  committing rather than hedging. The n=300 table is the clean comparison.
- **Segments are not independent of each other.** Party and political views largely track the same
  people, as do education and income, so the rows of these tables are not ten separate findings.
- **The n=2058 tables use a 50-person floor; the n=300 table cannot.** Raising the floor from 25 to
  50 on the full panel drops nothing but citizenship and moves no conclusion: Jev's median ratio
  stays at 0.40 and GPT-4.1's goes 1.06 to 1.10. At n=300 the same floor drops race outright and
  swings political views from 0.83 to 1.86, so that table stays at 25 and is used only to rule out
  the elicitation confound, never as a measurement in its own right.
- **Nothing here is a prediction about individuals.** These are group rates; the individual-level
  question is settled elsewhere and negatively. See [limitations](06-limitations.md).

## Reproduce

```bash
python scripts/twin2k/segment_diversity.py \
    --arm jev_noul=runs/jev_vs_gpt41_n2058/jev_noul.jsonl.gz \
    --arm gpt41_hard=runs/jev_vs_gpt41_n2058/gpt41_hard.jsonl \
    --min-segment 50 --permutations 20 --out /tmp/segment_diversity.json
```

Demographics come from the persona cache shipped under
[`runs/gpt41_panel_n2058/demographics_stateful/`](../../runs/gpt41_panel_n2058/demographics_stateful/),
so this needs no download and no credentials. `--variable` restricts to named demographics and
`--min-segment` moves the floor.

Back to [the documentation index](../README.md), or on to
[limitations](06-limitations.md).
