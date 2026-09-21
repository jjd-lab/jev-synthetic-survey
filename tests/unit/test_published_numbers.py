"""Numbers typed by hand into the site and the write-up must match the scored reports.

Two copies of one table drifted apart once, and a caption quoted a different figure from the
chart beneath it. Nothing here generates prose; it only reads what was typed and compares.

  * Site: a number wrapped in `<span data-fig="dotted.path">` is looked up in the export.
  * Markdown: a named row of a named table is compared cell by cell.

The typed text sets the precision: "73.27%" is checked to two places, "0.1045" to four.
"""

import importlib
import json
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
REPORTS = REPO_ROOT / "reports"

DATA_FIG = re.compile(r'data-fig="([^"]+)"[^>]*>([^<]+)<')
NUMBER = re.compile(r"-?\d[\d,]*\.?\d*")


@pytest.fixture(scope="module")
def figures():
    scripts_dir = REPO_ROOT / "scripts" / "twin2k"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    return importlib.import_module("export_site_data").build_figures()


def report(relative: str) -> dict:
    return json.loads((REPORTS / relative).read_text(encoding="utf-8"))


def matches(typed: str, value: float) -> bool:
    text = NUMBER.search(typed).group().replace(",", "")
    places = len(text.split(".")[1]) if "." in text else 0
    return round(value, places) == float(text)


def lookup(figures: dict, dotted: str) -> float:
    node = figures
    for key in dotted.split("."):
        node = node[key]
    return node


def test_every_tagged_number_on_the_site_matches_the_export(figures):
    html = (REPO_ROOT / "site" / "index.html").read_text(encoding="utf-8")
    tagged = DATA_FIG.findall(html)
    assert tagged, "no data-fig spans found; the site's numbers are unguarded"
    wrong = [f"{path}: typed {typed!r}, export has {lookup(figures, path)}"
             for path, typed in tagged if not matches(typed, lookup(figures, path))]
    assert not wrong, "\n".join(wrong)


def table_row(markdown: str, header_contains: str, label: str) -> list[str]:
    """Numeric cells of the row whose first cell is `label`, in the table under that header."""
    lines = markdown.splitlines()
    start = next(i for i, line in enumerate(lines)
                 if line.startswith("|") and header_contains in line)
    for line in lines[start + 2:]:
        if not line.startswith("|"):
            break
        cells = [c.strip().replace("`", "").replace("*", "") for c in line.strip("|").split("|")]
        if cells[0].startswith(label):
            return [c for c in cells[1:] if NUMBER.fullmatch(c.lstrip("~$").rstrip("%"))]
    raise AssertionError(f"no row {label!r} under a header containing {header_contains!r}")


def arm_row(figures: dict, arm: str) -> list[float]:
    a = figures["comparison"]["arms"][arm]
    return [a["soft_nominal"], a["soft_ordinal"], a["ece"], a["brier"], a["accuracy_pct"]]


def across_arms(figures: dict, key: str) -> list[float]:
    arms = figures["comparison"]["arms"]
    return [arms[a][key] for a in ("jev_choice", "gpt41_probs", "gpt41_hard", "jev_noul")]


def segment_ratios(variable: str) -> list[float]:
    arms = report("jev_vs_gpt41_n2058/segment_diversity_n2058.json")["arms"]
    return [arms[a]["by_variable"][variable]["separation_ratio"] for a in ("jev_noul", "gpt41_hard")]


def collapsed(relative: str, arm: str) -> int:
    return len(report(relative)["arms"][arm]["fidelity"]["collapsed_columns"])


SEGMENT_VARIABLES = {"political views": "demo_political_views", "party": "demo_party",
                     "race": "demo_race", "sex": "demo_sex", "age": "demo_age",
                     "religion": "demo_religion"}


def segment_rows() -> list[tuple[str, str, str, list]]:
    """The ratio table appears twice: in full on the survey page, as ratios only on the Jev page."""
    rows = []
    for label, variable in SEGMENT_VARIABLES.items():
        jev, gpt = segment_ratios(variable)
        rows.append(("docs/jev/07-segment-diversity.md", "GPT-4.1 hard ratio", label, [jev, gpt]))
        # survey page columns: humans, noise floor, Jev separation, ratio, GPT-4.1 separation, ratio
        rows.append(("docs/survey/05-segment-diversity.md", "| Variable | humans", label,
                     [None, None, None, jev, None, gpt]))
    return rows


def published_rows(figures: dict) -> list[tuple[str, str, str, list[float]]]:
    grounding = "jev_grounding_n300/score_grounding.json"
    clean = "jev_grounding_n300/score_grounding_clean.json"
    return segment_rows() + [
        ("README.md", "| Arm |", "Jev Choice (", arm_row(figures, "jev_choice")),
        ("README.md", "| Arm |", "Jev Noul", arm_row(figures, "jev_noul")),
        ("README.md", "| Arm |", "GPT-4.1 probabilities", arm_row(figures, "gpt41_probs")),
        ("README.md", "| Arm |", "GPT-4.1 hard answer", arm_row(figures, "gpt41_hard")),
        ("docs/jev/06-grounding.md", "demographics, chained", "collapsed columns",
         [collapsed(grounding, "jev_demographics"), collapsed(clean, "jev_demog_stateless"),
          collapsed(clean, "jev_prior_answers")]),
        ("docs/jev/02-planned-comparison.md", "| Measure", "accuracy (from the vector)",
         across_arms(figures, "accuracy_pct")),
        ("docs/jev/02-planned-comparison.md", "| Measure", "distribution gap, 65",
         across_arms(figures, "soft_nominal")),
        ("docs/jev/02-planned-comparison.md", "| Measure", "ordinal distribution gap",
         across_arms(figures, "soft_ordinal")),
        ("docs/jev/02-planned-comparison.md", "| Measure", "calibration error",
         across_arms(figures, "ece")),
    ]


def test_published_tables_match_the_reports(figures):
    wrong = []
    for relative, header, label, expected in published_rows(figures):
        typed = table_row((REPO_ROOT / relative).read_text(encoding="utf-8"), header, label)
        assert len(typed) >= len(expected), f"{relative} | {label} | row is missing cells"
        for cell, value in zip(typed, expected, strict=False):
            if value is not None and not matches(cell, value):
                wrong.append(f"{relative} | {label} | typed {cell}, report has {value:.4f}")
    assert not wrong, "\n".join(wrong)
