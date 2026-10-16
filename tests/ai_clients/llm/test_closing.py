"""``close --model gpt|gemini``: only a combination that awaits the authors (FR-016)."""

from ai_clients import __main__ as cli
from ai_clients.llm import store
from tests.ai_clients.llm.fakes import answer

CLOSE = ["close", "--model", "gemini", "--problem", "1_A", "--scenario", "hybrid"]


def three_failures(providers):
    providers["gemini"].default = answer("gemini", text="{}")
    cli.main(
        [
            "generate",
            "--model",
            "gemini",
            "--problem",
            "1_A",
            "--scenario",
            "hybrid",
            "--confirm-spend",
            "5",
        ]
    )


def test_close_records_the_decision_and_the_discarded_suite(providers, repo, capsys):
    three_failures(providers)
    assert cli.main([*CLOSE, "--reason", "schema never respected"]) == cli.EXIT_OK
    assert "1_A hybrid: suite recorded (discarded_manual)" in capsys.readouterr().out
    suite = store.read_suite(repo, "gemini", "1_A", "hybrid")
    assert suite.manual_close.reason == "schema never respected" and suite.tests == []


def test_close_refuses_another_state(providers, repo, capsys):
    cli.main(
        [
            "generate",
            "--model",
            "gemini",
            "--problem",
            "1_A",
            "--scenario",
            "hybrid",
            "--confirm-spend",
            "5",
        ]
    )
    assert cli.main([*CLOSE, "--reason", "x"]) == cli.EXIT_USAGE
    assert (
        "1_A hybrid is terminal, not awaiting manual handling; nothing was recorded"
        in capsys.readouterr().err
    )


def test_close_needs_a_reason_and_dry_run_writes_nothing(providers, repo, capsys):
    three_failures(providers)
    assert cli.main([*CLOSE, "--reason", "   "]) == cli.EXIT_USAGE
    assert cli.main([*CLOSE, "--reason", "x", "--dry-run"]) == cli.EXIT_OK
    assert "dry run: nothing was recorded" in capsys.readouterr().out
    assert store.combination_state(repo, "gemini", "1_A", "hybrid").kind == "awaiting_manual"
