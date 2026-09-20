# Appendix: the question inventory

Every column this repo scores, the task it belongs to, and how many options it offers. Background on
where these 108 columns come from, and on the 18 holdout columns that are not scored, is in
[01 Dataset and instrument](survey/01-dataset-and-instrument.md).

Two facts frame the whole table:

- **40 of the 108 columns are one task**, the pricing study. That is why every figure in this repo
  is averaged within a task and then across equally weighted tasks, never pooled over columns. See
  [02 Metrics](survey/02-metrics.md).
- **60 columns are asked of everyone; the other 48 belong to 13 between-subject groups**, and each
  respondent sees exactly one arm of each group. A simulated respondent is asked the same arm its
  human counterpart saw.

## The 108 columns and the 16 tasks

Nineteen groups of columns, merged into 16 scored tasks the way the dataset's paper aggregates its
17: nonseparability's benefits and risks halves count once, anchoring's two scenarios count once, and
proportion dominance's two problems count once.

| Group | Column ids | Columns | Options | Scored task | Asked of |
|---|---|---:|---|---|---|
| Product preferences, pricing | `QID9_1` to `QID9_40` | 40 | two-option | Pricing | everyone |
| False consensus support | `QID287_1` to `_7`, `_10` to `_12` | 10 | multi-option (5-point) | False consensus | everyone |
| Nonseparability, benefits | `QID288_1` to `_4` | 4 | multi-option (7-point) | Nonseparability | everyone |
| Nonseparability, risks | `QID289_1` to `_4` | 4 | multi-option (7-point) | Nonseparability | everyone |
| Dominator neglect | `QID196` | 1 | two-option | Dominator neglect | everyone |
| Omission bias | `QID291` | 1 | multi-option (4 options) | Omission bias | everyone |
| Asian disease (framing) | `QID157` / `QID158` | 2 | multi-option | Asian disease | one of 2 arms |
| Outcome bias | `QID161` / `QID162` | 2 | multi-option | Outcome bias | one of 2 arms |
| Anchoring, African countries | `QID163` / `QID165` | 2 | two-option | Anchoring | one of 2 arms |
| Anchoring, redwood | `QID167` / `QID169` | 2 | two-option | Anchoring | one of 2 arms |
| Absolute vs relative saving | `QID183` / `QID184` | 2 | two-option | Absolute vs relative saving | one of 2 arms |
| Allais paradox | `QID192` / `QID193` | 2 | two-option | Allais paradox | one of 2 arms |
| Myside bias | `QID194` / `QID195` | 2 | multi-option | Myside bias | one of 2 arms |
| Less is more | `QID171` to `QID173` | 3 | multi-option | Less is more | one of 3 arms |
| Proportion dominance, problem 1 | `QID174` to `QID176` | 3 | multi-option | Proportion dominance | one of 3 arms |
| Proportion dominance, problem 2 | `QID177` to `QID179` | 3 | multi-option | Proportion dominance | one of 3 arms |
| WTA/WTP (Thaler) | `QID189` to `QID191` | 3 | multi-option | WTA/WTP (Thaler) | one of 3 arms |
| Linda (conjunction fallacy) | `QID159_1` to `_3` / `QID160_1` to `_3` | 6 | multi-option | Linda (conjunction fallacy) | one of 2 arms |
| Probability matching | `QID198_1` to `_10` / `QID203_1` to `_6` | 16 | two-option | Probability matching | one of 2 arms |
| **Total** | | **108** | 65 two-option, 43 multi-option | **16 tasks** | 60 everyone, 48 condition |

Every one of the 108 is a holdout column, present in the dataset's wave 4 response file, so a
"holdout" column in an earlier version of this table would have read yes 108 times.

## Two-option and multi-option

The split is exact and was verified against the run files rather than assumed. The ordered-scale flag
is true on precisely the 43 columns with more than two options, so "65 nominal", "65 binary" and "the
65 two-option columns" all name one set, and "43 ordinal", "43 multiclass" and "the 43 multi-option
columns" name the other.

| | Columns | Which groups |
|---|---:|---|
| **two-option** | 65 | Pricing (40), Probability matching (16), both anchoring scenarios (4), Allais (2), Absolute vs relative saving (2), Dominator neglect (1) |
| **multi-option** | 43 | False consensus (10), Linda (6), both nonseparability halves (8), both proportion dominance problems (6), Less is more (3), WTA/WTP (3), Asian disease (2), Outcome bias (2), Myside bias (2), Omission bias (1) |

Option counts across the 43 multi-option columns: 5 options on 16 columns, 6 on 13, 7 on 10, 10 on 3,
and 4 on 1.

**Multi-option means one answer out of more than two, not more than one answer.** No scored column in
this instrument is multi-select, so the repo's multi-select metrics are unexercised here.

## The pricing block: `QID9_1` to `QID9_40`

The 40 pricing columns are one task and 37% of the scored columns, which is the single strongest
reason for the equal-weight-per-task rule.

Every one is the same two-option stem over a different product: "Please consider the following
product category: ... you see the following product ...: Land O Lakes Salted Stick Butter, 16 oz, 4
Sticks. The product is priced at: $X. Would you or would you not purchase this product?", with
options "Yes, I would purchase the product" and "No, I would not purchase the product". Forty
distinct product categories, each with its own price.

**The price is piped per respondent.** It is randomized per person and per product, spanning **$0.00
to $59.98** across respondents, so the task runs from obvious buys to obvious refusals. Each product
carries 161 to 197 distinct prices across the panel, and the shipped question catalog holds one
arbitrary draw that only 0.757% of cells ever saw. Any result produced before the pipeline
substituted each respondent's own price is not comparable to one produced after; the measurement and
the fix are in [01 Dataset and instrument](survey/01-dataset-and-instrument.md).

The per-product stems and prices live in
[`configs/twin2k/twin2k_question_mapping.json`](../configs/twin2k/twin2k_question_mapping.json).

## The 60 always-asked columns, question by question

These are the columns answered by all 2,058 respondents. Options are shuffled per persona except on
rating scales, where the scale keeps its order.

| Column | Task | Stem | Options | Ordered |
|---|---|---|---|:-:|
| `QID9_1` to `QID9_40` | pricing study | 40 product categories, each with a per-respondent price | Yes, I would purchase the product / No, I would not purchase the product | no |
| `QID196` | dominator neglect | two trays of marbles, 100 against 10, draw a white marble to win | the small tray / the large tray | no |
| `QID291` | omission bias | a deadly flu with a 10% chance of dying, and a vaccine carrying a 5% risk of a weaker flu | definitely not take / probably not take / probably take / definitely take, each with its consequence clause | yes |
| `QID287_1` | false consensus | "Would you support or oppose ... Placing a tax on carbon emissions?" | Strongly oppose / Somewhat oppose / Neither oppose nor support / Somewhat support / Strongly support | yes |
| `QID287_2` | false consensus | "... Ensuring 40% of all new clean energy infrastructure development spending goes to low-income communities?" | same 5-point scale | yes |
| `QID287_3` | false consensus | "... Federal investments to ensure a carbon-pollution free electricity sector by 2035?" | same 5-point scale | yes |
| `QID287_4` | false consensus | "... A 'Medicare for All' system in which all Americans would get healthcare from a government-run plan?" | same 5-point scale | yes |
| `QID287_5` | false consensus | "... A 'public option', which would allow Americans to buy into a government-run healthcare plan if they choose to do so?" | same 5-point scale | yes |
| `QID287_6` | false consensus | "... Immigration reforms that would provide a path to U.S. citizenship for undocumented immigrants currently in the United States?" | same 5-point scale | yes |
| `QID287_7` | false consensus | "... A law that requires companies to provide paid family leave for parents?" | same 5-point scale | yes |
| `QID287_10` | false consensus | "... A 2% tax on the assets of individuals with a net worth of more than $50 million?" | same 5-point scale | yes |
| `QID287_11` | false consensus | "... Increasing deportations for those in the US illegally?" | same 5-point scale | yes |
| `QID287_12` | false consensus | "... Offering seniors healthcare vouchers to purchase private healthcare plans in place of traditional medicare coverage?" | same 5-point scale | yes |
| `QID288_1` to `_4` | nonseparability, benefits | "Please rate the following technology or products from 'not at all beneficial' to 'extremely beneficial'": bicycles, alcoholic beverages, chemical plants, pesticides | not at all beneficial / low benefit / slightly beneficial / neutral / moderately beneficial / very beneficial / extremely beneficial | yes |
| `QID289_1` to `_4` | nonseparability, risks | the same four technologies, rated "not at all risky" to "extremely risky" | not at all risky / low risk / slightly risky / neutral / moderately risky / very risky / extremely risky | yes |

The benefits and risks halves are held out and scored together because the measure the task extracts
is the correlation between them.

## The 48 between-subject condition columns

The remaining 48 columns are the 13 between-subject groups listed in the main table. Their stems live
in [`configs/twin2k/twin2k_question_mapping.json`](../configs/twin2k/twin2k_question_mapping.json),
tagged with a condition group and a condition arm.

Each arm's columns are filled by **31.6 to 51.3%** of the panel, because each respondent was
randomized into exactly one arm. That is not missing data: **presence is the randomization record**,
since the survey software left no assignment variable behind. The expected number of valid responses
on one of these columns is the arm's share of the panel, where on the 60 always-asked columns it is
the whole sample.

Two limits on reading them, expanded in
[01 Dataset and instrument](survey/01-dataset-and-instrument.md): per-arm fit is not the framing
effect and cannot detect a model that ignores the manipulation, and below 50 valid respondents per
column the collapse and blind-spot flags are not computed at all.

## The 18 holdout columns that are not scored

The holdout set is 126 columns. One filter cuts it to 108: **no option list the decoder can match.**

| Type | Columns | Which |
|---|---:|---|
| horizontal slider | 12 | `QID290` times 10, the false-consensus estimates, plus `QID154` and `QID156`, base rate |
| single-line text box | 6 | `QID164`, `QID166`, `QID168`, `QID170` (anchoring) plus `QID181`, `QID182` (sunk cost) |

Two experiments are therefore absent entirely rather than partially: **base rate**, whose arms are
both sliders, and **sunk cost**, whose arms are both text boxes. **Anchoring** keeps its
more-or-fewer judgment and loses only its numeric estimate. The 10 false-consensus sliders are fully
answered and otherwise ideal; they are out only because a slider has no option list.

## Quirks worth knowing before reading a per-column number

- **`QID287` is numbered 1 to 7 and 10 to 12.** There is no `_8` or `_9`. Matrix rows are therefore
  resolved by column name rather than by position; positionally, `_10` would have taken `_12`'s label
  and three questions would have been scored against the wrong ground truth.
- **`QID198`'s two options are literally the labels `1` and `2`**, so its prompt reads "1. 1 / 2. 2"
  and its stored cells arrive as floats before being cast back to strings. Read the first responses
  on that task for confusion before trusting it.
- **`QID158` ships with two typos in the dataset** ("nobody people will die", "600 people be die").
  Stems are copied verbatim on purpose: editing one would score a simulated respondent on a question
  no human was asked.
- **Rating-scale items share a stem and differ only in the row label**, and option shuffling is off
  for every one of them, so the scale keeps its order.
- **Every answer in the scored set decodes to a real option**, asserted at generation time. On the 60
  always-asked columns, a valid-response count below the sample size is therefore an unambiguous
  content-filter diagnostic and never missing ground truth.

## Questions that were dropped, and why the reasons differ

An earlier 21-question set included seven columns that are not holdout. They came out for two
unrelated reasons, and the natural reading, that they all failed the same test, is wrong.

- **`QID25_1` to `QID25_4`, four Big Five items, were a leak.** One catalog entry holds 44 Big Five
  columns and the run scored 4, so the prior-answers persona kept 40 same-battery items that
  essentially determine the trait. That is not a metric problem, it is a copy test.
- **`QID221`, `QID126` and `QID128` were dropped on instrument grounds, not leakage.** `QID126` and
  `QID128` carry an empty question text in the catalog, and they are not alone: 20 entries do, the
  whole Beck Depression Inventory battery, whose shared instruction lives in a separate descriptive
  block that produces no data column. A scored item from that battery therefore needs a stem
  transcribed by hand. `QID221` is the Wason selection task, a cognitive test with a *correct*
  answer, so simulating it measures reasoning rather than preference, which is not what a
  response-distribution metric is for.
- **Restoring the multi-select bucket from those three now costs a leak, which it did not before.**
  All 84 checkbox columns are non-holdout and every one of them is now in the prior-answers persona,
  so scoring one of them while its sibling columns sit in the prompt is the same copy test the Big
  Five items failed. Any restoration has to remove the scored columns' own siblings from the persona
  first.

One flag this list used to raise is settled by measurement: `QID126` and `QID128` are typed as
multi-select here although their stem says "pick out the **one** statement", and 121 plus 13 and 141
plus 50 of the 2,058 respondents select more than one. Multi-select was the right type, and retyping
them to single choice would have truncated real answers.
