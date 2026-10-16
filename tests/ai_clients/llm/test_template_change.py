"""``change-template --model gpt|gemini --template llm`` (FR-009)."""

import pytest

from ai_clients import __main__ as cli
from ai_clients.llm import config, store
from tests.ai_clients.llm.fakes import answer


@pytest.fixture()
def changed(providers, repo, monkeypatch, tmp_path):
    """A finished selection made with the current text-base, then the text-base edited."""
    providers["gpt"].table[("1_A", "black_box", 1)] = answer("gpt", text="bad")
    cli.main(["generate", "--model", "gpt", "--problem", "1_A", "--confirm-spend", "1"])
    path = tmp_path / "llm_prompt.txt"
    path.write_text(config.LLM_TEMPLATE_PATH.read_text() + "\nOne more rule.\n")
    monkeypatch.setattr(config, "LLM_TEMPLATE_PATH", path)
    return path


CHANGE = ["change-template", "--model", "gpt", "--template", "llm", "--reason", "clearer rule"]


def test_the_change_is_recorded_and_the_old_attempts_move_aside(changed, providers, repo, capsys):
    capsys.readouterr()
    assert cli.main(CHANGE) == cli.EXIT_OK
    out = capsys.readouterr().out
    assert "1_A black_box: 3 file(s) superseded" in out
    assert "3 combination(s) to make again, 7 file(s) moved to data/suites/gpt/superseded/" in out
    change = store.template_changes(repo, "gpt")[0]
    assert change.number == 1 and change.reason == "clearer rule"
    assert change.superseded[0].files == ["suite.json", "attempt_2.json", "attempt_1.json"]
    moved = store.superseded_dir(repo, "gpt", 1, "1_A", "black_box")
    assert sorted(p.name for p in moved.iterdir()) == [
        "attempt_1.json",
        "attempt_2.json",
        "suite.json",
    ]
    assert store.combination_state(repo, "gpt", "1_A", "black_box").kind == "pending"
    assert cli.main(["generate", "--model", "gpt", "--resume", "--confirm-spend", "1"]) == 0
    record = store.read_attempt(repo, "gpt", "1_A", "black_box", 1)
    assert record.template_sha256 == change.to_sha256


def test_the_same_text_base_is_refused(providers, repo, capsys):
    cli.main(["generate", "--model", "gpt", "--problem", "1_A", "--confirm-spend", "1"])
    assert cli.main(CHANGE) == cli.EXIT_USAGE
    assert "is the current template of the run" in capsys.readouterr().err


def test_dry_run_moves_nothing(changed, repo, capsys):
    assert cli.main([*CHANGE, "--dry-run"]) == cli.EXIT_OK
    assert "dry run: change 1 would make 3 combination(s) again" in capsys.readouterr().out
    assert store.template_changes(repo, "gpt") == []


def test_an_interrupted_change_is_finished_by_running_it_again(changed, repo, monkeypatch, capsys):
    from ai_clients.llm import template_change

    real = template_change.os.replace
    calls = {"n": 0}

    def flaky(source, target):
        calls["n"] += 1
        if calls["n"] == 3:  # 1: the atomic write of the record, 2: the first file moved
            raise KeyboardInterrupt
        real(source, target)

    monkeypatch.setattr(template_change.os, "replace", flaky)
    assert cli.main(CHANGE) == cli.EXIT_INTERRUPTED
    monkeypatch.setattr(template_change.os, "replace", real)
    capsys.readouterr()
    assert cli.main(CHANGE) == cli.EXIT_OK
    assert "finished the interrupted change 1: 6 file(s) moved" in capsys.readouterr().out
