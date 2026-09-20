# The dataset and the instrument

Everything in this repo runs on Twin-2K-500, a public benchmark for simulating survey respondents
with a language model. This page describes the dataset, the part of it this repo scores, the
ceiling and floor any result has to be read between, and where this setting departs from the one
the dataset's own paper reports.

Twin-2K-500 is CC BY 4.0 (Toubia et al., *Twin-2K-500*,
[arXiv 2505.17479](https://arxiv.org/abs/2505.17479)). It is not redistributed here;
[`scripts/twin2k/fetch_twin2k.py`](../../scripts/twin2k/fetch_twin2k.py) downloads it.

## Who the respondents are

2,058 US adults recruited through Prolific, surveyed across four waves in February 2025. The sample
is not population representative, it is US only, and it has been public since 2025, so any model
evaluated on it may have seen it. Read comparisons between arms, not absolute numbers.

Each respondent's record carries 14 demographic items, which are the only attributes in the data;
the other 746 columns are answers to questions, not facts about the person. The 14 are region of
the United States, sex assigned at birth, age band, highest level of schooling, race or origin, US
citizenship, marital status, religion, frequency of attending religious services, party
identification, family income band, political views, household size, and employment status. They
are the paper's own Appendix A.2 list, and they are what every persona in this repo is built from.

## The four waves

Waves 1 to 3 build the twin. Wave 4 is a retest of the held-out items only, and exists to establish
how often a human reproduces their own earlier answer.

The instrument runs to "over 500 questions". Compressed to the paper's own task groups:

| Group | Content | Questions |
|---|---|---|
| Demographics | 12 items from Santurkar et al. plus household size and employment | 14 |
| Personality traits | Big 5, need for cognition, agentic/communal, minimalism, empathy, green, social desirability, conscientiousness, anxiety, individualism/collectivism, selves, regulatory focus, tightwad/spendthrift, depression, need for uniqueness, self-monitoring, self-concept clarity, need for closure, maximization | 279 |
| Cognitive abilities | cognitive reflection, fluid and crystallized intelligence, syllogisms, over-confidence and over-placement, financial literacy, numeracy, modus ponens, Forward Flow, Wason | 85 |
| Economic preferences | ultimatum game (send and receive), mental accounting, discounting, present bias, risk aversion, loss aversion, trust game (send and receive), dictator game, thought listings | 34 |
| Heuristics and biases, between subject | 11 tasks, each respondent assigned one condition | 16 per respondent |
| Heuristics and biases, within subject | 5 tasks: false consensus, nonseparability of risk and benefit, omission bias, probability matching, dominator neglect | |
| Product preferences | pricing study, 40 binary purchase decisions | 40 |

### Three ways to count the questions, none of them wrong

Mixing them is the source of most confusion about this dataset. The shipped question catalog has
**256 entries**, carrying 246 distinct question ids, the paper describes **about 500 questions**,
and the response CSV has **760 question columns** (761 counting the respondent id). A matrix
question id such as `QID25`, the Big Five battery, is one catalog entry, 44 questions and 44 columns
at once. Entries outnumber ids because ten ids are each used twice, which is its own trap and is
covered below.

## The holdout design

The paper holds out the heuristics-and-biases battery: "We use the responses to the heuristics and
biases questions from waves 1-3 as holdout data, and train the digital twins based on the rest of
the data from waves 1-3." Wave 4 "repeated the within- and between-subject heuristics and biases
experiments from the first three waves as well as the pricing study from wave 3 (88 questions in
total)".

Each respondent's record is split into three files: a **persona** file holding all non-holdout wave
1 to 3 content, an **evaluation** file holding the wave 1 to 3 answers to the held-out items (the
ground truth), and a **retest** file holding the wave 4 answers to those same items, used only for
the human ceiling.

So the holdout set does not have to be inferred. It is exactly the wave 4 instrument, and the wave 4
response file ships with the dataset. It has **126 columns**, with a median of **98 answered per
respondent**, because a respondent sees only one condition of each between-subject task.

Use that file, not the paper's "88", as the operational definition. The paper's question-level
counts are loose in two places. Section 6 says "88 holdout questions (across 177 tasks)" where the
same section and its Figure 2 use **17 tasks**, so 177 is a typo. And 98 columns reconcile to 88
questions only if false consensus, listed in Table 1 as "10 (5-point Likert) + 10 (slider)", is
counted as its 10 underlying policy items rather than its 20 columns.

This repo derives the same partition a second way and asserts the two are equal.
[`build_twin2k_config.py`](../../scripts/twin2k/build_twin2k_config.py) returns every column whose
catalog block sits outside the six persona blocks (Personality, Economic preferences, Economic
preferences intro, Cognitive tests, Forward Flow, Demographics). That is 126 columns, set-equal to
the wave 4 file, checked on every run. One function is then used twice: the config generator asserts
that every scored column is inside the holdout set, and the persona generator excludes exactly that
set. Every scored question is therefore held out, and no scored question is persona material in any
arm.

This is worth one paragraph because it did not start that way. An earlier column-level exclusion
rule left **94 of the 126 holdout columns in the prior-answer persona**: 30 of the 40 pricing
decisions, all 10 false-consensus items, and essentially the whole between-subject battery. No
column-level rule could have reached them, because those are sibling *tasks* of scored questions
rather than sibling columns of one catalog entry. A leak of that kind is invisible in the output. It
reports nothing and only raises the score.

## From 760 columns to the 108 that are scored

Two independent chains run from the same 760 columns, one producing the scored set and one producing
the persona. Their intersection is empty by assertion, in both directions.

**The scored set:**

```
 760  response columns in the wave 1-3 response file (excluding the respondent id)
-634  columns inside the six persona blocks
 126  HOLDOUT, the block complement, asserted set-equal to the wave 4 response file
- 18  no option list the decoder can match
        12 horizontal sliders: 10 false-consensus estimates plus 2 base-rate items
         6 text boxes: 4 anchoring plus 2 sunk cost
 108  SCORED, 65 two-option columns and 43 multi-option columns
        60 ordinary columns, every one answered by all 2,058 respondents
        48 between-subject condition columns at 31 to 51% fill, each respondent in exactly one arm
```

**The persona:**

```
 760  response columns
- 14  Demographics block, which becomes the persona block itself in every arm
-126  HOLDOUT, excluded outright, the paper's own partition
 620  PRIOR-ANSWER columns, mean 552.7 answered per respondent (median 552, min 526, max 589)
```

Both chains sum exactly, and the buckets are disjoint:

| Bucket | Columns | Why |
|---|---:|---|
| Demographics block | 14 | the persona block, every arm |
| Prior answers | 620 | the prior-answers arm only |
| Scored by the run | 108 | holdout, so out of every persona |
| Holdout but unscored | 18 | held out of the persona and past the decoder |
| Low decode rate | 0 | the 0.99 decode-rate floor drops nothing |
| **Total** | **760** | |

481 of the 620 prior-answer columns are answered by all 2,058 respondents.

Ten columns are worth naming because a question catalog keyed by question id cannot reach them.
`QID268` to `QID272` and `QID275` to `QID279` are the belief-bias syllogism items, answered by all
2,058 respondents. The shipped catalog does contain them, and in fact claims all 760 columns; the
problem is that it holds 256 entries under only 246 distinct question ids, and the 10 duplicated ids
are exactly these. Each is used twice by the dataset, once for a syllogism item under `Cognitive
tests` and once for a free-text personality item whose column is the `_TEXT` variant. Any lookup
that keys the catalog by question id keeps one entry and silently drops the other, which is what
makes these columns look absent.

Verified against the shipped dataset on 2026-09-20: 760 CSV columns excluding the respondent id,
every one of them claimed by some catalog entry, and exactly those 10 ids duplicated.

The single filter that cuts 126 down to 108 is **no option list the decoder can match**. Two
experiments are therefore absent entirely rather than partially: base rate, whose arms are both
sliders, and sunk cost, whose arms are both text boxes. Anchoring keeps its more-or-fewer judgment
and loses only its numeric estimate. Fill rate is not a filter: a condition column filled by a third
of the panel is the randomization record, not a defect.

## The 108 scored questions, and the 16 tasks

65 columns have exactly two options; 43 have more than two and carry an ordered scale. No scored
column is multi-select, so the repo's multi-select metrics are unexercised on this instrument.

Sixty columns are asked of everyone. The other 48 belong to 13 between-subject groups and are asked
only of the arm each respondent was randomized into. Averaged into tasks the way the paper
aggregates its 17, the scored set spans **16 tasks**: nonseparability's benefits and risks halves
count once, as do anchoring's two scenarios and proportion dominance's two problems.

The full column-by-column inventory is the
[question inventory appendix](../appendix-question-inventory.md).

### Between-subject arms, and what per-arm numbers cannot say

Each respondent was randomized into exactly one arm of each of the 13 groups, so each arm's columns
are filled by 31.6 to 51.3% of the panel. A simulated respondent is asked **the same arm its human
counterpart saw**. Asking both arms would turn a between-subject manipulation into a within-subject
one and erase the effect being measured.

**The assignment is read from the presence of a filled column, never from its content, and that
bound is the whole design.** The survey software left no assignment variable in the data, so which
arm a respondent saw survives only as which columns they answered. Reading presence is not leakage;
reading the answer would be.

Two limits follow, and they are reasons to read these 48 columns differently rather than caveats to
skim.

- **Per-arm fit is not the framing effect, and cannot detect a model that ignores the frame.** Real
  humans favor the certain program **71.9%** of the time in the gain frame against **36.3%** in the
  loss frame, an effect of 35.6 percentage points, an arm-to-arm distribution gap of 0.356. A
  simulated respondent that ignores the frame and answers the pooled human distribution in both arms
  scores a distribution gap of **0.182 and 0.173**, unremarkable beside the rest of a run, while
  reproducing **none** of the effect. No contrast metric is shipped, so the arm pairs have to be read
  side by side.
- **At small samples the guardrails are absent, not passing.** An arm draws roughly 16 to 25
  respondents out of 50, below the floor at which the collapse and blind-spot flags are computed at
  all, so those flags read as "not computed" rather than "clear" on all 48 columns.

### The pricing block is piped text, and that nearly broke it

The 40 pricing columns are the largest task in the scored set. Their price is **randomized per
respondent** by the survey software, and the shipped question catalog is a single rendered
instrument that holds one arbitrary draw.

Measured over 294 respondents by 40 products, 11,760 cells: each product carries **161 to 197
distinct prices**, and only **0.757%** of cells (89 of 11,760) ever saw the catalog's price. Asked
at that one catalog price the 40 products are statistically indistinguishable, with yes-rates of
40.4 to 45.3%, a chi-squared p of 0.25 and a correlation with catalog price of +0.099 at p = 0.54.
Asked at the price the respondent actually saw, the correlation is **−0.356** and the yes-rate runs
**75.8% down to 16.4%** across price quintiles. Rendering the catalog's draw made the largest task in
the scored set carry no learnable signal at all, and put its 83.89% human ceiling out of reach in
principle.

The fix is per-respondent question text rather than a per-respondent persona: the generator rewrites
each pricing stem's price to a token, and the preprocessor substitutes each respondent's own price.
Two properties of the source data make the recovery exact rather than approximate, and both are
asserted at load time. The price is identical between the wave 4 question text and the wave 1 to 3
question text (100% of 11,760 cells), so pairing wave 4 question text with wave 1 to 3 answers is
sound; and the per-respondent file's wave 1 to 3 answers equal the label file's cells exactly
(100%), so the join is the right join. Nothing else in the holdout is piped.

**Any scorecard produced before this token existed understates pricing and is not comparable to one
produced after it.** This is a scorecard-invalidating change, not an additive one.

## The ceiling: humans reproduce themselves 81.68% of the time

The paper reports a human test-retest ceiling of **81.72%** across its 17 tasks. Recomputed with the
paper's own formula (exact match for two-option items, `1 − |deviation| / range` otherwise, averaged
within a column, then within a task, then across equally weighted tasks) on the wave 1 to 3 answers
against the wave 4 answers, over exactly the 108 scored columns, it is **81.68% across the 16
tasks** used here. That is 0.04 points from the paper's figure, so the scored set does not sit at an
easier or harder point of the instrument than the set the paper reports on.

| Task | retest | Task | retest |
|---|---:|---|---:|
| WTA/WTP (Thaler) | 89.18% | Omission bias | 80.58% |
| False consensus | 87.44% | Asian disease | 80.28% |
| Nonseparability (both halves) | 86.32% | Absolute vs relative saving | 79.15% |
| Outcome bias | 86.29% | Less is more | 77.10% |
| Proportion dominance | 86.15% | Probability matching | 74.42% |
| Myside bias | 84.56% | Allais paradox | 73.99% |
| Pricing | 83.89% | Dominator neglect | 72.16% |
| Anchoring | 82.93% | | |
| Linda (conjunction) | 82.41% | **Equal weight across 16** | **81.68%** |

Read the per-task column before reading any per-task score of a model. A simulated respondent cannot
be held to 100% on dominator neglect when the same humans reproduce themselves 72.16% of the time,
and the 16 ceilings span 17 points, so one flat threshold across tasks would be a different standard
on each.

The 60 always-asked columns average **82.78%**, so the between-subject experiments are the harder
half. Every one of the 60 pairs across all 2,058 respondents. The 48 condition columns pair at
**100%** as well, because wave 4 re-ran each respondent in the arm they were originally assigned, so
no arm-switch pairs exist and each condition column rests on 651 to 1,056 pairs. That is independent
confirmation that presence really is the randomization record.

## The floor: a leave-one-out majority that never looks at the person

The other reference point is a predictor that ignores the persona entirely and answers each column
with the modal label of the *other* respondents. On this instrument it scores **73.27%** over the
full 2,058-respondent panel and **73.59%** over the 300-respondent slice used in the model
comparison. The human ceiling beats the same floor by **+8.41 points**, so that is how much headroom
real individual signal is worth on this metric. The definition and the reason for the leave-one-out
form are on the [metrics page](02-metrics.md).

## How this setting differs from the paper's

| Axis | The paper | This repo | Consequence |
|---|---|---|---|
| Grounding content | full non-holdout wave 1 to 3 record | 14 demographics, or those plus all 620 remaining columns | matched at the top rung: nothing a respondent answered is excluded except the paper's own holdout |
| Holdout partition | task level, three-file split | task level, the same 126 columns, asserted both ways | matched |
| Question rendering | each respondent's own instrument, so piped values are theirs | one shared mapping plus a per-respondent price token | matched where it matters |
| Call granularity | one call per respondent, all items in one context | one call per respondent and question | the paper's twin can be internally consistent across items and carry inferences forward; its answers are also mutually dependent in a way these are not |
| Option order | never shuffled | shuffled per persona, no option pinned | deliberate divergence: the paper's own cited reason is that order moves answers, so this repo randomizes it away rather than inheriting it |
| Temperature | 0 for every arm but one | 0.7 | priced by the paper's own arm at about 0.5 points |
| Model | GPT-4.1-mini in the best arm | `azure/gpt-4.1` | the one clean pair in the table below, JSON Persona on each model, puts GPT-4.1 0.57 points above the mini, so this pushes the other way |
| Answer format | free-text JSON, parsed and retried | provider-enforced schema | fewer parse losses here; no measurable accuracy claim either way |
| Reasoning | an arm, costing 1.3 points | always on, never scored | untested here; the paper's evidence says it does not help |
| Metric | exact match or graded deviation, averaged within then across 17 equally weighted tasks | distribution gaps, calibration, Brier, plus the paper's accuracy as a side-by-side | most numbers here are not on the paper's scale |
| Items | 88 holdout questions across 17 tasks, on the paper's own count, which is loose (see above) | 108 holdout columns across 16 tasks | everything in the holdout the decoder can read, including the between-subject arms |
| Condition assignment | each respondent's own instrument carries their arm | derived from which arm's columns their answer sheet fills | matched |

For reference, the paper's published arms:

| Arm | Accuracy |
|---|---|
| Human test-retest (ceiling) | 81.72% |
| Text Persona and GPT-4.1-mini | **71.72%** |
| Text Persona (default temperature 0.7) and GPT-4.1-mini | 71.24% |
| JSON Persona (predicted output) and GPT-4.1 | 71.92% |
| JSON Persona and GPT-4.1 | 71.05% |
| Text Persona (repeating questions) | 70.45% |
| Text Persona (reasoning) | 70.39% |
| JSON Persona and GPT-4.1-mini | 70.48% |
| LLM finetuning (500 samples) | 69.61% |
| Text Persona and Gemini-flash2.5 | 69.40% |
| Persona Summary and GPT-4.1-mini | 68.02% |
| Random guessing (floor) | 59.17% |

The demographics-only rung that the baseline arm here occupies has **no published accuracy
anywhere**. The dataset's own HuggingFace repository ships 13 arm folders including a demographics
only arm, which is absent from the paper's table and is the only folder with no accuracy evaluation.
Its responses do ship, so the number is computable by anyone who wants it.

### What is and is not comparable

- **The distributional numbers in this repo are not comparable to 71.72%.** Different metric,
  different item set, different sample size. Read arm against arm. The one number that *is* on the
  paper's scale is the accuracy metric reproduced in
  [`paper_accuracy.py`](../../scripts/twin2k/paper_accuracy.py), and even there the item set and
  sample differ.
- **No result predating the per-respondent price token is comparable to one after it.**
- **No prior-answers result predating the current persona is comparable to one after it.** That
  arm's persona grew from 322 to 480 to 620 answers, and from 12.5k to 19.3k to roughly 22.1k
  tokens, across two changes. The two demographics arms read a different mapping file and are
  untouched.
- **Report per task, never pooled.** 40 of the 108 columns are the pricing study, so a pooled figure
  is dominated by one experiment. See the [metrics page](02-metrics.md).

## Where to go next

- [02 Metrics](02-metrics.md): every measure used here, defined once.
- [03 Grounding panel](03-grounding-panel.md): what persona content is worth, measured on all 2,058
  respondents.
- [Question inventory](../appendix-question-inventory.md): all 108 columns, all 16 tasks.
- [`runs/README.md`](../../runs/README.md) and [`reports/README.md`](../../reports/README.md): the
  artifacts and the commands that regenerate them.
- Toubia et al., *Twin-2K-500*, [arXiv 2505.17479](https://arxiv.org/abs/2505.17479): waves,
  accuracy, the three-file split, the instrument table and the prompts.
- Peng et al., *Funhouse Mirrors*, [arXiv 2509.19088](https://arxiv.org/abs/2509.19088): the
  follow-up measuring twins at an average correlation of 0.20 across 164 outcomes.
