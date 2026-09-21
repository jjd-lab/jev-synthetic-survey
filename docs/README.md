# Documentation

Two tracks. The survey track holds what I learned about simulating this survey with a language
model, which transfers to any model you point at it. The Jev track holds the evaluation of one
specific model and the verdict on it.

## Survey track

| Page | What it covers |
|---|---|
| [01 Dataset and instrument](survey/01-dataset-and-instrument.md) | Twin-2K-500: who the respondents are, the 108 scored questions, the 16 tasks, the human ceiling, and how this setting differs from the paper's |
| [02 Metrics](survey/02-metrics.md) | every measure used in both tracks, defined once, and the equal-weight-per-task rule |
| [03 Grounding panel](survey/03-grounding-panel.md) | experiment 1: what persona content buys you, GPT-4.1 over all 2,058 respondents |
| [04 Elicitation effects](survey/04-elicitation-effects.md) | how you ask changes what the model answers, and the structured-output failures that follow |
| [05 Segment diversity](survey/05-segment-diversity.md) | do the demographic segments of a synthetic panel differ the way real ones do? Flattening on most variables, caricature on politics |
| [06 Limitations](survey/06-limitations.md) | what this instrument and sample cannot tell you, whatever model you run |

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
| [05 Option descriptions](jev/05-option-descriptions.md) | experiment 4: does prompting Jev TypeSafe's way close the gap? Fixed in advance, and it does not |
| [06 Grounding](jev/06-grounding.md) | experiment 5: replace 14 demographic fields with 620 of the respondent's own prior answers. Both models gain per-person signal, in the same direction |
| [07 Segment diversity](jev/07-segment-diversity.md) | does Jev reproduce the differences between demographic groups? It flattens them, worse by task than by variable |
| [08 What this licenses](jev/08-what-this-licenses.md) | what the result supports, what it does not, and what to run next |

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
| the distribution test | C3, `c3_left_wins` | Jev's answer probabilities match the human answer distribution at least as well as GPT-4.1's stated probabilities do |
| the calibration test | C1 | Jev's calibration error on the yes/no questions is at most 0.05 |
| Jev Choice | `jev_chained`, `jev`, `jev_choice`; `jc` in a filename | Jev asked to pick among the listed options |
| Jev Noul | `jev_noul_chained`, `jev_noul`, `jev_demographics`; `nc` in a filename | Jev asked for one probability that the answer is yes, with no options offered, on the 65 two-option columns; `Choice` on the other 43 |
| Jev Choice described | `jev_choice_described`, `jev_described` | Jev Choice with a description attached to each option |
| GPT-4.1 probabilities | `gpt41_probs_chained`, `gpt41_probs`, `bc` | GPT-4.1 asked to state a probability for each option |
| GPT-4.1 hard answer | `gpt41_hard_chained`, `gpt41_hard`, `ac` | GPT-4.1 asked to pick one option, no probabilities |
| Jev Noul, stateless | `jev_noul_demog_stateless`, `jev_demog_stateless` | the same 14-demographic persona, each question asked on its own |
| Jev Noul, 620 prior answers | `jev_noul_prior_answers`, `jev_prior_answers` | the persona is 620 of the respondent's own earlier answers, stateless |
| the GPT-4.1 panel arms | `arm1`, `chained`, `prior_answers` | demographics stateless, demographics stateful, and 620 prior answers, over all 2,058 respondents. `arm1` was named before the arms were |
| stateful | `chained` | the model sees its own earlier answers as it works through the questionnaire |
| stateless | | the model never sees its own earlier answers; each question is asked on its own |
| a cell | | one respondent answering one question |
| the distribution gap | `soft_nominal` | soft total variation distance on the 65 two-option columns |
| the ordinal distribution gap | `soft_ordinal` | soft Wasserstein-1 on the 43 multi-option columns |
| | `wilcoxon_p_left_lower` | one-sided p that the first-named arm is lower, per column |
| | `path` | where the scorer read the run from on the machine that scored it, such as `outputs\twin2k\...`; not a location in this repo |

`c3_left_wins` is a sign check on the deltas. The test itself is the per-column Wilcoxon within each
half, which is why the two can disagree; see [the Noul follow-up](jev/03-noul-follow-up.md).

Jev's two elicitation primitives keep their TypeSafe names, `Choice` and `Noul`, because that is
what the API calls them: a `Choice` picks among options and is relative to them, a `Noul` returns
one absolute probability that a statement is true.

## Where the evidence is

[`runs/README.md`](../runs/README.md) maps every run file to the claim it supports.
[`reports/README.md`](../reports/README.md) maps every scored report back to the runs it came from
and the command that regenerates it.
