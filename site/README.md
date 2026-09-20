# Visual explainer

A static essay for GitHub Pages. It keeps Jev as the hero, then teaches the
synthetic-survey idea and the `gpt-4.1` Twin-2K n=2058 panel before the
comparison. Every number is read from [`data/figures.json`](data/figures.json),
which is generated from `reports/` — the page never loads the JSONL dumps.

## View it locally

From the repo root:

```bash
python3 -m http.server 8765 --directory site
```

Then open [http://127.0.0.1:8765/](http://127.0.0.1:8765/). Opening `index.html`
as a `file://` URL will not load the figures; the browser blocks that fetch.

Regenerate the figure file after a scoring change:

```bash
python3 scripts/twin2k/export_site_data.py
```

## View it on GitHub Pages

After this repo is public and Pages is enabled (Settings → Pages → Source:
GitHub Actions), the essay is at:

https://jjd-lab.github.io/jev-synthetic-survey/

Set that URL as the repository homepage. The first deploy runs on a push to
`main` that touches `site/`, or from Actions → pages → Run workflow.

## Public launch notes

Suggested repository description:

> Does a native probability vector beat a verbalized one? Jev vs gpt-4.1 on Twin-2K-500. The registered test fails on one column of six.

Suggested topics: `synthetic-survey`, `digital-twins`, `llm`, `calibration`, `jev`.

Share the honest hook, not a win:

> A $4 decision model vs a $136 verbalized-probability run on 24,596 survey
> cells. The cheap one lost the registered test. Asking the yes/no questions a
> different way closed most of the gap.

HN / r/MachineLearning / TypeSafe will punish “Jev wins.” The write-up already
says it does not. The surprising split is the story.
