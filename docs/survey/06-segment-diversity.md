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
with fewer than 25 people, and compute each segment's answer distribution twice: once from the
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

| Variable | humans | noise floor | Jev `Noul` | ratio | GPT-4.1 hard | ratio |
|---|---|---|---|---|---|---|
| political views | 0.1188 | 0.0683 | 0.1425 | 1.20 | 0.3140 | **2.64** |
| party | 0.0995 | 0.0725 | 0.1132 | 1.14 | 0.2411 | **2.42** |
| sex | 0.0809 | 0.0380 | 0.0239 | **0.30** | 0.0561 | 0.69 |
| age | 0.0851 | 0.0577 | 0.0340 | **0.40** | 0.0934 | 1.10 |
| race | 0.1161 | 0.0869 | 0.0270 | **0.23** | 0.0798 | 0.69 |
| education | 0.0820 | 0.0654 | 0.0267 | 0.33 | 0.0673 | 0.82 |
| religion | 0.1057 | 0.0809 | 0.0519 | 0.49 | 0.1239 | 1.17 |
| employment | 0.1072 | 0.0895 | 0.0344 | 0.32 | 0.0871 | 0.81 |
| income | 0.0673 | 0.0610 | 0.0398 | 0.59 | 0.0803 | 1.19 |
| region | 0.0609 | 0.0577 | 0.0171 | 0.28 | 0.0466 | 0.77 |

Citizenship is absent because 2,054 of 2,058 respondents are citizens, so the second segment never
reaches 25 people. Marital status and household size behave like income and are omitted for space.

The same measurement on the 300-respondent arms, where **every arm is soft**, so nothing about the
comparison depends on elicitation
([`reports/jev_vs_gpt41_n300/segment_diversity_n300.json`](../../reports/jev_vs_gpt41_n300/segment_diversity_n300.json)):

| Variable | Jev `Choice` | Jev `Noul` | GPT-4.1 probabilities |
|---|---|---|---|
| political views | 0.83 | 0.82 | **1.56** |
| party | 0.86 | 0.87 | **1.79** |
| sex | 0.28 | 0.25 | 0.41 |
| age | 0.31 | 0.31 | 0.57 |

## Interpretation

**This instrument carries much less demographic signal than it looks like.** Human separation clears
the shuffle floor by very little: +0.0032 on region, +0.0063 on income, +0.0102 on household size.
That is the holdout doing what it was designed to do. Twin-2K-500 holds out a cognitive-bias
battery, and those questions are built so that answers should *not* track who you are. So for most
variables in the table there is barely a group difference to reproduce, and a low ratio there is not
much of an accusation. The variables worth reading are the ones with real excess: political views
(+0.0505), sex (+0.0429), race (+0.0292), age (+0.0274), party (+0.0270).

**On political identity, the two models fail in opposite directions.** Politics is where humans
separate most, and it is the only place either arm exceeds the human level. Jev sits just above it,
1.14 on party and 1.20 on political views. GPT-4.1 is at 2.42 and 2.64, which is to say it spreads
Republicans and Democrats roughly two and a half times further apart than they actually are on a
battery of questions that is not about politics. That is caricature, and it is the more dangerous
failure of the two: a crosstab built on it would report a polarization that is not in the data.

**The 2x gap between the models is not an artifact of how they were asked.** Those two figures come
from a soft arm and a one-hot arm, and committing mechanically spreads segment shares wider than
averaging probabilities does, so that comparison is confounded on its own. The n=300 table removes
the confound by making every arm soft, and the gap survives almost exactly: on party, GPT-4.1 is
1.79 against Jev's 0.86, a factor of 2.08, against a factor of 2.12 in the full-panel table.

**Away from politics, Jev flattens.** Ratios of 0.23 to 0.40 on race, sex and age, against GPT-4.1's
0.69 to 1.10 on the same variables and the same people. Jev's segments are real but compressed, and
GPT-4.1 tracks those three about as far as the humans do. This is the one dimension measured in this
repo where GPT-4.1 is clearly the better instrument and Jev is clearly the worse one.

**Flattening and fidelity are not the same thing, and Jev wins the other.** Within segments, Jev is
closer to the humans on every variable, 0.229 to 0.257 against 0.287 to 0.379. It is nearer the
right answer inside each group while under-stating how much the groups differ. Those coexist because
both arms sit near the pooled marginal, and the one that hedges harder lands closer to it.

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
- **25 people is a floor, not a guarantee.** At n=300 most segments sit near it and the noise floor
  nearly swallows the human signal, which is why the full panel carries this result and the n=300
  table is used only to rule out the elicitation confound.
- **Nothing here is a prediction about individuals.** These are group rates. The individual-level
  question is settled elsewhere and negatively: every arm sits below the persona-blind floor. See
  [limitations](05-limitations.md).

## Reproduce

```bash
python scripts/twin2k/segment_diversity.py \
    --arm jev_noul=runs/jev_vs_gpt41_n2058/jev_noul.jsonl.gz \
    --arm gpt41_hard=runs/jev_vs_gpt41_n2058/gpt41_hard.jsonl \
    --permutations 20 --out /tmp/segment_diversity.json
```

Demographics come from the persona cache shipped under
[`runs/gpt41_panel_n2058/demographics_stateful/`](../../runs/gpt41_panel_n2058/demographics_stateful/),
so this needs no download and no credentials. `--variable` restricts to named demographics and
`--min-segment` moves the floor.

Back to [the documentation index](../README.md), or on to
[limitations](05-limitations.md).
