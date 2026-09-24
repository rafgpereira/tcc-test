"""Tests for `python -m mutation generate`, with a fake engine (FR-010, FR-006, resume of R5)."""

import json

import pytest

import mutation.__main__ as cli
from mutation import config, persistence, runtime


@pytest.fixture()
def repo(tmp_path, dataset_builder, dense_problem, monkeypatch):
    """A repository with one dense real problem (189_C), the cwd of the command."""
    dataset_builder(tmp_path, {"189_C": dense_problem})
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture()
def fake_engine(make_engine, monkeypatch):
    """The command builds a real runtime; give it one over the fake engine (and no leftovers)."""
    engine = make_engine()
    made = []

    def make_runtime(workers):
        made.append(workers)
        if workers == 1:
            return runtime.InlineRuntime(engine.as_engine())
        return runtime.ThreadRuntime(engine.as_engine(), workers)

    monkeypatch.setattr(cli, "_make_runtime", make_runtime)
    monkeypatch.setattr("sandbox.isolation.kill_slot_processes", lambda slot: 0)
    engine.runtimes_made = made
    return engine


def test_generate_writes_a_hundred_mutants_and_the_record(repo, fake_engine, capsys):
    assert cli.main(["generate"]) == 0
    folder = repo / config.PROBLEMS_DIR / "189_C"
    assert len(list(folder.glob("Mutant_*.cpp"))) == 100
    assert persistence.read_generation(repo, "189_C").status == "complete"
    out = capsys.readouterr().out
    assert "189_C" in out and "100 mutants" in out and "1 generated" in out


def test_the_limits_and_the_suite_come_from_the_problem_folder(
    repo, fake_engine, dense_problem, monkeypatch
):
    seen = {}
    real_select = cli.orchestrator.select_mutants

    def spy(problem_id, source, suite, limits, **kw):
        seen["limits"], seen["tests"] = limits, len(suite.tests)
        return real_select(problem_id, source, suite, limits, **kw)

    monkeypatch.setattr(cli.orchestrator, "select_mutants", spy)
    cli.main(["generate"])
    metadata = json.loads(dense_problem["metadata.json"])
    assert seen["limits"].time_limit_seconds == metadata["time_limit_seconds"]
    assert seen["limits"].memory_limit_bytes == metadata["memory_limit_bytes"]
    testes = json.loads(dense_problem["testes.json"])
    assert seen["tests"] == sum(len(testes[g]) for g in testes if g.endswith("_tests"))


def test_a_second_run_skips_the_problem_already_generated(repo, fake_engine, capsys):
    cli.main(["generate"])
    compiled_before = sum(fake_engine.compiles.values())
    capsys.readouterr()
    assert cli.main(["generate"]) == 0
    assert sum(fake_engine.compiles.values()) == compiled_before  # nothing was recompiled
    out = capsys.readouterr().out
    assert "already generated, skipped" in out and "1 skipped" in out


def test_a_dataset_that_differs_from_the_manifest_is_refused_before_any_work(
    repo, fake_engine, capsys
):
    (repo / "data" / "dataset" / "problems" / "189_C" / "AC_ref.cpp").write_text("tampered")
    assert cli.main(["generate"]) == cli.EXIT_DATA_FAILURE
    err = capsys.readouterr().err
    assert "AC_ref.cpp" in err and "manifest" in err
    assert sum(fake_engine.compiles.values()) == 0
    assert not (repo / config.MUTANTS_DIR).exists()


def test_a_missing_manifest_is_a_data_failure_not_a_crash(repo, fake_engine):
    (repo / "manifests" / "dataset.manifest.json").unlink()
    assert cli.main(["generate"]) == cli.EXIT_DATA_FAILURE


def test_an_unknown_problem_is_a_usage_error(repo, fake_engine, capsys):
    assert cli.main(["generate", "--problem", "1_A"]) == cli.EXIT_USAGE
    assert "1_A" in capsys.readouterr().err


def test_problem_restricts_the_run(
    tmp_path, dataset_builder, dense_problem, sparse_problem, monkeypatch, fake_engine
):
    dataset_builder(tmp_path, {"189_C": dense_problem, "189_D": sparse_problem})
    monkeypatch.chdir(tmp_path)
    cli.main(["generate", "--problem", "189_C"])
    assert persistence.closed_problems(tmp_path) == ["189_C"]


def test_a_problem_that_first_order_cannot_close_fails_loudly_and_writes_nothing(
    tmp_path, dataset_builder, dense_problem, sparse_problem, monkeypatch, fake_engine, capsys
):
    dataset_builder(tmp_path, {"189_C": dense_problem, "189_D": sparse_problem})
    monkeypatch.chdir(tmp_path)
    assert cli.main(["generate"]) == cli.EXIT_DATA_FAILURE
    out = capsys.readouterr().out
    assert "189_D" in out and "FAILED" in out and "1 failed" in out
    assert persistence.closed_problems(tmp_path) == ["189_C"]  # the healthy one still went through
    assert not (tmp_path / config.PROBLEMS_DIR / "189_D").exists()


def test_leftovers_of_an_interrupted_run_are_discarded_at_the_start(repo, fake_engine):
    leftover = repo / config.BUILDING_DIR / "189_C"
    leftover.mkdir(parents=True)
    (leftover / "Mutant_1.cpp").write_text("half written")
    cli.main(["generate"])
    assert not leftover.exists()
    assert (repo / config.PROBLEMS_DIR / "189_C" / "Mutant_1.cpp").read_text() != "half written"


def test_ctrl_c_exits_130_and_leaves_no_closed_problem(repo, fake_engine, monkeypatch, capsys):
    def interrupt(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(cli.orchestrator, "select_mutants", interrupt)
    assert cli.main(["generate"]) == cli.EXIT_INTERRUPTED
    assert "safe to run the command again" in capsys.readouterr().err
    assert persistence.closed_problems(repo) == []


def test_a_problem_folder_received_from_the_package_is_never_regenerated(repo, fake_engine, capsys):
    """Unzipping `data/mutants.zip` gives `Mutant_<n>.cpp` files and no `generation.json`."""
    received = repo / config.PROBLEMS_DIR / "189_C"
    received.mkdir(parents=True)
    (received / "Mutant_1.cpp").write_text("from the package")
    assert cli.main(["generate"]) == 0
    assert (received / "Mutant_1.cpp").read_text() == "from the package"
    assert sum(fake_engine.compiles.values()) == 0
    assert "already generated, skipped" in capsys.readouterr().out


def test_workers_must_be_a_positive_integer(repo, fake_engine):
    for bad in ("0", "-1", "two"):
        assert cli.main(["generate", "--workers", bad]) == cli.EXIT_USAGE
    assert fake_engine.runtimes_made == []


def test_the_default_number_of_workers_is_half_of_the_cpus(monkeypatch):
    monkeypatch.setattr(cli.os, "cpu_count", lambda: 8)
    assert cli.default_workers() == 4
    monkeypatch.setattr(cli.os, "cpu_count", lambda: 1)
    assert cli.default_workers() == 1
    monkeypatch.setattr(cli.os, "cpu_count", lambda: None)
    assert cli.default_workers() == 1


def test_one_worker_runs_in_this_process_and_more_use_the_pool(repo, fake_engine):
    cli.main(["generate", "--workers", "1"])
    cli.main(["generate", "--workers", "3"])
    assert fake_engine.runtimes_made == [1, 3]


def test_the_default_run_asks_for_the_default_number_of_workers(repo, fake_engine, monkeypatch):
    monkeypatch.setattr(cli.os, "cpu_count", lambda: 10)
    cli.main(["generate"])  # the parser default is computed when the parser is built
    assert fake_engine.runtimes_made == [5]


def test_the_runtime_is_closed_even_when_the_run_is_interrupted(repo, monkeypatch, make_engine):
    closed = []

    class Spy(runtime.InlineRuntime):
        def close(self):
            closed.append(True)

    monkeypatch.setattr(cli, "_make_runtime", lambda workers: Spy(make_engine().as_engine()))
    monkeypatch.setattr("sandbox.isolation.kill_slot_processes", lambda slot: 0)
    monkeypatch.setattr(
        cli.orchestrator, "select_mutants", lambda *a, **k: (_ for _ in ()).throw(KeyboardInterrupt)
    )
    assert cli.main(["generate", "--workers", "1"]) == cli.EXIT_INTERRUPTED
    assert closed == [True]
