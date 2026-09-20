# Does Jev's native probability vector beat a verbalized one on Twin-2K-500?

**Status:** implemented, verdict **Reject (¬C3)**. A follow-up `Noul` arm closes the whole binary half
of the gap, so the pre-registered failure was in substantial part the elicitation, not the model.

## Question

TypeSafe AI's Jev is a decision-only model. It returns a typed value plus a calibrated probability
vector and generates no text. The question asked was narrow and pre-registered before any data:
**in the production-shaped setting, stateful, demographics-only, each twin chained to its own
running answers, does Jev's native vector beat gpt-4.1 asked to verbalize one?** That setting is the
one a new survey actually has, with no prior answers from its real respondents, only who they are.

Two criteria, both fixed in advance:

| | Criterion | Read on | Pass |
|---|---|---|---|
| **C3** | Better vector than verbalizing | JC vs BC | `soft` distributional error JC ≤ BC **in each bucket** (Wilcoxon over columns) and Brier JC ≤ BC (paired bootstrap) |
| **C1** | Calibration transfers | JC | equal-task-weighted ECE on the 65 binary columns ≤ 0.05 (0.05 to 0.10 marginal, > 0.10 fail) |

## Arms

Four arms, the **same 300 respondents** (loader order, respids 1 to 300), the same 108 scored columns,
the same 16 tasks, the same persona cache, and **24,596 asked cells in every arm**, set equality
asserted, not counts.

| Arm | Model | Elicitation | Cells | Errors |
|---|---|---|---|---|
| JC `jev_chained` | `jev-1.13.0` | native `Choice` vector | 24,596 | 0 |
| BC `gpt41_probs_chained` | azure/gpt-4.1 | `verbalized_probs`, `batch_grids: false` | 24,596 | 0 |
| AC `gpt41_hard_chained` | azure/gpt-4.1 | `hard_choice`, grids batched | 24,596 | |
| NC `jev_noul_chained` | `jev-1.13.0` | native `Noul` on the 65 binary columns, `Choice` on the 43 ordinal | 24,596 | 0 |

**C3 and C1 were registered on JC vs BC**, and that is the verdict. NC is a **follow-up arm built after
seeing JC lose the binary half**, it tests the one hypothesis the vendor's guidance points at, and it
is reported as the post-hoc result it is.

AC is a **loose sanity check only**, not a comparator. It has no probability columns, so it is scored
one-hot and any Brier or ECE number against it measures *"has a distribution at all"* rather than
calibration quality. BC is the only valid C3 comparator.

BC introduces no new elicitation: `response_mode: "verbalized_probs"` is an existing mechanism in
this engine, already measured on a separate survey panel, and the `weighted_draw` commit rule elicits
identically, it differs only in what it then commits. What is new here is running it on Twin.

## Reading the numbers

**The two column buckets are one split under two names.** `ordered_scale` is true on exactly the 43
columns with more than two options, so "65 nominal", "65 binary" and "the 65 two-option columns" all
name the same set, verified against the JSONL, not assumed.

| Bucket | n | Options per column | Metrics read on it |
|---|---|---|---|
| **nominal** = **binary** | 65 | exactly 2 | soft TVD, ECE, Murphy, binary Brier |
| **ordinal** = **multiclass** | 43 | 5 (16 cols), 6 (13), 7 (10), 10 (3), 4 (1) | soft W1, top-label ECE |

**"Multiclass" means one answer out of more than two options, not more than one answer.** No scored
Twin column is multi-select; the repo's `multi` type is unexercised on this instrument. Multiclass
Brier is the ordinary Brier score on a vector longer than 2, nothing more.

**Brier, per cell:** subtract the human's one-hot answer from the forecast, square each element, sum
them. A forecast of `[0.6, 0.3, 0.1]` against a human who chose the second option gives
`0.6² + 0.7² + 0.1² = 0.86`. The range is 0 to 2, sure and right scores 0, "no opinion" `[0.5, 0.5]`
scores 0.5, sure and wrong scores 2. Confident error is punished far harder than doubt, which is why
an arm can be the most accurate and still score worst: AC's 1.1664 is exactly that, every forecast
being a 1 and a set of 0s, so every miss costs the full 2.

**ECE reads the probability for JC and BC.** One forecast per cell, P(first canonical option), over
the 65 binary columns, sorted into 10 equal-width bins; per bin `|mean forecast − mean outcome|`,
weighted by bin size. AC has no vector, so it is scored one-hot and always states 100% confidence.
Rebinning separates the two cases cleanly:

| pooled ECE | 10 equal-width bins | equal-count bins | move |
|---|---|---|---|
| JC | 0.2532 | 0.2517 | 0.0015 |
| BC | 0.2270 | 0.2278 | 0.0008 |
| NC | 0.1837 | 0.1837 | 0.0000 |
| AC | 0.3456 | 0.0627 | 0.2829 |

The Jev and BC figures are stable under rebinning and mean what they say. AC's collapses, because
one-hot forecasts occupy only the two extreme bins, so AC's 0.3741 is a restatement of "AC has no
distribution", not a calibration result.

**Every accuracy figure below uses `argmax`**, the largest entry of the arm's own vector,
for all four arms. The model's stated `choice` is a *separate* schema field, generated after the
vector (`option_probabilities` is inserted as the first dynamic field,
`src/core/survey_runner_excel.py:415-419`), and no code links the two, so an arm can state a vector
and then name an option that is not its maximum:

| | stated `choice` strictly below the max | joint-maximum ties | accuracy, `argmax` | accuracy, stated `choice` |
|---|---|---|---|---|
| JC | 40 (0.16%) | 113 | 67.59% | 67.49% |
| BC | 189 (0.77%) | 320 | 64.78% | 64.90% |
| AC |, no vector | | 69.32% | 69.32% |
| NC | 29 of its 8,700 `Choice` cells (0.33%) | 145 | 67.28% |, not separable |

A tie is not a contradiction. `argmax` merely breaks it differently from the model, and the tie count
is tie-break-dependent, so only the strict column is a measurement. BC contradicts its own vector
about 5x as often as JC, and either commit rule moves accuracy by ~0.1 pt, so nothing in the verdict
turns on the choice of rule.

**NC is the one arm that cannot contradict itself on the binary columns**, because a `Noul` returns no
label to contradict. Its committed answer *is* a threshold on its own number, so `argmax` and commit
coincide there by construction, and only its 43 `Choice` columns have a stated label at all.

## Both C3 and C1 fail

```
paired: jev_chained vs gpt41_probs_chained   (108 shared columns, 300 shared respondents; lower is better)
  soft_nominal   delta +0.0196  [-0.0030, +0.0425]   wilcoxon p=1.0000    JC WORSE
  soft_ordinal   delta -0.0408  [-0.0977, +0.0181]   wilcoxon p=0.0308    JC better
  brier          delta -0.0558  [-0.0705, -0.0406]   wilcoxon p=0.9749    JC better
  C3 (left arm wins both halves): FAIL
```

C3 is a conjunction, and Jev loses the nominal half. **C1 also fails**: JC's equal-task-weighted ECE
on the 65 binary columns is 0.2029, four times the 0.05 threshold.

Per the pre-registered table this is **Reject**. The native vector is not better than the verbalized
one, and the recommendation stands unchanged. Stay with `verbalized_probs` and soft aggregation.

**The follow-up `Noul` arm does not overturn this**, and it was not eligible to. C3 is a pre-registered
comparison of JC against BC. It does explain a large part of it, and it fails the same pre-registered
per-column test against BC, see [the `Noul` section](#the-binary-loss-was-largely-the-elicitation-re-asking-those-columns-as-noul).

## The result is split, and the split is the finding

| Metric (task-equal-weighted) | JC (Jev) | BC (gpt-4.1 probs) | AC (gpt-4.1 hard) | NC (Jev `Noul`) |
|---|---|---|---|---|
| paper accuracy (argmax-committed) | 67.59% | 64.78% | 69.32% | 67.28% |
| LOO majority (shared floor) | 73.59% | 73.59% | 73.59% | 73.59% |
| soft TVD, 65 nominal cols | 0.1985 | 0.1789 | 0.2037 | 0.1530 |
| soft W1, 43 ordinal cols | 0.6864 | 0.7272 | 0.6987 | 0.6812 |
| Brier, multiclass, all cells | 0.7550 | 0.8108 | 1.1664 | 0.7385 |
| log loss | 1.6439 | 1.8152 | 4.0286 | 1.5486 |
| Brier on the 15,896 binary cells | 0.3052 | 0.2741 | 0.3456 | 0.2671 |
| Murphy reliability (lower better) | 0.0759 | 0.0544 | 0.1205 | 0.0385 |
| Murphy resolution (higher better) | 0.0190 | 0.0293 | 0.0246 | 0.0210 |
| ECE binary, equal-task | 0.2029 | 0.2393 | 0.3741 | 0.1472 |
| cells giving the human's answer p=0 | 1,681 | 674 | 11,466 | 1,069 |
| entropy ratio (1.0 = human diversity) | 0.8497 | 0.9596 | 0.6630 | 0.9467 |
| collapsed columns (one answer for all) | 24 | 13 | 10 | 23 |

Read the first three columns for the verdict and the fourth as the follow-up. **Between JC and BC, Jev
is better on multi-category items and worse on binary ones**, and two independent metric
families agree in both directions. On the 43 ordinal columns Jev wins Wasserstein-1 (0.6864 vs
0.7272, 26/43 columns, p=0.031) and that advantage is what carries its all-cell multiclass Brier win.
On binary items the Murphy decomposition puts BC ahead on both terms, better calibrated
(reliability 0.0544 vs 0.0759) *and* sharper (resolution 0.0293 vs 0.0190), which is the same
conclusion the nominal TVD reaches by another route.

Read the Murphy terms as components rather than an exact partition. With 10 equal-width bins over
continuous forecasts, `reliability − resolution + uncertainty` overshoots the true pooled binary
Brier by a within-bin variance term (measured here: +0.0013 JC, +0.0006 BC, −0.000 AC). The residual
is ~25x smaller than the JC-vs-BC gap it is being used to describe, so the ranking holds, but the
reliability term is not a clean calibration figure at that resolution.

### Pricing does not explain the C3 failure

The pre-registered expectation was that the vendor's documented numeric weakness would sink Jev on
the 40 pricing columns, where a randomized price is piped into the stem. It does, but that is not
what fails C3.

| soft nominal TVD, per column (unweighted) | n | JC | BC | JC better in |
|---|---|---|---|---|
| all nominal | 65 | 0.2235 | 0.1177 | 19/65 |
| pricing | 40 | 0.2246 | 0.1074 | 13/40 |
| **non-pricing** | 25 | 0.2219 | 0.1342 | **6/25** (p=0.9995) |

Jev is worse on nominal columns **in both blocks**. The task-equal-weighted `excl_pricing` figures
happen to tie at 0.1932 for both arms, but that is a coincidence of the weighting (0.193241 vs
0.193203 over just 5 tasks), driven by BC's one catastrophic column, Dominator neglect, 0.4140 , 
receiving a fifth of the non-pricing nominal weight. It is not evidence of parity.

Where pricing *does* dominate is **individual accuracy**: JC is −9.18 pt against AC on pricing versus
−1.34 pt on the other 15 tasks. Jev also beats AC outright on several reasoning tasks
(Proportion dominance +7.76, Myside bias +6.57, Linda +2.83), so its accuracy deficit is
concentrated exactly where the vendor said it would be.

### C1's failure is the grounding level, not Jev

All four arms fail C1, JC 0.2029, BC 0.2393, AC 0.3741, NC 0.1472, so a demographics-only twin
produces poorly calibrated *individual* forecasts regardless of who supplies the vector or how it is
asked for. This is the grounding ladder restated, ungrounded < demographics-only <
survey-response twins < interview-grounded agents, with individual-level reliability arriving only at
the top, and at demographics-only
grounding an individual outcome is near-unpredictable, so any confident forecast is miscalibrated by
construction. Changing the elicitation moves the number a long way, NC is the best-calibrated arm and
the only one out of the 0.20s, and still leaves it 1.5x the failure threshold, which is the clearest
evidence here that C1 is a statement about the *setting*. It does not license an individual-level
claim for any arm.

### What the vendor's prompting guidance predicts, and what was not tried

C3 gave Jev **the same input gpt-4.1 got**, minus the text-generation instructions. It got the survey prompt
as one prose `state`, the filled stem as `instructions`, and `criteria` as `{option: None}`, bare
labels, no descriptions (`scripts/twin2k/jev_client.py:154`). That matching is what makes C3 a
comparison of models. Every lever in TypeSafe's own guidance changes the input, so pulling one would
have turned C3 into a comparison of prompt engineering. They are therefore **untested by C3, not
refuted**, and one of them lands precisely on the half Jev loses. That one was pulled afterwards, as
a separate arm; the rest remain untried.

| Vendor-documented weakness | How it applies here | Status |
|---|---|---|
| "Jev is not a calculator"; numeric representations underperform semantic ones | 40 pricing columns pipe a randomized price into the stem | **measured, and it does not hold as stated.** The accuracy cost is real (−9.18 pt vs AC) but the cause is not arithmetic; see [Pricing is a boundary problem](#pricing-is-a-boundary-problem-not-an-arithmetic-one) |
| "Large, noisy state, accuracy falls as the state grows with content unrelated to the decision" (the vendor's "context rot") | the chained walk grows the state by one Q&A pair per cell, up to 83 | **untested.** There is no unchained Jev arm to compare against; see below |
| Yes/no is where the primitives diverge: "a Choice is **relative**, settling *which* option", each Noul absolute; the vendor's own example gives 0.22 vs 0.01 on an equivalent pair, and a statement plus its negation summing to 1.19 | all 65 binary columns were asked as `Choice`, never as `Noul` | **measured, and it was the leading candidate for good reason.** Re-asked as `Noul`, soft nominal TVD 0.1985 → 0.1530, more than the whole deficit to BC; see below |
| `criteria` descriptions exist to "separate the options from each other"; bare labels carry only themselves | `criteria={option: None}`, so on a binary pricing column Jev sees "Yes"/"No" and all the meaning sits in the stem | **untested, and now the lever this evidence implicates.** A constant offset in what counts as "yes" is exactly what a description would move |
| State should be "an object, so each part of the state has a descriptive name and its relationships remain clear" | state is one prose blob, the config's `survey_prompt` | untested |
| State is **data to judge**, not instructions to obey, "text that argues for its own classification can shift answers" | a survey twin *is* a role-play instruction | untested, and not obviously fixable: Jev has no role mechanism |
| "Literal reading, answers the question you wrote, not the one you meant" | Twin stems are framed scenarios, not direct questions to the answerer | untested |

**Context rot cannot be tested from these runs, because no unchained Jev arm exists.** `order_probe`
was specified as that arm, but `--chain` only cross-checked the config against `memory_mode` and never
gated the walk: `walk_persona` appended every answer to the history unconditionally. So `order_probe`
chained too, its input grows 653 → 6,645 tokens across the walk, matching JC cell for cell. Fixed in
`scripts/twin2k/probe_jev.py`, with the byte-equality assertion that was missing
(`tests/unit/test_probe_jev.py::test_without_chain_every_state_is_identical`).

Within the JC run itself the question is unanswerable: `history_len` has **zero** variance within a
column, every twin reaches a given column at the same walk position, so state size is perfectly
collinear with which question is being asked.

What the JC-vs-`order_probe` comparison does give is a reproducibility floor for the probe. On their
2,040 shared cells, two separate runs of what is effectively the same chained arm differ by a paired
Brier delta of +0.0017 (CI [−0.0119, +0.0162]), with 584 of 2,040 vectors bit-identical, against
+0.0065 between two labelled repeats of `order_probe` itself. The probe reproduces itself to within
Jev's own run-to-run noise. That is a fidelity check on our code; it says nothing about state size.

## Re-asking the binary columns as `Noul`

NC re-asks the 65 two-option columns as `Noul` and holds everything else at JC's values, meaning the same 300
personas, the same persona cache, the same chained walk, the same per-persona option-order RNG, the
same pinned `jev-1.13.0`, and the 43 ordinal columns still asked as `Choice`. Every shared cell carries
the same `presented_order` as JC, set equality asserted on respids and cell keys, not counts.
24,596 cells (15,896 `Noul`, 8,700 `Choice`), zero aborted walks, $4.02.

A `Noul` returns **one absolute number**, P(yes), and no label and no confidence. Two fields the other
arms *state* are therefore derived for NC. The vector is `{target: p, other: 1 − p}`, and the
committed answer is `p ≥ 0.5`. Both consequences matter when reading its numbers, the raw-sum
hygiene check is vacuous on its binary half (those vectors sum to 1 by construction, not by the
model's doing), and it is the one arm whose commit rule cannot disagree with its own vector.

The condition is one line appended to the stem, `Does this respondent answer "{target}"?`, with
everything before it byte-identical to what JC sent, and phrased so that high means yes as the docs
advise. `target` is **the first presented option**, so the per-persona RNG that permuted JC's options
also varies which side each respondent is asked about, which is what makes the asymmetry measured
below visible across a column instead of baked into every cell of it.

### Against JC the entire binary gap closes, and accuracy does not pay for it

| paired, 108 shared columns / 300 shared respondents (lower is better) | delta | 95% CI | Wilcoxon |
|---|---|---|---|
| soft TVD, 65 nominal | −0.0454 | [−0.0564, −0.0328] | p=0.0000, 49/65 columns |
| soft W1, 43 ordinal | −0.0052 | [−0.0098, +0.0004] | p=0.0537 |
| Brier, multiclass | −0.0165 | [−0.0203, −0.0127] | p=0.0000 |

0.1985 → 0.1530 on the nominal half is more than twice JC's whole 0.0196 deficit to BC, and every
calibration metric moves with it: ECE equal-task 0.2029 → 0.1472, Murphy reliability 0.0759 → 0.0385,
binary Brier 0.3052 → 0.2671, log loss 1.6439 → 1.5486, cells giving the human's answer p=0
1,681 → 1,069, entropy ratio 0.8497 → 0.9467. **Accuracy is unchanged**, 67.59% → 67.28%, a third of
a point, so the elicitation bought calibration without trading away hit rate. A 5-persona pilot had
suggested −3.4 pt of accuracy; that did not survive n=300 and was pilot noise.

**The mechanism is saturation.** On the 15,896 shared binary cells JC put a probability of *exactly
zero* on one option in 16.6% of them; NC did so in 0.0%, its scale never reaches the
endpoints. A zero on the human's answer costs the full 2 in Brier and is unbounded in log loss, so
removing that one behaviour accounts for most of the gain. The two primitives are not cosmetic
variants of each other. On the same cell and the same label they differ by a mean of 0.1301.

The ordinal delta is a control, not a result. Those 43 columns were asked identically in both arms, so
their −0.0052 bounds the combined effect of Jev's run-to-run noise *and* a perturbed history (NC
commits a thresholded answer where JC committed a stated one). Sitting at p=0.0537 it is the right
order of magnitude for noise, and it is a second, independent sighting of the reproducibility floor
measured on `order_probe`.

### Against BC the aggregation decides, and the pre-registered rule still fails

| soft TVD, 65 nominal columns | NC | BC | delta | CI | per-column test |
|---|---|---|---|---|---|
| task-equal-weighted (the repo's aggregation) | 0.1530 | 0.1789 | −0.0259 | [−0.0459, −0.0053] | |
| per column, unweighted | 0.1747 | 0.1177 | +0.0570 | | NC better in 21/65, **Wilcoxon p=0.9995** |

Both rows are correct and they point opposite ways. The repo aggregates mean-within-column →
within-task → **equal weight across the 16 tasks**, and one task holds 40 of the 65 binary columns, so
task weighting gives each of the 25 non-pricing columns roughly 8x the weight it gets per column. The
pre-registered C3 rule is the per-column Wilcoxon within each bucket, so **C3 still fails against BC** , 
now for a different reason than JC's. JC lost on both aggregations; NC wins the task-weighted one and
loses the per-column one. The scorer prints `c3_left_wins: true` for NC-vs-BC, but that flag reads
delta signs only and is looser than the registered rule; the registered rule governs.

Per column, `Noul` closes proportionally more of the gap where no price is piped into the stem, the
vendor's numeric weakness survives the change of primitive:

| soft nominal TVD, per column (unweighted) | n | JC | NC | BC |
|---|---|---|---|---|
| all nominal | 65 | 0.2235 | 0.1747 | 0.1177 |
| pricing | 40 | 0.2246 | 0.1848 | 0.1074 |
| non-pricing | 25 | 0.2219 | 0.1586 | 0.1342 |

NC beats JC on 26/40 pricing and 23/25 non-pricing columns, and it breaks the coincidental
`excl_pricing` tie reported above: 0.1467 against 0.1932 for both of the other two arms.

### A statement and its negation are incoherent by an order of magnitude less than the vendor's example

`Noul` makes the vendor's "a statement plus its negation summed to 1.19" claim measurable on a real
instrument for the first time here. Because the condition names whichever option was presented first,
every one of the 65 columns was asked about side A for some respondents and side B for others, and a
coherent forecaster would give P(A) + P(B) = 1 on the column's marginal.

| implied P(A) + P(B) over 65 columns | value |
|---|---|
| mean | 0.9950 |
| median | 0.9883 |
| range | 0.8654 to 1.0838 |
| mean deviation from 1, unsigned | 0.0234 |
| columns more than 2 SE from 1 | 29 of 65 (median \|z\| 1.58, max 49.37) |

So there is **no systematic inflation**, the mean sits within half a point of 1, but individual
columns are incoherent by 2.3 points on average and 29 of them significantly so. That is real and
worth knowing, and it is an order of magnitude smaller than the 0.19 in the vendor's own illustration.
One confound is structural and cannot be removed from this design: the target side is also the
first-presented side, so this figure carries any presentation-order effect along with the primitive's
incoherence. The order probe bounds that component at ≤0.017 column-marginal TVD, i.e. small but not
zero.

## Asking gpt-4.1 for probabilities costs 4.4 points of committed accuracy

BC lands 4.42 pt below AC (64.90% vs 69.32%), outside the ±2 pt gate. This gate is about what each
arm *committed*, so it is the one place the arms' own stated `choice` is used rather than `argmax`;
under `argmax` the gap is 4.54 pt (64.78% vs 69.32%) and the conclusion is identical. BC differs from
AC in two ways, so the plan required decomposing rather than blaming one, and the decomposition is
unambiguous:

| | AC | BC | BC − AC |
|---|---|---|---|
| Pricing, the **only** 40 columns where `batch_grids` differs | 63.97% | 64.86% | +0.89 |
| The other 15 tasks, one call per cell in both arms | 69.68% | 64.91% | −4.77 |

The entire loss sits where the grid setting is *not* in play, and pricing, the one block that was
unbatched, slightly improved. So this is the **`verbalized_probs` effect, not the grid-unbatching
effect**: asking gpt-4.1 to state a distribution moves its committed answer, the same class of effect
as a field-order effect measured earlier on a separate panel. The mechanism is the schema field order above , 
gpt-4.1 writes the whole vector before it writes `choice`, and BC's 0.77% strict contradiction rate
(vs JC's 0.16%) is the visible residue of that. `batch_grids: false` cost nothing measurable and
remains the right choice for matching the probe one call per cell.

## Jev is about 34 times cheaper

| Arm | Input tokens | Output | Cost |
|---|---|---|---|
| JC | 95,489,047 (billed) | free | $4.01 measured |
| BC | 91,186,347 (39.7% cached) | 1,052,004 | ~$136 inferred |
| NC | 95,694,291 (billed) | free | $4.02 measured |

Jev bills input only at $0.042/Mtok and its output is free, which is the whole difference. BC's figure
is *inferred* from gpt-4.1 list rates ($2.00/$0.50 cached/$8.00 per Mtok), the repo has no cost
model and this was not billed through, so treat it as an order-of-magnitude statement. Wall clock was
comparable: JC ~35 min at 16 concurrent walks, BC 22 min at 50.

This asymmetry is the strongest argument for revisiting Jev. It does not change the verdict, because
C3 was a quality criterion, but a 34x cost gap makes "no better" a different proposition than it
would be at parity. It also survives the better elicitation: NC's appended condition line adds 205,244
input tokens over the whole run, 0.2%, so the arm that closes the binary gap costs the same cent.

## Instrument behaviour, which the vendor does not document

Measured on `order_probe`, 25 respondents x 108 columns, 2,040 comparable cells. The arm was *intended*
to be unchained, precisely so that model noise stayed separate from path dependence; it chained (see
above), so every figure here is an **upper bound** that carries both. A flipped early answer changes
every later prompt, and the divergence compounds along the walk.

| | per-cell TVD | median | p90 | top-label flips | column-marginal TVD (n=25) |
|---|---|---|---|---|---|
| **determinism** (identical inputs, r1 vs r2) | 0.0551 | 0.0100 | 0.0900 | 7.5% | 0.0214 |
| **order** (options permuted, s2) | 0.0487 | 0.0200 | 0.0800 | 6.3% | 0.0170 |

**Jev is not deterministic**, the vendor confirms this, and its own consistency cookbook reports
cross-input consistency, which is not run-to-run reproducibility. Two identical *runs* differ by mean
TVD 0.055 per cell and flip the top label 7.5% of the time. The conclusion is unaffected by the
chaining defect: a deterministic model would have reproduced the whole walk exactly, history and all.
The magnitude is what is inflated, 0.055 bounds per-cell noise from above rather than measuring it.

**Order sensitivity is indistinguishable from zero**, and by a stronger argument than the
pre-registered gate: the order figure (0.0170) is *smaller* than the repeat noise measured on
identical inputs (0.0214). Permuting the options perturbs the vector less than simply asking twice.
The gate was "< 0.05 or stop"; the honest read is that the effect is below the floor that could
detect it. Path dependence inflates both figures by the same mechanism, so the comparison between them
survives the chaining defect even though neither absolute number is clean.

Scaling the n=25 column-marginal floor to n=300 gives roughly 0.006, so JC's +0.0196 nominal
deficit against BC is above the noise floor, the nominal loss is real, even though the
respondent-bootstrap CI straddles zero.

Vector hygiene was clean on both sides: JC's raw sums mean 0.9999 (min 0.99, 100% within 1% of 1)
with 11.9% of all vectors saturated at max p ≥ 0.999, 16.6% counting only its binary cells, which is
the figure the `Noul` comparison above turns on. BC's verbalized sums came back at exactly 1.0000,
100% within 1%, unlike the behaviour on an earlier panel that motivated checking at all.

### Pricing is a boundary problem, not an arithmetic one

The row above was written from the vendor's documented weakness rather than from the data. Measured
([`price_sensitivity.py`](scripts/twin2k/price_sensitivity.py), which reproduces this table), it points
the other way.

| over the 40 pricing columns | JC | NC | BC | humans |
|---|---|---|---|---|
| corr(piped price, P(yes)) | −0.551 | −0.522 | −0.488 | −0.333 |
| negative in | 40/40 | 40/40 | 40/40 | 40/40 |
| mean P(yes) | 0.601 | 0.591 | 0.343 | 0.416 |
| signed bias vs humans | +0.185 | +0.175 | −0.073 | |
| columns biased high | 36/40 | 37/40 | 10/40 | |

**Jev reads the price, and reads it harder than the humans do**, a stronger price response than the
real respondents in all 40 columns. What it gets wrong is the level: a near-constant +0.175 offset
on NC, which is **95% of that arm's entire pricing TVD** (0.185). It is not noise, not per-column
idiosyncrasy, and not a failure to process the number. Jev thinks people buy things; mostly they do not.

Re-committing at a shifted threshold instead of 0.5 recovers +8.45 pt of NC's pricing accuracy
(52.57% → 61.02% at 0.79) and +5.89 pt of JC's, while giving BC +0.03 pt, gpt-4.1's boundary
is already where it should be. That threshold is chosen on the same cells it is scored on, so it is an
**in-sample upper bound and not an achievable score**. As a diagnostic it is decisive: the ranking is
sound and only the operating point is wrong.

Two consequences. The `criteria`-descriptions row above moves from "untested" to the specific lever
this implicates, because a constant offset in *what counts as yes* is a framing problem a description
can address and a calculator cannot. And a calibration layer fit on held-out columns would likely
recover most of this block, but that is a different product than Jev, and it would have to be
pre-registered and scored out-of-sample to mean anything.

## What this licenses, and what it does not

- **Do not switch to Jev for distributional fidelity on binary items on the strength of C3.** BC beats
  JC there on every metric that measures it, and beats NC on the pre-registered per-column test.
- **Never ask Jev a yes/no item as a `Choice`.** That single substitution is worth more on the binary
  half than the whole JC-vs-BC gap, at the same cost, with no accuracy penalty, the strongest
  actionable result here, and the one to carry into any future Jev work.
- **The verdict is about Jev given gpt-4.1's input, which is the comparison C3 asked for.** It is not
  a verdict on Jev prompted the vendor's way: described `criteria` and an object state remain
  untested, and the one lever that *was* pulled afterwards moved the losing half a long way. Expect
  the others to matter too, and expect any C3 re-run to need re-registering around them.
- **Jev is the better ordinal forecaster** in this setting, and the cheapest by a wide margin. If a
  use case is ordinal-scale marginals under cost pressure, this result argues *for* it, but that is
  a narrower claim than C3 was testing, and it has not been tested on its own.
- **No individual-level claim for any arm.** Every arm sits below the persona-blind leave-one-out
  majority of 73.59% (JC −6.00, BC −8.80, AC −4.27), and all three fail C1.
- **Keep pricing broken out in any future Jev work.** The −9.18 pt accuracy gap on the piped-price
  block is the single largest effect measured here.
- **Contamination applies to both sides.** Twin-2K-500 has been public since 2025 and its tasks are
  classic behavioural-economics replications, so between-arm comparison is fairer than any absolute
  number.
- **Scope.** n=300, one instrument, one model version (`jev-1.13.0`, recorded per cell), binary and
  ordinal only; multi-select is untested and would need one `Noul` per option, the client now has the
  primitive, the scorer has no multi-select path. Using Jev on company
  survey data is a separate governance decision this experiment cannot make, everything here ran on
  Twin-2K-500 (CC BY 4.0) only.

## Next steps

Not run, and deliberately so:

1. **A C3 re-run with `Noul` pre-registered as the elicitation.** NC is post-hoc and cannot carry the
   criterion, but it has moved the interesting question: a registered JC-shaped arm using `Noul` for
   yes/no *and* described `criteria` is now the fair test of Jev against BC, and it needs its
   aggregation rule fixed in advance, that is the whole distance between the two answers NC gives.
2. **The unchained Jev arm that was supposed to exist.** Now that `--chain` gates the walk, an
   unchained run is a genuine second arm rather than a duplicate of JC, and it answers two questions
   at once: whether chaining earns its cost for Jev, and whether "context rot" bites on this state.
   It is also the prerequisite for packing, which only makes sense unchained.
3. **J2 / C2, does Jev read the *individual*?** Prior-answers grounding against the LOO floor. Bring
   back *with* question-packing: unchained, all ~108 questions on one shared state billed once,
   ~$0.45 instead of ~$25. The vendor warns this arm's 20k-token state is where "context rot" bites,
   so validate packed-vs-solo vectors on ~200 cells first, and settle step 2 before relying on the
   packing saving.
4. **An ordinal-only re-test**, since that is the half Jev won. The `Score` primitive is the obvious
   instrument, but the vendor states thresholds do not transfer between primitive types, so it cannot
   be compared to these `Choice` numbers.
5. **`response_mode` into the stateless path**, wanted independently of this result, and now with a
   measured warning attached: asking for probabilities cost 4.4 pt of committed accuracy on the
   stateful path, so a stateless rollout should re-measure that, not assume it.
6. **A walk that commits draws into the history**, rather than the model's own `choice`. Untestable
   offline; the natural follow-up if soft aggregation proves under-dispersed.

## Links

- The criteria this is read against are restated in full at the top of this page. They were
  written down before the Jev runs, in a working plan that is not published because it discusses
  unrelated private surveys; nothing in it beyond those criteria bears on this result.
- Scores in [reports/](reports/): `score_all_arms.json` (JC/BC/AC, the verdict) and
  `score_with_noul.json` (NC/JC/BC, the follow-up); the per-arm JSONL in [runs/](runs/), gzipped,
  including `jev_noul_chained.jsonl`
- The GPT-4.1 arms these are compared against, as run:
  [runs/gpt41_panel_n2058/](runs/gpt41_panel_n2058/) for the respondent-level workbooks,
  `reports/paper_accuracy_full_*.json` for their scores
- [docs/twin2k-grounding-variants.md](docs/twin2k-grounding-variants.md), the arm ladder BC joins as a fourth
  generated config
- [docs/twin2k-paper-vs-our-setting.md](docs/twin2k-paper-vs-our-setting.md), the 108 columns, 16 tasks, and
  the 81.68% human ceiling these arms are read against
- The grounding ladder that explains C1's failure is summarised inline above; see Toubia et al.,
  arXiv 2505.17479 for the dataset's own account of what its holdout is built to measure
- [docs/structured-output-method-failure-modes.md](docs/structured-output-method-failure-modes.md), why
  elicitation format changes answers, the same mechanism as the BC/AC gap
- Code: [`scripts/twin2k/jev_client.py`](scripts/twin2k/jev_client.py),
  [`probe_jev.py`](scripts/twin2k/probe_jev.py),
  [`prob_scoring.py`](scripts/twin2k/prob_scoring.py),
  [`price_sensitivity.py`](scripts/twin2k/price_sensitivity.py)
