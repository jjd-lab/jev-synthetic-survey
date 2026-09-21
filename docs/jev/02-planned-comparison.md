# The planned comparison, and the verdict

**Verdict: the strong claim fails.** Both tests fail. Jev's native probability vector is not better than GPT-4.1's
stated one on the comparison as it was set up, and for the two-option column the test turns on the
recommendation is unchanged: stay with verbalized probabilities and soft aggregation.

That is the strong claim, and its failure is the smaller half of the result. That arm
loses exactly one of the six reported measures and wins the other five, at a thirty-fourth of the
cost — so the weaker claim, that this is the better instrument once asked properly, is the one the
data actually speaks to. It is not what the comparison was set up to ask, and it is not settled here.

## Question

Does Jev's native probability vector describe the human answer distribution better than GPT-4.1's
stated one, in the demographics-only stateful setting? The two tests that decide it are in
[question and criteria](01-question-and-criteria.md).

## Setup

Four arms, the **same 300 respondents** (respondent ids 1 to 300 in loader order), the same 108
scored columns, the same 16 tasks, the same persona cache, and **24,596 asked cells in every
arm**. Set equality was asserted on respondent ids and cell keys, not just counts.

| Arm | Model | How it was asked | Errors |
|---|---|---|---|
| Jev Choice | `jev-1.13.0` | native `Choice` vector | 0 |
| GPT-4.1 probabilities | gpt-4.1 | states a probability per option, grids unbatched | 0 |
| GPT-4.1 hard answer | gpt-4.1 | picks one option, grids batched | not recorded |
| Jev Noul | `jev-1.13.0` | `Noul` on the 65 two-option columns, `Choice` on the 43 multi-option ones | 0 |

The comparison that decides the verdict is Jev Choice against GPT-4.1 probabilities. The other two
are described in [question and criteria](01-question-and-criteria.md).

The hard-answer arm was not run for this comparison. It is the first 300 respondents of the
2,058-respondent stateful panel run, extracted, with all 24,596 cells identical. That is why its
grids are batched where the probabilities arm's are not, and it is the reason those two differ in
two ways rather than one, which [elicitation effects](../survey/04-elicitation-effects.md)
decomposes.

GPT-4.1 probabilities introduces no new machinery: stating probabilities is an existing mode in
this engine, already measured on a separate survey panel. What is new is running it on this
instrument.

Both models received the same input, minus the text-generation instructions Jev has no use for.
Jev got the survey prompt as one prose `state`, the filled question stem as `instructions`, and
the options as bare labels with no descriptions
([`jev_client.py:154`](../../scripts/twin2k/jev_client.py)). That matching is what makes this a
comparison of models rather than of prompt engineering, and it has a consequence worth stating up
front: every lever in TypeSafe's own prompting guidance changes the input, so none of them were
pulled. They are untested here, not refuted. One of them lands precisely on the half Jev loses,
and is [the follow-up](03-noul-follow-up.md).

Runs: `runs/jev_vs_gpt41_n300/`. The 300 respondents are the first 300 rows of the panel and are
not demographically representative of it; see [runs/README.md](../../runs/README.md). Every claim
below is paired within those same respondents, which is what the bootstrap resamples, so the
comparison holds; the absolute levels describe that slice only.

## Metrics

Defined in [the metrics page](../survey/02-metrics.md). Three points that bear directly on reading
the tables:

Accuracy is computed from each arm's own vector (its largest entry), for all four arms. The
model's stated choice is a separate field, produced after the vector, and no code links the two,
so an arm can state a vector and then name an option that is not its maximum:

| | stated choice strictly below its own maximum | accuracy, from the vector | accuracy, as stated |
|---|---|---|---|
| Jev Choice | 40 (0.16%) | 67.59% | 67.49% |
| GPT-4.1 probabilities | 189 (0.77%) | 64.78% | 64.90% |
| GPT-4.1 hard answer | no vector | 69.32% | 69.32% |
| Jev Noul | 29 of its 8,700 `Choice` cells (0.33%) | 67.28% | not separable |

GPT-4.1 contradicts its own vector about five times as often as Jev does, but either rule moves
accuracy by about a tenth of a point, so nothing in the verdict turns on the choice of rule.

Calibration error is only meaningful for the arms that have a vector. GPT-4.1 hard answer
always states 100% confidence, so its figure restates "this arm has no distribution". Rebinning
separates the cases cleanly: pooled calibration error moves by 0.0015 or less for Jev Choice,
GPT-4.1 probabilities and Jev Noul when the bins change, and by 0.2829 for GPT-4.1 hard answer.

The two column groups are one split under two names. The 65 two-option columns are the same
set as the "nominal" columns; the 43 multi-option columns are the same set as the "ordinal" ones.
No scored column in this instrument accepts more than one answer.

## Results

### Both tests fail

```
paired: Jev Choice vs GPT-4.1 probabilities
(108 shared columns, 300 shared respondents; lower is better)
  distribution gap, two-option    delta +0.0196  [-0.0030, +0.0425]  Wilcoxon p=1.0000  Jev WORSE
  distribution gap, multi-option  delta -0.0408  [-0.0977, +0.0181]  Wilcoxon p=0.0308  Jev better
  Brier                           delta -0.0558  [-0.0705, -0.0406]  Wilcoxon p=0.9749  Jev better
  distribution test (wins both halves): FAIL
```

The distribution test is a conjunction and Jev loses the two-option half. The calibration test
fails too: Jev Choice's calibration error on the 65 two-option columns, weighted equally across
tasks, is 0.2029, four times the 0.05 threshold.

### The result is split, and the split is the finding

| Measure (equal weight per task) | Jev Choice | GPT-4.1 probs | GPT-4.1 hard | Jev Noul |
|---|---|---|---|---|
| accuracy (from the vector) | 67.59% | 64.78% | 69.32% | 67.28% |
| leave-one-out majority (shared floor) | 73.59% | 73.59% | 73.59% | 73.59% |
| distribution gap, 65 two-option cols | 0.1985 | 0.1789 | 0.2037 | 0.1530 |
| ordinal distribution gap, 43 cols | 0.6864 | 0.7272 | 0.6987 | 0.6812 |
| Brier, all cells | 0.7550 | 0.8108 | 1.1664 | 0.7385 |
| log loss | 1.6439 | 1.8152 | 4.0286 | 1.5486 |
| Brier on the 15,896 two-option cells (0 to 1 scale) | 0.3052 | 0.2741 | 0.3456 | 0.2671 |
| Murphy reliability (lower better) | 0.0759 | 0.0544 | 0.1205 | 0.0385 |
| Murphy resolution (higher better) | 0.0190 | 0.0293 | 0.0246 | 0.0210 |
| calibration error, two-option, equal-task | 0.2029 | 0.2393 | 0.3741 | 0.1472 |
| cells giving the human's answer zero probability | 1,681 | 674 | 11,466 | 1,069 |
| entropy ratio (1.0 = human diversity) | 0.8497 | 0.9596 | 0.6630 | 0.9467 |
| collapsed columns (one answer for everyone) | 24 | 13 | 10 | 23 |

Read the first three columns for the verdict and the fourth as the follow-up.

Jev is better on multi-option items and worse on two-option ones, and two independent families
of measure agree in both directions. On the 43 multi-option columns Jev wins the ordinal
distribution gap (0.6864 against 0.7272, better in 26 of 43 columns, p=0.031), and that advantage
is what carries its all-cell Brier win. On two-option items the Murphy decomposition puts GPT-4.1
ahead on both terms at once, better calibrated (reliability 0.0544 against 0.0759) and sharper
(resolution 0.0293 against 0.0190), which is the same conclusion the distribution gap reaches by
another route.

Read the Murphy terms as components rather than an exact partition. With 10 equal-width bins over
continuous forecasts, reliability minus resolution plus uncertainty overshoots the true pooled
two-option Brier by a within-bin variance term: measured here at +0.0013 for Jev Choice, +0.0006
for GPT-4.1 probabilities, and about zero for GPT-4.1 hard answer. That residual is roughly 25
times smaller than the gap it is being used to describe, so the ranking holds, but the reliability
term is not a clean calibration figure at this resolution.

### Pricing does not explain the failure

The expectation written down in advance was that TypeSafe's documented numeric weakness would sink
Jev on the 40 pricing columns, where a randomized price is piped into each question stem. It does
hurt there, but that is not what fails the test.

| distribution gap per column, unweighted | n | Jev Choice | GPT-4.1 probs | Jev better in |
|---|---|---|---|---|
| all two-option | 65 | 0.2235 | 0.1177 | 19/65 |
| pricing | 40 | 0.2246 | 0.1074 | 13/40 |
| **non-pricing** | 25 | 0.2219 | 0.1342 | **6/25** (p=0.9995) |

Jev is worse on two-option columns in both blocks. The equal-task-weighted figures excluding
pricing happen to tie at 0.1932 for both arms, but that is a coincidence of the weighting
(0.193241 against 0.193203 over just 5 tasks), driven by one catastrophic GPT-4.1 column
(Dominator neglect, 0.4140) taking a fifth of the non-pricing weight. It is not evidence of parity.

Where pricing does dominate is individual accuracy: Jev Choice is 9.18 points below GPT-4.1 hard
answer on pricing against 1.34 points on the other 15 tasks. Jev also beats it outright on several
reasoning tasks (Proportion dominance +7.76, Myside bias +6.57, Linda +2.83), so the accuracy
deficit is concentrated exactly where TypeSafe said it would be. The mechanism turns out not to be
arithmetic at all; see [price sensitivity](04-price-sensitivity.md).

### The calibration failure is about the setting, not about Jev

All four arms fail the calibration test: 0.2029, 0.2393, 0.3741 and 0.1472 for Jev Choice, GPT-4.1
probabilities, GPT-4.1 hard answer and Jev Noul respectively. A demographics-only simulated
respondent produces poorly calibrated *individual* forecasts regardless of which model supplies the
vector or how it is asked for.

That is what the grounding results in [the survey track](../survey/03-grounding-panel.md) predict:
individual-level reliability arrives only with far richer grounding than demographics. At this
level an individual outcome is close to unpredictable, so any confident forecast is miscalibrated
by construction. Changing how the question is asked moves the number a long way, and still leaves
it at three times the threshold. The test says something about the setting, not about the model,
and it licenses no individual-level claim for any arm.

## Interpretation

Jev's vector is better where the answer space is ordered and worse where it is binary. The binary
loss is what fails the test, and it turns out to be substantially an artifact of how the question
was asked rather than of the model's judgment, which is [the follow-up](03-noul-follow-up.md).
That does not rescue the verdict, and was never eligible to.

One asymmetry does not change the verdict but changes what it is worth. Jev bills input only, at
$0.042 per million tokens, with output free.

| Arm | Input tokens | Output | Cost |
|---|---|---|---|
| Jev Choice | 95,489,047 (billed) | free | $4.01 measured |
| GPT-4.1 probabilities | 91,186,347 (39.7% cached) | 1,052,004 | about $136 inferred |
| Jev Noul | 95,694,291 (billed) | free | $4.02 measured |

The GPT-4.1 figure is inferred from list rates ($2.00 per million input, $0.50 cached, $8.00
output), not billed through, so read it as an order of magnitude. A 34-fold cost gap makes "no
better" a different proposition than it would be at parity.

Note what the Jev figure is mostly buying. Both arms are chained, so each cell re-sends the walk so
far: 670 input tokens at the first question, 7,406 by the 83rd, 3,891 on average for Jev Noul and
3,882 for Jev Choice. Roughly five
sixths of the bill is the model re-reading its own earlier answers, not the persona. Unchained, the
same 24,596 cells would be about 16.5M tokens and $0.69.

Wall clock is not a like-for-like comparison here and should not be read as one, because the arms
ran at different concurrency: about 35 minutes for Jev Choice at 16 concurrent walks against 22
minutes for GPT-4.1 at 50. Per call, the measurement runs the other way. Jev's records carry
`latency_ms` and average 0.26 s across all 24,596 cells, median 0.23 s, p99 0.48 s. The GPT-4.1
arm was converted from workbooks and kept no per-call timing, so its rate can only be inferred
from its wall clock, at roughly 2.7 s per cell.

The 35-minute figure is also not what the same work costs today. Re-measured against a live
`Noul` walk at the same concurrency of 16 and against a warm persona cache, the throughput is
about 3,100 to 4,000 cells per minute, which puts a 24,596-cell arm at **6 to 8 minutes**. The
per-walk serial latency implied by that rate, 240 ms, sits on top of a 260 ms API mean, so the
walk is latency-bound with no measurable overhead and its wall clock scales down with
concurrency. Whatever cost the original arm its extra half hour, throttling or a cold persona
cache, was not the model's response time. Budget from 6 to 8 minutes, not 35.

## Caveats

- **The 300 respondents are not representative of the panel.** They are the first 300 rows, and
  respondent id order correlates with age. Paired comparisons are unaffected; absolute levels are
  not. See [runs/README.md](../../runs/README.md).
- **GPT-4.1 hard answer is not a comparator.** It has no vector, so its Brier and calibration
  numbers measure the absence of a distribution.
- **Jev is not deterministic.** Two identical runs differ by a mean per-cell distribution gap of
  0.055 and flip the top answer 7.5% of the time. Scaled to 300 respondents the column-level noise
  floor is about 0.006, so the +0.0196 two-option deficit is above it and the loss is real, even
  though the respondent bootstrap interval straddles zero. That 0.055 is an upper bound inflated by
  the accidental chaining described below. The [described arm](06-option-descriptions.md) later
  measured 0.011 per cell on byte-identical payloads. Its column-level floor came out at 0.0058 on
  the multi-option columns, which matches the 0.006 used here, so this conclusion is unchanged.
- **Contamination applies to both sides equally.** Twin-2K-500 has been public since 2025 and its
  tasks are classic replications, so between-arm comparison is fairer than any absolute number.
- **State growth was not tested.** The arm meant to test it chained by mistake, so no unchained Jev
  run exists. Within this run the question is unanswerable: every simulated respondent reaches a
  given column at the same position in the walk, so state size is perfectly confounded with which
  question is being asked. The defect is fixed in
  [`probe_jev.py`](../../scripts/twin2k/probe_jev.py), with the assertion that was missing.
- **Vector hygiene was clean on both sides.** Jev's raw vectors sum to a mean of 0.9999, all within
  1% of 1, with 11.9% saturated at a maximum probability of 0.999 or more, 16.6% counting only its
  two-option cells. GPT-4.1's stated vectors came back at exactly 1.0000.

## Reproduce

```bash
python scripts/twin2k/prob_scoring.py score \
    --arm jev_chained=runs/jev_vs_gpt41_n300/jev_choice.jsonl \
    --arm gpt41_probs_chained=runs/jev_vs_gpt41_n300/gpt41_probs.jsonl \
    --arm gpt41_hard_chained=runs/jev_vs_gpt41_n300/gpt41_hard.jsonl \
    --bootstrap 1000 --seed 20260919 --ece-bins 10 --out /tmp/check.json
```

Writes the equivalent of [`reports/jev_vs_gpt41_n300/score_all_arms.json`](../../reports/jev_vs_gpt41_n300/score_all_arms.json). See
[reports/README.md](../../reports/README.md) for what does and does not match byte for byte.
