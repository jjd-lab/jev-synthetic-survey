# What richer grounding buys, and what it does not

Every other arm in this track grounds the persona in 14 demographic fields. This one replaces them
with 620 of the respondent's own prior answers, a 21,000-token state, and asks what changes.

Run after the verdict, so it carries none of it.

## Setup

`probe_jev.py` against [`prior_answers_stateless.yaml`](../../configs/twin2k/prior_answers_stateless.yaml),
the same config and the same persona cache the GPT-4.1 prior-answers arm used, so the personas are
identical and only the model differs. 300 respondents, 108 columns, 24,596 cells, `Noul` on the 65
two-option columns and `Choice` on the 43 multi-option ones.

[`runs/jev_grounding_n300/jev_prior_answers.jsonl`](../../runs/jev_grounding_n300/jev_prior_answers.jsonl).

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
state on every single cell. Persona content and accumulated self-history are both just context, and
Jev bills both the same way.

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

## Distributional

| | demographics | 620 prior answers | |
|---|---|---|---|
| distribution gap (soft TVD) | 0.1530 | **0.1368** | p = 0.0000 |
| Brier | 0.7385 | **0.7041** | p = 0.0000 |
| calibration (ECE) | 0.1472 | **0.1218** | |
| accuracy | 67.28% | **68.35%** | |
| ordinal gap (soft W1) | **0.6812** | 0.7119 | p = 0.3313, not significant |

Four of five move the right way. The ordinal half moves the wrong way and does not clear
significance, so it is a null rather than a loss.

The calibration figure, 0.1218, is the best in this repo and still fails the registered bar of 0.05.

## Per person

The question richer grounding is supposed to answer: does the arm rank the *right people* high?
Spearman against the human within each column, price-controlled, on the 13 tasks measurable in both
arms.

| | demographics | 620 prior answers |
|---|---|---|
| equal weight over tasks | 0.0631 | **0.1020** |
| median | 0.0148 | **0.0795** |

Higher on 9 of 13 tasks. The largest moves are anchoring, −0.120 to +0.132, and less-is-more,
−0.032 to +0.080: tasks where demographics carried nothing and prior answers carry something.

## This is not a Jev-specific result

GPT-4.1 moves the same way on the same substitution, and its comparison is the clean one — both of
its arms are stateless and both cover all 2,058 respondents.

| | demographics | 620 prior | change | |
|---|---|---|---|---|
| gpt-4.1, n = 2,058 | 0.0945 | 0.1068 | +0.0123 | both stateless |
| Jev, n = 300 | 0.0631 | 0.1020 | +0.0389 | chained → stateless |

Both models convert real prior answers into per-person signal. What this repo can say is that **Jev
uses a 21k-token state the same way GPT-4.1 does**, not that it does so better. The two changes are
not measured on the same design:

- **Jev's comparison is confounded.** Statefulness changed along with grounding. The direction of
  the confound helps rather than hurts — the prior-answers arm won while carrying *less* state, so
  the grounding effect is a lower bound — but a lower bound is not a measurement.
- **The samples differ.** 300 respondents against 2,058, and the 300 are the first 300 rows, which
  are older, whiter and more conservative than the panel.
- **The task sets differ.** 13 tasks against 14; a task unmeasurable in one arm drops from the mean.

**The clean test costs about $0.69.** A Jev demographics arm run stateless completes the 2×2 and
isolates grounding from statefulness. Its prompt is the persona and the question and nothing else:
670 tokens per cell, measured from the first question of each existing walk, against the 3,891 the
chained arm averages once it is carrying up to 83 of its own answers. 16.5M tokens in total. Until
it exists, the +0.0389 above should be read as the direction, not the size.

## What it does not change

None of this touches the verdict. The registered comparison is Jev `Choice` against verbalized
GPT-4.1 on demographics-only grounding, and this arm is a different grounding, a different
elicitation and a later run. It also does not rescue individual prediction: 0.1020 is a correlation
near zero on most tasks, and the arm still sits below the persona-blind baseline on accuracy.

What it does establish is that the instrument, not the persona, is the binding constraint — and that
richer grounding moves both models, in the same direction, by an amount too small to change what
either is useful for.

Back to [the documentation index](../README.md), or
[what the result licenses](05-what-this-licenses.md).
