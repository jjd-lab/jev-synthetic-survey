# Twin-2K-500 — the paper's experimental setting vs ours

## Question

[`configs/twin2k/`](../configs/twin2k/) holds four runs, one of which
([twin2k-grounding-variants.md](twin2k-grounding-variants.md)) is labelled the paper's published
"Text Persona" twin at 71.72%. Judging that label needs the paper's setting stated at the same
resolution as ours: which items it holds out, how the persona and the question reach the model, how an
answer is elicited, and how accuracy is computed. This page is that statement, plus the difference
list.

Sources: Toubia et al., *Twin-2K-500*, arXiv 2505.17479 (local copy `data/open mind/twin-2k-500.pdf`);
the authors' own simulation code, `tianyipeng-lab/Digital-Twin-Simulation`, directory
`text_simulation/`; and the dataset's shipped `question_catalog.json`, `wave1_3_response_label.csv`
and `wave4_response_label.csv`.

**Our partition is now the paper's own, and it is asserted rather than trusted.** Every scored column
is holdout and every holdout column is out of the persona, checked twice over at generation time (§The
holdout split, §What each arm's persona holds). It did not start that way: an earlier column-level
exclusion rule left 94 of the 126 holdout columns in the prior-answer persona, which is worth one
sentence here because the failure is invisible — a leak of that kind raises scores and reports nothing.

## Instrument and sample

2,058 respondents, four waves, "over 500 questions" (Table 1). Waves 1–3 build the twin; wave 4 is a
retest of the holdout items only, and exists to establish the human test–retest ceiling.

Paper Table 1, compressed to task groups:

| Group | Content | Questions |
|---|---|---|
| Demographics | 12 Santurkar et al. items + household size, employment | 14 |
| Personality traits | Big 5 (44), need for cognition (18), agentic/communal (24), minimalism (12), empathy (20), green (6), social desirability (13), conscientiousness w2 (8), anxiety (21), individualism/collectivism (16), selves (3), regulatory focus (10), tightwad/spendthrift (4), depression (22), need for uniqueness (12), self-monitoring (13), self-concept clarity (12), need for closure (15), maximization (6) | 279 |
| Cognitive abilities | CRT, fluid/crystallized intelligence, syllogisms, over-confidence/-placement, financial literacy, numeracy, modus ponens, Forward Flow (20), Wason | 85 |
| Economic preferences | ultimatum (send/receive), mental accounting, discount, present bias, risk aversion, loss aversion, trust (send/receive), dictator, thought listings | 34 |
| Heuristics and biases — between subject | 11 tasks, each respondent assigned one condition | 16 per respondent |
| Heuristics and biases — within subject | 5 tasks: false consensus, nonseparability of risk/benefit, omission bias, probability matching, dominator neglect | — |
| Product preferences | pricing study, 40 binary purchase decisions | 40 |

Three counting levels do not agree, and mixing them is the source of most confusion here: the catalog
has **256 QuestionIDs**, the paper describes **~500 questions**, and the response CSV has **760
question columns** (761 with `pid`). A matrix QuestionID such as `QID25` (Big Five) is one catalog
entry, 44 questions, and 44 columns.

## The holdout split

The paper: "We use the responses to the heuristics and biases questions from waves 1-3 as holdout
data, and train the digital twins based on the rest of the data from waves 1-3." Wave 4 "repeated the
within- and between-subject heuristics and biases experiments from the first three waves as well as
the pricing study from wave 3 (88 questions in total)". Each respondent's record is partitioned into
three files — **Persona JSON** (all non-holdout wave 1–3 content), **Evaluation answer-block JSON**
(wave 1–3 answers to holdout items, the ground truth), and **Retest answer-block JSON** (wave 4
answers to the same items, used only for the test–retest ceiling).

So the holdout set is not a matter of inference: it is exactly the wave-4 instrument, and
`wave4_response_label.csv` ships. It has **126 columns** spanning precisely the Table 1 experiment
groups — 40 pricing, 20 non-experimental H&B, 10 false consensus, 56 between-subject experiment
columns across both conditions of each task — with a median of **98 answered per respondent** (a
respondent sees one condition per between-subject task).

Use the wave-4 file, not the paper's "88", as the operational definition. The paper's question-level
counts are loose in two places: §6 says "88 holdout questions (across 177 tasks)" where §6 itself and
Figure 2 use **17 tasks** (11 between-subject + 5 within-subject + 1 pricing), so 177 is a typo; and
98 columns reconcile to 88 questions only if false consensus, which Table 1 lists as "10 (5-point
Likert)+10 (slider)", is counted as its 10 underlying policy items rather than its 20 columns.

**Our side uses the same partition, derived a second way and asserted equal to the first.**
[`build_twin2k_config.py`](../scripts/twin2k/build_twin2k_config.py)'s `holdout_columns()` returns
every column whose catalog `BlockName` is outside the six persona blocks (`Personality`,
`Economic preferences`, `Economic preferences - intro`, `Cognitive tests`, `Forward Flow`,
`Demographics`) — 126 columns, **set-equal to `wave4_response_label.csv`**, which
[`build_twin2k_persona.py`](../scripts/twin2k/build_twin2k_persona.py) checks on every run. That one
function is used twice: the config generator asserts every *scored* column is inside the set, the
persona generator excludes exactly the set. All 108 scored questions are therefore holdout and none is
persona material in any arm, so there is no scored subset to keep apart from another.

The block names carry the partition but do not explain it. `Non-experimental heuristics and biases`
(`QID196`, `QID288`–`QID291`) and `False consensus` (`QID287`) are holdout because the within-subject
heuristics-and-biases experiments were repeated in wave 4; each between-subject condition is its own
one-entry block (`Allais Form 1`, `Sunk cost - yes`, …), which is why 37 of the catalog's 43 blocks are
holdout and only 6 are persona. `QID288` is the *benefits* half of Stanovich & West's nonseparability task and `QID289`
the *risks* half; the extracted measure is the correlation between them, so both halves are held out
together.

## What each arm's persona holds

The dataset has 760 response columns and the baseline persona carries 14, which looks like severe
under-use until the 14 are identified: they are the catalog's entire `Demographics` block,
`QID11`–`QID24`, which is exactly the Appendix A.2 list reproduced below. The other **746 columns are
responses, not attributes**. Carrying only the 14 is not a subset of a richer persona that got
truncated — it is the demographics-only rung of the grounding ladder, which is the level the baseline
arm exists to measure and the one the paper ships responses for but publishes no accuracy for.

The `_prior_answers` arm raises the persona to 634 mapping entries: the same 14 plus **620**
prior-answer `screener` columns, **552.7 of them answered by the average respondent** (median 552, min
526, max 589; 481 of the 620 columns are answered by all 2,058). **No column that a respondent answered
and the paper did not hold out reaches no prompt** — 620 is the whole remaining universe:

| Bucket | Columns | Why |
|---|---:|---|
| `Demographics` block (`QID11`–`QID24`) | 14 | the persona block, every arm |
| Prior-answer screeners | 620 | `_prior_answers` arm only; 158 `Bipolar` price lists rendered by splitting their row label, 84 `MAVR`/`MAHR` checkbox columns as identity-mapped single columns, 56 `FORM`/`SL`/`ML` as `free_text` |
| Scored by the run | 108 | holdout, so out of every persona |
| Holdout but unscored | 18 | 12 `HSLIDER` + 6 `SL` — held out of the persona *and* past the decoder |
| Low decode rate | 0 | `MIN_DECODE_RATE = 0.99` drops nothing; its former casualties were all holdout |
| **Total** | **760** | |

The buckets are disjoint and sum exactly, and they reproduce the generator's own console line —
`candidate prior-answer columns: 620` / `kept 620`. Every selector in the catalog now has a branch, and
an unrecognized one is fatal rather than a silent skip, so a dataset revision cannot shrink the persona
unnoticed. Nothing is counted twice between the persona block and the screeners: the demographic mapping
is keyed by the CSV column itself, with `demographic_key` carrying the persona field name, so excluding
`set(demographics)` really does exclude those columns.

Two mechanics carry the 140 columns that used to be skipped by selector, and neither needed a change to
how the persona is *rendered*:

- **The 84 `MAVR`/`MAHR` checkbox columns** (20 Beck Depression Inventory groups + the Wason card task)
  are ordinary single-column screeners with an identity `choices` map, **not** `is_multi_select`. A
  checked box stores the option's own label text and an unchecked one stores `NaN`, so the single-choice
  branch decodes the first and skips the second silently — only the boxes the respondent actually checked
  reach the prompt, which is the right reading of "select each that applies". 23.1 checked boxes per
  respondent. `is_multi_select`'s `== 1` test belongs to the coded format Twin's `data_format: text`
  never produces.
- **The 56 `FORM`/`SL`/`ML` free-text columns** carry `free_text: true`, and
  `extract_screener_profile` renders the cell as written — the same mechanism `extract_demographics`
  already used for age/state/zipcode. Their cardinality (2,058 distinct self-description essays) rules
  out enumerating them into `choices`. The flag is explicit rather than inferred from an empty `choices`
  because grid screeners also have empty `choices`, so an inferred test would make
  their meaning depend on branch order.

The 10 catalog-less columns are worth naming because no rule can reach them: `QID268`–`QID272` and
`QID275`–`QID279` are the belief-bias syllogism items ("that it is certain that the glock is a YOF"),
answered by all 2,058 respondents, but absent from `question_catalog.json` — so `holdout_columns()`
cannot classify them either and they appear in no skip counter. They are the gap between 760 CSV columns
and everything the catalog walk accounts for. `QID273`/`QID274`, which the range spans, *are* catalogued
`Cognitive tests` items and are ordinary screeners.

### The two funnels

Two independent chains from the same 760 columns. They used to be one chain, when the scored set was
chosen for metric-bucket coverage and then intersected with the holdout; now each is derived from the
partition and the intersection is empty by assertion.

**A — the scored set** ([`build_twin2k_config.py`](../scripts/twin2k/build_twin2k_config.py)):

```
 760  response columns in wave1_3_response_label.csv (excl. pid)
-634  columns inside the six PERSONA_BLOCKS
 126  HOLDOUT — block-complement, asserted set-equal to wave4_response_label.csv
- 18  no option list the decoder can match
        12 HSLIDER: QID290 ×10 (false-consensus estimate) + QID154, QID156 (base-rate)
         6 SL:      QID164/166/168/170 (anchoring) + QID181/182 (sunk cost)
 108  SCORED — 65 nominal + 43 ordinal + 0 multi
        60 ordinary columns, every one 2,058/2,058 filled
        48 between-subject condition columns at 31–51% fill, each respondent in exactly one arm
```

**B — the persona** ([`build_twin2k_persona.py`](../scripts/twin2k/build_twin2k_persona.py)):

```
 760  response columns
- 14  Demographics block → becomes the persona block itself, in every arm
-126  HOLDOUT → excluded outright, the paper's own partition
 620  PRIOR-ANSWER SCREENERS — mean 552.7 answered/respondent, median 552, min 526, max 589
        564 decode through a `choices` map:
              158 Bipolar price lists, rendered by splitting their 'LEFT:RIGHT' row label
               84 MAVR/MAHR checkbox columns, identity-mapped, NaN = unchecked = skipped
              322 Likert / SAVR / SAHR
         56 free text (38 FORM + 15 SL + 3 ML, holdout SL already removed above), rendered verbatim
```

Nothing is subtracted at this step any more: the candidate set *is* the persona.

Both chains sum exactly. The intersection is **0 and guarded twice**: `assert_holdout_only` refuses a
scored column outside the holdout, and `main()` in the persona generator refuses a persona that carries
one. That pair of asserts is what retires the old "never pool the two scored sets" rule — there is no
longer a second set.

**The 158 Bipolar columns are rendered by splitting the row label, which is where their meaning is.**
All 13 `Bipolar` entries sit in the `Economic preferences` block — the multiple-price-list and
uncertainty-equivalence batteries yielding discount rate, present bias, risk aversion and loss aversion
(Table 1: 34 economic-preference questions), which are persona material for the paper too. Their
`Columns` are literally `'1'` and `'2'`, so what a recorded `'1'` MEANS lives in the row label, which the
catalog writes as `'LEFT:RIGHT'` (`'$6.00 in 6 weeks:$3.00 in 5 weeks'`). All 158 rows carry exactly one
colon and every entry's `Columns` is `['1','2']`, so `_bipolar_sides` splits the label and emits
`{'1': left, '2': right}`; a label it cannot split, or a `Columns` that is not `['1','2']`, is fatal
rather than skipped, because a label split the wrong way would render the option the respondent did
*not* choose. The paper's own renderer emits `  {i} = {column}` and inherits the ambiguity this avoids,
so on these columns our persona is more informative than theirs rather than merely equivalent. Cost:
**+6,798 tokens per persona** (12,521 → 19,319 on the rendered `Q:`/`A:` lines, o200k_base), and unlike
the Likert batteries a ladder cannot be compressed — its content *is* the 158 individual comparisons.

**The prior-answer persona carries no holdout column.** The exclusion is the 126-column block-level set
above, and the generator raises if `kept ∩ holdout` is non-empty, so the `_prior_answers` arm is the
paper's Text Persona arm *in kind*. It was not always: excluding only the columns the run scored left
**94 of the 126 in the persona** — 30 of the 40 pricing decisions, all 10 false-consensus items,
`QID288_3`/`_4`, all four `QID289` risk ratings, and essentially the whole between-subject battery.
No column-level rule could have reached them, because `QID9_11`–`QID9_40`, `QID287` and `QID289` are
sibling *tasks* of scored questions rather than sibling columns of one catalog entry. Closing it cost
nothing in coverage: the 90 columns dropped relative to the old rule were the half-answered
between-subject conditions.

## Prompt formatting, verbatim on both sides

### The paper's system prompt (Appendix A.1)

Used "for all LLM-based simulations":

> You are an AI assistant. Your task is to answer the 'New Survey Question' as if you are the
> individual described in the 'Persona Profile' (which contains their past survey responses). Remain
> consistent with the persona's previous answers and stated characteristics. Carefully follow any
> instructions provided for the new question, including formatting requirements.

The shipped code's `GEMINI_SYSTEM_INSTRUCTION` in `llm_helper.py` is near-identical but not the same
string — it says "person" where the paper says "individual" and "consists of" where the paper says
"contains".

### The paper's user message (`create_text_simulation_input.py`)

One `.txt` file per respondent, assembled as
`COMBINED_PROMPT_HEADER + persona + COMBINED_PROMPT_SEPARATOR + questions`:

```
## Persona Profile (This individual's past survey responses):
<persona text>

---
## New Survey Question & Instructions (Please respond as the persona described above):
<question text>
```

Each item inside either block is rendered by `format_question_text` in
`convert_persona_to_text.py` as the stem, a type line, an options list, and an answer line:

```
Question Type: Single Choice          (SAVR/SAHR; "Multiple Choice" for MAVR/MAHR,
Options:                               "Matrix", "Slider", "Text Entry", "Text Entry (Form)")
  1 - <label>                         (MC options use "i - label"; matrix columns use "i = label")
  2 - <label>
Answer: 2 - <selected text>
```

The same renderer serves both blocks, switched by one flag. `convert_persona_to_text.py` calls it with
`with_answers=True`, so **every persona item carries the respondent's real answer** and the `[Masked]`
branches are unreachable from that path — holdout items are already gone, removed upstream by the
three-file partition, not by the renderer. `convert_question_json_to_text.py` calls it with
`with_answers=False`, so each question to be answered renders **`Answer: [Masked]`** as the slot the
model must fill. An item with no data renders `[No Answer Provided]` — which means genuinely missing
and deliberately withheld are distinguishable, the former only ever appearing in the persona.
A descriptive-block (`DB`) item renders `[Descriptive Information]` and carries no answer line.

Questions are prefixed `Q1:`, `Q2:`, … on a single counter that runs continuously across blocks (`DB`
items are skipped and consume no number), under the header "Please answer the following questions as
if you were taking this survey," with the JSON format spec appended last. **Options are never shuffled
anywhere in the pipeline.**

The renderer also carries a `demographic_only` flag that keeps only the first block — the Demographics
block — which is the shipped code's counterpart of our baseline arm and of the unpublished
`Demographics Only` folder on HuggingFace.

### The paper's 14 demographic items (Appendix A.2)

Reproduced with their option lists because they are what our persona block renders:

| Question | Options |
|---|---|
| Which part of the United States do you currently live in? | Northeast; Midwest; South; West; Pacific (each with its state list) |
| What is the sex that you were assigned at birth? | Male; Female |
| How old are you? | 18-29; 30-49; 50-64; 65+ |
| What is the highest level of schooling or degree that you have completed? | Less than high school; High school graduate; Some college, no degree; Associate's degree; College graduate/some postgrad; Postgraduate |
| What is your race or origin? | White; Black; Asian; Hispanic; Other |
| Are you a citizen of the United States? | Yes; No |
| Which of these best describes you? | Married; Living with a partner; Divorced; Separated; Widowed; Never been married |
| What is your present religion, if any? | Protestant; Roman Catholic; Mormon; Orthodox; Jewish; Muslim; Buddhist; Hindu; Atheist; Agnostic; Other; Nothing in particular |
| Aside from weddings and funerals, how often do you attend religious services? | More than once a week; Once a week; Once or twice a month; A few times a year; Seldom; Never |
| In politics today, do you consider yourself a | Republican; Democrat; Independent; Something else |
| Last year, what was your total family income from all sources, before taxes? | Less than $30,000; $30,000-$50,000; $50,000-$75,000; $75,000-$100,000; $100,000 or more |
| In general, would you describe your political views as | Very conservative; Conservative; Moderate; Liberal; Very liberal |
| Including yourself, how many people currently live in your household? | 1; 2; 3; 4; More than 4 |
| What is your current employment status? | Full-time employment; Part-time employment; Unemployed; Self-employed; Home-maker; Student; Retired |

### Ours (`survey_prompt`, shared verbatim by every arm)

```
<survey_context>
This is a survey research simulation. The Twin-2K-500 study surveyed 2,058 US adults across
four waves, covering demographic, psychological, economic, personality and cognitive
measures, replications of behavioral economics experiments, and a pricing survey.
</survey_context>

<persona>
Answer the survey question as the person described below. Before you respond, evaluate which
of the factors listed would actually affect your answer to this question. Then use that
information to respond accordingly. Remain consistent with this person's previous answers
and stated characteristics.

Demographics:
- Age: {age}
- Sex assigned at birth: {sex}
…14 hyphen-bulleted items, the Appendix A.2 list with short field labels…
</persona>

<conversation_history>
{conversation_history}
</conversation_history>

<current_question>
Question: {question}
Options: {options}

Return your answer with:
• choice: Option number(s) you select based on your persona and prior answers
  • explanation: Brief reasoning for this response
</current_question>
```

**The shape is this repo's own, not the paper's Appendix A.1 wording** (which earlier runs used).
Tagged sections ordered stable → volatile keep the persona a cacheable prefix across every question
a respondent is asked, and it is the shape the rest of the engine is tuned for.
Matching the paper's prompt text bought nothing while elicitation diverges anyway: one call per
question, an enforced schema, shuffled options, temperature 0.7.

Two constraints are worth knowing before editing it. `{framing_guidance}` and `{response_format}` are
supplied only by the *stateful* runner, and this one text is shared by the two stateless arms and both
stateful ones — so the answer format is inlined literally, matching `_CHOICE_RESPONSE_FORMAT`
in [`survey_runner_excel.py`](../src/core/survey_runner_excel.py). One consequence for
`_probs_chained`: the inlined block asks for `choice` and `explanation` only, so that arm's probability
vector is requested by the enforced schema alone, never by `_VERBALIZED_CHOICE_RESPONSE_FORMAT`. And
the demographics are rendered as short labelled bullets rather than the survey's own question text; the
`_prior_answers` arm's 620 prior answers arrive separately, through `{conversation_history}`, as
`Q:`/`A:` pairs.

`This is a survey research simulation.` inside `<survey_context>` is not in the paper. On this prompt
shape it is **insurance rather than load-bearing** — re-probed after the rewrite, the same 8
respondents × 2 questions pass 16/16 both with the line and with `<survey_context>` deleted. Under the
Appendix A.1 wording the same probe failed 12 of 16 bare, deterministically per respondent, so the
filter deleted whole people. That failure mode and why the arms cannot share a panel are in the
content-filter section of [twin2k-grounding-variants.md](twin2k-grounding-variants.md).

## Elicitation

| | Paper (`run_LLM_simulations.py`) | Ours ([`src/core/survey_runner_excel.py`](../src/core/survey_runner_excel.py)) |
|---|---|---|
| Call granularity | **one call per respondent**, covering the whole holdout set | **one call per (persona, question)**, batched at `max_concurrency: 100` |
| Question numbering | `Q1:`…`Qn:` within a single prompt | one question per prompt, no numbering |
| Output contract | free-text JSON keyed `"Q1"`…`"Qn"`, each `{"Question Type", "Reasoning"?, "Answers": {…}}`; `Answers` is `SelectedByPosition` + `SelectedText` (choice/matrix), `Values` (slider), or `Text` | Pydantic model, provider-enforced: `choice: int` bounded `ge=1, le=n_options` (or `choices: List[int]`) plus `explanation: str` |
| Schema enforcement | none — raw text is stored and parsed downstream | structured output; provider-aware method (`json_schema` for Azure) |
| Failure handling | `save_and_verify_callback` drives up to `max_retries` retries of [call → save → verify] | provider rejects off-schema output; a failed batch item is re-invoked once, and an item that still fails lands as an `Error` row that drops from metrics **and** as a `(respid, question)` record in `run_errors_*.jsonl` with its real cause. On a `--checkpoint-dir` run those cells are never marked complete, so the same command with `--resume` re-asks them one call each (03-survey-response.md) |
| Reasoning | an **arm**, not a default (`--include_reasoning`); "Text Persona (Reasoning)" scored 70.39% vs 71.72% without | always on, one sentence, and never scored |
| Option order | never shuffled | shuffled per persona (`_shuffled_option_order`); **nothing pinned** — `preserve_anchors: false` and no question declares `anchor_options` |
| Temperature | 0 for every arm except the one that tests 0.7 | `survey_temperature: 0.7` |
| Concurrency | `max_concurrent_requests: 5`, `max_retries: 10` | `max_concurrency: 100` (50 on `chained` and `probs_chained`), the only knob |

Two consequences of the call-granularity difference are worth naming. Their twin answers all 88
holdout items *in one context*, so it can be internally consistent across them and can carry over
whatever it inferred while answering `Q1` into `Q40`; our stateless path cannot, and that is exactly
what the `_chained` arm isolates. Against that, their single call makes answers within a respondent
statistically dependent in a way ours are not.

Their accuracy metric: exact match for binary items; `1 − |deviation| / range` otherwise; averaged
within a task, then across the 17 equally-weighted tasks. Ours: TVD (nominal), Wasserstein-1
(ordinal), Jaccard and `marginal_prevalence_mad` (multi) — distributional distances, not per-person
hit rates.

Their published arms, for the two choices we diverge on:

| Arm | Accuracy |
|---|---|
| Human test–retest (ceiling) | 81.72% |
| Text Persona & GPT-4.1-mini | **71.72%** |
| Text Persona (Default Temperature 0.7) & GPT-4.1-mini | 71.24% |
| JSON Persona (Predicted Output) & GPT-4.1 | 71.92% |
| JSON Persona & GPT-4.1 | 71.05% |
| Text Persona (Repeating Questions) | 70.45% |
| Text Persona (Reasoning) | 70.39% |
| JSON Persona & GPT-4.1-mini | 70.48% |
| LLM finetuning (500 samples) | 69.61% |
| Text Persona & Gemini-flash2.5 | 69.40% |
| Persona Summary & GPT-4.1-mini | 68.02% |
| Random guessing (floor) | 59.17% |

### The human ceiling on our own 16 tasks is 81.68%

The 81.72% ceiling above is the paper's, across its 17 tasks. Recomputed with the paper's own formula —
exact match for binary items, `1 − |deviation| / range` otherwise, averaged within a column, then within
a task, then across equally-weighted tasks — on `wave1_3_response_label.csv` against
`wave4_response_label.csv` over exactly the 108 scored columns, it is **81.68% across our 16
experiments**, 0.04 pt from the paper's figure. So the scored set does not sit at an easier or harder
point of the instrument than the set the paper reports on.

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
| Linda (conjunction) | 82.41% | **Equal-weight across 16** | **81.68%** |

Tasks are merged the way the paper aggregates its 17: nonseparability's benefits and risks halves count
once, as do anchoring's two scenarios and proportion dominance's two problems.

Read the per-task column before reading any per-task score of ours. A twin cannot be held to 100% on
dominator neglect when the same humans reproduce themselves 72.16% of the time, and the 16 ceilings
span 17 points, so a flat threshold across tasks would be a different standard on each.

**The 60 always-asked tasks average 82.78%, so the between-subject experiments are the harder half.**
Every one of the 60 pairs for all 2,058 respondents. The 48 condition columns pair at **100%** as well —
wave 4 re-ran each respondent in the arm they were originally assigned, so no arm-switch pairs exist and
each condition column rests on 651–1,056 pairs. That is independent confirmation of the
presence-is-the-randomization-record reading in §Between-subject arms.

## Our 108 questions, in full

**The paper's whole holdout instrument, minus the 18 columns one measured filter removes.** Every row is
in `wave4_response_label.csv`, so the `Holdout` column of earlier versions of this table is gone — it
would read ✔ 108 times. Sixty columns are asked of everyone; the other 48 are the 13 between-subject
groups, asked only of the arm each respondent was randomized into (§Between-subject arms).

| Task | Our ids | Count | Bucket | Asked of |
|---|---|---:|---|---|
| Product Preferences — Pricing | `QID9_1`–`QID9_40` | 40 | nominal | everyone |
| False consensus support | `QID287_1`–`_7`, `_10`–`_12` | 10 | ordinal | everyone |
| Nonseparability — benefits | `QID288_1`–`_4` | 4 | ordinal | everyone |
| Nonseparability — risks | `QID289_1`–`_4` | 4 | ordinal | everyone |
| Dominator neglect | `QID196` | 1 | nominal | everyone |
| Omission bias | `QID291` | 1 | ordinal | everyone |
| Asian disease (framing) | `QID157` / `QID158` | 2 | ordinal | one of 2 arms |
| Outcome bias | `QID161` / `QID162` | 2 | ordinal | one of 2 arms |
| Anchoring — African countries | `QID163` / `QID165` | 2 | nominal | one of 2 arms |
| Anchoring — redwood | `QID167` / `QID169` | 2 | nominal | one of 2 arms |
| Absolute vs relative saving | `QID183` / `QID184` | 2 | nominal | one of 2 arms |
| Allais paradox | `QID192` / `QID193` | 2 | nominal | one of 2 arms |
| Myside bias | `QID194` / `QID195` | 2 | ordinal | one of 2 arms |
| Less is more | `QID171`–`QID173` | 3 | ordinal | one of 3 arms |
| Proportion dominance 1 | `QID174`–`QID176` | 3 | ordinal | one of 3 arms |
| Proportion dominance 2 | `QID177`–`QID179` | 3 | ordinal | one of 3 arms |
| WTA/WTP (Thaler) | `QID189`–`QID191` | 3 | ordinal | one of 3 arms |
| Linda (conjunction fallacy) | `QID159_1`–`_3` / `QID160_1`–`_3` | 6 | ordinal | one of 2 arms |
| Probability matching | `QID198_1`–`_10` / `QID203_1`–`_6` | 16 | nominal | one of 2 arms |

65 nominal + 43 ordinal + **0 multi**, and **16 experiments now carry at least one scored column against
5 before** (counting anchoring's two scenarios as one task and proportion dominance's two problems as
one, which is how the paper aggregates its 17). No denominator is quoted deliberately: the paper's "11
between-subject" does not reconcile column-for-column with the catalog's 12 between-subject experiment
families, the same looseness §The holdout split already flags in its question counts.

The single filter that cuts 126 → 108 is **no option list our decoder can match**: 12 `HSLIDER`
(`QID290`'s 10 false-consensus estimates, 100% filled and otherwise ideal, plus `QID154`/`QID156`
base-rate) and 6 `SL` text boxes (4 anchoring, 2 sunk cost). Two experiments are therefore out entirely
rather than partially — **base rate** (both arms are sliders) and **sunk cost** (both arms are text
boxes); anchoring keeps its more/fewer judgment and loses only its numeric estimate. Fill rate is no
longer a filter: a condition column filled by 31–51% of the panel is the randomization record, not a
defect (§Between-subject arms).

| Our id | Type | Selector | Block | Paper task | Stem | Options | Ordered | Shuffled |
|---|---|---|---|---|---|---|:-:|:-:|
| `QID9_1` | single | SAVR | Product Preferences - Pricing | pricing study | "Please consider the following product category: Dairy Products… you see the following product…: Land O Lakes Salted Stick Butter, 16 oz, 4 Sticks. The product is priced at: ${stem_value}. Would you or would you not purchase this product?" — the price is **piped per respondent**, below | Yes, I would purchase the product / No, I would not purchase the product | ✘ | ✔ |
| `QID9_2`–`QID9_40` | single | SAVR | ″ | ″ | same stem, 39 other category/product pairs — 40 distinct categories, each with its own piped price; prices span **$0.00–$59.98** across respondents, so the task spans obvious buys to obvious refusals. See [`twin2k_question_mapping.json`](../configs/twin2k/twin2k_question_mapping.json) | ″ | ✘ | ✔ |
| `QID196` | single | SAVR | Non-experimental heuristics and biases | dominator neglect | two trays of marbles, 100 vs 10, draw a white marble to win | the small tray / the large tray | ✘ | ✔ |
| `QID291` | single | SAVR | ″ | omission bias | deadly flu, 10% chance of dying, vaccine carries 5% risk of a weaker flu | definitely not take / probably not take / probably take / definitely take (each with its consequence clause) | ✔ | ✘ |
| `QID287_1` | single | Likert | False consensus | false consensus | "Would you support or oppose… — Placing a tax on carbon emissions?" | Strongly oppose / Somewhat oppose / Neither oppose nor support / Somewhat support / Strongly support | ✔ | — |
| `QID287_2` | single | Likert | ″ | ″ | "— Ensuring 40% of all new clean energy infrastructure development spending goes to low-income communities?" | ″ | ✔ | — |
| `QID287_3` | single | Likert | ″ | ″ | "— Federal investments to ensure a carbon-pollution free electricity sector by 2035?" | ″ | ✔ | — |
| `QID287_4` | single | Likert | ″ | ″ | "— A 'Medicare for All' system in which all Americans would get healthcare from a government-run plan?" | ″ | ✔ | — |
| `QID287_5` | single | Likert | ″ | ″ | "— A 'public option', which would allow Americans to buy into a government-run healthcare plan if they choose to do so?" | ″ | ✔ | — |
| `QID287_6` | single | Likert | ″ | ″ | "— Immigration reforms that would provide a path to U.S. citizenship for undocumented immigrants currently in the United States?" | ″ | ✔ | — |
| `QID287_7` | single | Likert | ″ | ″ | "— A law that requires companies to provide paid family leave for parents?" | ″ | ✔ | — |
| `QID287_10` | single | Likert | ″ | ″ | "— A 2% tax on the assets of individuals with a net worth of more than $50 million?" | ″ | ✔ | — |
| `QID287_11` | single | Likert | ″ | ″ | "— Increasing deportations for those in the US illegally?" | ″ | ✔ | — |
| `QID287_12` | single | Likert | ″ | ″ | "— Offering seniors healthcare vouchers to purchase private healthcare plans in place of traditional medicare coverage?" | ″ | ✔ | — |
| `QID288_1` | single | Likert | Non-experimental heuristics and biases | nonseparability (benefits) | "Please rate the following technology or products from 'not at all beneficial' to 'extremely beneficial' — bicycles" | not at all beneficial / low benefit / slightly beneficial / neutral / moderately beneficial / very beneficial / extremely beneficial | ✔ | — |
| `QID288_2`–`_4` | single | Likert | ″ | ″ | "— alcoholic beverages", "— chemical plants", "— pesticides" | ″ | ✔ | — |
| `QID289_1`–`_4` | single | Likert | ″ | nonseparability (risks) | "Please rate the following technology or products from 'not at all risky' to 'extremely risky'" — the same four technologies | not at all risky / low risk / slightly risky / neutral / moderately risky / very risky / extremely risky | ✔ | — |

Four notes on this table, which lists the 60 always-asked columns; the 48 condition columns are stems
in [`twin2k_question_mapping.json`](../configs/twin2k/twin2k_question_mapping.json) tagged
`condition_group` / `condition_arm`. The `QID287`/`QID288`/`QID289` items carry a `grid_group`, so they
share a stem and only the row label differs; `shuffle_options` is unset for every Likert item, so the
scale keeps its order. `QID287`'s rows are numbered **1–7 and 10–12** — there is no `_8`/`_9` — which is
why `build_matrix_entries` resolves a row by its CSV column name rather than by position; positionally,
`_10` would have taken `_12`'s label and three questions would have been scored against the wrong
ground truth. Every answer in the scored set decodes to a real option, asserted at generation time,
under two fill rules: each of these 60 columns is answered by all 2,058 respondents, and each condition
group has exactly one fully-filled arm per respondent. So on the 60, `n_valid` below 50 in a
`validation_summary` is an unambiguous content-filter diagnostic and never missing ground truth; on the
48, expected `n_valid` is the arm's share of the panel.

`QID198`'s two options are literally the labels `1` and `2`, so its prompt reads "1. 1 / 2. 2" and its
CSV cells arrive from pandas as floats — the Twin preprocessor casts them back to `"1"`/`"2"` (see
02-persona-generation.md). Read
the first responses on that task for confusion before trusting it. `QID158` also ships with two dataset
typos ("nobody people will die", "600 people be die"); stems are copied verbatim on purpose, since
editing one would score the twin on a question no human was asked.

### The pricing price is piped text, and rendering the catalog's draw made the pricing task unlearnable

The pricing block is Qualtrics piped text: **the price is randomized per respondent**, and
`question_catalog.json` — a single rendered instrument — holds one arbitrary draw. Measured on
`wave_split/chunks/wave_persona_chunk_001.parquet` (294 respondents × 40 products = 11,760 cells): each
product carries **161–197 distinct prices**, and only **0.757%** of cells (89 of 11,760) ever saw the
catalog's price. Asked at the catalog price the 40 products are statistically indistinguishable —
yes-rates 40.4–45.3%, χ² p = 0.25, corr with catalog price +0.099 at p = 0.54 — against corr **−0.356**
and a yes-rate running **75.8% → 16.4%** across price quintiles when the real price is used. So the
largest task in the scored set carried no learnable signal, and the 83.89% human retest ceiling on
pricing was unreachable in principle.

The fix is per-respondent question text, not a per-respondent persona: the generator rewrites each
pricing stem's price to the `{stem_value}` token, the config's `preprocess.params.stem_values_dir`
points the Twin preprocessor at `wave_split/`, and `_fill_stem` substitutes each respondent's own price
in step 03 (03-survey-response.md). Nothing about
`get_question_text` or any other survey changes.

Two properties of the source data make the recovery exact rather than approximate, and both are asserted
at load time: the price is **identical between `wave4_Q_wave1_3_A` and `wave4_Q_wave4_A`** (100% of
11,760 cells — one draw per person-product, not per wave, so pairing wave-4 question text with wave-1-3
answers is sound), and the parquet's wave-1-3 answers **equal the label CSV's cells exactly** (100%), so
the join on `pid` is the right join. Nothing else in the holdout is piped: the other 23 catalog entries
have exactly one stem across all 294 respondents.

**This is the axis on which we were unintentionally *unlike* the paper.** Their pipeline renders each
respondent's own instrument JSON, so their twin always saw the real price; ours read one catalog and
showed everyone the same one. **Any Twin scorecard produced before this existed understates pricing and
is not comparable to one produced after.** The cost is the fetch: `wave_split/` is ~189 MB against
~26 MB for the three CSV/JSON files.

### Between-subject arms

Qualtrics randomized each respondent into exactly one arm of each of the 13 groups above, so each arm's
columns are filled by only 31.6–51.3% of the panel. A twin is asked **the same arm its human counterpart
saw**: `build_twin2k_config.py` tags every entry with `condition_group` and `condition_arm`,
`condition_assignments()` in [`question_mapper.py`](../src/data/question_mapper.py) turns a
respondent's ground truth into `{"__condition__Disease": "gain", …}`, and `QuestionRouter.is_asked`
withholds the arms the respondent was not assigned. Asking both arms would convert a between-subject
manipulation into a within-subject one and erase the effect being measured. The mechanism is
survey-agnostic and inert where no question declares a group — see
03-survey-response.md.

**The assignment is read from the presence of a filled column, never from its content, and that bound is
the whole design.** Qualtrics left no assignment variable in the CSV, so which arm a respondent saw
survives only as which columns they answered — presence *is* the randomization record. Reading presence
is not leakage; reading the answer would be. Generalizing this to a non-condition question would be:
"this respondent answered Q, therefore ask Q" is harmless, but any rule that looked at *what* they said
would feed the ground truth into the prompt. `condition_assignments` raises if a group has zero or two
or more arms present, which is the check that keeps the hand-authored grouping honest.

**Two limits on what per-arm numbers can say.** They are the reason to read these columns differently
from the other 60, not a caveat to skim.

- **Per-arm fit is not the framing effect, and cannot detect a frame-blind twin.** Real humans favor the
  certain program **71.9%** in `QID157`'s gain frame against **36.3%** in `QID158`'s loss frame — a
  35.6pp effect, arm-to-arm TVD 0.356. A twin that ignores the frame and answers the pooled human
  distribution in both arms scores TVD **0.182 / 0.173**, unremarkable beside the rest of the run, while
  reproducing **+0.0pp** of the effect. No contrast metric is shipped, so the arm pairs must be read side
  by side; the export carries each arm's distribution, so the contrast is a few lines in a notebook.
- **The guardrails are absent, not passing.** At `max_rows: 50` an arm draws n≈16–25, below
  `min_n_for_gating`, so `collapse` is forced `False` and `blind_spot` is `None` on all 48 columns, with
  `entropy_thin` / `kl_thin` marking why (04-validation-export.md).
  Grow the panel; lowering the floor manufactures flags from noise rather than restoring the guardrail.

### What was dropped from the earlier 21-question set, and why the reasons differ

Seven of the earlier questions were not holdout, and they came out for **two unrelated reasons**. The
distinction matters because the natural reading — that they all failed the same test — is wrong.

- **`QID25_1`–`QID25_4` (Big Five) were the leak.** One catalog entry holds 44 Big Five columns and the
  run scored 4, so the prior-answer persona kept 40 same-battery items that essentially determine the
  trait. Not a metric problem: a **copy test**.
- **`QID221`, `QID126`, `QID128` were dropped on instrument grounds, not leakage.** `QID126`/`QID128`
  carry **empty `QuestionText`** in the catalog — and they are not alone: **20 entries do**, the whole
  Beck Depression Inventory battery (`QID126`, `QID128`–`QID134`, `QID136`–`QID147`, all
  `Personality`/`MC`/4 columns), whose shared instruction lives in the separate `DB` block `QID127`, one
  of the 14 entries that produce no CSV column at all. So a scored BDI item needs a stem transcribed by
  hand, which [`build_twin2k_config.py`](../scripts/twin2k/build_twin2k_config.py) does — the one
  place this pipeline transcribes a question by hand, against its own premise. `QID221` is the Wason
  selection task, a cognitive test with a *correct* answer, so simulating it measures reasoning rather
  than preference, which is not what a response-distribution metric is for.
- **Restoring the `multi` bucket from these three now costs a leak, which it did not before.** All 84
  `MAVR`/`MAHR` columns are non-holdout and every one of them is now in the `_prior_answers` persona, so
  scoring `QID126_*` while its three sibling columns sit in the prompt is the same copy test `QID25`
  failed. Any restoration has to remove the scored columns' own siblings from the persona first — on top
  of the hand-written stem and the correct-answer framing. `build_multi_entry` is kept in the generator
  for that reason even though `MULTI_QIDS` is empty.

One flag this page used to raise is settled by measurement: `QID126`/`QID128` are typed `multi` by us
although their stem says "pick out the **one** statement", but 121 + 13 and 141 + 50 of 2,058
respondents select more than one — so `multi` was the right type and retyping them to `single` would
have truncated real answers.

## Differences and what each costs

| Axis | Paper | Ours | Consequence |
|---|---|---|---|
| Grounding content | full non-holdout wave 1–3 record | baseline 14 demographics; `_prior_answers` adds all 620 remaining columns, every Table 1 group | **matched** — nothing a respondent answered is excluded except the paper's own holdout |
| Holdout partition | task level, three-file split | task level — the same 126 columns, asserted both ways | matched; the arm is the paper's in kind |
| Question rendering | each respondent's own instrument JSON, so piped values are the respondent's | one shared mapping, plus a `{stem_value}` token filled per respondent for the 40 pricing prices | matched where it matters. Until the token existed, everyone saw one catalog price draw that 99.2% of respondents never saw — the whole pricing task was noise (§The pricing price is piped text) |
| Call granularity | one call per respondent, all items in context | one call per (persona, question) | no cross-item consistency on the stateless arms — the thing `_chained` measures; our answers are also mutually independent, theirs are not |
| Option order | never shuffled | shuffled per persona, no option pinned | deliberate divergence: the paper's own cited reason (Brucks & Toubia) is that order moves answers, so we randomise it away rather than inherit it |
| Temperature | 0 (all arms but one) | 0.7 | priced by their own arm: 71.24% vs 71.72%, so ≈0.5 pt |
| Model | GPT-4.1-mini (best arm) | `azure/gpt-4.1` | their GPT-4.1 arms run 0.6–0.9 pt above the mini equivalents, so this pushes the other way |
| Answer format | free-text JSON, parsed, retried | provider-enforced Pydantic schema | fewer parse losses for us; no measurable accuracy claim either way |
| Reasoning | an arm (`--include_reasoning`), costing 1.3 pt | always on, unscored | untested on our side; the paper's evidence says it does not help |
| Metric | exact match / `1 − ǀdevǀ/range`, averaged within then across 17 equally-weighted tasks | TVD, Wasserstein-1, Jaccard, `marginal_prevalence_mad` | **no number we produce is on the paper's scale** |
| Sample | 2,058 respondents | `max_rows: 50` | wide CIs; the three arms also survive the content filter at different rates, so they must be scored on the intersection |
| Items | 88 holdout questions across 17 tasks | 108 holdout columns across 16 experiments | everything in the holdout our decoder can read, including the between-subject arms; only base rate and sunk cost are absent entirely (sliders and text boxes) |
| Condition assignment | each respondent's own instrument JSON carries their arm | derived from which arm's columns their answer sheet fills (§Between-subject arms) | matched: the twin sees the arm its human saw |

## What is and is not comparable

- **Nothing we produce is comparable to 71.72%.** Different metric, different item set, different
  sample size. Read our runs variant-against-variant.
- **No Twin result predating the `{stem_value}` token is comparable to one after it.** The whole pricing
  task asked a price almost nobody was shown, so those runs understate pricing (§The pricing price is
  piped text). This is a scorecard-invalidating change, not an additive one.
- **No `_prior_answers` result predating the current persona is comparable to one after it.** That arm's
  persona went 322 → 480 → 620 answers and 12.5k → 19.3k → ~22.1k tokens across two changes (the price
  lists, then the checkbox and free-text columns), so the recorded 3-arm finding (neither prior answers
  nor chaining detectable at n=50) describes a persona that arm no longer sends and needs re-running.
  `baseline` and `chained` read a different mapping file and are untouched, so the reference points are
  intact.
- **The three arms compare to each other only on the intersection of respondents that survived all
  three**, because the Azure content filter deletes specific respondents deterministically and the
  large `_prior_answers` prompt survives it where the bare demographics prompt does not.
- **Report per task, never pooled.** 40 of the 108 are pricing, so a pooled nominal figure is dominated
  by one task. Averaging within task and then across tasks is also exactly how the paper aggregates its
  17, so this is the paper-faithful reading rather than a workaround. The directions differ by bucket:
  distributional metrics are lower-better, individual accuracy is exact match on the 65 nominal items
  and **MAE (lower-better)** on the 43 ordinal ones, so reading the ordinal sign backwards mis-reads
  most of the report.
- **The 48 condition columns are a plumbing proof at n=50, not a result**, and per-arm fit says nothing
  about whether the twin responds to the manipulation at all (§Between-subject arms).
- **`_prior_answers` is the paper's Text Persona arm in kind, not in value.** The holdout partition now
  matches, but temperature 0.7, option shuffling, one call per (persona, question) and a distributional
  metric all still differ.

## The grounding-content decision is closed

The persona now carries the **complete non-holdout, non-demographic record** — 620 of 620 columns. Every
decision this section used to hold open is implemented: task-level exclusion (§The holdout split, §What
each arm's persona holds), the 158 `Bipolar` price lists, the 84 `MAVR`/`MAHR` checkbox columns and the
56 free-text ones (same section). There is nothing left to admit, so the only grounding difference left
between the paper's persona and ours is the holdout partition, and that one is deliberate and matched.

What remains open is elsewhere: call granularity (one call per respondent vs one per question),
temperature, and option shuffling — all priced in the Differences table above.

## Links

- [twin2k-grounding-variants.md](twin2k-grounding-variants.md) — our three arms, the content-filter
  deviation, and how prior answers reach the prompt
- public-survey-data-analogues.md — how Twin-2K-500 was chosen and wired up
- llm-survey-playbook.md — the grounding ladder these arms sit on
- 03-survey-response.md — the `{conversation_history}` contract
- Toubia et al., *Twin-2K-500*, arXiv 2505.17479 — §3 waves, §6 accuracy and the three-file split,
  Table 1 instrument, Table 2 arms, Appendix A.1/A.2 prompts
- `tianyipeng-lab/Digital-Twin-Simulation`, `text_simulation/` — the authors' own renderer and runner
- Peng et al., *Funhouse Mirrors*, arXiv 2509.19088 — the follow-up measuring twins at average
  r = 0.20 across 164 outcomes
