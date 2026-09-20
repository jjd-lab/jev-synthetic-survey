# Twin-2K-500 grounding × chaining variants

## Question

The committed Twin run grounds each persona in 14 demographics. The Twin-2K-500 paper grounds
its twins in the respondent's own answers to ~400 earlier questions and reports 71.72%
accuracy for that. Two things could explain a gap: the persona *content*, or the fact that
our stateless path asks each question in isolation. These are separable, so separate them.

## The three runs

Same 108 questions, same 2,058 respondents, same prompt. Two factors, one at a time. All three arms ask
each twin only the between-subject arm its human counterpart was randomized into, so 48 of the 108 draw
an arm's share of the panel rather than the full n
([twin2k-paper-vs-our-setting.md](twin2k-paper-vs-our-setting.md#between-subject-arms)).

| Config | Persona holds | Sees its own earlier answers | Paper equivalent |
|---|---|---|---|
| `twin2k_survey_config.yaml` | 14 demographics | no | none published (see below) |
| `..._prior_answers.yaml` | + 620 past Q&A | no | **Text Persona, 71.72%** — the paper's arm in kind, not in value |
| `..._chained.yaml` | 14 demographics | yes | none |

`prior_answers` − baseline = what the respondent's own past answers are worth.
`chained` − baseline = what answer chaining is worth.

The same generator emits a fourth arm, `probs_chained`, which varies elicitation rather than grounding
or chaining: it is `chained` asked for a probability vector instead of an answer. It belongs to neither
contrast above, and it is read in
[jev-twin2k-validation-findings.md](../FINDINGS.md).

## Where the arms stand

**All three arms have now run on the whole 2,058-respondent panel on the current prompt**, so both
contrasts are measurable at panel scale and share one persona-blind leave-one-out majority (73.27%).

| arm | paper accuracy | edge vs LOO majority | Spearman (price-ctrl) | TVD / W1 | collapsed | blind spots |
|---|--:|--:|--:|--:|--:|--:|
| `baseline` | 70.26% | −3.01 | +0.095 | 0.253 / 0.714 | 24 / 108 | 44 |
| `chained` | 70.04% | −3.23 | +0.085 | 0.200 / 0.651 | **16** / 108 | **31** |
| `prior_answers` | **72.92%** | **−0.35** | **+0.107** | **0.157** / 0.681 | 25 / 108 | 40 |

**Answer chaining is worth −0.22 pt. Prior answers are worth +2.66 pt.** Only the second moves accuracy,
and it is the only arm that comes within noise of the persona-blind predictor — closing nine tenths of
the baseline's deficit and clearing the paper's best published twin (71.72%) by 1.2 pt. It is still
*below* LOO, so no arm carries net individual signal on this metric, and only Anchoring's 6.25% of the
equal weight is pinned in every arm — Probability matching is pinned in two of three and is the task
that separates them. Reports: `outputs/twin2k/{paper_accuracy,individual_signal}_full_{arm1,chained,prior_answers}.json`;
per-task deep dive, all three arms side by side, in `outputs/twin2k/task_deep_dive_full.md`.

**Accuracy and diversity are bought by different things, and neither lever buys both.** Chaining unpins
a third of the collapsed columns (24 → 16) and a third of the blind spots (44 → 31) while losing
accuracy. Prior answers gain 2.66 pt of accuracy while collapsing *one more* column than the baseline
(24 → 25) and lowering ordinal diversity (h_syn/h_hum 0.678 → 0.639). `Probability matching` isolates
the mechanism: 16/16 columns collapsed at h_syn = 0 in both `baseline` and `prior_answers`, but 8/16 in
`chained`. Knowing what a person answered before does not stop the model playing the rational optimum;
seeing *its own* answers does. These are two independent defects with two independent levers.

**Most of the +2.66 is not individual prediction.** `Pricing` (+9.08 over LOO across 40 of 108 columns),
`Less is more` (+13.08) and `False consensus` (+4.31) carry all of it; everything else sits at or below
LOO. But Pricing's correlation falls from +0.325 raw to +0.069 once each respondent's own randomized
price is held fixed, so the largest column-weighted contributor is the weakest evidence of individual
signal. `False consensus` is the one clean win — +0.476 controlled Spearman *and* +4.31 accuracy at
h_syn/h_hum 0.913 — and mechanistically the right task, since "what fraction of others agree with you"
is a direct function of the attitudes those 620 columns encode.

`chained`'s superseded n=50 run is on a prompt that no longer exists — the `<answer_style>` block was
committed 2026-09-03 17:48, after that run's 17:14 export — so only its panel run is prompt-matched to
anything current.

**The full-panel baseline sits 3.01 pt BELOW a persona-blind predictor.** 14 demographics, 108 questions,
2,058 respondents, `azure/gpt-4.1`, scored on the post-repair files (`*_091556.xlsx`, `[errors] total=0`):

| | value | read against |
|---|---|---|
| Paper accuracy (equal weight over 16 tasks) | **70.26%** | leave-one-out majority **73.27%** → edge **−3.01** |
| | | human test-retest ceiling 81.68%, paper's best twin 71.72% |
| Spearman vs human, price-controlled | **+0.095** | equal weight over the 14 measurable tasks; raw +0.113 |
| TVD (65 nominal columns) | 0.253 | equal-weight task mean; 0 = identical panels |
| Wasserstein-1 (43 ordinal columns) | 0.714 | equal-weight task mean |
| Diversity | h_syn/h_hum 0.445 nominal, 0.678 ordinal | 24 of 108 columns collapsed, 44 carry a blind spot |

Landing within 1.5 pt of the paper's best published twin while *losing* to the column's own modal answer is
the whole reading: the accuracy number is close to the paper's because both are close to the majority, not
because either is reading the individual. Only two tasks beat the baseline by more than 3 pt (`Less is more`
+10.18, `Pricing` +7.87), and pricing's edge is the shared randomized price rather than the person — six
sevenths of its raw +0.301 correlation disappears when price rank is held fixed (+0.048). Anchoring and
Probability matching are fully collapsed (h_syn = 0, 20 columns, 12.5% of the equal weight), so they cannot
move between arms at all. Reports: `outputs/twin2k/paper_accuracy_full_arm1.{json,txt}` and
`individual_signal_full_arm1.{json,txt}`.

**Neither contrast is pinned by a significance test, and 50 respondents could not have pinned either.**
Both panel figures are equal-weight means over 16 task means. At `max_rows: 50` the paired Wilcoxon on
pricing — 40 questions, the only task with enough columns to test — gave baseline → `prior_answers`
ΔTVD +0.0060 (p = 0.091, sign *against* prior answers) and baseline → `chained` +0.0020 (p = 0.801),
with the 20 non-pricing questions cancelling (p = 0.189, p = 0.940). So the n=50 verdict was "smaller
than 50 respondents can resolve", and the panel run reversed the sign of the larger contrast — which is
the reason this arm needed the full panel rather than a cheaper slice. The paired test has not been
re-run at n=2,058; **+2.66 pt is 1.5× the size of the whole `chained` effect and moves in the predicted
direction, but it is untested.** Any paired test must use the 60 always-asked columns only: an arm of a
condition group draws n≈16–25, which no paired test can use.

**The crossed `prior_answers` × `chained` cell is now the one configuration worth reconsidering.** The
standing argument against it was that on top of 620 real prior answers the model's own earlier answers
add near-zero information, supported by chaining contributing −0.22 pt with no prior answers to compete
with. The panel result weakens that: the two levers turn out to move *different* metrics — prior answers
buy accuracy and no diversity, chaining buys diversity and no accuracy — so the crossed cell is the only
untested configuration that could hold both. Against it stands cost and speed: it is the slowest path,
`memory_mode: full` walking each persona through its 80–84 questions sequentially (60 always-asked plus
one arm of each of the 13 groups), at `prior_answers` prompt sizes. Still not built, no longer dismissed.

**The baseline's grounding level is unpublished.** HuggingFace ships 13 arm folders including
`Demographics Only - GPT4.1-mini`, which is absent from the paper's Table 2 and is the only
folder with no `accuracy_evaluation/` — so no accuracy exists for our exact level anywhere.
Its responses do ship, so the number is computable.

## Why the variants are generated, not copied

Every reading above assumes the three differ in nothing else. The framework has no config
inheritance and `main.py` has no override flags, so the alternative is four hand-maintained
copies of a 60-line prompt — where editing one file confounds the comparison invisibly.
[`scripts/twin2k/build_twin2k_variants.py`](../scripts/twin2k/build_twin2k_variants.py)
copies the baseline's text (comments included) and substitutes only what defines an arm —
`demographic_mapping`, `memory_mode` plus the runner flags that cancel its side effects
(`chain_own_answers`, `batch_grids`, `prompt_cache_key_by_respid`), the `max_concurrency` those
imply, `output_dir`, and on `probs_chained` the two settings that arm adds (`response_mode` and a
`persona_cache_path` pointing at `chained`'s cache, so both walk the same twins) — asserting each
substitution fired. Re-run it after any edit to the baseline.

**An arm's runner settings belong in the script's substitution table, never in the generated
file.** They read as per-file tuning, which is what invites the hand-edit, but the next
regeneration reverts one silently. The check that catches this is exact and cheap: the script's
output for each variant must equal the file on disk byte for byte, so run it and expect an empty
`git diff` on `configs/`.

## How past answers reach the prompt

Not through a new placeholder. [`build_twin2k_persona.py`](../scripts/twin2k/build_twin2k_persona.py)
emits one `type: "screener"` entry per prior-answer column, so `QuestionMapper` decodes them
into `screener_profile`, and `render_history()` renders that into the existing
`{conversation_history}` channel as `Q:`/`A:` pairs.

**`{conversation_history}` is the only history channel there is.** `render_history` in
[`survey_runner_excel.py`](../src/core/survey_runner_excel.py) takes the one `screener_profile` and
renders it either as an LLM summary (`screener_summary`, when the config sets
`personas.screener_summarization_prompt`) or as verbatim `Q:`/`A:` pairs (when it does
not — Twin's mode), then always appends this run's own answers last. So summary-vs-verbatim
is a config switch on one channel rather than two prompt placeholders, and choosing summary mode cannot
silently drop answer chaining. Twin omits `screener_summarization_prompt`, which both selects verbatim
rendering and avoids spending one LLM call per persona compressing a profile that is either empty
(baseline, chained) or wanted whole (prior_answers).

Design calls in the generator, each with a cost:

- **Leakage is excluded at task level: all 126 of the paper's holdout columns stay out, whether this run
  scores them or not.** `holdout_columns()` lives in
  [`build_twin2k_config.py`](../scripts/twin2k/build_twin2k_config.py), which asserts the scored set
  is a subset of it, so the scored set and the persona cannot drift into overlap; the persona generator
  additionally asserts the set equals the columns of `wave4_response_label.csv`. The earlier
  column-level rule left **94 of the 126 in the persona** — no column-level rule could reach them,
  because `QID9_11`–`QID9_40`, `QID287` and `QID289` are sibling *tasks* of scored questions rather than
  sibling columns of one catalog entry. Worth one sentence because a leak of that kind reports nothing:
  it only raises the score.
- **`choices` is keyed by what the CSV stores, valued by the text to render.** The two
  disagree — `QID27`'s catalog labels are `TRUE`/`FALSE` against cells reading `True`/`False`
  — and extraction does a plain `choices.get(value)` with no case fallback. On the price lists the
  value is a different *option*, not a re-spelling, so `fit_to_csv` carries incoming values through
  instead of rebuilding the map from its own keys — rebuilding restores `A: 1` on 158 columns without
  raising anything.
- **Decodability is checked with the runtime's own `_normalize_choice_value`/`_is_filled`**, so
  the generator can never be stricter or laxer than the extraction it feeds. The two halves of that
  rule are separate: the *option list* is normalized (`_normalize_choice_value(1.0)` → `'1'`) but the
  *answer* is stringified first (`_canonicalize_single_answer(1.0)` → `'1.0'`), so an integer-labelled
  column decodes only because the Twin preprocessor casts it, and `build_twin2k_config.py` reads the
  cast frame for exactly that reason.
- **The 84 `MAVR`/`MAHR` checkbox columns decode as ordinary single-choice screeners, not as
  `is_multi_select`.** A checked box stores the option's **own label text** and an unchecked one stores
  `NaN`, so an identity map over the catalog's `Options` is all the decode they need; the multi branch's
  `respondent_row[col] == 1` test belongs to a coded format Twin never produces. Every column of a
  battery is handed the *whole* option list and `fit_to_csv` narrows each to the one value its column
  holds — unlike `Bipolar` there is nothing to get backwards, because the answer text is the option's own
  label either way. The unchecked cells are skipped silently by the runtime, which is the correct reading
  of a "select each that applies" item: only the boxes the respondent checked reach the prompt.
- **The 56 `SL`/`ML`/`FORM` free-text columns carry `free_text: true` and no `choices`**, and are the one
  thing here that needed a change in `src/`: `extract_screener_profile` renders the cell as written, the
  case `extract_demographics` already had for age/state/zipcode. The flag is explicit rather than inferred
  from an empty `choices`, because grid screeners have empty `choices` too (they are
  `is_grid`) and an implicit test would make their correctness depend on branch *order*. `MIN_DECODE_RATE`
  is skipped for them — there is no decode map, so a filled cell is by definition readable — but a column
  nobody answered is still dropped.
- **An unhandled selector is now fatal.** Every selector in the catalog reaches a branch, so a future
  dataset revision cannot silently drop columns the way the duplicate-`QuestionID` bug did.
- **The 158 `Bipolar` economic-preference price lists are rendered by splitting their row label**
  (discount rate, present bias, risk aversion, loss aversion — 21% of all response columns, and once the
  largest exclusion here). Their `Columns` read `'1'`/`'2'`, so what a stored code means lives in the row
  label, which the catalog writes as `'LEFT:RIGHT'` (`'$6.00 in 6 weeks:$3.00 in 5 weeks'`).
  `_bipolar_sides` splits on that one colon and emits `{'1': left, '2': right}`. Anything it cannot split
  cleanly, or a `Columns` that is not `['1','2']`, is fatal rather than skipped: a label split the wrong
  way renders the option the respondent did *not* choose, which reads perfectly and is backwards.
- **Every entry is a single-column screener, never `is_grid`** — the grid branch tests
  `is not None`, and a blank matrix cell from a CSV is `NaN`, so it would render `label: nan`. A price
  list could not use it in any case: `scale` is one map per battery, and a price list's two options
  change on every row.

Result: **620 prior-answer columns — the whole non-holdout, non-demographic record**, 552.7 answered by
the average respondent (median 552, min 526, max 589; 481 of the 620 answered by all 2,058). There is
nothing left to admit: the persona and the paper's now differ in nothing but the holdout partition.
`MIN_DECODE_RATE = 0.99` drops nothing — its former casualties were all half-answered
between-subject columns, which the holdout exclusion removes first. The full 760 → 620 accounting, and
the parallel 760 → 108 chain for the scored set, are in
[twin2k-paper-vs-our-setting.md](twin2k-paper-vs-our-setting.md#the-two-funnels).

## An identity-framed persona block does not survive Azure's content filter

The prompt keeps `This is a survey research simulation.` inside its `<survey_context>` block. On the
current prompt shape that line is **insurance, not load-bearing**: re-probed after the
rewrite, the same 8 respondents × 2 questions pass **16/16 both with the line and with
`<survey_context>` deleted entirely**.

It was load-bearing under the paper's Appendix A.1 wording, which earlier runs used. There, without the
line, Azure rejected the request on the **input** — `ContentPolicyViolationError` before the model saw
anything — on 12 of 16 (respondent × question) probes, against 16 of 16 with it. What changed is the
framing, not the demographics: A.1 enumerates race, religion, party, political views and citizenship
under "answer as if you are the individual described", and the tagged shape does not.

Two properties of that failure make it worth a section rather than a footnote, because any future
prompt edit can reintroduce it:

- **It is deterministic per respondent, not flaky.** Respondents 2–7 failed 100% of attempts
  (9 tries each, delays included); 1 and 8 passed 100%. So the filter does not thin the panel
  at random — it deletes specific people entirely, biasing the sample toward whoever it lets
  through. It also survives retries, so `max_retries` cannot mask it.
- **The persona block is the trigger, not the question.** The question alone passes; the persona block
  alone fails, classifying as identity impersonation. And wording changes *inside* the block do not
  help — swapping any single one of `age`, `race`, or `religious_attendance` between two respondents
  flipped the verdict, because the whole prompt sat at the threshold and any perturbation tipped it.
  Only changing the surrounding framing moved it.

The provider strips Azure's category detail from the error, so which filter category fires is
unconfirmed. A residual ~4% of calls still filter with the line in place; those land as `Error`
rows and are excluded from metrics like any other failure. **Check the per-question
`Collected N valid responses` line, not `n_failed`** — the validator reported `n_failed=0` on a
question that had lost 2 of 50 personas.

## All three arms need the piped pricing price

The pricing price is randomized per respondent, so `question_catalog.json` holds one arbitrary draw that
only **0.757%** of respondents saw; at that price all 40 products are statistically indistinguishable
(χ² p = 0.25), i.e. the largest task in the scored set carried no signal. The mapping therefore renders
the price as a `{stem_value}` token and the baseline config's
`preprocess.params.stem_values_dir: data/twin2k500/wave_split` recovers each respondent's own price.
Evidence and the two assertions that make the recovery exact:
[twin2k-paper-vs-our-setting.md](twin2k-paper-vs-our-setting.md#the-pricing-price-is-piped-text-and-rendering-the-catalogs-draw-made-the-pricing-task-unlearnable).

Two consequences for these arms specifically. The param is **not** one of the three the variant generator
substitutes, so it arrives in `_prior_answers` and `_chained` by verbatim copy — dropping it from the
baseline silently drops it from all three, and a stem with the token and no value raises rather than
prompting with the token. And because the change moves the whole pricing task, **no arm's results
predating it can be compared with results after it**; the intersection rule below is about the content
filter and does not rescue a cross-version comparison.

## Reading the results

Five properties of this instrument, measured on the full baseline, constrain how any arm reads.
Per-task and per-column numbers: `outputs/twin2k/task_deep_dive_full.md`.

- **Where a task measures a bias, the error is directional, and the twin exaggerates whichever answer
  the framing pulls toward — which is not the same as being more normative.** `Dominator neglect`
  inverts outright: 63.9% of humans take the *dominating* small tray (1 black of 10 = 10%, against 8 of
  100 = 8%), 94.0% of twins take the large one, which is the whole −26.00 edge and the worst on the
  instrument. The twin also *over*-produces the Allais certainty effect (93.8% take the sure million
  against 69.2%). On both it sits further from the expected-value choice than its human, not closer;
  `Probability matching` is the task where the same exaggeration lands on the normative side, the twin
  playing the rational all-`1` optimum every time. More respondents will not average any of this out.
  Prior answers repair the `Dominator neglect` marginal (62.2% small tray, TVD 0.017) and still score
  54.71% against a 53.40% no-knowledge-of-the-person expectation, so fixing the direction bought no
  pairing — see the next bullet.
- **Aggregate fit and individual validity come apart on single columns here.** `QID184` matches the
  human marginal to 1.2 points (35.6% vs 34.4% Yes) at Spearman **−0.016**: the right distribution
  assigned to the wrong people, on one column at n=1,027.
- **12.5% of the equal weight is pinned in this arm, but only half of it is inert across arms.**
  `Anchoring` (4 columns) and `Probability matching` (16) both have h_syn = 0 here — one answer for
  every twin, and it is the human mode, so their +0.00 edge is construction rather than agreement. Only
  `Anchoring` stays that way: it reproduces at 78.13% and 4/4 collapsed in every arm, so it is the
  6.25% to exclude from cross-arm comparisons. `Probability matching` moves as soon as the twin sees its
  own prior answers (8/16 collapsed, −1.59 pt under chaining), which is what makes it the task that
  separates the arms — keep it in. It is also near-unpredictable in principle: the human retest itself
  loses to the majority there (−1.74).
- **Every Likert scale shows centre avoidance plus a one-sided extreme — the twin is not uniformly
  compressed.** Across the 26 scales with a midpoint the twin takes it 5.5% of the time against the
  humans' 12.1% (4.5% vs 24.2% on `QID287_2`, the sharpest case). The ends go the other way: summed over
  both, the twin uses an extreme 25.5% against 31.6%, and on 14 of the 43 ordinal columns it uses one
  *more* than its humans — `Agree strongly` takes 0.0–0.4% against 4.2–17.4% on the `Less is more`
  items while `Disagree strongly` takes 87.8% against 43.5%. It abandons one end and piles onto the
  other, so an average over both hides the effect. This is what produces 44 blind-spotted columns at an
  ordinal h_syn/h_hum of 0.678, and it barely moves TVD when the missed option is small — which is why
  blind spot is reported separately rather than trusted to the distance.
- **Accuracy and correlation disagree about which task is better grounded, and correlation is right.**
  `False consensus` (+2.61 edge, Spearman +0.456, h_syn/h_hum 0.920) is the one task with real
  individual signal, and the one whose answer 14 demographics genuinely carry — `party` and
  `political_views` predict policy attitudes. `Less is more` scores a larger +10.18 edge at Spearman
  +0.061, purely by exaggerating the human mode (87.8% `Disagree strongly` against 43.5%). Both metrics
  belong on one sheet for exactly this reason.

**Report per task, never pooled.** All 108 questions are paper holdout and none is persona material in
any arm, so there is no scored subset to keep apart from another — but 40 of the 108 are the pricing
study, so a pooled nominal figure is dominated by one task. The task inventory is in
[twin2k-paper-vs-our-setting.md](twin2k-paper-vs-our-setting.md#our-108-questions-in-full); averaging
within task and then across tasks is also how the paper aggregates its 17.

**The 48 between-subject columns are read differently from the other 60.** Each carries n≈16–25 at
`max_rows: 50`, so they are a plumbing proof rather than a result; and per-arm fit is not the framing
effect, so a twin that ignores the manipulation entirely still scores unremarkably on both arms. Read the
arm pairs side by side —
[twin2k-paper-vs-our-setting.md](twin2k-paper-vs-our-setting.md#between-subject-arms).

**The `multi` (Jaccard) bucket is unexercised** — the holdout blocks contain no MAVR/MAHR at all, and
every one of those 84 columns is now persona material instead. Two things a reader might try to put back
are deliberately out and should not be restored casually, and both are now copy tests:
`QID25_1`–`QID25_4` because the persona carries 40 same-battery Big Five siblings;
`QID221`/`QID126`/`QID128` because their own sibling columns are in the persona as of this change — on
top of which one is a cognitive test with a *correct* answer and the other two need a hand-written stem,
their catalog `QuestionText` being empty, as it is for all 20 entries of the Beck Depression Inventory
battery they belong to, whose instruction sits in the column-less `DB` block `QID127`.

Accuracy is also not comparable to the paper's own figures: the paper scores exact match on
binary and `1 − |deviation|/range` otherwise, averaged within then across tasks. This repo
scores TVD / Wasserstein-1. Read variant-against-variant, not against 71.72%.

Temperature stays 0.7 and option shuffling stays on, against the paper's 0. That is a
deliberate choice to keep the three mutually comparable rather than to chase the paper's
absolute numbers.

Because every always-asked column is answered by all 2,058 respondents (asserted at generation time),
`n_valid` below 50 on one of those 60 in a `validation_summary` is an unambiguous content-filter
diagnostic — never missing ground truth. On the 48 condition columns the expected `n_valid` is the arm's
share of the panel instead.

## Cost

**~22k input tokens per prompt on the prior-answer run**, against 400 on the baseline; ~82 questions
asked per respondent × 50 respondents × 3 runs ≈ 12,300 calls. `include_request_id: false` keeps the
persona a cacheable prefix shared across every question a respondent is asked.

**530 of the 620 entries carry a short battery tag, not their instruction stem** — 54 batteries supply
those rows, and one entry per row meant one copy of the stem per row. `BATTERY_TAGS` in
[`build_twin2k_persona.py`](../scripts/twin2k/build_twin2k_persona.py) replaces each with a tag, but
the tag does two different jobs:

- On the **16 matrix batteries** it is a pure saving: a 203-char stem ×44, a 476-char stem ×24, an
  84-char stem ×65 was half the persona's question text, and a tag like `I see myself as someone who`
  loses nothing, because the row label is a self-contained first-person statement and the *answer* label
  carries the scale (`Agree strongly`, `TRUE`, `Not at all 0`). **18,866 → 11,503 tokens on the rendered
  `Q:`/`A:` lines (−39%).** The three batteries answered on a numbered scale are the exception — their
  interior points render as bare digits (`A: 8`) and their original stems never stated the range either,
  so those tags carry it (`(1 = not important, 9 = highly important)`), ~660 tokens to make 53 answers
  readable.
- On the **13 price lists** it is the only place the comparison can live, and it is a cost:
  **+6,798 tokens (12,521 → 19,319, +54%)** for the 158 rows. The six payment ladders share one generic
  tag because their row label is self-describing, but the seven lotteries must define their lottery in
  the tag — their left side reads only `Lottery`, and QID251/QID252 plus QID276/QID278 have
  byte-identical `Rows`, so without it those 28 answers are indistinguishable from each other. A ladder
  also cannot be compressed the way a Likert battery can: its whole content *is* the individual
  comparisons.
- On the **21 checkbox groups and 4 free-text batteries** it is again the only place the instruction can
  live. The 20 BDI groups have an empty `QuestionText`, so a fallback to the stem would render no question
  at all; `QID10`'s 20 word-association boxes and `QID271`/`QID272`/`QID275`'s 6 thought boxes each repeat
  one stem per box, and the three thought listings must be told apart the way the lotteries were — their
  stems are near-identical and only survey order says which game each follows (`QID271`/`QID272` the trust
  game, `QID275` the dictator game), so each tag names its own decision and the `Rows` label numbers the
  box. Cost of the 140 rows: **+2,684 tokens (19,319 → ~22,050, +14%)** — checkbox 777, `SL` 761, `ML`
  336, `FORM` 811, for ~74 answered lines. A fifth of what the price lists cost.

Two traps for a future edit. **Do not put the stem on the first row of each battery and bare labels
after**: `prior_answer_history` drops entries with no answer, so a respondent who skipped row 1 loses the
frame for that whole battery, and respondents do skip (min 526 of 620 answered) — it corrupts some
personas, not all. And **`prior_answers` results predating any of the tags, the price lists or the 140
checkbox and free-text columns cannot be compared with results after them**; `baseline` and `chained`
read a different mapping file and are
untouched, so only this one arm ever needs re-running. Tags are asserted complete in both directions at
generation time, so a new battery or a stale key is fatal rather than a silent return to full stems.

## Links

- [twin2k-paper-vs-our-setting.md](twin2k-paper-vs-our-setting.md) — the paper's setting verbatim beside ours, difference by difference
- public-survey-data-analogues.md — how Twin-2K-500 was chosen and wired up
- llm-survey-playbook.md — grounding ladder; these runs sit at "survey-response twins" (⚠️), not "interview-based agents"
- 03-survey-response.md — the `{conversation_history}` contract
- Toubia et al., *Twin-2K-500*, arXiv 2505.17479 — §4 twin construction, Table 2 arms, Appendix A.1/A.2 prompts
- Peng et al., *Funhouse Mirrors*, arXiv 2509.19088 — the follow-up measuring twins at average r = 0.20 across 164 outcomes

## Next steps

- **Put a paired test under the +2.66 pt.** It is the one headline figure here with no significance test behind it, and it is the figure the grounding-ladder claim rests on. Run the same paired Wilcoxon used at n=50, on the 60 always-asked columns, `baseline` against `prior_answers` at n=2,058. Costs nothing — all three exports exist.
- **Reconsider the crossed `prior_answers` × `chained` cell**, which the panel result promoted from dismissed to untested: it is the only configuration that could hold both accuracy and diversity, since each existing lever buys exactly one. Price it before building it — it is `prior_answers` prompt sizes on the slowest path.
- **`prior_answers` reruns cost ~$2,450 and take three days.** $1.19 a persona-walk at the 92.3% prompt-cache hit rate `prompt_cache_key_by_respid` holds at `max_concurrency: 32`, against $2.24 unpinned (see stateful-persona-parallelism.md); the $1,000/day cap binds before the clock does, so it resumes across days under `--run-id prior_answers_rm`. **Every launch must pass `--sample N`** — the generated config carries `max_rows: 50` and `main.py` falls back to it, so omitting it silently runs 50 respondents. With all 2,058 checkpointed `ok`, a `--resume` run now re-exports and re-scores the panel without spending anything.
- Intersection scoring is not the obstacle it was expected to be: the arms lost almost the same people, not different ones — one respondent on `QID287_11` in `baseline` and `prior_answers`, none in `chained`.
- Compute the unpublished `Demographics Only` accuracy from the shipped responses, for an external check on the baseline.
