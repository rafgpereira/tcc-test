"""The on-disk state of the SLM suites: directories, the lock and write-once atomic files."""

import os

import pytest

from ai_clients import config, store
from tests.ai_clients.test_schemas import execution, generation


def test_ensure_suites_dir_creates_every_level(tmp_path):
    store.ensure_suites_dir(tmp_path)
    for path in (
        tmp_path / "data" / "suites",
        tmp_path / config.SUITES_DIR,
        tmp_path / config.PROBLEMS_DIR,
    ):
        assert path.is_dir()
        assert oct(path.stat().st_mode & 0o777) == oct(0o700)


def test_combination_dir_is_problem_then_scenario(tmp_path):
    assert store.combination_dir(tmp_path, "1_A", "hybrid") == (
        tmp_path / "data" / "suites" / "slm" / "problems" / "1_A" / "hybrid"
    )


def test_a_second_command_cannot_take_the_lock(tmp_path):
    with (
        store.exclusive_run(tmp_path),
        pytest.raises(store.AlreadyRunningError, match="already running"),
        store.exclusive_run(tmp_path),
    ):
        pass


def test_the_lock_is_released_when_the_command_fails(tmp_path):
    with pytest.raises(RuntimeError), store.exclusive_run(tmp_path):
        raise RuntimeError("boom")
    with store.exclusive_run(tmp_path):  # free again
        pass


def test_a_generation_is_written_and_read_back(tmp_path):
    record = store.GenerationRecord.model_validate(
        generation(scenario="white_box", attempt=2, seed=44)
    )
    path = store.write_generation(tmp_path, record)
    assert path == store.combination_dir(tmp_path, "1_A", "white_box") / "attempt_2.generation.json"
    assert store.read_generation(tmp_path, "1_A", "white_box", 2) == record


def test_an_execution_is_written_and_read_back(tmp_path):
    record = store.ExecutionRecord.model_validate(execution())
    path = store.write_execution(tmp_path, record)
    assert path.name == "attempt_1.execution.json"
    assert store.read_execution(tmp_path, "1_A", "black_box", 1) == record


def test_a_generation_is_never_overwritten(tmp_path):
    record = store.GenerationRecord.model_validate(generation())
    store.write_generation(tmp_path, record)
    with pytest.raises(FileExistsError):
        store.write_generation(tmp_path, record)


def test_an_execution_is_never_overwritten(tmp_path):
    record = store.ExecutionRecord.model_validate(execution())
    store.write_execution(tmp_path, record)
    with pytest.raises(FileExistsError):
        store.write_execution(tmp_path, record)


def test_an_interrupted_write_leaves_no_file_and_no_temporary(tmp_path, monkeypatch):
    record = store.GenerationRecord.model_validate(generation())

    def fail(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(os, "replace", fail)
    with pytest.raises(KeyboardInterrupt):
        store.write_generation(tmp_path, record)
    folder = store.combination_dir(tmp_path, "1_A", "black_box")
    assert list(folder.iterdir()) == []


def test_reading_a_missing_record_returns_none(tmp_path):
    assert store.read_generation(tmp_path, "1_A", "black_box", 1) is None
    assert store.read_execution(tmp_path, "1_A", "black_box", 1) is None
