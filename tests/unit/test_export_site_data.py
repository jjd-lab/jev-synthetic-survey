"""The site figures file has to quote the same headlines as the write-up."""

import importlib
import sys

import pytest

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def exporter():
    scripts_dir = REPO_ROOT / "scripts" / "twin2k"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    return importlib.import_module("export_site_data")


def test_headlines_match_readme(exporter):
    figures = exporter.build_figures()
    arms = figures["comparison"]["arms"]
    panel = figures["panel"]["arms"]

    assert figures["verdict"] == "strong_claim_fails"
    assert round(arms["jev_choice"]["soft_nominal"], 4) == 0.1985
    assert round(arms["gpt41_probs"]["soft_nominal"], 4) == 0.1789
    assert round(arms["jev_noul"]["soft_nominal"], 4) == 0.1530
    assert round(arms["jev_choice"]["accuracy_pct"], 2) == 67.59
    assert round(arms["gpt41_probs"]["accuracy_pct"], 2) == 64.78
    assert round(arms["gpt41_hard"]["accuracy_pct"], 2) == 69.32
    assert round(panel["demographics_stateless"]["accuracy_pct"], 2) == 70.26
    assert round(panel["demographics_stateful"]["accuracy_pct"], 2) == 70.04
    assert round(panel["prior_answers_stateless"]["accuracy_pct"], 2) == 72.92
    assert panel["demographics_stateless"]["collapsed_columns"] == 24
    assert panel["demographics_stateful"]["collapsed_columns"] == 16
    assert panel["prior_answers_stateless"]["collapsed_columns"] == 25
    assert figures["comparison"]["paired_jev_choice_vs_gpt41_probs"]["c3_jev_wins"] is False


def test_write_figures_round_trips(exporter, tmp_path):
    out = tmp_path / "figures.json"
    exporter.write_figures(out)
    assert out.is_file()
    payload = exporter.load_json(out)
    assert payload["verdict"] == "strong_claim_fails"
    assert payload["comparison"]["n"] == 300
    assert payload["panel"]["n"] == 2058
