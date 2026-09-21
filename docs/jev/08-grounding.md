# What richer grounding buys, and what it does not

Every other arm in this track grounds the persona in 14 demographic fields. This one replaces them
with 620 of the respondent's own prior answers, a 21,000-token state, and asks what changes.

Run after the verdict, so it carries none of it.

## Setup

`probe_jev.py` against [`prior_answers_stateless.yaml`](../../configs/twin2k/prior_answers_stateless.yaml),
the same config and the same persona cache the GPT-4.1 prior-answers arm used, so the personas are
identical and only the model differs. 300 respondents, 108 columns, 24,596 cells, `Noul` on the 65
two-option columns and `Choice` on the 43 multi-option ones.

Two arms ship here:
[`jev_prior_answers.jsonl`](../../runs/jev_grounding_n300/jev_prior_answers.jsonl) and
[`jev_demographics_stateless.jsonl`](../../runs/jev_grounding_n300/jev_demographics_stateless.jsonl),
the second added to complete the 2×2 below. It cost $0.69 and 6m 28s, with no aborts.

| | |
|---|---|
| Cost | **$24.40** measured, against $4.02 for the demographics arm |
| Wall clock | **17m 25s** at concurrency 16, plus 35s to retry |
| Aborted | 8 personas, all rate limits, all cleared on retry at concurrency 8 |
| Mean latency | 0.38 s/cell, against 0.26 s/cell on the demographics arms |

The cost is the state, and the arithmetic is exactly linear. Jev bills input only, at a flat rate,
and every cell re-sends everything: 3,891 tokens per cell on demographics against 23,624 on 620
prior answers, so 95.7M tokens becomes 581.0M. **6.07x the tokens, 6.07x the cost.** Nothing about
the model got more expensive.

Worth separating the two things that fill a prompt, because they price differently. The
demographics persona is small — 670 tokens per cell at the first question of a walk, including the
question itself. What makes that arm cost $4.02 rather than $0.69 is **chaining**: by the 83rd
answer the prompt has grown to 7,406 tokens, and the arm averages 3,891. The prior-answers arm
carries no chain at all and still costs six times more, because 620 real answers are a 21k-token
state on every single cell. Billed input is that state plus the question and a per-request
overhead: 23,624 tokens per cell on average, between 23,096 and 24,838. Persona content and
accumulated self-history are both just context, and Jev bills both the same way.

That linearity is itself worth noting, because the comparator does not pay it. The GPT-4.1
prior-answers run was **91.4% cached prompt tokens** across 2,348M prompt tokens: the repeated
persona is billed once and read from cache thereafter. Jev's records carry an `input_tokens` field
and no cache field, and the billed total matches the uncached sum to the cent.

**The two are not a cost comparison.** That GPT-4.1 run covers all 2,058 respondents against this
arm's 300, and the repo records no dollar figure for it at all — the panel arms never had one. What
transfers between them is the caching *rate*, which does not depend on sample size. The honest claim
is narrow: on a long fixed persona re-sent per question, prompt caching is worth more than the
per-token rate, and this is the workload where Jev's cost advantage would narrow. Whether it
narrows, and by how much, is not measured here.

## The arm carries no self-history at all

Worth stating before the numbers, because it runs against the result. The shipped demographics arm
is **chained** — each cell sees the model's own earlier answers, `history_len` running 0 to 83. This
arm is **stateless**: `history_len` is 0 on every one of its 24,596 cells, matching the GPT-4.1
prior-answers arm it was built to sit beside.

So this arm gave up accumulated self-state and replaced it with real human answers.

## Population level

Both arms stateless, so grounding is the only difference.

| | demographics | 620 prior answers | |
|---|---|---|---|
| distribution gap (soft TVD) | 0.1484 | **0.1368** | p = 0.0000 |
| Brier | 0.7172 | **0.7041** | p = 0.0000 |
| calibration (ECE) | 0.1298 | **0.1218** | |
| accuracy | 67.50% | **68.35%** | |
| ordinal gap (soft W1) | **0.6576** | 0.7119 | p = 0.8767, not significant |

Four of five move the right way. The ordinal half moves the wrong way and does not clear
significance, so it is a null rather than a loss.

The calibration figure, 0.1218, is the best in this repo and still fails the bar of 0.05.

Three diagnostics say how the spread itself changed, and they do not all point the same way:

| | demographics, chained | demographics, stateless | 620 prior, stateless |
|---|---|---|---|
| entropy ratio | 0.9467 | 0.9587 | 0.9519 |
| collapsed columns | 23 | 22 | 29 |
| zero-probability cells | 1,069 | 546 | **117** |

A zero-probability cell is one where the arm put probability *zero* on the answer the human actually
gave. It is a different measure from the blind-spot flag on [the metrics
page](../survey/02-metrics.md), which is about options and not cells. Richer grounding cuts them
4.7-fold, from 2.2% of cells to 0.5%, which is the largest relative effect measured on this arm. It
also raises the collapsed count, and the two are not in tension: a collapsed column is one where
every respondent gets the same *argmax*, a zero-probability cell is a zero in the *vector*. The
prior-answers arm hedges more — it stops ruling answers out — while still committing to the same top
answer on a few more columns. Its better calibration is the same fact seen from another angle.

Chaining moves both the wrong way: it doubles zero-probability cells, 546 to 1,069, and narrows the
distribution, 0.9587 to 0.9467. Feeding the model its own earlier answers makes it more certain, and
more certainty on a persona carrying little per-person signal means more cells where the truth is
excluded outright.

One caveat on reading these together: entropy ratio and the gaps above are aggregated equal-weight
per task, and the zero-probability count is a raw cell count. Pricing contributes 40 of the 108
columns, so it weighs 40 times more in the cell count than in the task-weighted figures.

## Segment level, briefly

A secondary diagnostic, kept short because it is not what this arm was run to answer. Median
separation ratio across the demographic variables, where 1.00 reproduces real group differences:
demographics chained 0.286, demographics stateless 0.282, 620 prior answers **0.185**.

So the arm that tracks individuals best flattens groups the most, and chaining is close to
irrelevant here — +0.004 separation against −0.0106 per-person correlation. One difference between
the models is worth recording: chaining *unpins* collapsed columns for GPT-4.1, 24 down to 16 of
108, and leaves Jev's where they were, 22 to 23. Full treatment in
[07 Segment diversity](07-segment-diversity.md).

## Individual level

The question richer grounding is supposed to answer: does the arm rank the *right people* high?
Spearman against the human within each column, price-controlled. Over the 13 tasks measurable in
both stateless arms it rises from 0.0933 on 14 demographics to **0.1045** on 620 prior answers, a
gain of +0.0113.

A third arm, demographics with chaining, makes a 2×2 with one cell missing. That arm is measurable
on one task fewer, Omission bias, so the table below is over the 12 tasks all three share and its
figures are its own, not the ones above:

| | chained | stateless |
|---|---|---|
| 14 demographics | 0.0731 | 0.0837 |
| 620 prior answers | — | **0.1083** |

which separates two effects that had been moving together:

| | |
|---|---|
| **grounding**, both arms stateless | **+0.0246** |
| **statefulness**, both arms demographics | **−0.0106** |

Richer grounding helps. Chaining, on this measure, slightly hurts: letting the model see its own
earlier answers makes it track individuals a little *worse* than asking each question cold. The two
had been pulling in opposite directions, which is why the confounded contrast between the chained
demographics arm and the stateless prior-answers arm read as +0.0352 — a real +0.0246 plus a
+0.0106 that was only the removal of a harmful chain.

The grounding effect is +0.0246 on these 12 tasks and +0.0113 on the 13 above. One task moves it
by a factor of two, so the direction is the finding here and the size is not.

## This is not a Jev-specific result

GPT-4.1 moves the same way on the same substitution, and its comparison is the clean one — both of
its arms are stateless and both cover all 2,058 respondents.

| | demographics | 620 prior | change |
|---|---|---|---|
| gpt-4.1, n = 2,058 | 0.0945 | 0.1068 | +0.0123 |
| Jev, n = 300 | 0.0933 | 0.1045 | +0.0113 |

Both comparisons are stateless-to-stateless, so both are clean. Jev's gain is the same size as
GPT-4.1's, on the same substitution, in the same direction. What remains uncontrolled is the sample:
300 respondents against 2,058, and the 300 are the first 300 rows, which are older, whiter and more
conservative than the panel. Task coverage also differs, 13 against 14.

So the claim this arm supports is that **Jev converts a long persona into per-person signal as well
as GPT-4.1 does**. It is not evidence of a capability GPT-4.1 lacks.

## What it does not change

None of this touches the verdict. The comparison was set up around Jev `Choice` against verbalized
GPT-4.1 on demographics-only grounding, and this arm is a different grounding, a different
elicitation and a later run.

**The conclusion rests on the two levels the criteria are stated in.** At the population level,
richer grounding is a clear but small win: the distribution gap goes 0.1484 to 0.1368 and Brier
0.7172 to 0.7041, both at p = 0.0000, and zero-probability cells fall 4.7-fold. At the individual
level it is a clear but small win too, +0.0113 on rank correlation, and **it does not change what
the arm is useful for**: 0.1045 is a correlation near zero on most tasks, and the arm still sits
below the persona-blind baseline on accuracy.

Those two together are the finding. A 21k-token persona of the respondent's own answers buys real
population fidelity and real per-person signal, in the same direction as it buys them for GPT-4.1,
and neither is enough to make an individual prediction worth acting on. The instrument, not the
persona, is the binding constraint.

## The takeaway about the model

Hold the size of the effect aside and look at what producing it required. A model that emits no
text, returns one typed value and a probability per option, and costs **$0.00099 and 0.38 seconds
per answer** read a 21,000-token persona and carried it onto questions that persona does not
contain. The 620 prior answers are different questions from the 108 scored here, so nothing in the
state is a lookup for anything being asked: the arm has to generalise from what a person said
elsewhere to what they would say here. It did that across all 24,596 cells, the 8 personas that hit
rate limits clearing on retry, on prompts of up to 24,838 billed tokens, and the result moved both
levels in
the right direction at once.

That is worth stating plainly because the cost figures invite the opposite assumption. Cheap and
fast usually means shallow, and a decision-only model that generates nothing looks like the kind of
thing that should only be able to pattern-match a short persona. It is not what happened: given more
context it used more of it, and the arm that carried the most context is the one that ranks
individuals best and rules out the truth least often.

Two limits keep this from being a capability claim. GPT-4.1 moves the same way on the same
substitution, so nothing here is unique to Jev. And "uses the context" is what was measured — the
arm produces no reasoning trace to inspect, so how it gets from 620 answers to a probability is not
observable from these runs. What is observable is that the context changed the answers, in the
direction more context should change them.

Back to [the documentation index](../README.md), or
[what the result licenses](05-what-this-licenses.md).
