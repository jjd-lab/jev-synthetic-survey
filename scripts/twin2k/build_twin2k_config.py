"""Generate the Twin-2K-500 mapping JSONs from the dataset's own question catalog.

Twin-2K-500 ships `question_catalog.json` — 256 entries carrying the real question
text, option lists, matrix rows/columns, Qualtrics selector, and the exact CSV
column names. This script reads that catalog and emits the two mapping files the
pipeline needs, so no question text or option label is ever hand-transcribed from
a 200 KB JSON file:

  configs/twin2k/twin2k_demographic_mapping.json  - the 14 demographic items
  configs/twin2k/twin2k_question_mapping.json     - the 108 scored questions

It also prints the `survey.questions:` YAML block for pasting into the config.

The selection is the paper's holdout instrument, and both halves of that claim are
asserted rather than trusted: every scored column lies outside the six persona blocks
(so it cannot also be in the persona), and no human is silently dropped from scoring —
ordinary columns are answered by all 2,058 respondents, between-subject condition columns
by exactly the one arm each respondent was randomized into, and every answer decodes to a
real option. The second check is why this script reads the response CSV.

A one-time-generator pattern: the source
of truth is read at generation time and matrix questions are expanded into
per-item `single` entries, so every runtime consumer stays grid-blind.

Mapping-format contract (from `src/data/question_mapper.py`):
  - `single`: `choices` keyed by ordinal STRING ("1", "2", ...) because
    `get_choice_options_list` sorts them with `int()`. Needs an explicit `column`.
  - `multi`: `choices` keyed by CSV COLUMN NAME; the cell holds the option text
    when selected and is empty otherwise.

Usage:  .venv\\Scripts\\python.exe scripts/twin2k/build_twin2k_config.py
"""

import json
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

# The runtime's own ground-truth decoder. Checking the selection with anything else
# would let this generator disagree with the extraction it feeds.
from src.data.preprocessors.twin2k import cast_numeric_labels  # noqa: E402
from src.data.question_mapper import (  # noqa: E402  (path bootstrap above)
    _canonicalize_single_answer,
    _is_filled,
)

CATALOG_PATH = Path("data/twin2k500/question_catalog.json")
RESPONSE_CSV = Path("data/twin2k500/wave1_3_response_label.csv")
OUT_DIR = Path("configs/twin2k")
DEMOGRAPHIC_OUT = OUT_DIR / "twin2k_demographic_mapping.json"
QUESTION_OUT = OUT_DIR / "twin2k_question_mapping.json"

# The six catalog blocks the paper carries as persona material. Everything else is its
# holdout — the wave-4 retest instrument, 126 columns. One definition, used twice: this
# script asserts every SCORED column is holdout, `build_twin2k_persona.py` excludes
# exactly the same set from the persona. Sharing the function is what keeps the scored
# set and the persona from drifting into overlap.
PERSONA_BLOCKS = {
    "Personality",
    "Economic preferences",
    "Economic preferences - intro",
    "Cognitive tests",
    "Forward Flow",
    "Demographics",
}

# The 14 Demographics-block items, in catalog order, with the placeholder name each
# becomes in `survey_prompt`. All are SAVR with exactly one CSV column, and all are
# ForceResponse: ON (0 blanks across 2,058 rows), so no `choices` decode is needed —
# the label CSV already holds the answer text.
DEMOGRAPHICS = {
    "QID11": "region",
    "QID12": "sex",
    "QID13": "age",
    "QID14": "education",
    "QID15": "race",
    "QID16": "citizen",
    "QID17": "marital",
    "QID18": "religion",
    "QID19": "religious_attendance",
    "QID20": "party",
    "QID21": "income",
    "QID22": "political_views",
    "QID23": "household_size",
    "QID24": "employment",
}

# The scored set: the paper's whole holdout instrument, minus what our decoder cannot
# read or our panel cannot answer. Matrix parents are named once and expanded into the
# listed row numbers (matching the CSV column suffix).
#
#   Product Preferences - Pricing   QID9_1-QID9_40          40   nominal
#   False consensus support         QID287_1-_7, _10-_12     10   ordinal
#   Nonseparability - benefits      QID288_1-_4               4   ordinal
#   Nonseparability - risks         QID289_1-_4               4   ordinal
#   Marble tray                     QID196                    1   nominal
#   Flu vaccine                     QID291                    1   ordinal
#   13 between-subject conditions   see CONDITION_GROUPS     48   24 ordinal + 24 nominal
#
# 108 questions = 65 nominal + 43 ordinal + 0 multi. Read results PER TASK: 40 of the 108
# are pricing, so a pooled nominal figure is dominated by one task. Averaging within task
# then across tasks is also how the paper aggregates its 17 tasks. The 48 condition columns
# are asked only of the arm each respondent was randomized into, so each carries n≈16-25 of
# a 50-respondent panel — per-arm numbers there are a plumbing proof, not a result.
#
# The other 18 holdout columns are out because no option list the decoder can match exists:
# 12 HSLIDER (QID290's 10 false-consensus estimates, plus QID154 and QID156 base-rate) and
# 6 SL text boxes (QID164/166/168/170 anchoring, QID181/182 sunk cost). The `multi` (Jaccard)
# bucket is unexercised — the holdout blocks contain no MAVR/MAHR at all.

# Unordered single-select: the options are categories, so TVD is the right metric
# and shuffling them blunts position bias.
NOMINAL_SINGLE_QIDS = (
    # binary purchase decisions, each a self-contained stem, 1 CSV column
    [f"QID9_{i}" for i in range(1, 41)]
    # binary tray choice
    + ["QID196"]
)

# Ordered single-select that is NOT a matrix. QID291's four options run
# definitely-not -> probably-not -> probably -> definitely take the vaccine, in
# catalog order, so it is a 4-point scale: it must keep that order (no shuffle)
# and score with Wasserstein rather than TVD, which would discard the ordering.
ORDERED_SINGLE_QIDS = ["QID291"]

# {matrix parent: [row numbers]} -> per-item `single` entries with ordered_scale.
MATRIX_ITEMS = {
    # 5-point oppose -> support, 10 policy items. Rows are numbered 1-7 and 10-12:
    # there is no _8/_9, which is why rows resolve by column name below.
    "QID287": [1, 2, 3, 4, 5, 6, 7, 10, 11, 12],
    "QID288": [1, 2, 3, 4],   # nonseparability, benefits half (7-point)
    "QID289": [1, 2, 3, 4],   # nonseparability, risks half (7-point), same 4 technologies
}

# Between-subject conditions: 13 groups, 48 columns. Each respondent was randomized by
# Qualtrics into exactly ONE arm, so each arm is filled by only 31.6-51.3% of the panel.
# Every entry below is tagged `condition_group` + `condition_arm`, which `QuestionRouter.is_asked`
# reads to ask each twin only its human's arm — asking both arms would turn a between-subject
# manipulation into a within-subject one and erase the effect being measured.
#
# The grouping and the arm names are the only hand-authored part; the arm-aware
# `assert_ground_truth_complete` below makes a wrong grouping fail loudly (a respondent with
# 0 or >=2 arms filled, or a partially filled arm).
#
# {group: {arm: [qid, ...]}} — plain single-selects, 26 columns.
CONDITION_GROUPS = {
    "Disease":              {"gain": ["QID157"], "loss": ["QID158"]},
    "OutcomeBias":          {"success": ["QID161"], "failure": ["QID162"]},
    "AnchoringAfrica":      {"low": ["QID163"], "high": ["QID165"]},
    "AnchoringRedwood":     {"low": ["QID167"], "high": ["QID169"]},
    "AbsoluteVsRelative":   {"calculator": ["QID183"], "jacket": ["QID184"]},
    "Allais":               {"form1": ["QID192"], "form2": ["QID193"]},
    "Myside":               {"ford": ["QID194"], "german": ["QID195"]},
    "LessIsMore":           {"A": ["QID171"], "B": ["QID172"], "C": ["QID173"]},
    "ProportionDominance1": {"A": ["QID174"], "B": ["QID175"], "C": ["QID176"]},
    "ProportionDominance2": {"A": ["QID177"], "B": ["QID178"], "C": ["QID179"]},
    "ThalerWTAWTP":         {"wtp_certainty": ["QID189"], "wta_certainty": ["QID190"],
                             "wtp_noncertainty": ["QID191"]},
}

# {group: {arm: (matrix parent, [row numbers])}} — expanded by `build_matrix_entries`, 22 columns.
CONDITION_MATRIX_GROUPS = {
    "Linda":               {"no_conjunction": ("QID159", [1, 2, 3]),
                            "conjunction":    ("QID160", [1, 2, 3])},
    "ProbabilityMatching": {"problem1": ("QID198", list(range(1, 11))),
                            "problem2": ("QID203", list(range(1, 7)))},
}

# Which condition groups are ordered scales (Wasserstein, catalog order kept) vs nominal
# categories (TVD, shuffled). Read off the catalog's own option lists:
#   ordered  — Disease/6-pt favor-A->favor-B, OutcomeBias/7-pt incorrect->correct,
#              LessIsMore + ProportionDominance1/5-pt Likert, ProportionDominance2/6-pt
#              unlikely->likely, Myside/6-pt definitely-no->definitely-yes,
#              ThalerWTAWTP/10-step $ ladder, Linda/6-pt improbable->probable.
#   nominal  — Anchoring (more/fewer), AbsoluteVsRelative (Yes/No), Allais (two lotteries),
#              ProbabilityMatching (1/2, red/green).
# Linda's catalog order runs "Extremely improbable, Very improbable, Somewhat probable,
# Moderately probable, Very probable, Extremely probable" — the low end skips an "improbable"
# step. Catalog order is taken as the scale, the same convention already used for QID287.
ORDERED_CONDITION_GROUPS = {
    "Disease", "OutcomeBias", "Myside", "LessIsMore",
    "ProportionDominance1", "ProportionDominance2", "ThalerWTAWTP", "Linda",
}

# multi-select (MAVR/MAHR): one CSV column per option, option text if selected.
# Empty: the holdout blocks hold no multi-select. `build_multi_entry` stays because it
# carries the BDI instruction text for QID126/QID128 and is how the bucket comes back.
MULTI_QIDS = []

# The pricing block's price is Qualtrics-randomized PER RESPONDENT, so the catalog's stem
# holds only one arbitrary draw. Measured on wave_persona_chunk_001 (294 respondents):
# each product carries 161-197 distinct prices spanning $0.00-$59.98, and only 0.757% of
# cells ever saw the price the catalog prints. Scoring against the catalog price therefore
# asks a question the respondent was never asked -- the 40 yes-rates collapse into
# 40.4-45.3% (chi2 p=0.25, corr with catalog price +0.099, p=0.54), i.e. pure noise, while
# the price each person actually saw gives corr=-0.356 and 75.8% -> 16.4% across quintiles.
#
# So the price is replaced by `STEM_VALUE_TOKEN` here and filled in per respondent at
# runtime from `wave_split/` (see `src/data/preprocessors/twin2k.py`). This is the dataset's
# own Qualtrics piped text; nothing else in the 126-column holdout is piped -- the other 23
# catalog entries have exactly 1 distinct stem across all 294 respondents.
PRICE_PIPED_QIDS = [f"QID9_{i}" for i in range(1, 41)]

# Must match `STEM_VALUE_TOKEN` in `src/core/survey_runner_excel.py`, which substitutes it.
# Written with braces so a stem that reaches a prompt unfilled is obvious on sight, and
# matched by plain `str.replace` there rather than `str.format` so no other brace in any
# survey's question text is touched.
STEM_VALUE_TOKEN = "{stem_value}"

# `The product is priced at: $7.39.` -> the price, so it can be swapped for the token.
_PRICE_RE = re.compile(r"(priced at:\s*\$)\s*[0-9]+(?:\.[0-9]+)?")


def load_catalog() -> dict:
    """Return {key: catalog entry} for every entry in the dataset's question catalog.

    `QuestionID` is NOT unique: 10 of them appear twice, once under "Cognitive tests" and
    once under "Personality"/"Economic preferences", carrying different stems and disjoint
    `csv_columns`. A plain `{e["QuestionID"]: e}` comprehension kept only the last of each
    pair, silently discarding 10 fully-populated persona columns (`QID268`-`QID272`,
    `QID275`-`QID279`) and making them look like columns the catalog never described.

    So a repeated id gets its block appended. Nothing looks those up by key: every direct
    `catalog[qid]` here is a demographic or a scored holdout item, and none of those
    collide; every other consumer walks `.values()`. The count check is the guard — if a
    future dataset revision collides on block too, this fails loudly instead of dropping
    rows again.
    """
    if not CATALOG_PATH.exists():
        raise FileNotFoundError(
            f"{CATALOG_PATH} not found — run scripts/twin2k/fetch_twin2k.py first"
        )
    entries = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    catalog = {}
    for entry in entries:
        key = entry["QuestionID"]
        if key in catalog:
            key = f"{key}@{(entry.get('BlockName') or '').strip()}"
        catalog[key] = entry
    if len(catalog) != len(entries):
        raise RuntimeError(
            f"catalog lost {len(entries) - len(catalog)} of {len(entries)} entries to "
            f"duplicate QuestionID+BlockName keys"
        )
    return catalog


def holdout_columns(catalog: dict) -> set:
    """Every CSV column the paper holds out: those outside the six persona blocks.

    Independently checkable — the paper's holdout IS its wave-4 retest instrument, so this
    set equals the columns of `wave4_response_label.csv`. Both are 126.
    """
    return {
        column
        for entry in catalog.values()
        if (entry.get("BlockName") or "").strip() not in PERSONA_BLOCKS
        for column in entry.get("csv_columns") or []
    }


def _ordinal_choices(options: list) -> dict:
    """Build the {"1": text, ...} choices dict that `single` questions require."""
    return {str(i): text for i, text in enumerate(options, start=1)}


def build_demographic_mapping(catalog: dict) -> dict:
    """Build the demographic mapping: one text-field entry per demographic item."""
    mapping = {}
    for qid, key in DEMOGRAPHICS.items():
        entry = catalog[qid]
        columns = entry["csv_columns"]
        if len(columns) != 1:
            raise RuntimeError(f"{qid}: expected 1 CSV column, got {columns}")
        if columns[0] != qid:
            raise RuntimeError(f"{qid}: CSV column is {columns[0]!r}, not the qid")
        # No `choices`: the label CSV stores the answer text, so the mapper's
        # text-field branch passes it through unchanged.
        mapping[qid] = {
            "question": entry["QuestionText"],
            "type": "demographic",
            "demographic_key": key,
        }
    return mapping


def build_single_entry(entry: dict, ordered: bool = False) -> dict:
    """Build a plain single-select entry (SAVR, one CSV column).

    `ordered` marks the option list as a scale: it routes the question to the
    ordinal metric bucket (Wasserstein) and suppresses shuffling, which would
    otherwise scramble the scale in the prompt.
    """
    columns = entry["csv_columns"]
    if len(columns) != 1:
        raise RuntimeError(f"{entry['QuestionID']}: expected 1 CSV column, got {columns}")
    return {
        "question": entry["QuestionText"],
        "type": "single",
        "ordered_scale": ordered,
        # Unordered options may be shuffled to blunt position bias; an ordered
        # scale must keep catalog order.
        "shuffle_options": not ordered,
        "choices": _ordinal_choices(entry["Options"]),
        "column": columns[0],
    }


def build_matrix_entries(entry: dict, rows: list, ordered: bool = True) -> dict:
    """Expand selected matrix rows into per-item `single` entries.

    Grid expansion: each item carries the real CSV column,
    `grid_group` (the parent qid) and `grid_label` (the row text), so the stateful
    runner could combine them while the stateless runner just asks one at a time.

    `ordered` defaults True because every matrix in the scored set except probability
    matching is a Likert scale; it means the same thing as in `build_single_entry`.
    """
    qid = entry["QuestionID"]
    row_labels = entry["Rows"]
    scale = entry["Columns"]
    stem = entry["QuestionText"]
    csv_columns = entry["csv_columns"]

    if len(csv_columns) != len(row_labels):
        raise RuntimeError(
            f"{qid}: {len(csv_columns)} CSV columns but {len(row_labels)} rows"
        )
    # Resolve a row by its COLUMN NAME, never by position. QID287's rows are numbered
    # 1-7 and 10-12, so `csv_columns[row_no - 1]` would hand row 10 the column of row 12
    # and score three questions against the wrong ground truth.
    labels_by_column = dict(zip(csv_columns, row_labels))

    entries = {}
    for row_no in rows:
        column = f"{qid}_{row_no}"
        if column not in labels_by_column:
            raise RuntimeError(
                f"{qid}: no column {column!r} (have {sorted(labels_by_column)})"
            )
        label = labels_by_column[column]
        entries[column] = {
            "question": f"{stem} — {label}",
            "type": "single",
            # A Likert scale must keep catalog order and never shuffle; unordered
            # categories (probability matching's 1/2, red/green) may be shuffled.
            "ordered_scale": ordered,
            "shuffle_options": not ordered,
            "choices": _ordinal_choices(scale),
            "column": column,
            "grid_group": qid,
            "grid_label": label,
        }
    return entries


def templatize_price(question: str, qid: str) -> str:
    """Swap the catalog's single price draw for the per-respondent piped-text token.

    Asserts exactly one price is present. A stem that silently kept its literal price would
    score 40 questions against a price 99.2% of respondents never saw, which is the whole
    defect this exists to remove — and it would look identical in the mapping file.
    """
    templated, n = _PRICE_RE.subn(rf"\1{STEM_VALUE_TOKEN}", question)
    if n != 1:
        raise RuntimeError(
            f"{qid}: expected exactly 1 'priced at: $N' in the stem, found {n}: "
            f"{question[-120:]!r}"
        )
    return templated


def build_multi_entry(entry: dict) -> dict:
    """Build a multi-select entry: `choices` keyed by CSV column name."""
    qid = entry["QuestionID"]
    options = entry["Options"]
    columns = entry["csv_columns"]
    if len(options) != len(columns):
        raise RuntimeError(
            f"{qid}: {len(options)} options but {len(columns)} CSV columns"
        )
    question_text = entry["QuestionText"]
    if not question_text.strip():
        # Beck Depression Inventory items carry their instruction in a separate
        # descriptive (DB) block, leaving QuestionText empty. Supply the generic
        # BDI instruction so the prompt is answerable at all.
        question_text = (
            "Pick out the one statement in the group below that best describes "
            "the way you have been feeling the past two weeks, including today."
        )
    return {
        "question": question_text,
        "type": "multi",
        "choices": dict(zip(columns, options)),
    }


def assert_holdout_only(mapping: dict, catalog: dict) -> None:
    """Every scored column must be one the paper holds out.

    The four selection constants above are hand-named QID lists, which is exactly the kind
    of selection that rots when the catalog changes. This ties them back to the same rule
    `build_twin2k_persona.py` excludes by, so the scored set cannot start overlapping the
    persona without failing here first.
    """
    holdout = holdout_columns(catalog)
    scored = set()
    for entry in mapping.values():
        if entry.get("column"):
            scored.add(entry["column"])
        if entry["type"] == "multi":
            # `multi` keys its choices by CSV column name, one column per option.
            scored.update(entry.get("choices", {}))

    leaking = sorted(scored - holdout)
    if leaking:
        raise RuntimeError(
            f"{len(leaking)} scored column(s) are persona material, not holdout: {leaking}"
        )
    print(f"holdout check: {len(scored)} scored columns, all within the {len(holdout)}-column holdout")


def _decode_problems(qid: str, entry: dict, filled: list) -> list:
    """Report answers that `_canonicalize_single_answer` cannot map to a real option.

    An answer that decodes to nothing is worse than a missing one: the canonicalizer falls
    back to the raw text, inventing a ground-truth category no model can produce.
    """
    options = set(entry["choices"].values())
    off_list = sorted(
        {
            answer
            for answer in {_canonicalize_single_answer(v, entry) for v in set(filled)}
            if answer not in options
        }
    )
    return [f"{qid}: answers outside the option list: {off_list[:3]}"] if off_list else []


def _condition_problems(groups: dict, df: pd.DataFrame) -> list:
    """Check the between-subject groups: exactly one arm per respondent, fully filled.

    This is the arm-aware replacement for the blanket fill rule, and it is the guard that
    makes `CONDITION_GROUPS` safe to hand-author. Three failures are caught:

      - a *partially* filled arm, which would make `condition_assignments` route a twin into
        an arm whose remaining questions have no ground truth;
      - a respondent with 0 or >=2 arms filled, which means the grouping does not match how
        Qualtrics actually randomized (`condition_assignments` raises on this at runtime, so
        catching it here turns a mid-run crash into a generation-time error);
      - an off-list answer, same rule as the non-condition columns.
    """
    problems = []
    for group, arms in sorted(groups.items()):
        fully_filled = {}
        for arm, entries in sorted(arms.items()):
            columns = [entry["column"] for entry in entries.values()]
            missing = [c for c in columns if c not in df.columns]
            if missing:
                problems.append(f"{group}/{arm}: column(s) absent from {RESPONSE_CSV.name}: {missing}")
                continue
            n_filled = df[columns].map(_is_filled).sum(axis=1)
            partial = (n_filled > 0) & (n_filled < len(columns))
            if partial.any():
                problems.append(
                    f"{group}/{arm}: {int(partial.sum())} respondent(s) filled some but not "
                    f"all {len(columns)} column(s), e.g. pid {df.loc[partial, 'pid'].head(3).tolist()}"
                )
            fully_filled[arm] = n_filled == len(columns)
            for qid, entry in sorted(entries.items()):
                problems.extend(
                    _decode_problems(qid, entry, [v for v in df[entry["column"]] if _is_filled(v)])
                )

        if len(fully_filled) != len(arms):
            continue  # an arm's columns are missing; the one-arm count would be meaningless
        n_arms = sum(fully_filled.values())
        wrong = n_arms != 1
        if wrong.any():
            problems.append(
                f"{group}: {int(wrong.sum())}/{len(df)} respondent(s) filled "
                f"{sorted(set(n_arms[wrong]))} of the {len(arms)} arms, not exactly 1, "
                f"e.g. pid {df.loc[wrong, 'pid'].head(3).tolist()}"
            )
    return problems


def assert_ground_truth_complete(mapping: dict, df: pd.DataFrame) -> None:
    """Every scored answer must decode to a real option, and no human may be silently dropped.

    Two fill rules, because the scored set holds two kinds of question:

    **Non-condition columns must be answered by EVERY respondent.** Without this the pipeline
    still "works" and that is the danger: an unfilled cell leaves the qid out of
    `ground_truth`, `build_valid_pairs` drops that human, and a half-filled question quietly
    scores 50 LLM answers against ~25 humans — visible only as a smaller `n_valid`.
    Full-sample completeness is asserted rather than panel completeness because it is both
    stronger and simpler: 2058/2058 implies 100% on any `max_rows` panel.

    **Condition columns must be filled for exactly one arm per respondent** (`_condition_problems`).
    A partial panel is expected there and is not a defect — it *is* the randomization, which
    `QuestionRouter.is_asked` reproduces by asking each twin only its own arm.
    """
    n_rows = len(df)
    problems = []
    # {group: {arm: {qid: entry}}} — checked as groups, since no single arm is ever complete.
    condition_groups = {}
    n_plain = 0

    for qid, entry in mapping.items():
        if entry["type"] != "single":
            continue  # `multi` spreads one answer across columns; no per-column fill rule.
        group = entry.get("condition_group")
        if group is not None:
            condition_groups.setdefault(group, {}).setdefault(entry["condition_arm"], {})[qid] = entry
            continue
        n_plain += 1
        column = entry["column"]
        if column not in df.columns:
            problems.append(f"{qid}: column {column!r} absent from {RESPONSE_CSV.name}")
            continue
        filled = [v for v in df[column] if _is_filled(v)]
        if len(filled) != n_rows:
            problems.append(f"{qid}: {len(filled)}/{n_rows} filled ({len(filled) / n_rows:.1%})")
            continue
        problems.extend(_decode_problems(qid, entry, filled))

    problems.extend(_condition_problems(condition_groups, df))

    if problems:
        raise RuntimeError(
            "ground truth is incomplete or undecodable:\n  " + "\n  ".join(problems)
        )
    n_condition = sum(len(entries) for arms in condition_groups.values() for entries in arms.values())
    print(
        f"ground-truth check: {n_plain} columns {n_rows}/{n_rows} filled; "
        f"{n_condition} columns across {len(condition_groups)} condition groups with exactly "
        f"one fully-filled arm per respondent; every answer on-list"
    )


def build_question_mapping(catalog: dict, df: pd.DataFrame) -> dict:
    """Build the full question mapping for the scored question set."""
    mapping = {}

    for qid in NOMINAL_SINGLE_QIDS:
        mapping[qid] = build_single_entry(catalog[qid], ordered=False)

    for qid in ORDERED_SINGLE_QIDS:
        mapping[qid] = build_single_entry(catalog[qid], ordered=True)

    for parent, rows in MATRIX_ITEMS.items():
        mapping.update(build_matrix_entries(catalog[parent], rows))

    for qid in MULTI_QIDS:
        mapping[qid] = build_multi_entry(catalog[qid])

    # Between-subject conditions. Built with the same two builders as everything else — the
    # only difference is the two tags, which is the whole point: conditioning is a routing
    # gate over the ordinary mapping, not a second kind of question.
    #
    # A typo in `ORDERED_CONDITION_GROUPS` would silently demote a scale to TVD-with-shuffle,
    # which no downstream check can notice, so the names are tied to the groups here.
    unknown = sorted(ORDERED_CONDITION_GROUPS - set(CONDITION_GROUPS) - set(CONDITION_MATRIX_GROUPS))
    if unknown:
        raise RuntimeError(f"ORDERED_CONDITION_GROUPS names unknown group(s): {unknown}")

    for group, arms in CONDITION_GROUPS.items():
        ordered = group in ORDERED_CONDITION_GROUPS
        for arm, qids in arms.items():
            for qid in qids:
                mapping[qid] = build_single_entry(catalog[qid], ordered=ordered)
                mapping[qid].update(condition_group=group, condition_arm=arm)

    for group, arms in CONDITION_MATRIX_GROUPS.items():
        ordered = group in ORDERED_CONDITION_GROUPS
        for arm, (parent, rows) in arms.items():
            entries = build_matrix_entries(catalog[parent], rows, ordered=ordered)
            for entry in entries.values():
                entry.update(condition_group=group, condition_arm=arm)
            mapping.update(entries)

    # After the entries exist, so the token is applied to exactly the stems that ship.
    for qid in PRICE_PIPED_QIDS:
        mapping[qid]["question"] = templatize_price(mapping[qid]["question"], qid)
    # The stateful runner's GRID branch builds its stem from the parent and never calls
    # `_fill_stem`, so a piped question inside a grid would send the literal token to the
    # model. These 40 are standalone SAVR today; this is what keeps that true.
    grid_piped = [qid for qid in PRICE_PIPED_QIDS if mapping[qid].get("grid_group")]
    if grid_piped:
        raise RuntimeError(
            f"{len(grid_piped)} piped question(s) are grid members ({grid_piped[:3]}); the "
            f"grid branch cannot substitute {STEM_VALUE_TOKEN}"
        )
    print(f"piped text: {len(PRICE_PIPED_QIDS)} pricing stems carry {STEM_VALUE_TOKEN}")

    assert_holdout_only(mapping, catalog)
    assert_ground_truth_complete(mapping, df)
    return mapping


def format_questions_yaml(mapping: dict) -> str:
    """Render the `survey.questions:` block for pasting into the YAML config."""
    lines = ["  questions:"]
    for qid, entry in mapping.items():
        lines.append(f'    - id: "{qid}"')
        lines.append(f'      type: "{entry["type"]}"')
    return "\n".join(lines)


def main() -> None:
    catalog = load_catalog()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    demographics = build_demographic_mapping(catalog)
    DEMOGRAPHIC_OUT.write_text(
        json.dumps(demographics, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {DEMOGRAPHIC_OUT} ({len(demographics)} demographic items)")

    if not RESPONSE_CSV.exists():
        raise FileNotFoundError(
            f"{RESPONSE_CSV} not found — run scripts/twin2k/fetch_twin2k.py first"
        )
    # Same cast the runtime preprocessor applies, so the decode check below sees exactly the
    # cells the pipeline will see (QID198's options are the integers 1 and 2, which pandas
    # reads as 1.0/2.0 and the canonicalizer then cannot match).
    df = cast_numeric_labels(pd.read_csv(RESPONSE_CSV, low_memory=False))

    questions = build_question_mapping(catalog, df)
    QUESTION_OUT.write_text(
        json.dumps(questions, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    counts = {}
    for entry in questions.values():
        bucket = "ordinal" if entry.get("ordered_scale") else entry["type"]
        counts[bucket] = counts.get(bucket, 0) + 1
    print(f"Wrote {QUESTION_OUT} ({len(questions)} questions: {counts})")

    print(f"\nPaste into {OUT_DIR}/twin2k_survey_config.yaml:\n")
    print(format_questions_yaml(questions))


if __name__ == "__main__":
    main()
