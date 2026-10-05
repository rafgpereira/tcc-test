"""Tests for the life cycle of a problem folder: building, closing, resuming (T055; FR-023, FR-024)."""

import json
import os
import stat

import pytest

from dataset import config
from dataset.persistence import store

PID = "1101_A"


@pytest.fixture()
def root(tmp_path):
    store.ensure_work_dir(tmp_path)
    return tmp_path


def test_a_problem_is_built_in_the_building_folder_with_mode_0700(root):
    folder = store.start_building(root, PID)
    assert folder == root / config.BUILDING_DIR / PID
    assert folder.is_dir()
    assert stat.S_IMODE(folder.stat().st_mode) == 0o700


def test_finalizing_moves_the_folder_with_an_atomic_rename(root, monkeypatch):
    folder = store.start_building(root, PID)
    store.write_problem_text(folder, "enunciado.md", "text")
    renames = []
    real = os.rename
    monkeypatch.setattr(os, "rename", lambda a, b: (renames.append((a, b)), real(a, b))[1])
    final = store.finalize_building(root, PID)
    assert final == root / config.PROBLEMS_DIR / PID
    assert (final / "enunciado.md").read_text() == "text"
    assert not folder.exists()
    assert len(renames) == 1


def test_finalizing_refuses_to_overwrite_a_closed_problem(root):
    store.write_problem_text(store.start_building(root, PID), "a.txt", "1")
    store.finalize_building(root, PID)
    store.write_problem_text(store.start_building(root, PID), "a.txt", "2")
    with pytest.raises(FileExistsError):
        store.finalize_building(root, PID)


def test_a_partial_building_folder_found_at_the_start_is_discarded(root):
    partial = store.start_building(root, PID)
    store.write_problem_text(partial, "AC_ref.cpp", "half written")
    other = store.start_building(root, "1102_B")
    store.write_problem_text(other, "x", "y")
    removed = store.reset_building(root)
    assert removed == 2
    assert list((root / config.BUILDING_DIR).iterdir()) == []


def test_starting_again_rebuilds_from_scratch(root):
    first = store.start_building(root, PID)
    store.write_problem_text(first, "stale.txt", "old")
    again = store.start_building(root, PID)
    assert list(again.iterdir()) == []


def test_reset_building_never_touches_the_closed_problems(root):
    done = store.start_building(root, PID)
    store.write_problem_text(done, "validacao.json", "{}")
    store.finalize_building(root, PID)
    store.start_building(root, "1102_B")
    store.reset_building(root)
    assert (root / config.PROBLEMS_DIR / PID / "validacao.json").is_file()


def test_the_status_of_a_closed_problem_is_read_from_validacao_json(root):
    assert store.problem_status(root, PID) is None
    folder = store.start_building(root, PID)
    store.write_problem_json(folder, "validacao.json", {"problem_id": PID, "status": "discarded"})
    assert store.problem_status(root, PID) is None  # still building: not closed
    store.finalize_building(root, PID)
    assert store.problem_status(root, PID) == "discarded"


@pytest.mark.parametrize("status", ["complete", "pending_triage", "discarded"])
def test_the_three_final_statuses_are_not_reprocessed(root, status):
    folder = store.start_building(root, PID)
    store.write_problem_json(folder, "validacao.json", {"problem_id": PID, "status": status})
    store.finalize_building(root, PID)
    assert store.is_closed(root, PID)


def test_an_unknown_problem_is_not_closed(root):
    assert not store.is_closed(root, PID)


def test_the_extraction_timestamp_is_written_once_and_preserved(root):
    folder = store.start_building(root, PID)
    first = store.preserved_timestamp(folder, now="2026-09-21T10:00:00Z")
    assert first == "2026-09-21T10:00:00Z"
    store.write_problem_json(folder, "metadata.json", {"extraction_timestamp": first})
    later = store.preserved_timestamp(folder, now="2027-01-01T00:00:00Z")
    assert later == "2026-09-21T10:00:00Z"


def test_files_are_written_atomically_and_deterministically(root):
    folder = store.start_building(root, PID)
    store.write_problem_json(folder, "b.json", {"z": 1, "a": [1, 2]})
    text = (folder / "b.json").read_text()
    assert text == '{\n  "a": [\n    1,\n    2\n  ],\n  "z": 1\n}\n'
    assert not any(p.name.endswith(".tmp") for p in folder.iterdir())


def test_source_files_are_normalized_to_utf8_and_lf(root):
    folder = store.start_building(root, PID)
    store.write_problem_text(folder, "AC_ref.cpp", "int main(){}\r\n")
    assert (folder / "AC_ref.cpp").read_bytes() == b"int main(){}\n"


def test_a_pending_triage_folder_holds_only_the_validation_and_the_candidate(root):
    folder = store.start_building(root, PID)
    store.write_problem_json(folder, "validacao.json", {"problem_id": PID})
    store.write_problem_text(folder, "AC_candidate.cpp", "x")
    store.finalize_building(root, PID)
    names = sorted(p.name for p in (root / config.PROBLEMS_DIR / PID).iterdir())
    assert names == ["AC_candidate.cpp", "validacao.json"]


def test_written_files_are_given_to_the_host_user_when_running_as_root(root, monkeypatch):
    calls = []
    monkeypatch.setattr(store, "chown_to_host", lambda path: calls.append(path.name))
    folder = store.start_building(root, PID)
    store.write_problem_text(folder, "a.txt", "x")
    store.write_problem_json(folder, "b.json", {})
    assert PID in calls and "a.txt" in calls and "b.json" in calls
    json.dumps(calls)
