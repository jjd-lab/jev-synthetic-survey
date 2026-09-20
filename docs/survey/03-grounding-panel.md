# What persona content buys you

GPT-4.1 playing all 2,058 Twin-2K-500 respondents, three times, varying what the persona contains
and whether the model sees its own earlier answers.

## Question

A simulated respondent has to be grounded in something. The cheapest thing to ground it in is who
the person is: 14 demographics. The dataset's paper grounds its twins in the respondent's own
answers to hundreds of earlier questions instead, and reports 71.72% accuracy for that.

Two different things could explain the gap between a demographics-only run and that figure: the
persona **content**, or the fact that a stateless run asks each question in isolation and so cannot
be consistent across a questionnaire. Those are separable, so this experiment separates them.

Two contrasts, each varying one factor:

```
prior answers  −  demographics       = what the respondent's own past answers are worth
stateful       −  stateless          = what seeing its own earlier answers is worth
```

## Setup

Same 108 questions, same 2,058 respondents, same prompt text, `gpt-4.1`, temperature 0.7,
options shuffled per persona. All three arms ask each simulated respondent only the between-subject
arm its human counterpart was randomized into, so 48 of the 108 columns draw an arm's share of the
panel rather than the full sample.

| Arm | Persona holds | Sees its own earlier answers | Config | Output |
|---|---|---|---|---|
| **demographics, stateless** | 14 demographics | no | [`demographics_stateless.yaml`](../../configs/twin2k/demographics_stateless.yaml) | [`runs/gpt41_panel_n2058/demographics_stateless/`](../../runs/gpt41_panel_n2058/demographics_stateless/) |
| **demographics, stateful** | 14 demographics | yes | [`demographics_stateful.yaml`](../../configs/twin2k/demographics_stateful.yaml) | [`runs/gpt41_panel_n2058/demographics_stateful/`](../../runs/gpt41_panel_n2058/demographics_stateful/) |
| **prior answers, stateless** | 14 demographics + 620 past answers | no | [`prior_answers_stateless.yaml`](../../configs/twin2k/prior_answers_stateless.yaml) | [`runs/gpt41_panel_n2058/prior_answers_stateless/`](../../runs/gpt41_panel_n2058/prior_answers_stateless/) |

Each folder holds the respondent-level workbook, the validation summary, and the persona cache the
arm ran from. The prior-answers folder also holds the per-cell file, 168,768 cells across all 2,058
respondents. [`runs/README.md`](../../runs/README.md) maps every file.

There is no prior-answers plus stateful cell. On top of 620 real prior answers, the model's own
earlier answers add near-zero information, and it is by far the slowest path. The result below
weakens that argument, which is noted in the interpretation.

### How the persona is grounded, and how past answers reach the prompt

The demographics persona is 14 labeled bullets. The prior-answers persona adds 620 columns, which is
**the whole non-holdout, non-demographic record**: mean 552.7 answered per respondent (median 552,
min 526, max 589), with 481 of the 620 columns answered by all 2,058 people. Nothing a respondent
answered is excluded except the paper's own holdout.

They reach the prompt through the existing conversation-history channel as verbatim question and
answer pairs, not through a new placeholder: the persona generator emits one entry per prior-answer
column, and the runner renders them. That channel can also render an LLM-written summary instead,
which this survey deliberately does not use: the profile is either empty (the two demographics arms)
or wanted whole.

Cost of that, in prompt size: **about 22k input tokens per prompt on the prior-answers arm, against
400 on the demographics arms.** 530 of the 620 entries carry a short battery tag in place of
repeating their instruction stem, which does two opposite jobs. On the 16 matrix batteries it is a
pure saving, 18,866 down to 11,503 tokens on the rendered question and answer lines, a 39%
reduction, because the row label is already a self-contained first-person statement. On the 13 price
lists it is the only place the comparison can live and it is a cost, 12,521 up to 19,319 tokens, a
54% increase for 158 rows, because a price ladder's whole content *is* its individual comparisons and
cannot be compressed. The 21 checkbox groups and 4 free-text batteries add a further 2,684 tokens,
19,319 up to about 22,050.

### The three configs are generated, not hand-maintained

Every reading below assumes the arms differ in nothing else. The framework has no config inheritance
and no override flags, so the alternative is three hand-maintained copies of a 60-line prompt, where
editing one file confounds the comparison invisibly.
[`build_twin2k_variants.py`](../../scripts/twin2k/build_twin2k_variants.py) copies the baseline's
text, comments included, and substitutes only what defines an arm, asserting that each substitution
fired. An arm's runner settings belong in that script's substitution table and never in the
generated file: they read as per-file tuning, which is what invites a hand edit, and the next
regeneration reverts it silently. The check is exact and cheap: the script's output must equal the
file on disk byte for byte, so run it and expect an empty `git diff` on `configs/`.

## Metrics

All defined on the [metrics page](02-metrics.md): accuracy against the leave-one-out majority floor,
the distribution gap on two-option columns, the ordinal distribution gap on multi-option columns,
rank correlation with the human (price-controlled on the pricing block), the entropy ratio,
collapsed columns and blind spots. Every figure is an equal weight across the 16 tasks.

Two reminders that bear directly on the tables. **The floor, not the headline, is the number to
read**: a persona-blind predictor scores 73.27% here. And **distances are lower-better while accuracy
and correlation are higher-better**, so the columns below do not all point the same way.

## Results

All three arms ran on the whole 2,058-respondent panel on the current prompt, so both contrasts are
measurable at panel scale and share one persona-blind floor of **73.27%**.

| Arm | accuracy | edge vs floor | rank corr. (price-controlled) | distribution gap / ordinal gap | collapsed | blind spots |
|---|--:|--:|--:|--:|--:|--:|
| demographics, stateless | 70.26% | −3.01 | +0.095 | 0.253 / 0.714 | 24 / 108 | 44 |
| demographics, stateful | 70.04% | −3.23 | +0.085 | 0.200 / 0.651 | **16** / 108 | **31** |
| prior answers, stateless | **72.92%** | **−0.35** | **+0.107** | **0.157** / 0.681 | 25 / 108 | 40 |

```
seeing its own earlier answers   = −0.22 points of accuracy
the respondent's own past answers = +2.66 points of accuracy
```

Reference points for the accuracy column: the human test-retest ceiling is 81.68%, the paper's best
published twin is 71.72%, and the persona-blind floor is 73.27%.

The demographics-stateless arm in more detail, since it is the reference the other two move from:

| | value | read against |
|---|---|---|
| accuracy, equal weight over 16 tasks | **70.26%** | leave-one-out majority 73.27%, so an edge of **−3.01** |
| rank correlation with the human, price-controlled | **+0.095** | equal weight over the 14 measurable tasks; raw +0.113 |
| distribution gap, 65 two-option columns | 0.253 | equal-weight task mean; 0 = identical panels |
| ordinal distribution gap, 43 multi-option columns | 0.714 | equal-weight task mean |
| diversity | entropy ratio 0.445 two-option, 0.678 multi-option | 24 of 108 columns collapsed, 44 carry a blind spot |

Per-task and per-column numbers for all three arms, side by side, are in
[`reports/task_deep_dive_full.md`](../../reports/task_deep_dive_full.md).

## Interpretation

**Only prior answers move accuracy, and that arm is the only one that comes within noise of a
predictor that never looks at the person.** +2.66 points closes nine tenths of the demographics
arm's deficit to the floor and clears the paper's best published twin by 1.2 points. It is still
*below* the floor, so no arm on this instrument carries net individual signal on this metric.

Accuracy and diversity are bought by different things, and neither lever buys both. Seeing its
own earlier answers unpins a third of the collapsed columns (24 to 16) and a third of the blind
spots (44 to 31) while losing accuracy. Prior answers gain 2.66 points of accuracy while collapsing
one *more* column than the demographics arm (24 to 25) and lowering multi-option diversity (entropy
ratio 0.678 to 0.639). Probability matching isolates the mechanism: 16 of 16 columns collapsed to a
single answer in both stateless arms, but 8 of 16 in the stateful one. Knowing what a person answered
before does not stop the model playing the rational optimum; seeing its *own* answers does. These
are two independent defects with two independent levers.

Most of the +2.66 is not individual prediction. Three tasks carry all of it: Pricing (+9.08 over
the floor, across 40 of 108 columns), Less is more (+13.08) and False consensus (+4.31). Everything
else sits at or below the floor. And Pricing's correlation with the human falls from +0.325 raw to
+0.069 once each respondent's own randomized price is held fixed, so the largest column-weighted
contributor is the weakest evidence of individual signal. False consensus is the one clean win,
+0.476 price-controlled correlation *and* +4.31 accuracy at an entropy ratio of 0.913, and it is
mechanistically the right task: "what fraction of others agree with you" is a direct function of the
attitudes those 620 columns encode.

**Landing near a published figure while losing to the column's own modal answer is the whole
reading.** The demographics arm sits 1.5 points from the paper's best published twin and 3.01 points
below a persona-blind predictor. The accuracy number is close to the paper's because both are close
to the majority, not because either is reading the individual. Only two tasks beat that arm's floor
by more than 3 points (Less is more +10.18, Pricing +7.87), and pricing's edge is the shared
randomized price rather than the person: six sevenths of its raw +0.301 correlation disappears when
price rank is held fixed, leaving +0.048.

**Aggregate fit and individual validity come apart on single columns.** One column matches the human
marginal to 1.2 points (35.6% against 34.4% choosing Yes) at a rank correlation of **−0.016**: the
right distribution assigned to the wrong people, on one column at n=1,027.

Accuracy and correlation disagree about which task is best grounded, and correlation is right.
False consensus (+2.61 edge, correlation +0.456, entropy ratio 0.920) is the one task with real
individual signal, and the one whose answer 14 demographics genuinely carry, since party
identification and political views predict policy attitudes. Less is more scores a larger +10.18
edge at a correlation of +0.061, purely by exaggerating the human mode: 87.8% "Disagree strongly"
against the humans' 43.5%. Both metrics belong on one sheet for exactly this reason.

**Where a task measures a bias, the error is directional, and the model exaggerates whichever answer
the framing pulls toward.** That is not the same as being more normative. Dominator neglect inverts
outright: 63.9% of humans take the *dominating* small tray (1 black marble of 10, against 8 of 100)
and 94.0% of simulated respondents take the large one, which is the whole −26.00 edge and the worst
result on the instrument. The model also *over*-produces the Allais certainty effect, 93.8% taking
the sure million against the humans' 69.2%. On both it sits further from the expected-value choice
than its human, not closer. Probability matching is the task where the same exaggeration lands on
the normative side, the model playing the rational optimum every time. More respondents will not
average any of this out. Prior answers repair the dominator-neglect marginal (62.2% small tray, a
distribution gap of 0.017) and the arm still scores 54.71% against a 53.40% no-knowledge expectation,
so fixing the direction bought no pairing.

**Every rating scale shows center avoidance plus a one-sided extreme, so the model is not uniformly
compressed.** Across the 26 scales with a midpoint the model takes it 5.5% of the time against the
humans' 12.1%, and in the sharpest case 4.5% against 24.2%. The ends go the other way: summed over
both, the model uses an extreme 25.5% of the time against 31.6%, and on 14 of the 43 multi-option
columns it uses one extreme *more* than its humans. On the Less is more items "Agree strongly" takes
0.0 to 0.4% against the humans' 4.2 to 17.4% while "Disagree strongly" takes 87.8% against 43.5%. It
abandons one end and piles onto the other, so an average over both hides the effect. This is what
produces 44 blind-spotted columns at a multi-option entropy ratio of 0.678, and it barely moves the
distribution gap when the missed option is small, which is why blind spots are reported separately
rather than trusted to the distance.

Two tasks are pinned, and only one of them is inert across arms. Anchoring (4 columns) and
Probability matching (16) both collapse to one answer in the demographics-stateless arm, and it is
the human mode, so their +0.00 edge is construction rather than agreement; together they are 12.5% of
the equal weight. Only Anchoring stays that way, reproducing at 78.13% with all 4 columns collapsed
in every arm, so it is the 6.25% to exclude from cross-arm comparisons. Probability matching moves as
soon as the model sees its own prior answers (8 of 16 collapsed, −1.59 points under the stateful
arm), which is what makes it the task that separates the arms. It is also near-unpredictable in
principle: the human retest itself loses to the majority there, by −1.74.

The crossed cell is now the one configuration worth reconsidering. The standing argument against
running prior answers *and* statefulness together was that the model's own earlier answers add
near-zero information on top of 620 real ones, supported by statefulness contributing −0.22 points
where it had no prior answers to compete with. This result weakens that: the two levers move
*different* metrics, one buying accuracy and no diversity and the other buying diversity and no
accuracy, so the crossed cell is the only untested configuration that could hold both. Against it
stands speed: it is the slowest path, walking each persona through its 80 to 84 questions
sequentially at prior-answers prompt sizes.

## Caveats

Neither contrast is pinned by a significance test. Both panel figures are equal-weight means over
16 task means. The paired test has not been run at n=2,058. **+2.66 points is 1.5 times the size of
the whole statefulness effect and moves in the predicted direction, but it is untested.** Any paired
test must use the 60 always-asked columns only: an arm of a between-subject group draws roughly 16 to
25 respondents, which no paired test can use.

A 50-respondent pilot could not have resolved either contrast, and got one sign wrong. At 50
respondents the paired test on pricing, the only task with enough columns to test, gave a change in
distribution gap of +0.0060 for prior answers (p = 0.091, sign *against* prior answers) and +0.0020
for statefulness (p = 0.801), with the 20 non-pricing questions canceling (p = 0.189, p = 0.940). The
panel run reversed the sign of the larger contrast. That is the reason these arms needed the full
panel rather than a cheaper slice.

**An identity-framed persona block does not survive the endpoint's content filter, and the failure is not
random.** The prompt keeps the line "This is a survey research simulation." inside its context
block. On the current prompt shape that line is insurance rather than load-bearing: re-probed after a
rewrite, the same 8 respondents by 2 questions pass 16 of 16 both with the line and with the whole
context block deleted. It *was* load-bearing under the dataset paper's own prompt wording, which
earlier runs used: without the line, the endpoint rejected the request on the input, before the model saw
anything, on 12 of 16 probes, against 16 of 16 with it. What changed is the framing, not the
demographics.

Two properties of that failure make it worth stating, because any future prompt edit can reintroduce
it:

- **It is deterministic per respondent, not flaky.** Respondents 2 to 7 failed 100% of attempts, 9
  tries each with delays; respondents 1 and 8 passed 100%. The filter does not thin the panel at
  random, it deletes specific people entirely, biasing the sample toward whoever it lets through.
  It also survives retries, so a retry setting cannot mask it.
- **The persona block is the trigger, not the question.** The question alone passes; the persona
  block alone fails, classified as identity impersonation. Wording changes *inside* the block do not
  help: swapping any single one of age, race or religious attendance between two respondents flipped
  the verdict, because the whole prompt sat at the threshold. Only changing the surrounding framing
  moved it.

A residual of about 4% of calls still filters with the line in place; those land as error rows and
are excluded from metrics like any other failure. Check the per-question count of valid responses
collected, not the failure counter: the validator reported zero failures on a question that had lost
2 of 50 personas. In principle the three arms are therefore comparable only on the intersection of
respondents that survived all three. In practice that turned out not to be an obstacle, because the
arms lost almost the same people rather than different ones: one respondent on one column in two of
the arms, none in the third. Every cell the filter refused in an earlier run came back answered in
the run that shipped, so no shipped arm carries a filter-deleted cell. The deterministic deletion
is a property to re-check after any prompt edit, not an open defect in the data here.

The 48 between-subject columns are read differently from the other 60, and per-arm fit says
nothing about whether the model responds to the manipulation at all. See
[01 Dataset and instrument](01-dataset-and-instrument.md).

No prior-answers result predating the current persona is comparable to one after it. That arm's
persona grew from 322 to 480 to 620 answers, and from 12.5k to 19.3k to about 22.1k tokens, across
two changes. The two demographics arms read a different mapping file and are untouched, so only that
one arm ever needs re-running.

Accuracy here is not comparable to the paper's own figures in value, only in kind. Temperature
0.7, shuffled options and one call per respondent-question all differ from the paper's setting, and
those choices were made to keep the three arms mutually comparable rather than to chase an absolute
number. See the difference table on
[01 Dataset and instrument](01-dataset-and-instrument.md).

## Reproduce

Scoring needs only what ships in this repo.

```bash
python scripts/twin2k/paper_accuracy.py \
    --details runs/gpt41_panel_n2058/demographics_stateless/respondent_details_20260904_091556.xlsx
python scripts/twin2k/individual_signal.py \
    --details runs/gpt41_panel_n2058/demographics_stateless/respondent_details_20260904_091556.xlsx \
    --summary runs/gpt41_panel_n2058/demographics_stateless/validation_summary_20260904_091556.xlsx
```

Those write the demographics-stateless pair of reports. The other two arms substitute their own
folder and workbook timestamps:

| Report | Arm | Scored from |
|---|---|---|
| [`reports/paper_accuracy_full_arm1.json`](../../reports/paper_accuracy_full_arm1.json), [`reports/individual_signal_full_arm1.json`](../../reports/individual_signal_full_arm1.json) | demographics, stateless | `runs/gpt41_panel_n2058/demographics_stateless/` |
| [`reports/paper_accuracy_full_chained.json`](../../reports/paper_accuracy_full_chained.json), [`reports/individual_signal_full_chained.json`](../../reports/individual_signal_full_chained.json) | demographics, stateful | `runs/gpt41_panel_n2058/demographics_stateful/` |
| [`reports/paper_accuracy_full_prior_answers.json`](../../reports/paper_accuracy_full_prior_answers.json), [`reports/individual_signal_full_prior_answers.json`](../../reports/individual_signal_full_prior_answers.json) | prior answers, stateless | `runs/gpt41_panel_n2058/prior_answers_stateless/` |
| [`reports/task_deep_dive_full.md`](../../reports/task_deep_dive_full.md) | all three | the same workbooks, per task |

`arm1` in those filenames is the demographics-stateless arm, named before the arms were.
Adding `--ceiling` to the accuracy command recomputes the human test-retest figure, which must land
on 81.68%; that is the scorer's external check and it needs the dataset itself, via
[`scripts/twin2k/fetch_twin2k.py`](../../scripts/twin2k/fetch_twin2k.py).

Running a new arm rather than rescoring an old one goes through `main.py` with the arm's config.
**Every launch must pass `--sample N`**: the generated configs carry a 50-respondent smoke-run
limit and the runner falls back to it, so omitting the flag silently runs 50 respondents.

[`reports/README.md`](../../reports/README.md) maps every report back to its run;
[`runs/README.md`](../../runs/README.md) maps every run file to the claim it supports.
