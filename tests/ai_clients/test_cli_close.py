"""``python -m ai_clients close``: options, refusals and exit codes."""

import pytest

from ai_clients import __main__ as cli
from ai_clients import config, store
from tests.ai_clients.fakes import record_generation, start_run


@pytest.fixture()
def awaiting(monkeypatch, repo):
    """``1_A hybrid`` awaits manual handling (23 unparseable answers)."""
    monkeypatch.chdir(repo)
    start_run(repo)
    for n in range(1, config.MAX_ATTEMPTS + 1):
        record_generation(repo, "1_A", "hybrid", n, parsed=False)
    return repo


def close(*extra, reason="never parsed"):
    return cli.main(
        ["close", "--problem", "1_A", "--scenario", "hybrid", "--reason", reason, *extra]
    )


def test_close_records_the_suite_and_exits_0(awaiting, capsys):
    assert close() == cli.EXIT_OK
    assert capsys.readouterr().out == "1_A hybrid: suite recorded (discarded_manual)\n"
    suite = store.read_suite(awaiting, "1_A", "hybrid")
    assert suite.status == "discarded_manual" and suite.manual_close.reason == "never parsed"


def test_a_second_close_is_a_usage_error(awaiting, capsys):
    assert close() == cli.EXIT_OK
    assert close() == cli.EXIT_USAGE
    assert "1_A hybrid is terminal, not awaiting manual handling" in capsys.readouterr().err


def test_dry_run_shows_the_decision_and_writes_nothing(awaiting, capsys):
    assert close("--dry-run") == cli.EXIT_OK
    out = capsys.readouterr().out
    assert '"reason": "never parsed"' in out and "dry run: nothing was recorded" in out
    folder = store.combination_dir(awaiting, "1_A", "hybrid")
    assert not (folder / config.MANUAL_CLOSE_FILE).exists()
    assert not (folder / config.SUITE_FILE).exists()


def test_a_blank_reason_is_a_usage_error(awaiting, capsys):
    assert close(reason="   ") == cli.EXIT_USAGE
    assert "--reason must not be empty" in capsys.readouterr().err


def test_a_combination_in_another_state_is_a_usage_error(awaiting, capsys):
    code = cli.main(["close", "--problem", "2_B", "--scenario", "hybrid", "--reason", "x"])
    assert code == cli.EXIT_USAGE
    assert "2_B hybrid is pending_generation, not awaiting manual handling" in (
        capsys.readouterr().err
    )


def test_an_unknown_problem_is_a_usage_error(awaiting, capsys):
    code = cli.main(["close", "--problem", "9_Z", "--scenario", "hybrid", "--reason", "x"])
    assert code == cli.EXIT_USAGE and "not in data/dataset: 9_Z" in capsys.readouterr().err


@pytest.mark.parametrize("missing", ["--problem", "--scenario", "--reason"])
def test_every_option_is_required(awaiting, missing):
    argv = ["close", "--problem", "1_A", "--scenario", "hybrid", "--reason", "x"]
    position = argv.index(missing)
    del argv[position : position + 2]
    assert cli.main(argv) == cli.EXIT_USAGE


def test_without_a_run_it_asks_for_generate_first(repo, monkeypatch, capsys):
    monkeypatch.chdir(repo)
    assert close() == cli.EXIT_USAGE
    assert "run generate first" in capsys.readouterr().err
