# Does Jev reproduce the differences between demographic groups?

Every other measure in this track asks whether Jev matches the population as a whole. This one asks
whether its demographic groups differ from each other the way real ones do, which is what a survey
is usually broken out for. An arm can match the overall marginal exactly and still hand every group
the same answer, leaving every crosstab empty.

The method, the metrics and the full measurement are in
[survey/06 Segment diversity](../survey/06-segment-diversity.md). This page is the verdict on Jev.

## What is measured

For one demographic variable and one scored column, split the respondents into segments of at least
50, and compute each segment's answer distribution twice: from the humans, and from the arm.
**Separation** is the mean pairwise distance between segments. The **ratio** is the arm's separation
over the humans': 1.00 reproduces real group structure, below 1.00 flattens it, above 1.00
exaggerates it. Both failures are wrong.

Throughout this page, "Jev `Noul`" means `Noul` on the 65 two-option columns and `Choice` on the
43 multi-option ones — 64.6% of cells and 35.4% respectively. `Noul` takes a yes/no condition, so it
cannot be asked of a multi-option column.

The **noise floor** — the same quantity with segment labels shuffled — is what makes the ratio
readable, and on this instrument it is large. Twin-2K-500 holds out a cognitive-bias battery whose
questions are built so answers should *not* track who you are, so on most variables there is little
real group difference to reproduce and a low ratio is not much of an accusation. The variables with
genuine excess over the floor are political views, sex, party, religion, race and age.

## Jev flattens, away from politics

Full panel, 2,058 respondents, 50-person floor
([`reports/jev_vs_gpt41_n2058/segment_diversity_n2058.json`](../../reports/jev_vs_gpt41_n2058/segment_diversity_n2058.json)):

| Variable | Jev `Noul` ratio | GPT-4.1 hard ratio |
|---|---|---|
| political views | 1.23 | **2.68** |
| party | 1.35 | **2.87** |
| race | **0.23** | 0.68 |
| sex | **0.30** | 0.69 |
| age | **0.40** | 1.10 |
| religion | 0.52 | 1.22 |

Away from politics Jev reproduces a quarter to half of the real gap between groups, against GPT-4.1
tracking those same variables about as far as the humans do. **This is the one dimension measured in
this repo where GPT-4.1 is the better instrument and Jev is the worse one.**

## By task the collapse is worse than by variable

Averaged over the 11 non-political demographics, Jev's median ratio is **0.21 by task against 0.40
by variable**. Averaging over tasks was hiding it:

| Task | Jev `Noul` ratio |
|---|---|
| Probability matching | 0.03 |
| Dominator neglect | 0.06 |
| Outcome bias | 0.06 |
| Allais paradox | 0.09 |
| Anchoring | 0.15 |
| Less is more, Asian disease | 0.18 |
| ... | ... |
| Proportion dominance | 0.63 |
| Myside bias | 0.71 |
| Nonseparability | 0.85 |
| Pricing | 0.92 |
| False consensus | 1.27 |

On the first four the persona changes essentially nothing. Jev keeps group structure on three tasks
and loses most of it on the rest. A crosstab built from this arm would be empty on most of the
battery and only misleadingly full on false consensus.

## On politics it exaggerates, but far less than GPT-4.1 does

Politics is where humans separate most and the only place either arm exceeds the human level. Jev
sits just above it at 1.35 and 1.23. GPT-4.1 is at 2.87 and 2.68, spreading Republicans and
Democrats roughly two and a half times further apart than they actually are on a battery that is not
about politics. Both caricature; GPT-4.1 caricatures twice as hard, and a crosstab built on it would
report a polarization that is not in the data.

**The gap between the arms is not an artifact of how they were asked.** Those two figures come from
a soft arm and a one-hot arm, and committing mechanically spreads segment shares wider than
averaging probabilities does, so the comparison is confounded on its own. The n=300 measurement
removes the confound by making every arm soft, and the gap survives: on party, GPT-4.1 is 1.79
against Jev Choice's 0.86, a factor of 2.08, against 2.13 on the full panel.

## Jev wins the other half of the measure

Separation is between segments; **fidelity** is the distance to the humans *within* a segment. Jev is
closer on every variable, 0.229 to 0.257 against GPT-4.1's 0.287 to 0.376. It sits nearer the right
answer inside each group while understating how much the groups differ. Both follow from the same
habit: both arms sit near the pooled marginal, and the one that hedges harder lands closer to it and
spreads less.

Flattening and misplacement are separate defects, and each arm has one.

## What this licenses

- **Do not use this Jev arm for crosstabs.** On the median task it reproduces a fifth of the real
  group difference, and on four tasks essentially none. Breakdowns built on it will read as
  "no demographic effect" when the humans show one.
- **The pooled-marginal results are unaffected.** This measures a different thing from the
  distribution and calibration tests that carry the verdict; nothing here changes them.
- **It is not an individual-level claim.** These are group rates. Every arm sits below the
  persona-blind floor on individual accuracy; see [what this licenses](05-what-this-licenses.md).
- **Scope.** One instrument, one model version, demographics-only grounding. Whether a persona
  carrying prior answers would separate segments further is untested here.

Back to [the documentation index](../README.md), the method in
[survey/06](../survey/06-segment-diversity.md), or
[what the result licenses](05-what-this-licenses.md).
