"""Tests that the generated Twin-2K-500 arm configs still match their generator.

`prior_answers_stateless.yaml`, `_chained.yaml` and `_probs_chained.yaml` are written
by `scripts/twin2k/build_twin2k_variants.py`, and AGENTS.md forbids hand-editing them: the arms
are read as a difference, so an edit to one file confounds the comparison invisibly.

The prohibition alone did not hold. `prior_answers` accumulated four hand-edited settings
(`memory_mode: full`, `chain_own_answers`, `batch_grids`, `max_concurrency`) that the generator
knew nothing about, and nothing complained -- because a hand-edit is only punished the next time
somebody regenerates, which nobody had done. Running the script then would have rewritten the
arm as a stateless near-duplicate of the baseline and silently changed the experiment.

So the invariant is asserted here instead of trusted: for each variant, the generator's output
must equal the file on disk BYTE for byte. Byte, not line, because the substitutions add lines
and a lone LF among CRLF lines is exactly the mistake the generator sniffs newlines to avoid.

The failure this catches reads as "you hand-edited a generated file, or you changed the baseline
without re-running the generator" -- and the fix for both is to move the setting into the
script's substitution table and re-run it.
"""

import importlib
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "scripts" / "twin2k"


@pytest.fixture(scope="module")
def generator():
    """Import the generator as a module, with the repo root as cwd for its relative BASELINE."""
    sys.path.insert(0, str(SCRIPTS))
    try:
        module = importlib.import_module("build_twin2k_variants")
        yield importlib.reload(module)
    finally:
        sys.path.remove(str(SCRIPTS))


def _read_exact(path: Path) -> str:
    # newline="" so the file's own line endings survive the read; normalising them here would
    # make the comparison pass on a mismatch the generator is specifically written to prevent.
    with open(path, encoding="utf-8", newline="") as handle:
        return handle.read()


@pytest.fixture(scope="module")
def baseline_text(generator) -> str:
    return _read_exact(REPO_ROOT / generator.BASELINE)


@pytest.mark.parametrize("variant", ["prior_answers_stateless", "demographics_stateful", "gpt41_probs"])
def test_the_generated_config_matches_the_generator(generator, baseline_text, variant):
    """The on-disk arm config is byte-identical to what the generator would write for it."""
    name, summary, substitutions = next(v for v in generator.VARIANTS if v[0] == variant)
    produced = generator.build_variant(baseline_text, name, summary, substitutions)
    on_disk = _read_exact(
        REPO_ROOT / "configs" / "twin2k" / f"{variant}.yaml"
    )
    assert produced == on_disk, (
        f"{variant}.yaml is not what the generator produces. Either it was "
        f"hand-edited (move the setting into build_twin2k_variants.py) or the baseline changed "
        f"without a re-run (run the script)."
    )


def test_every_substitution_finds_exactly_one_line_in_the_baseline(generator, baseline_text):
    """A needle matching twice would substitute both, silently; matching zero times raises."""
    for name, _summary, substitutions in generator.VARIANTS:
        for find, _replace in substitutions:
            assert baseline_text.count(find) == 1, (
                f"{name}: {find!r} occurs {baseline_text.count(find)} times in the baseline, "
                f"expected exactly 1"
            )


def test_the_arms_differ_only_where_the_generator_says_they_do(generator):
    """The loaded arms differ on the substituted settings, and agree on the survey prompt."""
    from src.core.config_loader import load_survey_config

    arms = {
        name: load_survey_config(
            str(REPO_ROOT / "configs" / "twin2k" / f"{filename}.yaml")
        )
        for name, filename in [
            ("baseline", "demographics_stateless"),
            ("prior_answers", "prior_answers_stateless"),
            ("chained", "demographics_stateful"),
            ("probs_chained", "gpt41_probs"),
        ]
    }
    # The 60-line prompt is the thing generation exists to keep identical.
    prompts = {arm.survey_prompt for arm in arms.values()}
    assert len(prompts) == 1, "the arms' survey_prompt has drifted -- re-run the generator"

    # And the cache-routing flag is the prior_answers arm's alone, so no other arm inherits a
    # cost optimisation it has not measured.
    assert arms["prior_answers"].prompt_cache_key_by_respid is True
    assert arms["baseline"].prompt_cache_key_by_respid is False
    assert arms["chained"].prompt_cache_key_by_respid is False
    assert arms["probs_chained"].prompt_cache_key_by_respid is False


def test_probs_chained_differs_from_chained_in_exactly_three_settings():
    """The Jev comparator, and the three flags that make it comparable to the Jev probe.

    Each one is load-bearing and each one is a way the JC-vs-BC result could be about something
    other than the model:

      `response_mode`    -- the arm's whole point: verbalize a distribution instead of picking.
      `batch_grids`      -- false matches the probe one call per cell. Left at its default true, 40
                            of 108 columns would be asked as 7 batched calls, and because a grid
                            writes one COMBINED history turn, every later cell's history would
                            differ too. This is the deliberate departure from `chained`.
      `persona_cache_path` -- shares `chained`'s cache, so both arms walk the same 300 twins rather
                            than 300 freshly generated ones.

    Asserted against `chained` rather than in isolation, so a future flag added to one and not the
    other shows up here as a difference instead of being discovered in a scored result.
    """
    from src.core.config_loader import load_survey_config

    def _load(filename):
        return load_survey_config(
            str(REPO_ROOT / "configs" / "twin2k" / f"{filename}.yaml")
        )

    chained, probs = _load("demographics_stateful"), _load("gpt41_probs")

    assert probs.response_mode == "verbalized_probs"
    assert probs.batch_grids is False
    assert probs.persona_cache_path == "runs/gpt41_panel_n2058/demographics_stateful/persona_cache.xlsx"

    assert chained.response_mode == "hard_choice"
    assert chained.batch_grids is True
    assert chained.persona_cache_path is None

    # And NOTHING else differs. Enumerating the whole config rather than a list of fields I
    # happened to think of is the point: a flag added to one arm and not the other fails here
    # instead of turning up as an unexplained gap in a scored result.
    differing = {
        field for field in type(probs).model_fields
        if getattr(probs, field) != getattr(chained, field)
    }
    assert differing == {"response_mode", "batch_grids", "persona_cache_path", "execution"}, (
        f"probs_chained vs chained differ in {sorted(differing)}; only the three elicitation "
        f"flags and `execution` (the output directory) may differ"
    )
    assert probs.execution.output_dir == "outputs/twin2k/gpt41_probs"
