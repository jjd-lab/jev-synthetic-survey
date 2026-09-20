"""Generate the prior-answer persona mapping for the Twin-2K-500 twin arms.

The Twin-2K-500 paper's digital twins are grounded in each respondent's OWN answers to
the ~412 non-holdout questions, rendered as question/answer text (paper §4, "Persona
JSON"). Their best arm scores 71.72% that way against 59.17% for random guessing and an
81.72% human test-retest ceiling. Our first Twin run used the 14 demographics only --
the grounding level the paper ships responses for but never publishes a score for.

This script emits the mapping that carries those prior answers into the prompt:

  configs/twin2k/twin2k_demographic_mapping_persona.json
      the same 14 demographic items, PLUS one `screener` entry per prior-answer column

`Respondent` turns those `screener` entries into `screener_profile`, and `render_history`
in the runner renders it into `{conversation_history}` -- verbatim `Q:`/`A:` pairs here,
because Twin's config sets no `screener_summarization_prompt`. That is the only history
channel there is, so no new placeholder is needed.

Every battery -- matrix, price list, checkbox group, free-text box set -- carries a SHORT tag
rather than the battery's instruction stem, which would otherwise repeat once per row and cost
39% of the persona's tokens for no information (see `BATTERY_TAGS`). Single-question entries
keep their stem verbatim -- there it IS the question. Every prompt-text choice therefore lives
in this generator: nothing in `src/` reads anything but the `question` field it emits.

**Leakage is excluded at TASK level: every one of the paper's 126 holdout columns stays
out, whether this run scores it or not.** That is the paper's own partition. Excluding only
the columns the run scores — the previous rule — left **94 of the 126 in the persona**,
because `QID9_11`..`QID9_40`, `QID287` and `QID289` are sibling *tasks* of scored questions
rather than sibling columns of one catalog entry, so no column-level rule could reach them.
`holdout_columns()` lives in `build_twin2k_config.py`, which asserts the scored set is a
subset of it, so the scored set and the persona cannot drift into overlap.

Costs nothing in coverage: the columns this drops relative to the old rule were the
half-answered between-subject conditions. The persona carries **620 columns / 552.7 answered
per respondent** (median 552, min 526, max 589; 481 of the 620 are answered by all 2,058
respondents) and `MIN_DECODE_RATE` drops nothing at all.

620 is the WHOLE non-holdout, non-demographic universe: 760 response columns - 126 held out
by the paper - 14 demographics. Nothing is skipped by selector any more, so the only
difference left between this persona and the paper's is the holdout partition, which is
deliberate. A column is still dropped when its real answers do not decode against the
catalog's own option list -- a mapping entry that never matches is dead weight that
contributes nothing to the prompt -- but today nothing does.

**The 158 `Bipolar` economic-preference price lists are rendered, not skipped** (discount
rate, present bias, risk and loss aversion — 21% of all response columns and once the largest
exclusion here). Their `Columns` are the bare codes `'1'`/`'2'`, so what a stored `'1'` MEANS
lives in the row label, which the catalog writes as `'LEFT:RIGHT'`
(`'$6.00 in 6 weeks:$3.00 in 5 weeks'`). `_bipolar_sides` splits on that colon and emits
`choices = {'1': left, '2': right}` so the prompt shows the option the respondent picked
instead of the code. This is the only place the map's value is a DIFFERENT option rather than
a re-spelling of its key (`QID27`'s `TRUE` -> `True`), which is why `fit_to_csv` has to carry
the value through rather than rebuild it. Costs 6,798 tokens per persona (12,521 -> 19,319 on
the rendered `Q:`/`A:` lines, o200k_base): unlike the Likert batteries, a price-list row cannot
be compressed, because the ladder's whole content IS the 158 individual comparisons. All 158 sit in the `Economic preferences` block, outside the
paper's holdout.

**The 84 MAVR/MAHR checkbox columns are rendered as ordinary single-column screeners** (the
20 Beck Depression Inventory groups and the Wason card task, 23.1 boxes checked per
respondent). They are NOT `is_multi_select`, whose branch tests `respondent_row[col] == 1` --
the coded-format convention Twin's `data_format: "text"` never produces. They do not need it:
a checked box stores the option's OWN LABEL TEXT and an unchecked one stores `NaN`, so
`_identity_choices` decodes a checked box and the single-choice branch skips `NaN` silently.
Only the boxes the respondent actually checked reach the prompt, which is the right reading
of a "select each that applies" item.

**The 56 SL/ML/FORM free-text columns are rendered too**, through the `free_text: true` flag
and `extract_screener_profile`'s matching branch -- 15 cognitive-test answers, the three
self-description essays (2,058 distinct texts), the 20-box word chain and the three
6-box thought listings. Their cardinality rules out enumerating them into `choices`, so the
cell is rendered as written, exactly as `extract_demographics` already does for age/state/
zipcode. `fit_to_csv` carries them through untested: with no option list there is no decode
rate, and a filled cell is by definition readable. Together the 140 cost +2,684 tokens per
persona (19,319 -> ~22,050 on the same lines), a fifth of what the price lists cost.

The thought listings were checked for leakage specifically: they describe reasoning about the
trust and dictator games (QID117-QID122, QID231), every one of which is itself already in the
persona, so the thoughts disclose nothing the answers don't.

`choices` is keyed by what the CSV actually STORES and valued by the text to render, rather
than being an identity map, because the two disagree: `QID27`'s catalog
labels are `TRUE`/`FALSE` while its cells read `True`/`False`, and extraction does a plain
`choices.get(value)` with no case fallback. Decoding is checked through the runtime's own
`_normalize_choice_value`/`_is_filled` so this generator can never be stricter than the
extraction it feeds -- checking against raw strings instead wrongly condemned `QID198`,
whose cells pandas reads as `1.0` and the runtime already normalises to `'1'`.

Every entry is a single-column `screener`, never `is_grid`: the grid branch tests
`is not None`, and a blank matrix cell read from a CSV is `NaN`, not `None`, so it would
render `label: nan`. The single branch's `choices.get(value)` returns None for `nan` and
skips the item silently. For a price list `is_grid` could not work at all -- its `scale` is
one map for the whole battery, while a price list's two options change on every row.

Usage:  .venv\\Scripts\\python.exe scripts/twin2k/build_twin2k_persona.py
"""

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.twin2k.build_twin2k_config import (  # noqa: E402  (path bootstrap above)
    OUT_DIR,
    build_demographic_mapping,
    holdout_columns,
    load_catalog,
)

# Private on purpose: these two decide what extraction considers a filled cell and what
# key it looks up. A generator that judged decodability by any other rule would either
# emit entries the runner cannot read or drop columns it reads fine.
from src.data.question_mapper import _is_filled, _normalize_choice_value  # noqa: E402

RESPONSE_CSV = Path("data/twin2k500/wave1_3_response_label.csv")
# The paper's holdout IS its wave-4 retest instrument, so this file's columns are a second,
# independent derivation of what must stay out of the persona. Asserted equal to the
# block-level set at generation time.
WAVE4_CSV = Path("data/twin2k500/wave4_response_label.csv")
PERSONA_OUT = OUT_DIR / "twin2k_demographic_mapping_persona.json"

# Selectors whose answers are one of a known option list, so an identity `choices` map
# can decode them.
CHOICE_SELECTORS = {"SAVR", "SAHR"}
MATRIX_SELECTORS = {"Likert", "Matrix"}

# Multi-answer checkbox batteries. One column per option; a checked box stores the option's
# own LABEL TEXT and an unchecked one stores `NaN`, so `_identity_choices` decodes them the
# same way a single-answer question is decoded and `fit_to_csv` narrows each column to the
# one value it holds. They do NOT go through `is_multi_select`, whose `== 1` test is the
# coded-format convention Twin's `data_format: "text"` never produces.
MULTI_SELECTORS = {"MAVR", "MAHR"}

# Free text. No option list exists to decode against, so these emit `free_text: true` and
# extraction renders the cell as written (`extract_screener_profile`'s free-text branch).
FREE_TEXT_SELECTORS = {"SL", "ML", "FORM", "TE"}

# The economic-preference price lists. Structurally a matrix, but its `Columns` are the bare
# codes `'1'`/`'2'` and the two things being compared live in the ROW label as `'LEFT:RIGHT'`,
# so it needs its own decode map instead of `_identity_choices` (see `_bipolar_sides`).
BIPOLAR_SELECTOR = "Bipolar"
BIPOLAR_COLUMNS = ["1", "2"]

# A column joins the persona only if nearly every real answer decodes. Below this the
# entry would be dead weight in the mapping while contributing nothing to the prompt.
MIN_DECODE_RATE = 0.99

# One SHORT tag per matrix battery, standing in for its instruction stem. The stem repeats
# once per row -- a 203-char stem x44, a 476-char stem x24, an 84-char stem x65 -- and is
# boilerplate ("Please indicate your agreement with each of the following statements about
# yourself.") while the row label is a self-contained first-person statement and the ANSWER
# label already carries the scale ("Agree strongly", "TRUE", "Not at all 0"). Tagging costs
# nothing in meaning and saves 39% of the persona's tokens (18,866 -> 11,503 on the rendered
# Q:/A: lines, o200k_base).
#
# Hand-written rather than derived: 12 of the 16 stems END on boilerplate, so "keep the last
# sentence" recovers the meaning for QID25 and garbage for QID29 ("Work fairly quickly.").
# Coverage is asserted both ways in `main`, because a silent fallback to the full stem is the
# regression this table exists to prevent.
BATTERY_TAGS = {
    "QID25": "I see myself as someone who",
    "QID26": "Agree or disagree",
    "QID27": "True or false of me",
    "QID28": "True or untrue of me",
    # Three batteries answer on a numbered scale whose interior points are bare digits
    # ("A: 8"), because the anchors live in the option labels and the ORIGINAL stems never
    # stated the range either. The tag carries it instead: ~660 tokens to make 53 answers
    # readable.
    "QID29": "Importance as a guiding principle in my life (1 = not important, 9 = highly important)",
    "QID30": "How accurately this describes me (1 = extremely inaccurate, 9 = extremely accurate)",
    "QID35": "Agree or disagree",
    "QID125": "Bothered by this symptom in the past week (0 = not at all, 3 = severely)",
    "QID232": "Agree or disagree",
    "QID233": "Agree or disagree",
    "QID234": "Agree or disagree",
    "QID235": "Agree or disagree",
    "QID236": "True or false of me",
    "QID237": "Agree or disagree",
    "QID238": "Agree or disagree",
    "QID239": "Agree or disagree",
    # The 13 `Bipolar` price lists. Here the tag is not a saving but the only place the
    # comparison can live: the row label holds the two sides and nothing else. The six
    # payment ladders are self-describing ('$6.00 in 6 weeks:$3.00 in 5 weeks'), so a generic
    # tag suffices. The seven lotteries are not -- their left side reads only 'Lottery', and
    # QID251/QID252 plus QID276/QID278 have BYTE-IDENTICAL `Rows`, so without the lottery's
    # terms in the tag those 28 answers would be indistinguishable from each other.
    "QID84": "Choose which payment you would prefer",
    "QID244": "Choose which payment you would prefer",
    "QID245": "Choose which payment you would prefer",
    "QID246": "Choose which payment you would prefer",
    "QID247": "Choose which payment you would prefer",
    "QID248": "Choose which payment you would prefer",
    "QID250": "Choose which you would prefer; the LOTTERY is a 50% chance of winning $6 and a 50% chance of winning $0",
    "QID251": "Choose which you would prefer; the LOTTERY is a 50% chance of winning $8 and a 50% chance of winning $2",
    "QID252": "Choose which you would prefer; the LOTTERY is a 50% chance of winning $10 and a 50% chance of winning $0",
    "QID276": "Choose which you would prefer; the LOTTERY is a 50% chance of LOSING $6 and a 50% chance of winning $0",
    "QID277": "Choose which you would prefer; the LOTTERY is a 50% chance of LOSING $8 and a 50% chance of LOSING $2",
    "QID278": "Choose which you would prefer; the LOTTERY is a 50% chance of LOSING $10 and a 50% chance of winning $0",
    "QID279": "Choose which you would prefer; the LOTTERY is a 50% chance of LOSING $8 and a 50% chance of winning a value x",
    # The 20 Beck Depression Inventory groups (QID126, QID128-QID134, QID136-QID147). Their
    # own `QuestionText` is EMPTY -- the battery's instruction lives in QID127, a column-less
    # `DB` block -- so a tag is the only place it can come from. One shared string loses
    # nothing: each option is a self-contained first-person sentence ("I feel sad"), and the
    # answer text IS that sentence. The BDI's suicidality group is simply absent from the
    # catalog (QID135 has no columns), so nothing here asks about self-harm.
    **{
        f"QID{qid}": (
            "Statements describing the way I have been feeling in the past week, "
            "including today (I selected each that applied)"
        )
        for qid in [126, *range(128, 135), *range(136, 148)]
    },
    "QID221": (
        "Card task — the rule is \"if there is an A on the letter side, there is a 3 on the "
        "number side\"; the cards I would turn over"
    ),
    "QID10": "Word association, starting from the word PAPER",
    # The three thought listings need telling apart the way the lotteries did: QID271's and
    # QID275's stems are near-identical and only survey ORDER says which game each follows --
    # QID271/QID272 the trust game (QID117-QID122), QID275 the dictator game (QID231), both
    # over the same $5. NB these three are among the ten QuestionIDs the catalog uses twice;
    # `BATTERY_TAGS` is keyed by QuestionID, and the `Cognitive tests` twins are `SAVR`, which
    # never consults this table, so the collision is inert -- but do not key a tag off a
    # colliding id expecting it to reach only one of the two entries.
    "QID271": "Thoughts I had while deciding how much of the $5 to send to the other person",
    "QID272": "Thoughts I had while deciding how much to send back to the other person",
    "QID275": "Thoughts I had while deciding how to split the $5 when I alone decided",
}


def assert_holdout_matches_wave4(holdout: set) -> None:
    """Cross-check the block-level holdout against the paper's own retest instrument.

    Two derivations of the same partition from two files: `BlockName` in the catalog, and
    the column list of the wave-4 CSV. If they ever disagree, the exclusion rule is wrong
    (or the dataset changed) — not something to discover after a 9,000-call run.
    """
    wave4 = set(pd.read_csv(WAVE4_CSV, nrows=0).columns) - {"pid"}
    if holdout != wave4:
        raise RuntimeError(
            f"holdout ({len(holdout)}) != wave-4 columns ({len(wave4)}); "
            f"only in blocks: {sorted(holdout - wave4)[:5]}; "
            f"only in wave 4: {sorted(wave4 - holdout)[:5]}"
        )
    print(f"holdout: {len(holdout)} columns, set-equal to {WAVE4_CSV.name}")


def _identity_choices(options: list) -> dict:
    """Seed the decode map from the catalog's option list, before `fit_to_csv` re-keys it."""
    return {str(option): str(option) for option in options}


def _battery_tag(entry: dict, n_rows: int) -> str:
    """The short stand-in for a matrix battery's instruction stem.

    Fatal when a battery reaches the persona untagged: falling back to the full stem would
    quietly restore the per-row duplication `BATTERY_TAGS` exists to remove, on a mapping
    nobody re-reads. A new battery here means the catalog or the holdout moved.
    """
    tag = BATTERY_TAGS.get(entry["QuestionID"], "").strip()
    if not tag:
        raise SystemExit(
            f"{entry['QuestionID']} contributes {n_rows} persona row(s) but has no "
            f"BATTERY_TAGS entry — add a short tag for its stem:\n"
            f"  {(entry.get('QuestionText') or '')[:200]!r}"
        )
    return tag


def _bipolar_sides(entry: dict, label: str) -> tuple:
    """Split a price-list row label `'LEFT:RIGHT'` into the two options it offers.

    Fatal rather than skipped on anything else. `Columns` gives no clue which side a stored
    `'1'` means -- that mapping IS the colon's position -- so a label this cannot split, or a
    `Columns` that is not `['1', '2']`, would silently emit an entry whose answer text is the
    wrong option. All 158 rows split on exactly one colon today; a change here means the
    dataset moved.
    """
    sides = [side.strip() for side in label.split(":")]
    if len(sides) != 2 or not all(sides):
        raise SystemExit(
            f"{entry['QuestionID']}: price-list row {label!r} is not 'LEFT:RIGHT', so which "
            f"option a stored '1' means cannot be recovered"
        )
    return sides[0], sides[1]


def candidate_entries(catalog: dict, excluded: set) -> tuple:
    """Yield (column, screener entry) for every prior-answer column, plus skip counts.

    Walks the catalog in its own order so the persona reads in survey order, which is
    how the paper's persona is laid out and how a respondent actually answered.

    Also returns the matrix batteries that contributed, so `main` can catch a `BATTERY_TAGS`
    key that no longer matches anything.
    """
    entries, skipped = {}, {"excluded": 0}
    tagged = set()
    for entry in catalog.values():
        selector = (entry.get("Settings") or {}).get("Selector") or entry["QuestionType"]
        stem = entry.get("QuestionText") or ""
        columns = entry.get("csv_columns") or []

        if selector in MATRIX_SELECTORS:
            labels, scale = entry.get("Rows") or [], entry.get("Columns") or []
            pairs = list(zip(columns, labels))
            rows = [(column, label) for column, label in pairs if column not in excluded]
            skipped["excluded"] += len(pairs) - len(rows)
            if not rows:
                continue
            # A short tag instead of `stem`, which would repeat once per row.
            tag = _battery_tag(entry, len(rows))
            tagged.add(entry["QuestionID"])
            for column, label in rows:
                entries[column] = {
                    "question": f"{tag} — {label}",
                    "type": "screener",
                    "choices": _identity_choices(scale),
                }
            continue

        if selector == BIPOLAR_SELECTOR:
            labels, scale = entry.get("Rows") or [], entry.get("Columns") or []
            if scale != BIPOLAR_COLUMNS:
                raise SystemExit(
                    f"{entry['QuestionID']}: price-list Columns are {scale}, not "
                    f"{BIPOLAR_COLUMNS}, so left/right can no longer be read off the code"
                )
            pairs = list(zip(columns, labels))
            rows = [(column, label) for column, label in pairs if column not in excluded]
            skipped["excluded"] += len(pairs) - len(rows)
            if not rows:
                continue
            tag = _battery_tag(entry, len(rows))
            tagged.add(entry["QuestionID"])
            for column, label in rows:
                left, right = _bipolar_sides(entry, label)
                entries[column] = {
                    "question": f"{tag} — {left} or {right}?",
                    "type": "screener",
                    # The CSV stores the code, the prompt must show the option it stands for.
                    # `fit_to_csv` carries these values through rather than re-deriving them.
                    "choices": {scale[0]: left, scale[1]: right},
                }
            continue

        if selector in CHOICE_SELECTORS:
            for column in columns:
                if column in excluded:
                    skipped["excluded"] += 1
                    continue
                entries[column] = {
                    "question": stem,
                    "type": "screener",
                    "choices": _identity_choices(entry.get("Options") or []),
                }
            continue

        if selector in MULTI_SELECTORS:
            rows = [column for column in columns if column not in excluded]
            skipped["excluded"] += len(columns) - len(rows)
            if not rows:
                continue
            # A tag, not `stem`: the 20 BDI groups have no stem at all, and QID221's repeats
            # once per card. Every column gets the WHOLE option list and `fit_to_csv` narrows
            # it to the single value that column holds. Unlike `Bipolar`, column<->option
            # alignment is therefore irrelevant: a checked box stores the option's own label
            # either way, so there is nothing to get backwards.
            tag = _battery_tag(entry, len(rows))
            tagged.add(entry["QuestionID"])
            for column in rows:
                entries[column] = {
                    "question": tag,
                    "type": "screener",
                    "choices": _identity_choices(entry.get("Options") or []),
                }
            continue

        if selector in FREE_TEXT_SELECTORS:
            labels = entry.get("Rows") or []
            if labels:
                # A battery of boxes (the word chain, the thought listings): the stem repeats
                # once per box, so tag it and let the row label number the box. Same
                # `zip(columns, Rows)` pairing the matrix branch uses.
                pairs = list(zip(columns, labels))
                rows = [(c, label) for c, label in pairs if c not in excluded]
                skipped["excluded"] += len(pairs) - len(rows)
                if not rows:
                    continue
                tag = _battery_tag(entry, len(rows))
                tagged.add(entry["QuestionID"])
                questions = {c: f"{tag} — {label}" for c, label in rows}
            else:
                # A standalone question (cognitive tests, the three self-description essays):
                # the stem IS the question, so keep it verbatim.
                rows = [c for c in columns if c not in excluded]
                skipped["excluded"] += len(columns) - len(rows)
                if not rows:
                    continue
                questions = {c: stem for c in rows}
            for column, question in questions.items():
                # No `choices` key at all: there is no option list, and the runtime's
                # free-text branch never consults one.
                entries[column] = {
                    "question": question,
                    "type": "screener",
                    "free_text": True,
                }
            continue

        # Every selector that reaches the persona now has a branch. Fatal rather than a
        # silent skip: a dataset revision that introduces a new selector must be noticed
        # here, not by a persona that quietly shrank.
        contributing = [column for column in columns if column not in excluded]
        if contributing:
            raise SystemExit(
                f"{entry['QuestionID']}: unhandled selector {selector!r} contributes "
                f"{len(contributing)} column(s) ({contributing[:3]}) — add a branch for it "
                f"or exclude it deliberately"
            )

    return entries, skipped, tagged


def fit_to_csv(entries: dict, df: pd.DataFrame) -> tuple:
    """Re-key each entry's `choices` by the values the CSV holds; drop what cannot decode.

    Answers are normalised with the runtime's `_normalize_choice_value` and matched to the
    catalog's option list ignoring case and surrounding space, so the emitted key is the
    CSV's own spelling and the emitted answer text is the catalog's canonical label.

    Returns (kept entries, [(column, decode rate, n answered, why)] for the drops,
    total decoded cells).
    """
    kept, dropped, answered_cells = {}, [], 0
    for column, entry in entries.items():
        if column not in df.columns:
            dropped.append((column, 0.0, 0, "column absent from the CSV"))
            continue
        values = [_normalize_choice_value(v) for v in df[column] if _is_filled(v)]
        if not values:
            dropped.append((column, 0.0, 0, "no answers in the CSV"))
            continue

        # Free text has no decode map, so there is nothing to re-key and no decode rate to
        # test -- a filled cell is by definition readable. Keep the entry as written.
        if entry.get("free_text"):
            kept[column] = entry
            answered_cells += len(values)
            continue

        # Keyed by the option as the catalog spells it, VALUED by the answer text to render.
        # Iterating `.items()` rather than the keys matters only for the price lists, whose
        # value is the row's option and not the stored code -- for every identity map built by
        # `_identity_choices` the two are the same string.
        canonical = {
            str(option).strip().casefold(): str(text)
            for option, text in entry["choices"].items()
        }
        # `sorted`, not bare `set`: string hashing is randomized per process, so iterating
        # the set would give this checked-in file a different key order on every run and
        # bury a real regeneration diff under ~2,800 lines of reordering.
        choices = {
            value: canonical[value.strip().casefold()]
            for value in sorted(set(values))
            if value.strip().casefold() in canonical
        }
        decoded = sum(1 for value in values if value in choices)
        rate = decoded / len(values)
        if rate < MIN_DECODE_RATE:
            unmatched = sorted({v for v in values if v not in choices})[:3]
            dropped.append((column, rate, len(values), f"unmatched {unmatched}"))
            continue

        kept[column] = {**entry, "choices": choices}
        answered_cells += decoded
    return kept, dropped, answered_cells


def main() -> int:
    if not RESPONSE_CSV.exists():
        raise FileNotFoundError(
            f"{RESPONSE_CSV} not found — run scripts/twin2k/fetch_twin2k.py first"
        )
    catalog = load_catalog()
    demographics = build_demographic_mapping(catalog)
    holdout = holdout_columns(catalog)
    assert_holdout_matches_wave4(holdout)
    excluded = holdout | set(demographics)
    print(f"excluding {len(excluded)} columns: {len(demographics)} demographic + "
          f"{len(holdout)} held out by the paper")

    entries, skipped, tagged = candidate_entries(catalog, excluded)
    stale = sorted(set(BATTERY_TAGS) - tagged)
    if stale:
        raise SystemExit(
            f"BATTERY_TAGS has {len(stale)} key(s) that no longer contribute any persona "
            f"column: {stale} — drop them, or find out why the battery left the persona."
        )
    print(f"candidate prior-answer columns: {len(entries)}")
    print(f"  {len(tagged)} batteries rendered with a short tag instead of their stem")
    print(f"  {skipped['excluded']} battery rows dropped as demographic or held out")

    df = pd.read_csv(RESPONSE_CSV, low_memory=False)
    kept, dropped, answered_cells = fit_to_csv(entries, df)
    for column, rate, n, why in dropped:
        print(f"  dropped {column}: {rate:.0%} of {n} answers decode — {why}")
    print(f"kept {len(kept)} columns ({len(dropped)} dropped for low decode rate)")
    if kept.keys() & holdout:
        raise RuntimeError(
            f"persona carries {len(kept.keys() & holdout)} holdout column(s): "
            f"{sorted(kept.keys() & holdout)[:5]}"
        )

    # 14 demographics first so the persona block and the prior answers stay separable;
    # `screener_profile` preserves this insertion order into the prompt.
    mapping = {**demographics, **kept}
    PERSONA_OUT.write_text(
        json.dumps(mapping, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    per_respondent = answered_cells / len(df)
    print(f"\nWrote {PERSONA_OUT}")
    print(f"  {len(demographics)} demographics + {len(kept)} prior-answer screeners")
    print(f"  {per_respondent:.0f} answered prior questions per respondent on average")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
