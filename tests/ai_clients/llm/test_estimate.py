"""The dry run and the refusal without confirmation: nothing is called nor recorded (SC-004)."""

import pytest

from ai_clients import __main__ as cli
from ai_clients.llm import config
from tests.ai_clients.llm.fakes import FakeProvider


@pytest.fixture()
def silent(providers):
    """Providers that fail the test on any call."""
    for model in config.MODELS:
        providers[model] = FakeProvider(model)
    return providers


def tree(repo):
    base = repo / "data" / "suites"
    return sorted(p.relative_to(repo).as_posix() for p in base.rglob("*")) if base.exists() else []


@pytest.mark.parametrize("model", config.MODELS)
def test_the_dry_run_calls_nothing_writes_nothing_and_needs_no_key(
    silent, repo, monkeypatch, capsys, model
):
    monkeypatch.delenv(config.ENV_API_KEY[model])
    assert cli.main(["generate", "--model", model, "--dry-run"]) == cli.EXIT_OK
    out = capsys.readouterr().out
    assert tree(repo) == [] and silent["created"] == []
    lines = out.splitlines()
    assert lines[-1] == "dry run: nothing was called nor recorded"
    total = next(line for line in lines if line.startswith(f"{model} total:"))
    assert "6 combinations, 6 calls (up to 18)" in total
    assert "CHARS_PER_TOKEN=3 conservative, before the pilot" in total
    assert f"output {config.MAX_OUTPUT_TOKENS} max" in total and "US$ " in total
    for scenario in config.SCENARIOS:
        assert any(line.startswith(f"{model} {scenario}: 2 combinations") for line in lines)
        assert any(line.startswith(f"largest prompt: {scenario} ") for line in lines)


def test_the_scope_options_change_the_estimate(silent, capsys):
    argv = ["generate", "--model", "gpt", "--dry-run", "--problem", "1_A", "--scenario", "hybrid"]
    assert cli.main(argv) == cli.EXIT_OK
    out = capsys.readouterr().out
    assert "gpt total: 1 combinations, 1 calls (up to 3)" in out
    assert cli.main(["generate", "--model", "gpt", "--dry-run", "--limit", "4"]) == cli.EXIT_OK
    assert "gpt total: 4 combinations" in capsys.readouterr().out


def test_without_confirmation_the_estimate_is_shown_and_nothing_is_called(silent, repo, capsys):
    assert cli.main(["generate", "--model", "gemini"]) == cli.EXIT_USAGE
    captured = capsys.readouterr()
    assert "gemini total: 6 combinations" in captured.out
    assert "this would make up to 18 paid calls (estimated US$ " in captured.err
    assert "to confirm, run again with --confirm-spend <max US$ for this run>" in captured.err
    assert tree(repo) == [] and silent["created"] == []


def test_done_combinations_leave_the_estimate(providers, capsys):
    cli.main(["generate", "--model", "gpt", "--problem", "1_A", "--confirm-spend", "5"])
    capsys.readouterr()
    assert cli.main(["generate", "--model", "gpt", "--dry-run"]) == cli.EXIT_OK
    assert "gpt total: 3 combinations" in capsys.readouterr().out
