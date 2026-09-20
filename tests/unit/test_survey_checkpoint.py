"""Unit tests for src/utils/survey_checkpoint.py (batched checkpoint/resume I/O)."""


from src.utils import survey_checkpoint as ckpt


def _record(respid, global_index, status="ok"):
    return {
        "respid": str(respid),
        "global_index": global_index,
        "status": status,
        "state": {"Q1": "Yes"},
        "explanations": {"Q1": "because"},
        "tier": None,
        "error_records": [],
    }


def test_save_and_load_roundtrip_preserves_global_index_order(tmp_path):
    run_dir = ckpt.init_run_dir(str(tmp_path), "t1")
    # Save two batches out of natural order to prove sorting is by global_index.
    ckpt.save_batch(run_dir, 2, [_record(200, 2), _record(300, 3)])
    ckpt.save_batch(run_dir, 1, [_record(0, 0), _record(100, 1)])

    records = ckpt.load_all_batches(run_dir)

    assert [r["global_index"] for r in records] == [0, 1, 2, 3]
    assert [r["respid"] for r in records] == ["0", "100", "200", "300"]


def test_manifest_resume_skips_completed_respids(tmp_path):
    run_dir = ckpt.init_run_dir(str(tmp_path), "t2")
    ckpt.save_batch(run_dir, 1, [_record(0, 0), _record(100, 1)])

    done = ckpt.completed_respids(run_dir)

    assert done == {"0", "100"}
    # A fresh run dir has no completed respids.
    empty_dir = ckpt.init_run_dir(str(tmp_path), "empty")
    assert ckpt.completed_respids(empty_dir) == set()


def test_load_skips_torn_trailing_line(tmp_path):
    run_dir = ckpt.init_run_dir(str(tmp_path), "t3")
    ckpt.save_batch(run_dir, 1, [_record(0, 0), _record(100, 1)])

    # Simulate a process killed mid-write: append a truncated JSON line to the batch file.
    batch_file = run_dir / "batch_001.jsonl"
    with open(batch_file, "a", encoding="utf-8") as handle:
        handle.write('{"respid": "999", "global_index": 2, "sta')  # torn, no newline

    records = ckpt.load_all_batches(run_dir)

    # The torn trailing line is skipped; the two valid records survive.
    assert [r["global_index"] for r in records] == [0, 1]


def test_load_skips_torn_line_with_trailing_newline(tmp_path):
    run_dir = ckpt.init_run_dir(str(tmp_path), "t3b")
    ckpt.save_batch(run_dir, 1, [_record(0, 0), _record(100, 1)])

    # Torn write followed by a trailing newline (torn line is not the literal last line).
    batch_file = run_dir / "batch_001.jsonl"
    with open(batch_file, "a", encoding="utf-8") as handle:
        handle.write('{"respid": "999", "global_index": 2, "sta\n')

    records = ckpt.load_all_batches(run_dir)

    assert [r["global_index"] for r in records] == [0, 1]


def test_save_batch_updates_manifest_batches_and_completed(tmp_path):
    run_dir = ckpt.init_run_dir(str(tmp_path), "t4")
    ckpt.save_batch(run_dir, 1, [_record(0, 0)])
    ckpt.save_batch(run_dir, 2, [_record(100, 1)])

    manifest = ckpt.load_manifest(run_dir)

    assert sorted(manifest["completed_respids"]) == ["0", "100"]
    assert [b["batch_num"] for b in manifest["batches"]] == [1, 2]
    assert [b["n_personas"] for b in manifest["batches"]] == [1, 1]


def test_norm_respid_canonicalizes_int_valued_floats():
    # int/float drift from Excel round-trips must compare equal for resume to work.
    assert ckpt.norm_respid(185772161) == "185772161"
    assert ckpt.norm_respid(185772161.0) == "185772161"
    assert ckpt.norm_respid("185772161.0") == "185772161"
    assert ckpt.norm_respid("185772161") == "185772161"
    # Non-integer / non-numeric ids are left as-is.
    assert ckpt.norm_respid("abc") == "abc"
    assert ckpt.norm_respid("12.5") == "12.5"


def test_resume_skips_across_int_float_respid_drift(tmp_path):
    # Batch saved with float respids; resume compares against int personas.
    run_dir = ckpt.init_run_dir(str(tmp_path), "drift")
    ckpt.save_batch(run_dir, 1, [_record(185772161.0, 0), _record(185772162.0, 1)])

    done = ckpt.completed_respids(run_dir)
    # int-form persona respids must be recognized as done
    assert ckpt.norm_respid(185772161) in done
    assert ckpt.norm_respid(185772162) in done


def test_no_tmp_files_left_after_save(tmp_path):
    run_dir = ckpt.init_run_dir(str(tmp_path), "t5")
    ckpt.save_batch(run_dir, 1, [_record(0, 0)])

    # Atomic writes must not leave .tmp files behind.
    assert list(run_dir.glob("*.tmp")) == []


# Question-scoped checkpoint (stateless runs), keyed on (question_id, respid)

def _row(respid, variation_id=0, response="Yes"):
    return {
        "respid": ckpt.norm_respid(respid),
        "response": response,
        "explanation": "[Var0] because",
        "tier": None,
        "variation_id": variation_id,
    }


def test_save_batch_writes_aborted_records_but_omits_them_from_completed(tmp_path):
    run_dir = ckpt.init_run_dir(str(tmp_path), "f4")
    ckpt.save_batch(run_dir, 1, [_record(0, 0), _record(100, 1, status="aborted")])

    assert len(ckpt.load_all_batches(run_dir)) == 2
    assert ckpt.completed_respids(run_dir) == {"0"}


def test_a_recovered_persona_replaces_its_aborted_record(tmp_path):
    run_dir = ckpt.init_run_dir(str(tmp_path), "f5")
    ckpt.save_batch(
        run_dir,
        1,
        [_record(0, 0), _record(100, 1), _record(200, 2), _record(300, 3, status="aborted")],
    )
    # --resume re-runs respid 300, appending a second record at the same global_index.
    ckpt.save_batch(run_dir, 2, [_record(300, 3)])

    records = ckpt.load_all_batches(run_dir)

    # Exactly one record per index, or main.py's integrity check fails the run.
    assert [r["global_index"] for r in records] == [0, 1, 2, 3]
    assert records[3]["status"] == "ok"


def test_a_persona_that_never_recovers_still_fills_its_index(tmp_path):
    """The regression that would otherwise break the export: dropping the aborted record
    leaves a hole, and the integrity check demands exactly one record per index."""
    run_dir = ckpt.init_run_dir(str(tmp_path), "f6")
    ckpt.save_batch(
        run_dir, 1, [_record(0, 0), _record(100, 1, status="aborted"), _record(200, 2)]
    )

    records = ckpt.load_all_batches(run_dir)

    assert [r["global_index"] for r in records] == [0, 1, 2]
    assert records[1]["status"] == "aborted"


def test_records_written_before_status_existed_are_read_as_successes(tmp_path):
    """Every pre-existing checkpoint must reconstruct unchanged."""
    run_dir = ckpt.init_run_dir(str(tmp_path), "f7")
    legacy = [_record(0, 0), _record(100, 1)]
    for record in legacy:
        del record["status"]
    ckpt.save_batch(run_dir, 1, legacy)

    loaded = ckpt.load_all_batches(run_dir)
    assert [r["global_index"] for r in loaded] == [0, 1]
    assert [r["respid"] for r in loaded] == ["0", "100"]
    assert ckpt.completed_respids(run_dir) == {"0", "100"}


def test_the_later_attempt_wins_when_both_attempts_aborted(tmp_path):
    run_dir = ckpt.init_run_dir(str(tmp_path), "f8")
    first = _record(100, 1, status="aborted")
    first["explanations"] = {"Q1": "first attempt"}
    second = _record(100, 1, status="aborted")
    second["explanations"] = {"Q1": "second attempt"}
    ckpt.save_batch(run_dir, 1, [first])
    ckpt.save_batch(run_dir, 2, [second])

    records = ckpt.load_all_batches(run_dir)

    assert len(records) == 1
    assert records[0]["explanations"] == {"Q1": "second attempt"}
