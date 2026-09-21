# What was asked of Jev, and how it would be judged

## The model

Jev, from TypeSafe, is a decision-only model. It returns a typed value and a probability vector
and generates no text at all. Version `jev-1.13.0` throughout, recorded in every record of every
run.

It offers several primitives. Two are used here:

- **`Choice`** picks among the options you give it and returns a probability for each. The
  probabilities are *relative* to the set of options offered: the question it answers is which
  option, not whether any one of them is true.
- **`Noul`** returns a single absolute probability that one statement is true. No options are
  offered and no label comes back.

That distinction turns out to matter more than anything else measured here, which is the subject
of [the Noul follow-up](03-noul-follow-up.md).

## The question

A survey firm that already simulates respondents with GPT-4.1 has to ask what it would gain by
switching. GPT-4.1 can be asked to state a probability for each option, in words, as part of its
answer. Jev returns a probability vector natively, as the thing it is built to produce.

So, narrowly:

> In the setting a new survey actually has, where you know who your respondents are but have none
> of their answers yet, does Jev's native probability vector describe the human answer
> distribution better than GPT-4.1's stated one?

"The setting a new survey actually has" pins three things: the persona holds demographics only, no
prior answers; the run is stateful, so each simulated respondent sees its own earlier answers as it
works down the questionnaire; and both models get the same input, the same questions, and the same
respondents.

## The two tests

Both were written down before the Jev runs, so that the result could not be chosen after seeing
the data. They are stated here in plain terms; the metrics are defined in
[the survey track's metrics page](../survey/02-metrics.md).

**The distribution test.** Jev's probability vectors must match the human answer distribution at
least as well as GPT-4.1's stated probabilities, *in both halves of the instrument at once*: the
65 two-option columns and the 43 multi-option columns, each judged by a Wilcoxon signed-rank test
over columns, plus a Brier score comparison over all cells with a paired bootstrap. It is a
conjunction on purpose. Winning one half and losing the other is not a win.

**The calibration test.** Jev's calibration error on the 65 two-option columns, weighted equally
across tasks, must be at most 0.05. Between 0.05 and 0.10 is marginal; above 0.10 is a failure.

The bar is not arbitrary. TypeSafe states the objective in
[`concepts/system-one.md`](https://docs.typesafe.ai/concepts/system-one.md):

> System One models are trained for calibrated decisions: their probabilities are optimized against
> outcomes to reflect uncertainty.

> Calibration is measured across groups of predictions; it does not guarantee that an individual
> answer is correct.

This test checks the first sentence on this instrument, at the level the second one names: ECE over
columns, equal weight per task, which is a group-level property rather than a claim about any one
answer. Note what is *not* claimed anywhere in the primitive pages — neither
[`choice.md`](https://docs.typesafe.ai/primitives/choice.md) nor
[`noul.md`](https://docs.typesafe.ai/primitives/noul.md) uses the word, describing the outputs only
as a probability per option and the probability that the answer is yes. A model that ranks options
correctly but whose probabilities are compressed would fail this test while remaining useful.

The verdict follows mechanically from the two:

| Outcome | Meaning |
|---|---|
| both pass | Jev's native vector beats verbalized elicitation in the production setting |
| distribution test passes, calibration marginal | usable for population and segment distributions, not for individuals |
| distribution test fails | the native vector is no better than the verbalized one; stay with what is already in use |

## What the tests were read on

Both were registered on **Jev Choice against GPT-4.1 probabilities**, and that pair alone carries
the verdict. Two other arms exist and neither is a comparator:

- **GPT-4.1 hard answer** has no probability vector at all, so any Brier or calibration number
  scored against it measures "has a distribution at all" rather than how good the distribution is.
  It is a loose sanity check on accuracy.
- **Jev Noul** was built after seeing Jev Choice lose the yes/no half. It is a follow-up, reported
  as one, and it was never eligible to carry a test fixed in advance.

## A note on the phrase "pre-registered"

The criteria above were fixed in writing before any Jev run, in a working plan. That plan is not
published: it discusses two unrelated private surveys at length, and nothing in it beyond these
criteria bears on this result. Nothing in this repository's history independently timestamps them
either, since the repository was created after the runs finished.

So treat "written down in advance" as what it is: a claim made by the authors, supported by the
internal consistency of the scorer, which implements exactly these rules and nothing more, and by
the fact that both tests were reported as failed. It is not an external pre-registration on a
registry, and the pages here avoid calling it one.

## Reproduce

The criteria are implemented in
[`scripts/twin2k/prob_scoring.py`](../../scripts/twin2k/prob_scoring.py) and nowhere else. Its
module docstring restates them, and
[`tests/unit/test_twin2k_prob_scoring.py`](../../tests/unit/test_twin2k_prob_scoring.py) checks
that the thresholds in the code are the ones above.
