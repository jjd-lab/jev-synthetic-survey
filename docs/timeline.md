# What ran, in what order

The order matters for reading the claims, because one arm was built after seeing another's result
and cannot carry a test fixed in advance. Every date below is the timestamp on the artifact the run
produced, so it is checkable rather than asserted.

| When | What ran | n | Artifact |
|---|---|---|---|
| 3 Sep 2026 | pilot of the stateful demographics arm, 50 respondents | 50 | not shipped; its content-filter errors are in `runs/gpt41_panel_n2058/content_filter_errors/` |
| 4 Sep, 08:04 | first full run of the stateless demographics arm, superseded | 2,058 | not shipped; its content-filter errors are kept |
| 4 Sep, 09:15 | **demographics, stateless** | 2,058 | `runs/gpt41_panel_n2058/demographics_stateless/` |
| 4 Sep, 13:16 | **demographics, stateful** | 2,058 | `runs/gpt41_panel_n2058/demographics_stateful/` |
| 6 to 8 Sep | **prior answers, stateless**, resumed across six sessions under a daily spend cap | 2,058 | `runs/gpt41_panel_n2058/prior_answers_stateless/`, one `run_tokens_*.json` per resumption |
| 19 Sep, 10:59 | 5-respondent trial of the GPT-4.1 probabilities arm | 5 | not shipped; it is the trial whose −3.4 pt accuracy signal did not survive |
| 19 Sep, 11:22 | **GPT-4.1 probabilities** | 300 | `runs/jev_vs_gpt41_n300/gpt41_probs_source/` |
| 19 Sep, morning | **Jev Choice**, the arm the two tests were fixed on | 300 | `runs/jev_vs_gpt41_n300/jev_choice.jsonl` |
| 19 Sep, evening | **Jev Noul**, built after seeing Jev Choice lose the yes/no half | 300 | `runs/jev_vs_gpt41_n300/jev_noul.jsonl` |
| 19 to 20 Sep | diagnostics over runs already collected: price sensitivity, the elicitation cost, the instrument's own noise | | `reports/` |
| 20 Sep | **Jev Choice described**, the first arm whose criteria were committed to this repository before it ran | 300 | `runs/jev_vs_gpt41_n300/jev_choice_described.jsonl` |

The described arm is the one exception to the timestamping caveat below: its rule and its criteria
were committed at `390c51c`, before the code that implements it and before any of its data existed.

`runs/jev_vs_gpt41_n300/` holds five files but only four runs. The GPT-4.1 hard-answer file is not
a run of its own: it is the first 300 respondents of the 4 September stateful panel run, extracted,
with all 24,596 cells identical.

## What this means for reading the result

The two tests were fixed on **Jev Choice against GPT-4.1 probabilities**, and only that pair carries
the verdict. Everything after it is labeled as what it is:

- **Jev Noul is post hoc.** It was built in response to a result, so it explains the verdict without
  being able to overturn it. The fair version is a fresh run with `Noul` registered as the
  elicitation and the aggregation rule fixed beforehand.
- **The hard-answer arm is a sanity check**, not a comparator. It has no probability vector.
- **The diagnostics are post hoc by construction.** They were run over data already collected, and
  the price threshold in particular is fitted on the same cells it is scored on.

The criteria themselves were written down before the Jev runs, in a working plan that is not
published because it discusses unrelated private surveys. Nothing in this repository's history
independently timestamps them, since the repository was created after the runs finished. Treat
"fixed in advance" as the authors' account, supported by a scorer that implements exactly those
rules and by both tests being reported as failed. It is not an external registration, and the pages
here avoid calling it one.
