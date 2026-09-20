"""Twin-2K-500 label-CSV preprocessor.

Adapts the public Twin-2K-500 response CSV to the loader's respondent-ID
contract *before* respondents are built, so no shared loader/mapper code needs a
Twin-specific branch. Referenced from ``twin2k_survey_config.yaml`` via::

    data_source:
      preprocess:
        callable: src.data.preprocessors.twin2k.preprocess

Three jobs.

**1. Rename Twin's ``pid`` to ``respid``.** ``Respondent`` recognises only
``respid`` / ``repid`` / ``responseid`` / ``Response ID``
(``src/data/respondent.py``), so without this every respondent silently becomes
``"unknown"`` — which then collapses the persona cache and the per-respondent
export onto a single key instead of raising.

**2. Recover the per-respondent pricing prices** into ``__stem__QID9_*`` columns,
when ``stem_values_dir`` is given. Twin's pricing block is Qualtrics piped text:
the price is randomized per respondent, so ``question_catalog.json`` holds only
one arbitrary draw. Measured on chunk 001 (294 respondents): each product carries
161-197 distinct prices spanning $0.00-$59.98, and only **0.757%** of cells ever
saw the catalog's price. Asking the catalog price makes all 40 products
indistinguishable (yes-rates 40.4-45.3%, chi2 p=0.25, corr with catalog price
+0.099 at p=0.54); asking the real one yields corr **-0.356** and 75.8% -> 16.4%
across price quintiles. So the 40 pricing questions are noise until this runs.

``Respondent`` turns ``__stem__QID9_1`` into ``stem_values["QID9_1"]``, and
``_fill_stem`` in ``src/core/survey_runner_excel.py`` substitutes it into the
``{stem_value}`` token the mapping carries. Surveys that pass no
``stem_values_dir`` get no such columns, so that substitution is inert for them.

Two properties of the source data make this exact rather than approximate, both
asserted in ``_load_stem_prices``: the price is *identical* between the parquet's
``wave4_Q_wave1_3_A`` and ``wave4_Q_wave4_A`` (100% of 11,760 cells, so there is
one price per person-product, not a per-wave draw), and the parquet's wave-1-3
answers equal the label CSV's cells *exactly* (100%), so the join on ``pid`` is
sound.

**3. Restore the string form of numeric-labelled answers** (``QID198_1``-``_10``,
the probability-matching grid whose two options are literally ``1`` and ``2``).
Their CSV columns are all-numeric with blanks, so pandas types them ``float64``
and every cell reads ``1.0`` while the option list holds ``'1'``.
``_canonicalize_single_answer`` stringifies before normalizing, so ``'1.0'``
survives unchanged and all 10 columns decode off-list — inventing a ground-truth
category no model can produce. Cast here rather than in
``_normalize_choice_value``, which every survey in this engine shares.

Nothing else is needed: the label CSV already stores option *text* (matching
``data_format: text``), single-select answers sit in one column per question, and
multi-select columns hold the option text when selected and are empty otherwise
— which is exactly the convention ``_extract_ground_truth_text`` implements.

No blank-demographic fill is included on purpose. A missing demographic key
*would* be fatal (the stateless runner splats demographics into the prompt
template, so an absent key raises ``KeyError`` rather than printing a blank), but
all 14 demographic items are Qualtrics ``ForceResponse: ON`` and measure 0 blank
cells across all 2,058 rows. If a future wave or a wider question set breaks
that, fill the demographic columns here rather than editing the runner.

The transform never writes disk. It reads only the parquet directory the config
names in ``stem_values_dir``; with that param omitted it is pure ``df -> df``.
"""

import json
import re
from pathlib import Path

import pandas as pd

from src.data.question_mapper import _is_filled

# Twin's respondent identifier -> the name the loader's Respondent looks for.
_ID_COLUMN = "pid"
_ID_TARGET = "respid"

# `Respondent` collects columns with this prefix into its `stem_values` dict.
_STEM_PREFIX = "__stem__"

# The parquet field pairing wave-4 question text with the wave-1-3 answers we score.
_INSTRUMENT_FIELD = "wave4_Q_wave1_3_A"
# Same instrument with wave-4 answers; used only to assert the price is wave-invariant.
_INSTRUMENT_FIELD_W4 = "wave4_Q_wave4_A"

# `The product is priced at: $7.39.` -> `7.39`. The captured text is kept as a STRING so
# the prompt shows exactly what the respondent saw ($0.00 stays "0.00", not "0.0").
_PRICE_RE = re.compile(r"priced at:\s*\$\s*([0-9]+(?:\.[0-9]+)?)")

# Only the pricing block is piped; every other holdout entry has one stem for everyone.
_PIPED_PREFIX = "QID9_"

# Columns whose option labels are bare integers, so pandas reads them as floats. Named
# explicitly rather than sniffed: a column that merely *looks* numeric (a $ ladder, a
# count) must keep whatever the CSV holds, and only the probability-matching grid has
# integers as its actual option text.
NUMERIC_LABEL_COLUMNS = [f"QID198_{i}" for i in range(1, 11)]


def _prices_from_instrument(payload: str) -> dict:
    """Pull {qid: price string} out of one respondent's rendered instrument."""
    prices = {}
    for block in json.loads(payload):
        for question in block.get("Questions") or []:
            qid = question.get("QuestionID") or ""
            if not qid.startswith(_PIPED_PREFIX):
                continue
            match = _PRICE_RE.search(question.get("QuestionText") or "")
            if match:
                prices[qid] = match.group(1)
    return prices


def _load_stem_prices(stem_values_dir: Path, wanted_pids: set) -> pd.DataFrame:
    """Read the parquet chunks and return one row per pid of ``__stem__QID9_*`` prices.

    Only `wanted_pids` are parsed. Each payload is ~45 KB of JSON and there are two per
    respondent, so on a `max_rows: 50` smoke run this is the difference between parsing
    100 documents and all 4,116.

    Asserts the price is wave-invariant per person-product. If a future revision randomized
    it again at wave 4, pairing wave-4 text with wave-1-3 answers would reintroduce exactly
    the mismatch this function exists to remove — silently, and only on the pricing block.
    """
    chunks = sorted(stem_values_dir.glob("*.parquet"))
    if not chunks:
        raise FileNotFoundError(
            f"no .parquet chunks in {stem_values_dir} — run "
            f"scripts/twin2k/fetch_twin2k.py (they are ~189 MB and carry the "
            f"per-respondent pricing prices)"
        )

    rows = []
    for chunk in chunks:
        frame = pd.read_parquet(chunk, columns=["pid", _INSTRUMENT_FIELD, _INSTRUMENT_FIELD_W4])
        for record in frame.itertuples(index=False):
            if record.pid not in wanted_pids:
                continue
            prices = _prices_from_instrument(getattr(record, _INSTRUMENT_FIELD))
            wave4 = _prices_from_instrument(getattr(record, _INSTRUMENT_FIELD_W4))
            if prices != wave4:
                differing = sorted(k for k in prices if prices[k] != wave4.get(k))
                raise RuntimeError(
                    f"pid {record.pid}: pricing price differs between "
                    f"{_INSTRUMENT_FIELD} and {_INSTRUMENT_FIELD_W4} for {differing[:3]}; "
                    f"the price is no longer one draw per person-product"
                )
            rows.append({"pid": record.pid, **{_STEM_PREFIX + q: p for q, p in prices.items()}})

    if not rows:
        raise RuntimeError(
            f"{stem_values_dir} covers none of the {len(wanted_pids)} respondents in the "
            f"response CSV; are these the right chunks?"
        )
    # Every respondent must yield the SAME pricing questions. Without this, a question whose
    # price failed to parse for everyone would simply have no column — invisible here, and a
    # KeyError from `_fill_stem` 40 questions into the run.
    key_sets = {frozenset(row.keys()) for row in rows}
    if len(key_sets) != 1:
        largest = max(key_sets, key=len)
        ragged = [sorted(largest - keys)[:3] for keys in key_sets if keys != largest]
        raise RuntimeError(
            f"respondents disagree on which pricing questions have a price; "
            f"{len(key_sets) - 1} variant(s) missing e.g. {ragged[:2]}"
        )

    prices_df = pd.DataFrame(rows)
    if prices_df["pid"].duplicated().any():
        raise RuntimeError(
            f"{stem_values_dir} yields duplicate pids; chunks are meant to partition the panel"
        )
    print(
        f"Loaded per-respondent prices: {len(prices_df)} respondents x "
        f"{len(prices_df.columns) - 1} pricing questions from {len(chunks)} chunk(s)"
    )
    return prices_df


def cast_numeric_labels(df: pd.DataFrame) -> pd.DataFrame:
    """Rewrite ``NUMERIC_LABEL_COLUMNS`` from floats to their integral string form.

    ``1.0 -> "1"``, blanks stay blank. Shared with
    ``scripts/twin2k/build_twin2k_config.py``, which asserts every scored answer decodes
    on-list: reading the raw CSV there while the runtime reads a cast one would let the
    generator pass on a question the runtime cannot decode.

    Raises:
        RuntimeError: if a filled cell is non-numeric or non-integral. Truncating a real
            fractional value would silently score against an option nobody chose.
    """
    df = df.copy()
    for column in NUMERIC_LABEL_COLUMNS:
        if column not in df.columns:
            continue
        numeric = pd.to_numeric(df[column], errors="coerce")
        filled = df[column].map(_is_filled)
        bad = df.loc[filled & (numeric.isna() | (numeric != numeric.round())), column]
        if not bad.empty:
            raise RuntimeError(
                f"{column}: {len(bad)} cell(s) are not whole numbers "
                f"({bad.unique()[:3].tolist()}); its options are integer labels"
            )
        # `None` rather than NaN for the blanks so `_is_filled` still reads them as unfilled
        # after the column's dtype flips from float64. `dtype=object` is explicit rather than
        # inferred: pandas' newer string dtype (the default from 3.0, `future.infer_string`
        # before it) infers `str` for this column and stores the blanks as NaN, which is the
        # exact sentinel this line exists to avoid.
        df[column] = pd.Series(
            [None if pd.isna(v) else str(int(v)) for v in numeric],
            index=numeric.index,
            dtype=object,
        )
    return df


def preprocess(df: pd.DataFrame, stem_values_dir: str = None, **params) -> pd.DataFrame:
    """Rename Twin-2K-500's ``pid`` to ``respid``, and add per-respondent pricing prices.

    Args:
        df: Raw Twin-2K-500 label-CSV DataFrame (one row per respondent).
        stem_values_dir: Directory of ``wave_split`` parquet chunks. Omit to skip the
            piped-price join — the 40 pricing questions then ask the catalog's single
            price draw, which 99.2% of respondents never saw.
        **params: Accepted for forward-compat; currently unused.

    Returns:
        The DataFrame with the ID column renamed, the numeric-labelled columns cast to
        strings, and, when ``stem_values_dir`` is given, one ``__stem__QID9_*`` column
        per pricing question.

    Raises:
        KeyError: if neither ``pid`` nor ``respid`` is present — the respondent ID
            would otherwise degrade to "unknown" for every row without any error.
        RuntimeError: if any respondent is missing any pricing price. A partial join
            would leave `{stem_value}` unfilled, which ``_fill_stem`` also refuses.
    """
    df = cast_numeric_labels(df)

    if stem_values_dir:
        # Joined BEFORE the rename so both sides key on Twin's own `pid`.
        id_column = _ID_COLUMN if _ID_COLUMN in df.columns else _ID_TARGET
        prices_df = _load_stem_prices(
            Path(stem_values_dir), set(df[id_column])
        ).rename(columns={"pid": id_column})
        stem_columns = [c for c in prices_df.columns if c != id_column]
        df = df.merge(prices_df, on=id_column, how="left")
        missing = df[stem_columns].isna().any(axis=1)
        if missing.any():
            raise RuntimeError(
                f"{int(missing.sum())} of {len(df)} respondents have no per-respondent "
                f"price (first: {df.loc[missing, id_column].head(3).tolist()}); "
                f"{stem_values_dir} does not cover the response CSV"
            )

    if _ID_COLUMN in df.columns:
        df = df.rename(columns={_ID_COLUMN: _ID_TARGET})
    elif _ID_TARGET not in df.columns:
        raise KeyError(
            f"Twin-2K-500 preprocessor found neither '{_ID_COLUMN}' nor "
            f"'{_ID_TARGET}' in the response CSV; got {list(df.columns)[:5]}..."
        )

    return df
