# Pre-launch review, 21 September 2026

A review of this repository before it was made public: the code, the write-up, the numbers and the
site. It records what was checked, what was wrong, what was changed, and what was deliberately left
alone. It was carried out with an AI coding assistant; every finding acted on was first confirmed
against the code or the scored report it concerns.

## How it was done

Three read-only passes, over the Python, the written content and the static site, produced
candidate findings. Each one acted on was then re-checked directly: a quoted number against the
report JSON it cites, a code claim against the file, a site claim against a rendered page. Several
candidates did not survive that check and are listed at the end.

## What was sound

The numerical core. About 45 figures quoted across the README and the Jev track were traced to a
key in a shipped report and matched exactly, including every paired delta, interval and p-value in
the planned comparison and the Noul follow-up. The repository had no secrets, no personal paths, no
commented-out code and no TODO markers. Tests run offline. Analyses done after seeing a result are
labelled as such on the page that reports them, and `docs/timeline.md` dates each run.

## Findings, and what changed

### Numbers

| Where | Was | Report says | Now |
|---|---|---|---|
| README segment table, political views | 1.20 and 2.64 | 1.2258 and 2.6818 | the README copy is gone; the survey page holds the table |
| README segment table, party | 1.14 and 2.42 | 1.3456 and 2.8725 | same |
| README segment table, race, GPT-4.1 | 0.69 | 0.6821 | same |
| grounding page, collapsed columns, chained demographics | 25 | 23 | 23, and "22 up to 25" reads "22 to 23" |
| site, persona-blind floor in the 2,058-respondent chapter | 73.59% | 73.27% (73.59 is the 300-respondent floor) | 73.27% |
| site, GPT-4.1's spread on politics | about 2.7× | 2.777 | 2.8× |
| README, docs, tokens per cell paired with Jev Choice's cost | 3,891 | 3,882 for Choice; 3,891 is Noul's | attributed to Noul, with its cost |
| grounding page, largest prompt | 22,589 tokens | billed input runs 23,096 to 24,838 per cell | quoted from the billed rows |

**The grounding gain.** The site and two pages said 620 prior answers improved Jev's per-person
signal "by twice as much" as GPT-4.1's. Recomputed with the exporter's own method, that holds on
the 12 tasks measurable in all three Jev arms (+0.0246 against +0.0123) and not on the 13 tasks
measurable in the two arms actually being compared (+0.0113). One task, Omission bias, moves the
ratio from 2.0 to 0.9. The write-up now stands on the 13-task basis, says the two gains are the same
size, keeps the 2×2 on its own 12-task basis with that stated, and says the direction is the
finding and the size is not.

Two definitions were colliding. "Blind spot" meant an under-used option on the metrics page and a
zero-probability cell on the grounding page; the second is now called a zero-probability cell. The
two-option Brier is on a 0 to 1 scale while the page defining Brier gave only the 0 to 2 scale; both
are now stated.

### Story and disclosure

- "Beats GPT-4.1 on all six measures" is true against GPT-4.1 probabilities. GPT-4.1 hard answer
  scores 69.32% accuracy against Jev Noul's 67.28%. Every statement of the claim now names the
  opponent, and the accuracy point and the per-column rule sit beside it.
- The social card read "REJECT" under a page reading "6–0". It now leads with the finding, and
  `site/assets/og.html` is its source.
- There was no statement of who wrote this or of any relationship to TypeSafe or OpenAI. There is
  now, in the README, the site and `CITATION.cff`.
- Vocabulary implying the criteria had been lodged with an outside body is gone. What was done is
  stated in plain words: written down before the runs, not independently timestamped.
- One voice, first person singular.

### Structure

Conclusions now come last in both tracks. The README went from about 470 lines to about 350 by
moving its operator manual into `docs/reproducing.md`, merging two navigation tables, and dropping
its copy of the segment table. The glossary in `docs/README.md` was rebuilt from the keys the
reports actually use, which differ by file for the same arm. Two grounding reports and one run that
no README listed are listed.

### Site

`site/data/figures.json` was caught by a `data/` ignore rule written for the dataset, so the first
successful deploy would have shown an error in every chart slot. It is committed and a test fails if
it goes stale. Charts had no accessible name; they have one. Chart titles measured 2.6 to 3.0:1 on
the light chapters; they clear 5:1. The walkthrough's tabs have the semantics and keyboard behaviour
of tabs. The palette is defined once.

### Code

A package docstring calling this a hackathon MVP, a fallback model id naming a different vendor's
model, four parameters on the persona builder that nothing used, `--help` text and comments
describing an execution mode that no longer exists, and a test marker that guarded no test. All
removed. `.githooks/pre-push` now refuses any ref but `main`.

## The guards added

- `tests/unit/test_published_numbers.py` checks every number on the site tagged with a `data-fig`
  path, and named rows of the write-up's tables, against the scored reports. Run before any fix, it
  failed on exactly the errors above.
- `tests/unit/test_links.py` resolves every link into the repository against the files git tracks.
  It reproduced the `figures.json` problem, and later caught a reference a bulk rename missed.
- `test_committed_figures_are_a_fresh_export` fails when a report changes and the export was not
  re-run.

They do not cover numbers in free prose in the markdown. Fewer copies is the mitigation.

## Deliberately left

- **Report files and their arm labels.** The labels are in every raw run row, some reports cannot be
  re-derived here, and the documented reproduce commands depend on them. The glossary decodes them.
- **The `excel_file` config key and the `excel_*` module names.** The four configs are the
  provenance of shipped runs, and the loader does read both CSV and xlsx. A mechanical rename of
  the modules is a candidate for later.
- **Line endings.** About 43 source and test files use CRLF and the rest LF, with no
  `.gitattributes`. Normalising touches every line of those files and many report files.
- **Lint scope.** Ruff selects `F` and `E9` only, so `line-length` is not enforced and about 280
  lines exceed it; the `# noqa` comments target rules that are not selected.
- **Figures with no stored report.** Price sensitivity, saturation rates, the coherence table and
  the run-to-run noise floors are printed by scripts. The pages now say so.
- **No intervals on the segment ratios or the price table**, and no correction for multiple
  comparisons anywhere. The metrics page now states this.
- **README length.** About 350 lines against a target of 220; the remainder is findings prose.
- **Site.** No axes on the charts, the price chart plots means where its caption argues slope, gold
  marks both prior-answers grounding and Jev Noul, webfonts load from a third party, the phone
  chapter strip scrolls sideways with no cue, and there is no structured data or per-figure anchor.
- **Dead but harmless.** `src/validation/validation_pairs.py` has only a test caller;
  `PersonaConfig.source` and `persona_temperature` are read by nothing but set in shipped configs.

## Candidates that did not survive checking

- "No errors" was reported as contradicted by eight aborted personas. The comparison arms recorded
  zero errors; the aborts were rate limits on the long-persona arm and cleared on retry. The claim
  was kept and its arm count corrected.
- Six different persona sizes were reported as inconsistent. They are different quantities under
  different tokenizers. One sentence now says what the billed figure includes.
- A chart was reported as dropping a muted style by accident. The hard-answer arm is muted where it
  has no probability vector and shown at full strength on accuracy, which it wins. Left as is.
- The live site was reported as broken. Nothing was live: the repository was private and Pages had
  never been enabled. The defect was real and would have appeared on the first deploy.

Back to [the documentation index](../README.md).
