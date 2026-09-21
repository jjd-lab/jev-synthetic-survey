# Jev on a synthetic survey: does a native probability vector beat a verbalized one?

**Visual explainer** — [read it as a page](https://jjd-lab.github.io/jev-synthetic-survey/), with the walkthrough and the figures.

I asked a decision-only model, TypeSafe's [Jev](https://typesafe.ai) `jev-1.13.0`, and GPT-4.1 to
play the same 300 survey respondents on the public
[Twin-2K-500](https://huggingface.co/datasets/LLM-Digital-Twin/Twin-2K-500) benchmark. That is 108
questions, 16 behavioral-economics tasks, and 24,596 answered cells per arm. Jev returns a
probability vector natively. I asked GPT-4.1 to state one in words.

Asked each yes/no question as a `Noul`, a single probability that the answer is yes, Jev leads
GPT-4.1 probabilities on all six measures, at a thirty-fourth of the cost, and comes within two points of GPT-4.1's hard-answer accuracy while returning a full probability
distribution, which a hard answer does not. Asked as a `Choice`, pick one of the two options and
the form the comparison was set up around, it trails on the distribution gap, 0.1985 against
0.1789. How you ask mattered more than which model you used.

**Independent work.** I have no affiliation with TypeSafe or OpenAI, and received no funding,
credits or early access from either. I paid for all Jev and GPT-4.1 usage myself. Neither company
had any input into the design or the write-up, and neither has seen it.

The full write-up is in [`docs/`](docs/README.md), split into a
[survey track](docs/README.md#survey-track) for what transfers to any model on this benchmark and a
[Jev track](docs/README.md#jev-track) for the verdict on this one.

New to synthetic survey respondents? [Start here](#new-to-this-start-here). For the raw runs, the
scored reports and the code, see [where to go](#where-to-go).

---

## New to this? Start here

**What a synthetic survey respondent is.** A language model asked to fill in a questionnaire as if
it were a particular person. You give it some facts about a real human, it answers questions that
human also answered, and you compare the two. The appeal is that real panels are slow and
expensive, so a model that could stand in for one would let you pretest a survey before fielding
it. Whether it can is an open question, and this repo is one measurement of it.

**The data is not mine, and neither is the benchmark design.** Everything here runs on
[Twin-2K-500](https://huggingface.co/datasets/LLM-Digital-Twin/Twin-2K-500), built for this exact
question by Toubia et al. (*Twin-2K-500*, [arXiv 2505.17479](https://arxiv.org/abs/2505.17479),
CC BY 4.0). They surveyed 2,058 US adults on Prolific across four waves in February 2025, over 500
questions each, then held one block out: a battery of classic behavioral-economics tasks. The rest
of a person's answers is what you may use to build their twin. The held-out block is the exam. I
did not collect any of it and I do not redistribute it;
[`fetch_twin2k.py`](scripts/twin2k/fetch_twin2k.py) downloads it from the authors.

**What a run does here.** For each of 300 respondents, build a persona out of their 14 demographic
items, walk that persona through 108 of the held-out questions one at a time, and record what the
model answered beside what the human actually answered. One pass over all 300 people is an **arm**.
Five arms make up the comparison below, and they differ only in which model was asked, and how.

**What is being compared.** Two ways of getting a probability out of a model. Jev is decision-only:
it generates no text at all, returning a typed value and a number per option natively.
GPT-4.1 is a general chat model, so I asked it to state those same numbers in words. The
question is whether the native vector beats the verbalized one.

**Why the tables below lead with a distribution gap instead of accuracy.** Nobody can predict how
one individual answers a trick question. The humans themselves only reproduce their own earlier
answer 81.68% of the time, and every arm here scores below a baseline that ignores the persona
entirely. What a survey is actually for is the population number, the share who picked option A. So
the metric that decides things is how far an arm's *distribution* of answers sits from the humans',
and an arm can win that while losing per-person accuracy.

[The dataset and the instrument](docs/survey/01-dataset-and-instrument.md) has the full design and
the three different ways this dataset's questions can be counted.
[The metrics page](docs/survey/02-metrics.md) defines every number below.

---

## Asked the right way, Jev leads verbalized GPT-4.1 on every measure

On the 65 yes/no questions a `Noul` — one probability, no options offered — is the form that fits
the model. Asked that way, Jev beats verbalized GPT-4.1 on all six measures: the two-option
distribution gap 0.1530 against 0.1789, the ordinal half 0.6812 against 0.7272, calibration 0.1472
against 0.2393, Brier 0.7385 against 0.8108, accuracy 67.28% against 64.78%, and cost $4.02 billed
against roughly $136.

**How you ask mattered more than which model you used.** The comparison was set up around a
two-option `Choice` on those same questions, and that form loses the distribution gap, 0.1985
against 0.1789. One substitution, same model, same respondents, same price, moves 0.1985 to 0.1530
— further than the whole distance between the two models. That is the result worth carrying into
any future work, and it is why the recommendation is `Noul` for anything yes/no.

Three things belong with it. The `Noul` arm was built after seeing the `Choice` result, so it cannot
settle the comparison the tests were written for; on the measure that one turned on, GPT-4.1
probabilities came out ahead. The `Noul` lead on the yes/no half is in the task-weighted gap this
codebase reports; on the stricter per-column rule fixed in advance GPT-4.1 probabilities are still
ahead, p=0.9995, because one task holds 40 of the 65 columns. And calibration missed its bar of 0.05
for every arm at once — 0.1472 at best — which makes it a statement about demographics-only grounding
rather than about any model.
[Details and both tests in full](docs/jev/02-planned-comparison.md).

## All five arms

Accuracy is last in this table on purpose. A synthetic panel earns its keep when the *distribution*
it produces matches the population's, so the first two columns are the ones the verdict turns on:
how far an arm's answer distribution sits from the humans' on the 65 two-option questions (soft
TVD), and how far it sits on the 43 questions whose options are ordered (soft Wasserstein-1). Lower
is better everywhere except the last column.

| Arm | distribution gap | ordinal gap | calibration (ECE) | Brier | accuracy | cost |
|---|---|---|---|---|---|---|
| Jev Choice (the arm the comparison was set up around) | 0.1985 | 0.6864 | 0.2029 | 0.7550 | 67.59% | $4.01 |
| Jev Choice + option descriptions | 0.1985 | 0.6822 | 0.2032 | 0.7553 | 67.51% | $4.03 |
| Jev Noul | **0.1530** | **0.6812** | **0.1472** | **0.7385** | 67.28% | $4.02 |
| GPT-4.1 probabilities | 0.1789 | 0.7272 | 0.2393 | 0.8108 | 64.78% | ~$136 |
| GPT-4.1 hard answer | 0.2037 | 0.6987 | 0.3741 | 1.1664 | **69.32%** | not measured |

300 respondents, 108 columns, 24,596 cells in every arm, equal weight per task. Every arm name,
metric name and report key is defined once in [the glossary](docs/README.md#names-used-throughout). Four things the
table will mislead you about if you read it alone:

- **"Jev Noul" is `Noul` only where `Noul` applies.** A `Noul` takes a yes/no condition, so it can be asked on the 65 two-option columns and not on the 43 multi-option ones, which fall back to `Choice`. By cell the arm is 64.6% `Noul` and 35.4% `Choice`. The name is the elicitation that changed, not the elicitation of every cell.
- **The hard-answer arm has no probability vector.** Its ECE and Brier score a one-hot spike, so
  they measure the absence of a distribution rather than the quality of one. It is in the table
  because it is the arm that wins accuracy, which is the whole point about accuracy. It was
  extracted from a larger panel run rather than collected on its own, so it has no separate cost.
- **The arm that wins accuracy is last on the distribution gap, on calibration and on Brier.** The
  distribution columns are where the arms actually separate, which is why they come first.
- **The descriptions arm changed 40 of the 108 columns**, the pricing block, because the
  description is derived from the option label and most labels yield none. The other 68 columns got
  a byte-identical payload, which is the control that proves the run was clean rather than a
  result. [What it did and did not move](docs/jev/05-option-descriptions.md).

## Asking the same question a different way closed most of the gap

I asked Jev every yes/no question as a `Choice`, meaning pick one of two options. That was the
wrong form, and it cost more than the whole gap I was trying to measure.

Re-asking those same 65 columns as a `Noul`, a single probability that the answer is yes with no
options offered, changes the result at the same price and with no loss of accuracy.

| | `Choice` | `Noul` |
|---|---|---|
| distribution gap (soft TVD, 65 two-option columns) | 0.1985 | 0.1530 |
| calibration error (ECE) | 0.2029 | 0.1472 |
| accuracy | 67.59% | 67.28% |
| cost | $4.01 | $4.02 |

The mechanism is saturation. Asked as a `Choice`, Jev put a probability of exactly zero on one of
the two options in 16.6% of two-option cells. Asked as a `Noul`, it did that in 0.0%. On the same
cell and the same label the two forms disagree by a mean of 0.13, so they are not variants of each
other.

If you take one thing from this repo, take this: on this model, never ask a yes/no question as a
two-option choice. [The follow-up in full](docs/jev/03-noul-follow-up.md).

That arm does not overturn the verdict and was never eligible to. I fixed the test on the `Choice`
arm and built `Noul` afterwards, having seen the result. Against GPT-4.1 it wins on the
aggregation this codebase uses, 0.1530 against 0.1789, and loses the per-column test that was fixed
in advance at p=0.9995. One task holds 40 of the 65 two-option columns, and that weighting choice
accounts for the entire disagreement between the two answers.

## Asking a model to state a probability moves its answer

Asking GPT-4.1 for a probability distribution cost 4.42 points of committed accuracy against
asking it to pick an answer, 64.90% versus 69.32%. The obvious confound is that the probability arm
also unbatched its grids. The entire loss sits in the 15 tasks where grid batching is not in play,
and the one block that was unbatched improved by 0.89 points, so the cause is the elicitation rather
than the batching.

If you ask a model to verbalize its uncertainty, expect its committed answer to move. I measured
that on one model and one instrument; treat it as a hypothesis worth checking on yours rather than
as a settled law. [Details](docs/survey/04-elicitation-effects.md).

## Where Jev is better

The verdict is a conjunction, so losing one half of it is not the same as losing outright. Measured:

- It wins the 43 ordinal questions on the ordinal distribution gap, 0.6864 against 0.7272, better in
  26 of 43 columns at p=0.031. That advantage carries its all-cell Brier win, 0.7550 against 0.8108.
- It costs about 34 times less: $4.01 billed against roughly $136 for the same 300 respondents,
  because Jev bills input only and its output is free.
  [How the GPT-4.1 figure is derived](docs/jev/02-planned-comparison.md).
- It answers about ten times faster per call, 0.26 s measured across all 24,596 cells against
  roughly 2.7 s inferred for GPT-4.1. The two arms' wall clocks look close only because they ran
  at different concurrency, so do not read those as a speed comparison.
- It answered every cell in all three comparison arms, 24,596 each, with no errors and no aborted
  walks. The long-persona arm hit rate limits on 8 personas, and every one cleared on retry.
- It tracks price more tightly than the respondents themselves do. The pricing block pipes a
  randomized price into each stem, and Jev's purchase probability follows it at r = −0.55 against
  the humans' −0.33, in 40 of 40 columns.

## Where it is worse

Jev loses the yes/no half, and most of that is the pricing block. I first wrote this up as
TypeSafe's documented "not a calculator" weakness. That was wrong. Measuring it gives a more useful
answer: the arithmetic is fine and the decision boundary is not.

| over the 40 pricing columns | Jev Choice | Jev Noul | GPT-4.1 | humans |
|---|---|---|---|---|
| corr(price, P(yes)) | −0.551 | −0.522 | −0.488 | −0.333 |
| mean P(yes) | 0.601 | 0.591 | 0.343 | 0.416 |
| signed bias | +0.185 | +0.175 | −0.073 | |
| columns biased high | 36/40 | 37/40 | 10/40 | |

The bias is near-constant, +0.185 asking as a `Choice` and +0.175 as a `Noul`, and on the `Noul`
arm it accounts for 95% of that arm's entire pricing error. Jev predicts a purchase far more often
than these respondents reported making one. Re-committing at a shifted threshold recovers 5.89
points of `Choice` pricing accuracy and 8.45 of `Noul`'s, while giving GPT-4.1 0.03 points, which
says the ranking is sound and only the operating point is wrong. That threshold is fitted in-sample,
so it bounds the failure rather than scoring it.
[Details](docs/jev/04-price-sensitivity.md).

## Matching the population is not the same as matching its groups

Every metric above is computed on the panel as a whole. A survey is normally read as crosstabs, and
an arm can match the overall marginal exactly while handing every demographic group the same answer.
So I measured how far apart each arm puts its segments, against how far apart the real ones are,
with a shuffled-label noise floor to say how much of the human gap is signal at all.

A ratio of 1.0 would reproduce the human gap. On party GPT-4.1 hard answer puts its groups 2.87
times as far apart as the real ones, and on race Jev Noul puts them 0.23 times as far.

The two models miss in opposite directions. GPT-4.1 spreads
Republicans and Democrats about 2.8 times further apart than they really are, on a
battery that is not about politics, which would show up as polarization that is not in the data. Jev
does the reverse everywhere else, compressing race, sex and age to a third of the real gap. That 2x
gap between the models is not an elicitation artifact: it holds at 1.79 against 0.86 when both arms
are soft.

Read the low ratios with the noise floor in hand. This holdout is a cognitive-bias battery built so
answers should not track who you are, so on most variables there is little group difference to
reproduce. [The full measurement](docs/survey/05-segment-diversity.md).

## Scope, and what would sharpen this

**The instrument.** Twin-2K-500's holdout is a cognitive-bias battery while the grounding is
personality and economic-preference content, so the test is out-of-domain by construction. Its
questions are built so that answers should not track who you are, and two independent
measurements confirm it: per-person correlation sits near zero on 15 of the 16 tasks whatever the
grounding, and human separation between demographic groups barely clears random grouping on most
variables. The instrument, more than any model, is what bounds the individual-level result, and a
holdout where person-level signal demonstrably exists is the thing that would sharpen it most.

**The sample.** 2,058 Prolific US adults, four waves, February 2025 (Toubia et al.,
[arXiv 2505.17479](https://arxiv.org/abs/2505.17479)). Not population-representative, US-only,
public since 2025, and built from classic replications, so contamination applies to every arm
equally. The 300 here are the first 300 rows and are older, whiter and more conservative than the panel.
Read the between-arm comparisons and do not read any absolute number.

**This evaluation.** 300 of 2,058 respondents. 108 of 126 holdout columns, because 18 sliders and
free-numeric items have no option list to decode against. One pinned model version. Two-option and
ordinal questions only, with multi-select untested.

**Individual-level prediction.** Every arm scores below a persona-blind leave-one-out majority
baseline of 73.59%. A demographics-grounded synthetic respondent is usable for a population's
distribution and not for predicting a specific person. That is the standing state of this field
rather than a result about Jev.

One number puts the rest in proportion: humans agree with their own earlier answers only 81.68% of
the time. [All limitations](docs/survey/06-limitations.md).

## Reproduce it

Python 3.11 or newer. Every run behind the verdict is in this repo, and scoring needs nothing
downloaded and no account.

```bash
pip install -r requirements.txt

python scripts/twin2k/prob_scoring.py score \
    --arm jev_noul=runs/jev_vs_gpt41_n300/jev_noul.jsonl \
    --arm jev=runs/jev_vs_gpt41_n300/jev_choice.jsonl \
    --arm bc=runs/jev_vs_gpt41_n300/gpt41_probs.jsonl \
    --bootstrap 1000 --seed 20260919 --ece-bins 10 \
    --out /tmp/check.json
```

That reproduces [`reports/jev_vs_gpt41_n300/score_with_noul.json`](reports/jev_vs_gpt41_n300/score_with_noul.json), which holds every
figure quoted above for Jev Choice, Jev Noul and GPT-4.1 probabilities. The described arm, the
hard-answer arm and the segment table come from the other reports listed in
[`reports/`](reports/README.md). Two fields will not match byte for byte: each arm's `path`, which records
where the file was read from and in the shipped report still names the working directory the run was
scored in, and occasionally the last digit of a p-value, which moves with the platform's
floating-point rounding.

The price diagnostic, what each step costs, credentials, and how to run or resume an arm are in
[`docs/reproducing.md`](docs/reproducing.md). [`runs/README.md`](runs/README.md) maps every run
file to the claim it supports.

## What I would do next

1. **Re-run the distribution test with `Noul`** as the elicitation fixed in advance, and fix the
   aggregation rule in advance. That choice accounts for the entire disagreement in the result
   above.
2. **More respondents.** 48 between-subject columns draw only 16 to 25 respondents at this sample
   size, which is where the per-column test is noisiest.
3. **A persona about what is being asked.** Every arm grounds in content the exam does not cover.
   The untested variant is an interview: answers related to the questions being scored. False
   consensus is the existence proof — the one task where the persona bears on the question, and the
   one with real per-person signal. [The full list](docs/jev/08-what-this-licenses.md#what-to-run-next).

Describing the options was the obvious first candidate and has since been run, fixed in advance, and
[it changes nothing](docs/jev/05-option-descriptions.md): the pricing bias moved +0.185 to +0.183
and the gap did not move at all. That closes the objection that `Choice` was merely
under-specified.

[The full list](docs/jev/08-what-this-licenses.md#what-to-run-next).

## Author's take

Everything above is measured. This part is opinion, kept separate on purpose.

I think Jev is a strong option and I would use it. It costs about 34 times less, it
answered every
one of 24,596 cells without an error, it leads on the ordinal half outright, and asked as a `Noul`
it leads GPT-4.1 probabilities on the yes/no half as well. The comparison as first set up, a
`Choice` on every yes/no item, went GPT-4.1's way on the distribution gap, and that result stands.
It also held the prompt fixed to be fair to both models, which left every one of TypeSafe's own
prompting options untouched. The one I changed afterwards moved that half by more than the whole
deficit, and I expect the others to matter too.

I would use it today for ordinal-scale marginals under cost pressure, with `Noul` for anything
yes/no. What I would test next is a fresh run with `Noul` and its aggregation rule both fixed
beforehand.

## Where to go

| If you want | Go to |
|---|---|
| the visual explainer | [the GitHub Pages essay](https://jjd-lab.github.io/jev-synthetic-survey/), source in [`site/`](site/README.md) |
| the write-up, paper style, with every caveat | [`docs/`](docs/README.md): the survey track, the Jev track, the question inventory |
| every arm name, metric and report key, defined once | [the glossary](docs/README.md#names-used-throughout) |
| the crosstab view | [survey track](docs/survey/05-segment-diversity.md), and [the verdict on Jev](docs/jev/07-segment-diversity.md) |
| what richer grounding buys | [06 Grounding](docs/jev/06-grounding.md) |
| what the result supports, and what to run next | [08 What this licenses](docs/jev/08-what-this-licenses.md) |
| to re-derive every number yourself, no account needed | [Reproduce it](#reproduce-it), then [`reports/`](reports/README.md) |
| to re-run the arms themselves, command by command | [`docs/reproducing.md`](docs/reproducing.md) |
| the raw per-cell answers, model beside human | [`runs/`](runs/README.md) |
| the arm configurations, and which run each produced | [`configs/twin2k/`](configs/twin2k/README.md) |
| the code: scorer, Jev probe, survey engine | [`scripts/twin2k/`](scripts/twin2k/README.md), [`src/`](src/), [`main.py`](main.py) |
| the tests | [`tests/`](tests/): `pytest`, offline, no network |

`src/` and `main.py` are adapted from a private survey-simulation codebase, which is why they carry
machinery this evaluation does not exercise.

## How to cite

> Jev on a synthetic survey: does a native probability vector beat a verbalized one? 2026.
> https://github.com/jjd-lab/jev-synthetic-survey

[`CITATION.cff`](CITATION.cff) carries the same in machine-readable form, which is what GitHub's
"Cite this repository" button reads.

The dataset is not mine. Cite it as Toubia, O., et al. *Twin-2K-500*,
[arXiv 2505.17479](https://arxiv.org/abs/2505.17479).

## License

Code and write-up are [MIT](LICENSE).

Twin-2K-500 is CC BY 4.0 and is not redistributed here; `fetch_twin2k.py` downloads it from the
source. The files under [`runs/`](runs/) are derived outputs that carry that dataset's human answers
alongside each model answer, and are redistributed under the same CC BY 4.0 terms with attribution
to its authors.
