"""Interrupting `generate` at any point loses nothing and the run can simply be started again.

The guarantees (Constitution, Principle VII; research R5): a problem exists in
`data/mutants/problems/` only if it is COMPLETE (one atomic rename closes it); whatever was in
progress is redone from scratch on the next run and never touches a closed problem; and the result
of an interrupted-then-resumed run is byte for byte the result of a run that was never interrupted.
"""

import hashlib
import shutil
from pathlib import Path

import pytest

import mutation.__main__ as cli
from dataset.persistence import store
from mutation import config, persistence, runtime

IDS = ["189_C", "189_D", "189_E", "189_F"]


@pytest.fixture()
def repo(tmp_path, dataset_builder, dense_problem, monkeypatch):
    def renamed(pid):
        return {
            name: text.replace('"problem_id": "189_C"', f'"problem_id": "{pid}"')
            for name, text in dense_problem.items()
        }

    dataset_builder(tmp_path, {pid: renamed(pid) for pid in IDS})
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sandbox.isolation.kill_slot_processes", lambda slot: 0)
    return tmp_path


def tree(root: Path) -> dict[str, str]:
    """SHA-256 of every file under `data/mutants/problems`, by relative path."""
    base = root / config.PROBLEMS_DIR
    return {
        p.relative_to(base).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(base.rglob("*"))
        if p.is_file()
    }


def use(monkeypatch, make_engine, workers_runtime="inline", **kw):
    engine = make_engine(**kw)

    def make(workers):
        if workers_runtime == "threads":
            return runtime.ThreadRuntime(engine.as_engine(), workers)
        return runtime.InlineRuntime(engine.as_engine())

    monkeypatch.setattr(cli, "_make_runtime", make)
    return engine


@pytest.fixture()
def reference(repo, monkeypatch, make_engine):
    """The tree of a run that was never interrupted (computed once, then removed)."""
    use(monkeypatch, make_engine)
    assert cli.main(["generate", "--workers", "1"]) == 0
    result = tree(repo)
    shutil.rmtree(repo / config.MUTANTS_DIR)
    return result


def test_interrupted_between_problems_then_resumed_equals_a_clean_run(
    repo, monkeypatch, make_engine, reference
):
    real = runtime.orchestrator.select_mutants
    calls = []

    def interrupting(problem_id, *a, **k):
        calls.append(problem_id)
        if len(calls) == 3:  # two problems are closed, the third is interrupted
            raise KeyboardInterrupt
        return real(problem_id, *a, **k)

    use(monkeypatch, make_engine)
    monkeypatch.setattr(runtime.orchestrator, "select_mutants", interrupting)
    assert cli.main(["generate", "--workers", "1"]) == cli.EXIT_INTERRUPTED
    assert persistence.closed_problems(repo) == IDS[:2]
    closed_before = tree(repo)

    monkeypatch.setattr(runtime.orchestrator, "select_mutants", real)
    assert cli.main(["generate", "--workers", "1"]) == 0
    after = tree(repo)
    assert {k: v for k, v in after.items() if k in closed_before} == closed_before  # untouched
    assert after == reference


def test_interrupted_in_the_middle_of_writing_a_problem_leaves_nothing_half_closed(
    repo, monkeypatch, make_engine, reference
):
    real = store.write_problem_text
    calls = {"n": 0}

    def flaky(folder, name, text):
        calls["n"] += 1
        if calls["n"] == 250:  # problem 3, in the middle of its Mutant_<n>.cpp files
            raise KeyboardInterrupt
        real(folder, name, text)

    use(monkeypatch, make_engine)
    monkeypatch.setattr(store, "write_problem_text", flaky)
    assert cli.main(["generate", "--workers", "1"]) == cli.EXIT_INTERRUPTED
    assert persistence.closed_problems(repo) == IDS[:2]
    assert not (repo / config.PROBLEMS_DIR / IDS[2]).exists()
    assert persistence.pending_building(repo) == [IDS[2]]  # partial, and known to be partial

    monkeypatch.setattr(store, "write_problem_text", real)
    assert cli.main(["generate", "--workers", "1"]) == 0
    assert persistence.pending_building(repo) == []
    assert tree(repo) == reference


def test_a_hard_kill_leaves_leftovers_that_the_next_run_discards(
    repo, monkeypatch, make_engine, reference
):
    """kill -9 / power cut: a half-built folder and a temporary file of an atomic write."""
    use(monkeypatch, make_engine)
    assert cli.main(["generate", "--workers", "1", "--problem", IDS[0]]) == 0
    building = repo / config.BUILDING_DIR / IDS[1]
    building.mkdir(parents=True)
    (building / "Mutant_1.cpp").write_text("half written")
    (building / ".Mutant_2.cpp.k3j2.tmp").write_text("temp of an atomic write")
    closed_before = tree(repo)

    assert cli.main(["generate", "--workers", "1"]) == 0
    assert not building.exists() and persistence.pending_building(repo) == []
    assert {k: v for k, v in tree(repo).items() if k in closed_before} == closed_before
    assert tree(repo) == reference


def test_resuming_never_rewrites_a_closed_problem(repo, monkeypatch, make_engine):
    use(monkeypatch, make_engine)
    cli.main(["generate", "--workers", "1", "--problem", IDS[0]])
    files = sorted((repo / config.PROBLEMS_DIR / IDS[0]).iterdir())
    stamps = {f.name: f.stat().st_mtime_ns for f in files}
    cli.main(["generate", "--workers", "1"])
    assert {f.name: f.stat().st_mtime_ns for f in files} == stamps  # not even touched


@pytest.mark.parametrize("workers", [2, 4])
def test_interrupted_with_several_problems_in_flight_then_resumed_equals_a_clean_run(
    repo, monkeypatch, make_engine, reference, workers
):
    real = runtime.orchestrator.select_mutants
    finished = []

    def interrupting(problem_id, *a, **k):
        if problem_id == IDS[2]:
            raise KeyboardInterrupt  # one worker is interrupted while others may be running
        selection = real(problem_id, *a, **k)
        finished.append(problem_id)
        return selection

    use(monkeypatch, make_engine, workers_runtime="threads")
    monkeypatch.setattr(runtime.orchestrator, "select_mutants", interrupting)
    assert cli.main(["generate", "--workers", str(workers)]) == cli.EXIT_INTERRUPTED
    assert IDS[2] not in persistence.closed_problems(repo)
    partial = tree(repo)

    monkeypatch.setattr(runtime.orchestrator, "select_mutants", real)
    assert cli.main(["generate", "--workers", str(workers)]) == 0
    assert {k: v for k, v in tree(repo).items() if k in partial} == partial
    assert tree(repo) == reference


def test_an_interruption_is_repeatable_any_number_of_times(
    repo, monkeypatch, make_engine, reference
):
    real = runtime.orchestrator.select_mutants
    use(monkeypatch, make_engine)
    for _ in range(3):  # each attempt is interrupted right after it closes one problem
        seen = []

        def once(problem_id, *a, _seen=seen, **k):
            if _seen:
                raise KeyboardInterrupt
            _seen.append(problem_id)
            return real(problem_id, *a, **k)

        monkeypatch.setattr(runtime.orchestrator, "select_mutants", once)
        assert cli.main(["generate", "--workers", "1"]) == cli.EXIT_INTERRUPTED
    monkeypatch.setattr(runtime.orchestrator, "select_mutants", real)
    assert len(persistence.closed_problems(repo)) == 3
    assert cli.main(["generate", "--workers", "1"]) == 0
    assert tree(repo) == reference


# ------------------------------------------------------------- a damaged closed problem


def test_a_closed_problem_that_lost_a_file_is_reported_and_never_silently_skipped(
    repo, monkeypatch, make_engine, capsys
):
    use(monkeypatch, make_engine)
    cli.main(["generate", "--workers", "1", "--problem", IDS[0]])
    (repo / config.PROBLEMS_DIR / IDS[0] / "Mutant_7.cpp").unlink()
    capsys.readouterr()
    assert cli.main(["generate", "--workers", "1", "--problem", IDS[0]]) == cli.EXIT_DATA_FAILURE
    out = capsys.readouterr().out
    assert "DAMAGED" in out and "Mutant_7.cpp" in out and IDS[0] in out
    assert "1 damaged" in out


def test_a_closed_problem_with_a_changed_file_is_reported(repo, monkeypatch, make_engine, capsys):
    use(monkeypatch, make_engine)
    cli.main(["generate", "--workers", "1", "--problem", IDS[0]])
    (repo / config.PROBLEMS_DIR / IDS[0] / "Mutant_3.cpp").write_text("tampered")
    assert cli.main(["generate", "--workers", "1", "--problem", IDS[0]]) == cli.EXIT_DATA_FAILURE
    assert "changed: Mutant_3.cpp" in capsys.readouterr().out


def test_deleting_a_damaged_problem_lets_the_next_run_regenerate_only_it(
    repo, monkeypatch, make_engine, reference
):
    use(monkeypatch, make_engine)
    cli.main(["generate", "--workers", "1"])
    (repo / config.PROBLEMS_DIR / IDS[1] / "Mutant_7.cpp").unlink()
    shutil.rmtree(repo / config.PROBLEMS_DIR / IDS[1])
    assert cli.main(["generate", "--workers", "1"]) == 0
    assert tree(repo) == reference


def test_check_closed_accepts_a_healthy_problem_and_a_package_folder(
    repo, monkeypatch, make_engine
):
    use(monkeypatch, make_engine)
    cli.main(["generate", "--workers", "1", "--problem", IDS[0]])
    assert persistence.check_closed(repo, IDS[0]) == []
    received = repo / config.PROBLEMS_DIR / "189_Z"
    received.mkdir()
    (received / "Mutant_1.cpp").write_text("from the package")  # no generation.json: not ours
    assert persistence.check_closed(repo, "189_Z") == []


# ------------------------------------------------------------- two runs at once


def test_a_second_generate_over_the_same_data_refuses_to_start(
    repo, monkeypatch, make_engine, capsys
):
    use(monkeypatch, make_engine)
    with persistence.exclusive_run(repo):  # the first run is alive
        assert cli.main(["generate", "--workers", "1"]) == cli.EXIT_DATA_FAILURE
    assert "already running" in capsys.readouterr().err
    assert persistence.closed_problems(repo) == []  # the refused run touched nothing


def test_the_lock_is_released_when_the_run_ends_however_it_ends(repo, monkeypatch, make_engine):
    use(monkeypatch, make_engine)
    monkeypatch.setattr(
        runtime.orchestrator,
        "select_mutants",
        lambda *a, **k: (_ for _ in ()).throw(KeyboardInterrupt),
    )
    assert cli.main(["generate", "--workers", "1"]) == cli.EXIT_INTERRUPTED
    with persistence.exclusive_run(repo):  # would raise if the interrupted run had kept the lock
        pass


def test_a_lock_left_by_a_killed_process_is_not_stale(repo):
    """The lock is an flock, not a file that must be deleted: a leftover `.lock` file is harmless."""
    (repo / config.MUTANTS_DIR).mkdir(parents=True, exist_ok=True)
    (repo / config.MUTANTS_DIR / config.LOCK_FILE).write_text("left by a kill -9")
    with persistence.exclusive_run(repo):
        pass
