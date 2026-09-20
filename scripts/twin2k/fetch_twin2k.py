"""Fetch the Twin-2K-500 files this project needs from Hugging Face.

Twin-2K-500 (LLM-Digital-Twin/Twin-2K-500) is a public, ungated, CC BY 4.0
dataset of 2,058 US respondents who answered a ~500-item battery across four
waves. `wiki/topics/public-survey-data-analogues.md` picked it as the public
analogue of a real survey validation because it is respondent-level and mixes
single- and multi-select formats — the two things the validation needs.

Three small files carry the instrument and the human answers (~26 MB). The
`wave_split/` parquet chunks (~189 MB) are also needed, for one reason: they are
the only place the PER-RESPONDENT question text lives, and Twin's pricing block
randomizes its price per respondent. Without them 40 of the 60 scored questions
would be asked at a price 99.2% of respondents never saw. See
`src/data/preprocessors/twin2k.py`.

`full_persona/` (~203 MB) is still skipped: this project builds personas from the
label CSV itself. Total repo is ~733 MB, not the ~4 GB an earlier version of this
docstring claimed.

`data/` is git-ignored, so nothing downloaded here enters the repo.

Usage:  .venv\\Scripts\\python.exe scripts/twin2k/fetch_twin2k.py
        (idempotent — files already present are left alone)
"""

import argparse
import shutil
from pathlib import Path

from huggingface_hub import hf_hub_download

REPO_ID = "LLM-Digital-Twin/Twin-2K-500"
DEST_DIR = Path("data/twin2k500")

# Repo-relative paths of the files we need, with why each one is here.
FILES = {
    "question_catalog_and_human_response_csv/question_catalog.json":
        "the instrument: question text, options, scale labels, CSV columns",
    "question_catalog_and_human_response_csv/wave1_3_response_label.csv":
        "waves 1-3 human answers as option TEXT (matches data_format: text)",
    "question_catalog_and_human_response_csv/wave4_response_label.csv":
        "wave 4 retest of a wave-1-3 subset: the test-retest reliability ceiling",
}

# The per-respondent instrument, split into 7 chunks of 294 respondents (7 x 294 = 2,058,
# i.e. exactly the label CSV's row count, so every scored respondent is covered). Kept in a
# subdirectory because they are bulk data read by the preprocessor, not files a human opens.
WAVE_SPLIT_SUBDIR = Path("wave_split")
WAVE_SPLIT_FILES = [
    f"wave_split/chunks/wave_persona_chunk_{n:03d}.parquet" for n in range(1, 8)
]

ATTRIBUTION = (
    "Twin-2K-500 (LLM-Digital-Twin/Twin-2K-500), licensed CC BY 4.0.\n"
    "  https://huggingface.co/datasets/LLM-Digital-Twin/Twin-2K-500\n"
    "  Attribution is required by the licence wherever these data are reported."
)


def _download(repo_path: str, target: Path, why: str, force: bool) -> None:
    """Copy one repo file to `target`, skipping it when already present."""
    if target.exists() and not force:
        size_mb = target.stat().st_size / 1024 / 1024
        print(f"  [skip] {target}  ({size_mb:.1f} MB already present)")
        return

    print(f"  [get ] {target}  <- {repo_path}\n         {why}")
    cached = hf_hub_download(
        repo_id=REPO_ID, filename=repo_path, repo_type="dataset",
        # Without this, --force would only re-copy from the HF cache rather
        # than actually re-fetching the file.
        force_download=force,
    )
    # Copy out of the HF cache so the pipeline reads a stable path.
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(cached, target)
    size_mb = target.stat().st_size / 1024 / 1024
    print(f"         done ({size_mb:.1f} MB)")


def fetch(force: bool = False, skip_wave_split: bool = False) -> None:
    """Download each needed file into DEST_DIR, skipping those already present."""
    DEST_DIR.mkdir(parents=True, exist_ok=True)

    for repo_path, why in FILES.items():
        _download(repo_path, DEST_DIR / Path(repo_path).name, why, force)

    if skip_wave_split:
        print(f"\n  [skip] {WAVE_SPLIT_SUBDIR}/ — the pricing questions will not run without it")
    else:
        why = "per-respondent question text; the only source of Twin's randomized prices"
        for repo_path in WAVE_SPLIT_FILES:
            target = DEST_DIR / WAVE_SPLIT_SUBDIR / Path(repo_path).name
            _download(repo_path, target, why, force)

    print(f"\nData in {DEST_DIR}/\n\n{ATTRIBUTION}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force", action="store_true",
        help="re-download even if the file is already in data/twin2k500/",
    )
    parser.add_argument(
        "--skip-wave-split", action="store_true",
        help="skip the ~189 MB parquet chunks; the 40 pricing questions cannot run without them",
    )
    args = parser.parse_args()
    fetch(force=args.force, skip_wave_split=args.skip_wave_split)


if __name__ == "__main__":
    main()
