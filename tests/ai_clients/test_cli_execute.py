"""``python -m ai_clients execute``: options, the summary, ``next:`` and exit codes."""

import pytest

from ai_clients import __main__ as cli
from ai_clients import config, store
from sandbox.types import InfraError
from tests.ai_clients.fakes import FakePythonRunner, echo_runner, record_generation, start_run


@pytest.fixture()
def fake(monkeypatch, repo):
    """``execute`` inside ``repo`` with a fake Python runner and no real slot cleanup."""
    monkeypatch.chdir(repo)
    runner = echo_runner()
    monkeypatch.setattr(cli, "make_runner", lambda: runner)
    cleaned = []
    monkeypatch.setattr(cli, "cleanup_slot", cleaned.append)
    runner.cleaned = cleaned
    return runner


def test_without_a_run_it_asks_for_generate_first(fake, capsys):
    assert cli.main(["execute"]) == cli.EXIT_USAGE
    assert "run generate first" in capsys.readouterr().err
    assert fake.calls == []


def test_it_executes_what_is_pending_and_prints_the_summary(fake, repo, capsys):
    start_run(repo)
    record_generation(repo, "1_A", "black_box")
    record_generation(repo, "2_B", "hybrid")
    assert cli.main(["execute"]) == cli.EXIT_OK
    out = capsys.readouterr().out.splitlines()
    assert out[:2] == [
        "1_A black_box attempt 1: accepted (2 kept, 0 discarded)",
        "2_B hybrid attempt 1: accepted (2 kept, 0 discarded)",
    ]
    assert out[2] == (
        "done: 2 executed, 2 accepted, 0 failed (0 need a new generation); suites: "
        "0 accepted_fallback, 0 accepted_low_confidence; 0 awaiting manual handling"
    )
    # 4 combinations were never generated
    assert out[3] == "next: docker compose run --rm app python -m ai_clients generate --resume"
    assert fake.cleaned == [0, 0]  # the slot is cleaned at the start and at the end


def test_no_next_line_when_nothing_needs_a_generation(fake, repo, capsys):
    start_run(repo)
    record_generation(repo, "1_A", "black_box")
    assert cli.main(["execute", "--problem", "1_A", "--scenario", "black_box"]) == cli.EXIT_OK
    assert not any(line.startswith("next:") for line in capsys.readouterr().out.splitlines())


def test_the_next_line_keeps_the_selection(fake, repo, capsys):
    start_run(repo)
    record_generation(repo, "2_B", "black_box")
    record_generation(repo, "1_A", "black_box")
    argv = ["execute", "--problem", "2_B", "--problem", "1_A", "--problem", "2_B"]
    assert cli.main(argv + ["--scenario", "hybrid", "--scenario", "black_box"]) == cli.EXIT_OK
    assert capsys.readouterr().out.splitlines()[-1] == (
        "next: docker compose run --rm app python -m ai_clients generate --resume "
        "--problem 1_A --problem 2_B --scenario black_box --scenario hybrid"
    )


def test_dry_run_lists_the_attempts_and_writes_nothing(fake, repo, capsys):
    start_run(repo)
    record_generation(repo, "1_A", "white_box", inputs=["1\n", "2\n", "3\n"])
    before = sorted(p.name for p in store.combination_dir(repo, "1_A", "white_box").iterdir())
    assert cli.main(["execute", "--dry-run"]) == cli.EXIT_OK
    out = capsys.readouterr().out.splitlines()
    assert out == [
        "1_A white_box attempt 1: 3 inputs, 2 public tests, limits 10 s and 1024 MiB",
        "dry run: 1 attempts to execute",
    ]
    assert fake.calls == [] and fake.cleaned == []
    after = sorted(p.name for p in store.combination_dir(repo, "1_A", "white_box").iterdir())
    assert before == after
    assert not (repo / "data" / "suites" / "slm" / ".lock").exists()


def test_limit_problem_and_scenario_select_the_attempts(fake, repo, capsys):
    start_run(repo)
    for pid in ("1_A", "2_B"):
        for scenario in ("black_box", "hybrid"):
            record_generation(repo, pid, scenario)
    assert cli.main(["execute", "--scenario", "hybrid", "--limit", "1"]) == cli.EXIT_OK
    out = capsys.readouterr().out.splitlines()
    assert out[0] == "1_A hybrid attempt 1: accepted (2 kept, 0 discarded)"
    assert out[1].startswith("done: 1 executed")
    assert cli.main(["execute", "--problem", "2_B"]) == cli.EXIT_OK
    out = capsys.readouterr().out.splitlines()
    assert [line.split(":")[0] for line in out[:2]] == [
        "2_B black_box attempt 1",
        "2_B hybrid attempt 1",
    ]


def test_an_infrastructure_failure_exits_with_3(fake, repo, monkeypatch, capsys):
    start_run(repo)
    record_generation(repo)
    broken = FakePythonRunner(default=lambda code, stdin: InfraError("cannot prepare the workdir"))
    monkeypatch.setattr(cli, "make_runner", lambda: broken)
    assert cli.main(["execute"]) == cli.EXIT_INFRA
    assert "cannot prepare the workdir" in capsys.readouterr().err
    assert store.combination_state(repo, "1_A", "black_box").kind == "pending_execution"
    assert fake.cleaned == [0, 0]


def test_a_changed_dataset_stops_before_anything_runs(fake, repo):
    start_run(repo)
    record_generation(repo)
    (repo / "data" / "dataset" / "problems" / "1_A" / "testes.json").write_text("{}\n")
    assert cli.main(["execute"]) == cli.EXIT_DATA_FAILURE
    assert fake.calls == []


def test_execute_has_no_resume_option(fake, repo):
    start_run(repo)
    assert cli.main(["execute", "--resume"]) == cli.EXIT_USAGE


def test_execute_also_reports_combinations_awaiting_manual_handling(fake, repo, capsys):
    start_run(repo)
    record_generation(repo, "1_A", "black_box")
    for n in range(1, config.MAX_ATTEMPTS + 1):
        record_generation(repo, "2_B", "hybrid", n, parsed=False)
    assert cli.main(["execute", "--problem", "1_A", "--problem", "2_B"]) == cli.EXIT_MANUAL
    captured = capsys.readouterr()
    assert "1_A black_box attempt 1: accepted (2 kept, 0 discarded)" in captured.out
    assert "manual: 2_B hybrid:" in captured.err
