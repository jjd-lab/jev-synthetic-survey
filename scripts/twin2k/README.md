# `scripts/twin2k/`

Every script here takes `--help`. Run them from the repo root, not from this directory.

Most readers need two of them: `prob_scoring.py` to reproduce the published numbers, and
`fetch_twin2k.py` only if they also want the price diagnostic. The rest are here because the
evaluation used them, not because reproducing it requires them.

## Scoring, which needs no credentials and no download

| Script | What it does |
|---|---|
| [`prob_scoring.py`](prob_scoring.py) | the scorer behind every figure in the write-up. `score` reads one or more arms and emits the distribution gaps, calibration, Brier and accuracy; `convert` turns a run workbook into per-cell JSONL |
| [`paper_accuracy.py`](paper_accuracy.py) | scores an arm with the *paper's* accuracy definition instead of this repo's, so the two can be read against each other |
| [`individual_signal.py`](individual_signal.py) | per-task individual-level correlation, for the question of whether an arm predicts a person rather than a population |
| [`segment_diversity.py`](segment_diversity.py) | whether an arm's demographic segments differ from each other the way the humans' do, against a shuffled-label noise floor |
| [`price_sensitivity.py`](price_sensitivity.py) | the pricing diagnostic: whether an arm's purchase probability tracks the price it was shown. The only scoring script that needs the dataset, for the per-respondent prices |

## Collecting a new arm, which needs credentials

| Script | What it does |
|---|---|
| [`probe_jev.py`](probe_jev.py) | walks personas through Jev and records a probability vector per cell. Resumes from its own output, per persona. Refuses any config outside `configs/twin2k/` and any endpoint that is not TypeSafe |
| [`jev_client.py`](jev_client.py) | the only place that knows TypeSafe's wire format. Imported by the probe rather than run directly |

The `gpt-4.1` arms are collected by [`main.py`](../../main.py) at the repo root, not from here.

## Fetching the dataset

[`fetch_twin2k.py`](fetch_twin2k.py) downloads Twin-2K-500 from Hugging Face into
`data/twin2k500/`, about 205 MB. Needed for the price diagnostic and for collecting any new arm.
The dataset is CC BY 4.0 and is not redistributed in this repo.

## Builders you will not normally run

These regenerate tracked files under `configs/twin2k/` from the dataset's own question catalog.
They exist so the mappings and the variant configs cannot drift from each other by hand. They
refuse stray arguments, because a bare `--help` probe used to rewrite the files they own.

| Script | Regenerates |
|---|---|
| [`build_twin2k_config.py`](build_twin2k_config.py) | the question and demographic mapping JSONs |
| [`build_twin2k_persona.py`](build_twin2k_persona.py) | the prior-answer persona mapping |
| [`build_twin2k_variants.py`](build_twin2k_variants.py) | the three variant configs, derived from the baseline so the shared prompt stays identical |
| [`export_site_data.py`](export_site_data.py) | headline series for the [visual explainer](../../site/README.md), read from `reports/` |

Back to [the repo overview](../../README.md), or to [the write-up](../../docs/README.md) for what
these scripts were used to measure.
