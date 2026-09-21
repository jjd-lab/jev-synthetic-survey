# Twin-2K-500 — per-task deep dive, all three arms

Full panel, 2,058 respondents × 108 paper-holdout questions, `gpt-4.1`, temperature 0.7, options
shuffled, between-subject arms gated so each twin is asked only the condition its human was randomized
into. One factor separates the arms:

| arm | grounding | elicitation | export |
|---|---|---|---|
| `baseline` (demographics-only) | 14 demographics | stateless, one call per question | `*_20260904_091556.xlsx` |
| `chained` (demographics-stateful) | 14 demographics | respondent-major, twin sees **its own** running answers | `*_20260904_131620.xlsx` |
| `prior_answers` | 14 demographics **+ the respondent's own 620 past answers** | stateless, matched to `baseline` question for question | `*_20260908_074918.xlsx` |

Sources: `paper_accuracy_full_{arm1,chained,prior_answers}.json`,
`individual_signal_full_{arm1,chained,prior_answers}.json`. Scorer: `scripts/twin2k/paper_accuracy.py`
(the paper's metric — exact match on binary, `1 − |deviation|/range` on ordinal, averaged within column,
then within task, then across 16 equally-weighted tasks).

## Headline

| | `baseline` | `chained` | `prior_answers` | read against |
|---|--:|--:|--:|---|
| Paper accuracy (equal weight, 16 tasks) | 70.26% | 70.04% | **72.92%** | ceiling 81.68%, paper's best twin 71.72%, paper's random floor 59.17% |
| Edge over persona-blind LOO majority | −3.01 | −3.23 | **−0.35** | the majority is 73.27%, identical for all three arms |
| Share of floor→ceiling closed | 49% | 48% | **61%** | |
| Spearman vs human, price-controlled | +0.095 | +0.085 | **+0.107** | raw +0.113 / +0.104 / +0.125 |
| TVD, 65 nominal columns | 0.253 | 0.200 | **0.157** | 0 = identical panels |
| Wasserstein-1, 43 ordinal columns | 0.714 | **0.651** | 0.681 | scale-points, unbounded |
| h_syn/h_hum, nominal / ordinal | 0.445 / 0.678 | **0.592 / 0.701** | 0.535 / 0.639 | 1.0 = twins as varied as humans |
| Collapsed columns | 24 | **16** | 25 | of 108 |
| Blind-spotted columns | 44 | **31** | 40 | of 108 |

**The two levers move different metrics and nothing here buys both.** Prior answers buy accuracy and
pay nothing for diversity (+2.66 pt, collapsed 24 → 25, ordinal h_syn/h_hum *falls* 0.678 → 0.639).
Chaining buys diversity and pays in accuracy (collapsed 24 → 16, blind spots 44 → 31, −0.22 pt). A
crossed `prior_answers` × `chained` cell is the only untested configuration that could buy both, which
weakens the standing argument that the cell is uninteresting.

**No arm carries net individual signal on this metric.** All three sit below a predictor that ignores
the persona entirely. `prior_answers` closes nine tenths of the baseline's deficit and clears the
paper's best published twin by 1.2 pt, but −0.35 is still negative, and 12.5% of the equal weight is
pinned in that arm by construction (mechanism 3).

## The short version, in plain language

Figures here are the `baseline` twin unless marked, because that is the arm a "demographics-only
digital twin" claim is about. Each claim names its task and quotes a question the twins were actually
asked. Where prior answers change the answer, it says so.

### 1. The twin gets about 7 answers in 10 right, but "right" mostly means "gave the popular answer"

> **Anchoring** — QID163: *"Do you think there are more or fewer than 12 African countries in the
> United Nations?"* → `more` / `fewer`

70.7% of humans answered `more`; **100% of twins answered `more`**. Across Anchoring's four questions
the twin never varied, so the task's 78.13% is precisely the average human modal share — arithmetic,
not agreement. It is 78.13% in all three arms, to the digit.

### 2. On 13 of 16 tasks the twin cannot tell one person from another

Only one task ranks individuals correctly, and it works for an unsurprising reason: the 14 demographics
I feed it include party and political views, which really do predict policy opinions. There is no
reason to expect that to carry over to anything else.

> **False consensus** — QID287, a 10-item matrix: *"Would you support or oppose… Placing a tax on
> carbon emissions?"* / *"…A 'Medicare for All' system in which all Americans would get healthcare
> from a government-run plan?"* → 5-point `Strongly oppose` … `Strongly support`

Spearman **+0.456** here, against +0.095 instrument-wide and ≈0 on eight of the other tasks. Prior
answers raise it to +0.476 — they add to an existing signal rather than creating one.

### 3. On questions built to catch people being irrational, the twin's marginal is displaced hard — and not always toward the rational answer

> **Dominator neglect** — QID196: *"…a large tray that contains 100 marbles and a small tray that
> contains 10 marbles… If you draw a black marble you win $2. The small tray contains 1 black marble
> and 9 white marbles, and the large tray contains 8 black marbles and 92 white marbles. From which
> tray would you prefer to select a marble?"* → `the small tray` / `the large tray`

The **small** tray is the better bet (10% against 8%) — humans take it **63.9%** of the time, the
`baseline` twin takes the large tray **94.0%** of the time. Here the twin is the irrational party, and
its 37.95% is below the 50% a coin flip would score. Prior answers repair the direction (62.2% small)
and buy no pairing — mechanism 1.

> **Probability matching** — QID198: *"A deck with 10 cards… 7 cards with the number '1' on the down
> side and 3 cards with the number '2'… predict the number on the down side of the top card… you will
> receive $100 for each downside number you correctly predict"* → `1` / `2`, ten times

Always predicting `1` is optimal, and **100% of twins do exactly that, on all ten shuffles**. Humans
probability-match instead: 7.8% answered `2` on shuffle 1, rising to 23.3% by shuffle 4. Here the twin
is the rational party. Prior answers do not change this; chaining does — mechanism 7.

So the direction of the error is not predictable from the fact that a task measures a bias. Both cases
are systematic, and neither averages out with more respondents.

### 4. The twin is far less varied than real people

On 20 of 108 questions *every single `baseline` twin* gave the identical answer (24 columns are flagged
collapsed, at h_syn/h_hum ≤ 0.30). On the scale questions it avoids the midpoint everywhere and
abandons one end while over-using the other — mechanism 4 has both sides.

> **Outcome bias** — QID161: *"A 55-year-old man had a heart condition… A bypass operation would
> relieve his pain and increase his life expectancy from age 65 to age 70. However, 8% of the people
> who have this operation die from the operation itself. His physician decided to go ahead with the
> operation. The operation succeeded. Evaluate the physician's decision."* → 7 points, `Incorrect, a
> very bad decision` … `Clearly correct, an excellent decision`

| | human | twin |
|---|--:|--:|
| Correct, all things considered | 53.5% | **99.8%** |
| Correct, but the opposite would be reasonable too | 17.7% | 0.0% |
| Clearly correct, an excellent decision | 16.4% | 0.2% |
| The decision and its opposite are equally good | 6.7% | 0.0% |

> **False consensus** — QID287_2: *"…Ensuring 40% of all new clean energy infrastructure development
> spending goes to low-income communities?"*

24.2% of humans picked `Neither oppose nor support`; **4.5% of twins did**.

> **Less is more** — QID171: *"I would find a game that had a 7/36 chance of winning $9 and a 29/36
> chance of winning nothing extremely attractive."* → `Disagree strongly` … `Agree strongly`

`Agree strongly` took 4.2% of humans and **0.0% of twins**; the midpoint took 13.3% and **0.0%**.

### 5. Matching the crowd is not the same as matching the person

> **Absolute vs relative saving** — QID184: *"Imagine that you go to purchase a jacket for $250. The
> salesperson informs you that the jacket you wish to buy is on sale for $240 at the other branch of
> the store which is ten minutes away by car. Would you drive to the other store?"* → `Yes` / `No`

Humans 34.4% `Yes`, twins 35.6% `Yes` — a 1.2-point match, 4th-best of the 65 nominal columns and the
best outside `Pricing`. Person-by-person agreement: Spearman **−0.016**, i.e. nothing. Getting the
aggregate right tells you nothing about whether the right individuals were assigned. The three columns
that fit better are all pricing items (`QID9_20` to within 0.05 of a point), where twin and human share
a randomized price — so every column above this one on distributional fit has a confound.

### 6. The pricing questions look like the twin's best result, but that is the price talking

> **Pricing** — QID9_1: *"Please consider the following product category: Dairy Products… you see the
> following product: Land O Lakes Salted Stick Butter, 16 oz, 4 Sticks. The product is priced at:
> $7.39. Would you or would you not purchase this product?"* → `Yes, I would purchase the product` /
> `No, I would not`

The `$7.39` is the catalog's draw; **the price is randomized per respondent, and each twin was shown
the same price its human saw** — which is the whole problem. Hold price constant and agreement nearly
vanishes: **+0.301 → +0.048** in `baseline`, **+0.325 → +0.069** in `prior_answers`. The twin is also
*more* price-sensitive than its human (+0.610 against +0.438).

### 7. Practical read

Usable for a population's overall split on straightforward attitude questions — the `False consensus`
case. Not usable for predicting what a specific person will do — the jacket question. Not usable at all
on questions designed to elicit a bias — the marbles and the card deck. Prior answers move the first
two a little and the third not at all.

## Every task, all three arms

The leave-one-out majority is computed from the human labels alone, so it is **identical per task in
every arm** — one column, and the three `edge` columns are directly comparable.

| Task | Cols | LOO | `baseline` | edge | `chained` | edge | `prior_answers` | edge |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| Outcome bias | 2 | 84.35 | 84.34 | −0.01 | 83.99 | −0.37 | 84.19 | −0.16 |
| Nonseparability | 8 | 81.53 | 79.51 | −2.02 | 80.30 | −1.23 | 81.38 | −0.15 |
| WTA/WTP (Thaler) | 3 | 80.13 | 78.99 | −1.14 | 79.94 | −0.20 | 79.11 | −1.03 |
| Anchoring | 4 | 78.13 | 78.13 | +0.00 | 78.13 | +0.00 | 78.13 | +0.00 |
| Myside bias | 2 | 79.03 | 73.91 | −5.13 | 71.79 | −7.25 | 77.73 | −1.31 |
| False consensus | 10 | 72.64 | 75.25 | **+2.61** | 73.59 | +0.95 | 76.96 | **+4.31** |
| Probability matching | 16 | 76.16 | 76.16 | +0.00 | 74.57 | −1.59 | 76.16 | +0.00 |
| Asian disease | 2 | 79.95 | 70.40 | −9.55 | 70.66 | −9.29 | 75.94 | −4.00 |
| Linda (conjunction) | 6 | 81.87 | 76.19 | −5.68 | 76.17 | −5.70 | 75.93 | −5.93 |
| Proportion dominance | 6 | 75.56 | 73.05 | −2.50 | 71.24 | −4.32 | 74.92 | −0.64 |
| Less is more | 3 | 57.44 | 67.62 | **+10.18** | 66.50 | **+9.06** | 70.53 | **+13.08** |
| Omission bias | 1 | 71.74 | 69.40 | −2.33 | 68.50 | −3.24 | 69.45 | −2.28 |
| Pricing | 40 | 56.95 | 64.81 | **+7.87** | 65.10 | **+8.15** | 66.03 | **+9.08** |
| Absolute vs relative saving | 2 | 69.67 | 60.63 | −9.04 | 60.53 | −9.14 | 64.47 | −5.20 |
| Allais paradox | 2 | 63.19 | 57.77 | −5.41 | 59.27 | −3.92 | 61.12 | −2.07 |
| Dominator neglect | 1 | 63.95 | 37.95 | −26.00 | 40.38 | −23.57 | 54.71 | −9.23 |
| **ALL 16 TASKS** | **108** | **73.27** | **70.26** | **−3.01** | **70.04** | **−3.23** | **72.92** | **−0.35** |

Only three tasks beat LOO in any arm, and they are the same three in all three arms: `Pricing`,
`Less is more`, `False consensus`. Those three carry the whole of `prior_answers`' +2.66, and the
largest of them by column count is the weakest evidence of individual signal in it (plain-language §6).

### Diagnostics, all three arms

`fit` is TVD for nominal tasks and Wasserstein-1 for ordinal ones, so it is **only comparable down the
rows sharing a bucket** — W₁ is in scale-points and unbounded, TVD is bounded 0–1. Lower is better in
both. `col/bs` is collapsed columns / blind-spotted columns. Spearman is price-controlled.

| Task | Bucket | ρ base | ρ chain | ρ prior | fit base | fit chain | fit prior | h base | h chain | h prior | col/bs base | chain | prior |
|---|:--|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| Absolute vs relative saving | nom | −0.016 | −0.056 | +0.029 | **0.079** | 0.103 | 0.143 | 0.822 | 0.774 | 0.704 | 0/0 | 0/0 | 0/0 |
| Allais paradox | nom | +0.010 | +0.046 | +0.056 | 0.228 | 0.132 | 0.157 | 0.667 | 0.818 | 0.643 | 0/0 | 0/0 | 1/0 |
| Anchoring | nom | — | — | — | 0.219 | 0.219 | 0.219 | 0.000 | 0.000 | 0.000 | 4/4 | 4/4 | 4/4 |
| Dominator neglect | nom | +0.010 | −0.032 | +0.028 | 0.580 | 0.440 | **0.017** | 0.346 | 0.765 | 1.014 | 0/0 | 0/0 | 0/0 |
| Pricing | nom | +0.048 | +0.036 | +0.069 | 0.174 | 0.095 | 0.168 | 0.837 | 0.964 | 0.849 | 0/0 | 0/0 | 0/0 |
| Probability matching | nom | — | — | — | 0.238 | 0.210 | 0.238 | 0.000 | 0.233 | 0.000 | 16/15 | 8/5 | 16/15 |
| Asian disease | ord | −0.040 | +0.003 | −0.002 | 0.578 | 0.653 | 0.481 | 0.768 | 0.825 | 0.741 | 0/1 | 0/1 | 0/1 |
| False consensus | ord | **+0.456** | +0.453 | **+0.476** | 0.381 | 0.499 | 0.429 | 0.920 | 0.932 | 0.913 | 0/1 | 0/0 | 0/1 |
| Less is more | ord | +0.061 | +0.066 | +0.126 | 0.552 | 0.689 | 0.517 | 0.633 | 0.630 | 0.706 | 1/3 | 0/3 | 0/0 |
| Linda (conjunction) | ord | +0.012 | −0.004 | −0.003 | 0.912 | 0.812 | 0.941 | 0.462 | 0.491 | 0.454 | 1/6 | 0/6 | 1/6 |
| Myside bias | ord | +0.190 | +0.185 | +0.195 | 0.367 | **0.304** | 0.603 | 0.992 | 1.041 | 0.745 | 0/0 | 0/0 | 0/1 |
| Nonseparability | ord | +0.096 | +0.081 | +0.132 | 0.820 | 0.713 | 0.754 | 0.561 | 0.561 | 0.497 | 0/7 | 2/5 | 1/7 |
| Omission bias | ord | +0.262 | +0.156 | +0.091 | 0.541 | 0.482 | 0.608 | 0.817 | 0.621 | 0.481 | 0/0 | 0/0 | 0/0 |
| Outcome bias | ord | +0.013 | +0.020 | +0.011 | 0.931 | 0.864 | 0.900 | 0.031 | 0.192 | 0.128 | 2/2 | 2/2 | 2/2 |
| Proportion dominance | ord | +0.145 | +0.135 | +0.224 | 0.619 | 0.363 | 0.503 | 0.929 | 0.995 | 0.954 | 0/3 | 0/3 | 0/1 |
| WTA/WTP (Thaler) | ord | +0.076 | +0.095 | +0.063 | 1.441 | 1.128 | 1.075 | 0.672 | 0.718 | 0.770 | 0/2 | 0/2 | 0/2 |

`Anchoring` and `Probability matching` cannot have a Spearman in `baseline` or `prior_answers` — no
variance to correlate — so 20 of 108 columns and 2 of 16 tasks are outside the ρ means above.

### Three metrics, three different rankings

On `baseline`:

| | best task | worst task |
|---|---|---|
| Accuracy | Outcome bias 84.34% | Dominator neglect 37.95% |
| Distributional fit, nominal (TVD) | Absolute vs relative saving 0.079 | Dominator neglect 0.580 |
| Distributional fit, ordinal (W₁) | Myside bias 0.367 | WTA/WTP 1.441 |
| Individual correlation | False consensus +0.456 | Asian disease −0.040 |

The disagreement is close to an inversion:

- `Absolute vs relative saving` has the best nominal fit (0.079) and sits third from the bottom on
  accuracy with a *negative* correlation. Right crowd, wrong people.
- `Outcome bias` has the best accuracy (84.34%) and one of the poorest ordinal fits (0.931), because
  99.8% of twins pile onto one option of seven — which maximises per-respondent hit rate against a
  53.5% human mode while wrecking the distribution. Its edge over LOO is −0.01, so it earns nothing.
- `False consensus` is the only task in the top third of *all three* columns at once.

`prior_answers` sharpens the inversion rather than resolving it: `Dominator neglect` moves from the
worst nominal fit (0.580) to the **best on the instrument** (0.017) while staying the worst task on both
accuracy (54.71%) and edge (−9.23). Only individual correlation and the LOO edge reliably identify the
tasks that are genuinely working, and they are the two hardest to get.

## Eight mechanisms behind the numbers

### 1. `Dominator neglect` — a sign inversion in two arms, and the instrument's cleanest equifinality case in the third

QID196, one column, n=1,027. The **small** tray strictly dominates: 1 black of 10 = 10%, against the
large tray's 8 of 100 = 8%. Alongside each arm's accuracy is what it would score if its answer carried
no information about which respondent it was (`Σ p_syn(o)·p_hum(o)`):

| | small tray | large tray | accuracy | independence expectation |
|---|--:|--:|--:|--:|
| humans | **63.9%** | 36.1% | — | — |
| `baseline` | 6.0% | **94.0%** | 37.95% | 37.72% |
| `chained` | 20.0% | 80.0% | 40.38% | 41.64% |
| `prior_answers` | **62.2%** | 37.8% | 54.71% | 53.40% |

Two findings, not one. `baseline` and `chained` invert the sign outright — real respondents take the
better tray 2:1 and the twin takes the worse one almost always, which is why 37.95% is below the 50%
a coin flip scores. `prior_answers` *repairs* the direction, landing within 1.7 pt of the human
marginal at TVD 0.017 and h_syn/h_hum 1.014.

But every arm scores its own independence expectation to within ~1.3 pt. So no arm knows *which*
people take the dominated tray, and `prior_answers`' −9.23 is not a wrong location — it is an empty
pairing. More respondents will not help: the aggregate is already right and the deficit is not noise.
A column can pass every distributional check on the sheet and carry nothing; only the LOO edge catches
it.

**Read "random floor" per item, not against the instrument-wide 59.17%.** That figure mixes binary
items (floor 50%) with graded ordinals (floor 58–63%, `1 − ((k²−1)/(3k))/(k−1)`). `Dominator neglect`
is the only task below its own floor. `Allais paradox` at 57.77% is below 59.17 and comfortably above
its own 50%.

**`Allais paradox` goes the other way**, which is why it is not the same finding. The twin
*over*-produces the certainty effect in problem 1 (93.8% take the sure million against 69.2% of humans)
and then takes the 11%-of-one-million in problem 2 (63.9% against 42.8%). That pair is the
expected-utility-consistent combination — the twin does not produce the paradox, the human majority
does.

**This is the finding a headline accuracy number hides.** Where the target is a documented deviation
from rationality, expect the marginal displaced hard in *one* direction and do not assume the direction
is the normative one: it is on `Allais` and `Probability matching`, and it is the opposite on
`Dominator neglect`.

### 2. Perfect aggregate fit with zero individual signal

`Absolute vs relative saving`, QID184, `baseline`:

| | Yes | No |
|---|--:|--:|
| human | 34.4% | 65.6% |
| twin | 35.6% | 64.4% |

A 1.2-point distributional match — TVD 0.079 — and Spearman **−0.016**. The twin reproduces the
marginal and assigns it to the wrong people. Equifinality, on one column, at n=1,027. **This is the
single clearest reason distributional fit cannot stand alone.** `Pricing` is the same story across 40
columns (mechanism 5).

### 3. Collapse is arm-specific, and the flag is a band rather than unanimity

In `baseline`, `Anchoring` (4 columns) and `Probability matching` (16) have h_syn = 0 — every twin gave
the same answer, and it is the human mode. The reported count of 24 is a wider flag,
`entropy_ratio ≤ 0.30` (`COLLAPSE_RATIO_MAX` in `src/validation/response_validator.py`), so 4 further
columns have *some* variety and still under a third of the humans'. Literal unanimity is those 20.

| | human | twin |
|---|--:|--:|
| QID163 "more" | 70.7% | 100.0% |
| QID165 "fewer" | 83.3% | 100.0% |
| QID167 "more" | 93.7% | 100.0% |
| QID169 "less" | 64.8% | 100.0% |

On a collapsed binary column, accuracy *is* the human share of that one answer — `Anchoring`'s 78.13%
is exactly the mean of those four percentages, arithmetic rather than agreement, and its TVD of 0.219
is likewise the mean distance from 100% to those shares.

**Only `Anchoring` is inert across arms — 6.25%, one task of 16.** It reproduces at 78.13% and 4/4
collapsed in all three, so exclude it from cross-arm comparisons. `Probability matching` is pinned in
`baseline` and `prior_answers` — another 6.25%, so 12.5% is pinned *within* either of those arms — but
it is not inert: chaining unpins 8 of its 16 columns (h_syn/h_hum 0.000 → 0.233) at a cost of 1.59 pt.
Keep it in; it is the task that separates the arms. It is also near-unpredictable in principle — the
human retest itself loses to the majority there (−1.74).

`Outcome bias` is the near-miss and the instrument's top-scoring task: h_syn/h_hum 0.031, 99.8% of
twins on one option of seven against a human mode of 53.5%, at Spearman +0.013 and a 0.931 ordinal
distance.

### 4. Center avoidance everywhere, and extremes that are one-sided rather than compressed

The twin refuses the midpoint on every scale, but it does not refuse the extremes — it abandons one end
and piles onto the other. Both ends of the `baseline` twin, so the shape is visible:

| Column | midpoint hum → twin | one end hum → twin | other end hum → twin |
|---|--:|--:|--:|
| QID287_2 (False consensus) | 24.2% → **4.5%** | oppose 8.0% → 1.1% | support 25.6% → **53.0%** |
| QID287_3 (False consensus) | 15.8% → **2.1%** | oppose 10.5% → 7.4% | support 33.7% → **50.1%** |
| QID171 (Less is more) | 13.3% → **0.0%** | agree 4.2% → 0.0% | disagree 43.5% → **87.8%** |
| QID172 (Less is more) | 12.8% → 8.9% | agree 17.4% → **0.4%** | disagree 24.7% → 24.3% |
| QID157 (Asian disease) | — | strong B 3.5% → **0.5%** | strong A 16.5% → 19.3% |

Instrument-wide the midpoint claim is general and the extremes claim is not: over the 26 scales that
have a midpoint the twin takes it 5.5% of the time against the humans' 12.1%, but summed over both ends
it uses an extreme 25.5% against 31.6% — and on 14 of the 43 ordinal columns it uses one *more* than
its humans. By task the split is clean: it barely reaches the ends on judgment items (`Outcome bias`
0.2% vs 12.3%, `Nonseparability` 2.2% vs 22.6%, `WTA/WTP` 4.5% vs 27.7%) and over-reaches on attitude
items (`False consensus` 57.7% vs 46.7%). One average over all 43 would hide both.

This is what drives 44 blind-spotted columns at an ordinal h_syn/h_hum of 0.678: real options that real
respondents choose get essentially no synthetic mass. It barely moves the distributional metric when
the missed option is small — `False consensus` still scores a respectable 0.381 — which is exactly why
blind spot needs its own column.

### 5. Pricing's correlation is the price, not the person

Twin randomizes each product's price per respondent, and the twin sees the same price its human saw.
Decomposing the 40 columns:

| correlation | `baseline` | `prior_answers` |
|---|--:|--:|
| twin vs human, raw | +0.301 | +0.325 |
| twin vs human, price held fixed | **+0.048** | **+0.069** |
| twin vs price | +0.610 | |
| human vs price | +0.438 | |

Six sevenths of the raw correlation is the shared price, and the twin tracks price **harder** than its
human does — a finding about the model's price sensitivity, not about grounding. Pricing is 40 of 108
columns, so this is also what most of the instrument's raw ρ is made of; controlling the price takes
`baseline` from +0.113 to +0.095 and `prior_answers` from +0.125 to +0.107. Pricing's TVD of 0.174 is
genuinely good, which makes it mechanism 2 at scale: good marginals, almost no person-level signal —
and it is the largest single contributor to `prior_answers`' headline gain.

### 6. Accuracy and diversity are bought by different things

The sharpest cross-arm result, and it only became visible once `prior_answers` reached panel scale.
Chaining unpins columns and loses accuracy; prior answers gain accuracy and unpin nothing. The earlier
reading of `chained` — "stateful bought variance, not signal" — has an exact mirror in
`prior_answers`: it bought signal, not variance. Two independent defects, two independent levers, no
arm holding both.

### 7. `Probability matching` isolates that mechanism

16/16 columns collapsed at h_syn/h_hum 0.000 in **both** `baseline` and `prior_answers`. 620 real prior
answers do not make the twin vary across shuffles. Only chaining does (8/16 collapsed, h_ratio 0.233,
−1.59 pt).

Knowing what a person answered before does not stop the model playing the rational optimum. Seeing
*its own* prior answers does. That is a statement about self-consistency pressure, not about grounding
content, and it is why the two levers cannot substitute for each other.

### 8. Where the failure is a blind spot instead of a location or a pairing

`Linda` is the one task no arm improves: −5.68 / −5.70 / −5.93, with 6/6 columns blind-spotted at
h_ratio ≈ 0.45–0.49 in every arm. The twin systematically never produces options humans do choose. The
diagnostic that catches this is the blind-spot flag, not entropy and not distance — Linda's W₁ (0.912
baseline) is bad, but `Absolute vs relative saving` has a far better distance (0.079) and a worse edge
per column (−9.04). Blind spot is reported separately for exactly this reason.

Accuracy and distributional fit stay near-independent throughout: `Outcome bias` posts the highest
accuracy at h_syn/h_hum 0.031, `WTA/WTP` has the worst ordinal fit and the third-highest accuracy. This
reproduces an entropy finding measured earlier on a different survey (entropy × error correlation
0.099) on a different panel and a different metric family, which moves it from a per-run property
toward a general one.

## The one task with real individual signal

`False consensus` (QID287, ten policy-attitude items) is the only task where the twin ranks people:
Spearman **+0.456** in `baseline` rising to **+0.476** with prior answers, per column +0.419 to +0.544,
h_syn/h_hum 0.920, distance 0.381, one blind spot in ten columns, and a positive edge in all three arms.
It is also the task where 14 demographics genuinely carry the answer — `party` and `political_views`
predict policy attitudes — which is the mechanism, and the reason it should not be expected to
generalize to the other 15 tasks. "What fraction of others agree with you" is likewise a direct
function of the attitudes the 620 prior-answer columns encode, so prior answers add to an existing
signal rather than creating one.

Read against it, `Less is more` (67.62%, ρ +0.061) is the opposite case despite a +10.18 edge: what
accuracy it has comes from exaggerating the human mode (87.8% "Disagree strongly" against 43.5%), not
from distinguishing respondents.

## What this constrains

- **12.5% of the equal weight is pinned inside `baseline` and inside `prior_answers`**, and only
  `Anchoring`'s 6.25% is inert across all three arms. That 6.25% is a ceiling on how large any
  cross-arm difference on this instrument can be. Exclude `Anchoring` from cross-arm comparisons; keep
  `Probability matching` in.
- **Aggregate distributional fit is not evidence of individual validity here.** QID184 is the proof on
  one column, Pricing across 40, and `prior_answers`' `Dominator neglect` is the extreme case — best
  fit on the instrument, worst edge on the instrument.
- **Where a task measures a bias, the marginal is displaced hard in one direction and the direction is
  not predictable.** Rational on `Allais` and `Probability matching`, anti-rational on `Dominator
  neglect`. Either way it is a directional error, not variance, and more respondents will not fix it.
- **Report accuracy, distributional fit and correlation together.** On every arm each one alone
  supports a conclusion the other two contradict.

## What this does not show

- **Not comparable to the paper's 71.72% as a like-for-like.** My temperature is 0.7 against their 0,
  options are shuffled against their fixed order, and I enforce a schema where they parse free text.
  The 72.92% > 71.72% ordering is real on this scorer, not evidence of a better twin.
- **No significance test on the arm contrasts.** +2.66 pt is an equal-weight mean over 16 task means,
  and the paired Wilcoxon machinery used at n=50 has not been re-run at panel scale. The n=50 result it
  replaces was indistinguishable from zero; this one is 1.5× the size of the whole `chained` effect and
  moves in the predicted direction, but it is unpinned by a test.
- **Nothing about novel features.** All 108 columns are paper holdout; every task has human ground
  truth. This says nothing about the twin's behaviour on questions no human answered.
- **Unscorable cells are dropped, not counted wrong.** `prior_answers` scores 168,768 pairs and drops
  53,496 (missing, `Error`, or off-list).

Return to [the grounding panel write-up](../../docs/survey/03-grounding-panel.md).
