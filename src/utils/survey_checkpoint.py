"""Checkpoint I/O for resumable survey runs, in two flavours keyed to the two runners.

Stateful runs checkpoint per batch of persona-walks (`save_batch`/`load_all_batches`, keyed on
respid); stateless runs checkpoint per question (`save_question`/`load_question`, keyed on
(question_id, respid)). Each uses its own manifest keys, so a run dir carries one flavour only.
Either way a crash loses at most one in-flight unit, and validation plus Excel export run once at
the end over the reconstructed full result set.

Batch-level resume only: a kill *during* a batch (or question) loses that unit's in-flight
personas, which re-run on resume.

In both flavours the manifest records what SUCCEEDED, not what was attempted: a failed cell or
aborted persona-walk is written to its JSONL but left out of the completed set, so plain `--resume`
re-runs it. That makes `--resume` the single repair path for both modes.

All writes are atomic (temp file + os.replace) so a killed process never leaves a half-written
file the loader trusts. On load, a torn trailing JSONL line is skipped rather than crashing.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Set


def is_failed_row(row: Dict[str, Any]) -> bool:
    """True if a stateless response row is the error path's sentinel rather than a real answer.

    Requires BOTH markers, because either alone can occur legitimately: a real option could be
    labelled "Error" (twin2k ships labels as odd as "1" and "2"), and only the error path writes an
    explanation starting "Failed: " (survey_runner_excel.py). Together they are unambiguous.

    Public because a repair script rebuilds `completed_pairs` from surviving rows
    and must apply the same rule, or pruning one error log would re-mark another's failures complete.
    """
    response = row.get("response")
    if response != "Error" and response != ["Error"]:
        return False
    return str(row.get("explanation", "")).startswith("Failed: ")


def _is_aborted(record: Dict[str, Any]) -> bool:
    """True if a stateful persona record is a walk that did not finish clean.

    Covers both an aborted walk and a walk that ran to the end carrying a failed cell — main.py
    sets an explicit `status` for both, so no sniffing is needed. Records written before that field
    existed have no `status` and are treated as successful, so old checkpoints reconstruct
    unchanged (and, since resume reads the manifest rather than the records, a pre-existing
    checkpoint's failed cells stay marked complete — repair those with rerun_failed.py).
    """
    return record.get("status", "ok") == "aborted"


def norm_respid(respid: Any) -> str:
    """Canonical string form of a respid, stable across int/float drift.

    The persona cache round-trips respids through Excel, so the same id can arrive as int
    185772161 in one run and float 185772161.0 in another. Both must compare equal for resume
    to skip already-saved personas, so an integer-valued float is canonicalized to its int form.
    """
    s = str(respid)
    if s.endswith(".0") and s[:-2].isdigit():
        return s[:-2]
    return s


def init_run_dir(checkpoint_dir: str, run_id: str) -> Path:
    """Create and return the per-run checkpoint dir: <checkpoint_dir>/<run_id>/.

    checkpoint_dir is the base directory passed via --checkpoint-dir (e.g.
    outputs/twin2k/chained/checkpoints); each run_id gets its own subdirectory under it.
    """
    run_dir = Path(checkpoint_dir) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def _manifest_path(run_dir: Path) -> Path:
    return Path(run_dir) / "manifest.json"


def load_manifest(run_dir: Path) -> Dict[str, Any]:
    """Load manifest.json, or return an empty manifest if none exists yet."""
    path = _manifest_path(run_dir)
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _atomic_write(path: Path, text: str) -> None:
    """Write text to path atomically (temp file in same dir + os.replace)."""
    tmp = Path(str(path) + ".tmp")
    with open(tmp, "w", encoding="utf-8") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def save_batch(
    run_dir: Path,
    batch_num: int,
    records: List[Dict[str, Any]],
    timestamp: Optional[str] = None,
) -> None:
    """Persist one batch's per-persona records, then update the manifest — both atomically.

    Args:
        run_dir: checkpoint directory from init_run_dir()
        batch_num: 1-indexed batch number (used for the batch_NNN.jsonl filename)
        records: one dict per persona (see the batched-panel-checkpoint-plan for the shape)
        timestamp: optional stamp recorded in the manifest batch entry
    """
    run_dir = Path(run_dir)
    batch_file = f"batch_{batch_num:03d}.jsonl"

    body = "".join(
        json.dumps(record, ensure_ascii=False) + "\n" for record in records
    )
    _atomic_write(run_dir / batch_file, body)

    # Update manifest after the batch file is safely on disk.
    manifest = load_manifest(run_dir)
    completed = set(manifest.get("completed_respids", []))
    # Same rule as save_question: only clean walks count as complete, so --resume re-runs a persona
    # that aborted or that finished carrying a failed cell, rather than skipping it. Both are still
    # written above with `status: aborted` -- the record keeps filling its global_index for the
    # integrity check, and load_all_batches drops it in favour of a later clean record if one arrives.
    completed.update(norm_respid(r["respid"]) for r in records if not _is_aborted(r))
    batches = manifest.get("batches", [])
    batches.append({
        "file": batch_file,
        "batch_num": batch_num,
        "n_personas": len(records),
        "timestamp": timestamp,
    })
    manifest["completed_respids"] = sorted(completed)
    manifest["batches"] = batches
    _atomic_write(_manifest_path(run_dir), json.dumps(manifest, ensure_ascii=False, indent=2))


def load_all_batches(run_dir: Path) -> List[Dict[str, Any]]:
    """Read every batch_*.jsonl in the run dir, sorted by global_index, one record per index.

    A trailing line that fails to parse (torn write from a killed process) is skipped so a
    partial batch file never crashes the merge.

    Deduplicated on global_index, because an aborted persona stays in its original batch file while
    its re-run appends a second record in a later one. The caller requires exactly one record per
    index (main.py's integrity check), so of the records for one index this keeps the successful one,
    falling back to the latest attempt when none succeeded:

    - persona recovered on resume -> the successful record wins
    - persona never recovered     -> its aborted record still fills the index, so the export works
                                     exactly as it did before this dedupe existed

    Records predating the `status` field are treated as successful (see _is_aborted), so an old
    checkpoint reconstructs unchanged.
    """
    run_dir = Path(run_dir)
    records: List[Dict[str, Any]] = []
    for batch_path in sorted(run_dir.glob("batch_*.jsonl")):
        with open(batch_path, "r", encoding="utf-8") as handle:
            content = handle.read()
        # Keep only non-empty lines so a trailing newline after a torn write doesn't shift
        # which line is "last".
        stripped = [ln for ln in (line.strip() for line in content.splitlines()) if ln]
        for i, line in enumerate(stripped):
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                # Only the last non-empty line may be torn (killed mid-write); anything
                # earlier is real corruption and must surface.
                if i == len(stripped) - 1:
                    continue
                raise
    # Stable sort, so records for the same index stay in batch-file order (batch_001 before
    # batch_002) and "later in the list" means "later attempt".
    records.sort(key=lambda r: r["global_index"])

    deduped: Dict[Any, Dict[str, Any]] = {}
    for record in records:
        index = record["global_index"]
        incumbent = deduped.get(index)
        # The later attempt wins, except that it must not replace a success with an abort.
        if incumbent is not None and _is_aborted(record) and not _is_aborted(incumbent):
            continue
        deduped[index] = record
    return [deduped[index] for index in sorted(deduped)]


def completed_respids(run_dir: Path) -> Set[str]:
    """Return the set of respids whose walk SUCCEEDED (canonical string form), from the manifest.

    Aborted personas are excluded, so a resume re-runs them.
    """
    manifest = load_manifest(Path(run_dir))
    return {norm_respid(r) for r in manifest.get("completed_respids", [])}


# Question-scoped checkpoint (stateless runs)
#
# The stateless runner walks questions serially and fans out across personas within a question, so
# its natural unit is one file per question holding one row per (respid, variation) — not one file
# per persona-wave. A stateless cell is independently re-runnable (no conversation history to
# poison), so resume and repair are both keyed on (question_id, respid).
#
# This uses its own manifest keys (`completed_pairs`, `questions`) so the persona-scoped schema
# above — and the integrity check that reads it — is untouched. A run dir carries one or the other,
# never both; readers dispatch on which key is present.


def _question_file(question_id: str) -> str:
    """Filename-safe slug for a question's checkpoint file."""
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in str(question_id))
    return f"question_{safe}.jsonl"


def save_question(
    run_dir: Path,
    question_id: str,
    rows: List[Dict[str, Any]],
    question_type: Optional[str] = None,
    timestamp: Optional[str] = None,
) -> None:
    """Persist one question's response rows, then update the manifest — both atomically.

    Args:
        run_dir: checkpoint directory from init_run_dir()
        question_id: the question just completed
        rows: one dict per response row: respid, response, explanation, tier, variation_id
        question_type: "single"/"multi", recorded so a resumed run can rebuild without re-asking
        timestamp: optional stamp recorded in the manifest question entry
    """
    run_dir = Path(run_dir)
    filename = _question_file(question_id)

    manifest = load_manifest(run_dir)
    questions = manifest.get("questions", {})
    # Checked before the write: overwriting first would destroy the other question's rows while
    # the manifest still claimed its cells complete.
    claimed = next(
        (qid for qid, meta in questions.items()
         if meta.get("file") == filename and qid != question_id),
        None,
    )
    if claimed is not None:
        raise ValueError(
            f"Checkpoint filename collision: question ids {claimed!r} and {question_id!r} both "
            f"map to {filename}. Rename one question id; a shared file would silently merge them."
        )

    body = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
    _atomic_write(run_dir / filename, body)

    questions[question_id] = {
        "file": filename,
        "question_type": question_type,
        "n_rows": len(rows),
        "timestamp": timestamp,
    }
    pairs = manifest.get("completed_pairs", {})
    # `completed_pairs` means "succeeded", not "attempted": a cell that only ever produced the
    # error sentinel is left out so the next --resume re-runs it instead of skipping it. Every row
    # is still written to the JSONL above -- the rows rebuild the question, and n_rows stays honest.
    #
    # There is deliberately no terminal-failure state, so a cell that cannot succeed (an output-side
    # content filter re-generates the same rejected text) is re-attempted on every resume and such a
    # run never reports "all complete". That is the correct behavior the moment the prompt changes,
    # which is the usual reason to resume; it is not a bug.
    pairs[question_id] = sorted(
        {norm_respid(row["respid"]) for row in rows if not is_failed_row(row)}
    )
    manifest["questions"] = questions
    manifest["completed_pairs"] = pairs
    _atomic_write(_manifest_path(run_dir), json.dumps(manifest, ensure_ascii=False, indent=2))


def load_question(run_dir: Path, question_id: str) -> List[Dict[str, Any]]:
    """Read one question's checkpointed rows, in written order.

    A torn trailing JSONL line (killed mid-write) is skipped, matching load_all_batches.
    """
    path = Path(run_dir) / _question_file(question_id)
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as handle:
        content = handle.read()
    stripped = [ln for ln in (line.strip() for line in content.splitlines()) if ln]
    rows: List[Dict[str, Any]] = []
    for i, line in enumerate(stripped):
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            # Only the last non-empty line may be torn; anything earlier is real corruption.
            if i == len(stripped) - 1:
                continue
            raise
    return rows


def completed_pairs(run_dir: Path) -> Dict[str, Set[str]]:
    """Return {question_id: {respid, ...}} that SUCCEEDED, respids in canonical form.

    Cells that only produced the error sentinel are excluded, so a resume re-runs them.
    """
    manifest = load_manifest(Path(run_dir))
    return {
        qid: {norm_respid(r) for r in respids}
        for qid, respids in manifest.get("completed_pairs", {}).items()
    }


def question_type_for(run_dir: Path, question_id: str) -> Optional[str]:
    """Question type recorded when the question was checkpointed, or None if unknown."""
    manifest = load_manifest(Path(run_dir))
    return manifest.get("questions", {}).get(question_id, {}).get("question_type")
