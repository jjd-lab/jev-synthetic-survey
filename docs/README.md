# Documentation

Two tracks. The survey track holds what we learned about simulating this survey with a language
model, which transfers to any model you point at it. The Jev track holds the evaluation of one
specific model and the verdict on it.

## Survey track

| Page | What it covers |
|---|---|
| [01 Dataset and instrument](survey/01-dataset-and-instrument.md) | Twin-2K-500: who the respondents are, the 108 scored questions, the 16 tasks, the human ceiling, and how this setting differs from the paper's |
| [02 Metrics](survey/02-metrics.md) | every measure used in both tracks, defined once, and the equal-weight-per-task rule |
| [03 Grounding panel](survey/03-grounding-panel.md) | experiment 1: what persona content buys you, GPT-4.1 over all 2,058 respondents |
| [04 Elicitation effects](survey/04-elicitation-effects.md) | how you ask changes what the model answers, and the structured-output failures that follow |
| [05 Limitations](survey/05-limitations.md) | what this instrument and sample cannot tell you, whatever model you run |
| [06 Segment diversity](survey/06-segment-diversity.md) | do the demographic segments of a synthetic panel differ the way real ones do? Flattening on most variables, caricature on politics |

## Reproducing

| Page | What it covers |
|---|---|
| [Reproducing the runs](reproducing.md) | the command behind every artifact in `runs/`, its prerequisites, and what a re-run will not match |

## Jev track

| Page | What it covers |
|---|---|
| [01 Question and criteria](jev/01-question-and-criteria.md) | what was asked of Jev, and the two tests written down before the runs |
| [02 The planned comparison](jev/02-planned-comparison.md) | experiment 2: Jev Choice against GPT-4.1, and the verdict |
| [03 The Noul follow-up](jev/03-noul-follow-up.md) | experiment 3: re-asking the yes/no questions a different way. Built after seeing the result, and it cannot change the verdict |
| [04 Price sensitivity](jev/04-price-sensitivity.md) | the largest single effect measured: Jev reads price harder than humans do, at the wrong operating point |
| [05 What this licenses](jev/05-what-this-licenses.md) | what the result supports, what it does not, and what to run next |
| [06 Option descriptions](jev/06-option-descriptions.md) | experiment 4: does prompting Jev TypeSafe's way close the gap? Pre-registered, and it does not |

[Appendix: question inventory](appendix-question-inventory.md) lists all 108 columns and the 16
tasks they belong to.

## The order the work was done

The grounding panel came first, then the planned comparison, then the Jev Noul re-ask, which was
built only after seeing that Jev had lost the yes/no half. The diagnostics were run over runs
already collected.

That order is why only the planned comparison carries the verdict. [The timeline](timeline.md)
gives each run with the artifact that dates it.

## Names used throughout

The runs and the scored reports use short internal codes. The pages use plain names. This table is
the only place both appear, so that a number in a report file can be traced back to a sentence.

| In the prose | In `runs/` and `reports/` | What it is |
|---|---|---|
| the distribution test | C3 | Jev's answer probabilities match the human answer distribution at least as well as GPT-4.1's stated probabilities do |
| the calibration test | C1 | Jev's calibration error on the yes/no questions is at most 0.05 |
| Jev Choice | `JC`, `jev_chained` | Jev asked to pick among the listed options |
| Jev Noul | `NC`, `jev_noul_chained` | Jev asked for one probability that the answer is yes, with no options offered |
| GPT-4.1 probabilities | `BC`, `gpt41_probs_chained` | GPT-4.1 asked to state a probability for each option |
| GPT-4.1 hard answer | `AC`, `gpt41_hard_chained` | GPT-4.1 asked to pick one option, no probabilities |
| stateful | `chained` | the model sees its own earlier answers as it works through the questionnaire |
| stateless | | the model never sees its own earlier answers; each question is asked on its own |
| a cell | | one respondent answering one question |

Jev's two elicitation primitives keep their TypeSafe names, `Choice` and `Noul`, because that is
what the API calls them: a `Choice` picks among options and is relative to them, a `Noul` returns
one absolute probability that a statement is true.

## Where the evidence is

[`runs/README.md`](../runs/README.md) maps every run file to the claim it supports.
[`reports/README.md`](../reports/README.md) maps every scored report back to the runs it came from
and the command that regenerates it.
