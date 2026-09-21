# Visual explainer

A static essay for GitHub Pages. It keeps Jev as the hero, then teaches the
synthetic-survey idea and, from the `gpt-4.1` Twin-2K n=2058 panel, the ceiling
and floor the comparison is read against. Every chart is drawn from
[`data/figures.json`](data/figures.json), which is generated from `reports/` —
the page never loads the JSONL dumps. The numbers typed into the prose carry a
`data-fig` path into that file, and `tests/unit/test_published_numbers.py` fails
if one drifts from it.

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
