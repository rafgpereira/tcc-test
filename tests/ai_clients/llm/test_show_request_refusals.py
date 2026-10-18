"""``show-request``: what is refused (nothing written), usage errors, and that it only reads."""

import json
import socket
import subprocess
from pathlib import Path

import pytest

from ai_clients import __main__ as cli
from ai_clients import requests_view
from ai_clients.llm import config
from ai_clients.prompt import load_template

ONE = ["--problem", "1_A", "--scenario", "black_box"]
ATTEMPT = Path("data/suites/gpt/problems/1_A/black_box/attempt_1.json")


def generate(model="gpt"):
    return cli.main(["generate", "--model", model, *ONE, "--confirm-spend", "10"])


def show(*extra, output="out/request.json", model="gpt"):
    return cli.main(["show-request", "--model", model, *ONE, "--output", output, *extra])


def edit_json(path: Path, **changes):
    data = json.loads(path.read_text())
    data.update(changes)
    path.write_text(json.dumps(data))


@pytest.fixture()
def made(providers, repo, capsys):
    assert generate() == cli.EXIT_OK
    capsys.readouterr()
    return repo


def test_a_template_not_in_the_history_is_refused_and_nothing_is_written(made, capsys):
    other = "c" * 64
    edit_json(made / "data/suites/gpt/run.json", template_sha256=other)
    edit_json(made / ATTEMPT, template_sha256=other)
    assert show() == cli.EXIT_DATA_FAILURE
    out, err = capsys.readouterr()
    current = load_template(config.LLM_TEMPLATE_PATH).sha256
    assert (
        f"the template of this attempt (sha256 {other}) is not the current one ({current})" in err
    )
    assert not (made / "out/request.json").exists()
    assert "<context_data>" not in out + err


def git(repo, *args):
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-C", str(repo), *args],
        check=True,
        capture_output=True,
    )


def test_an_old_template_found_in_git_is_written_with_a_warning(
    made, tmp_path, monkeypatch, capsys
):
    history = tmp_path / "history"
    rel = Path("src/prompt_templates")
    (history / rel).mkdir(parents=True)
    for path in requests_view.TEMPLATE_PATHS.values():
        (history / path).write_bytes((requests_view.REPO_ROOT / path).read_bytes())
    git(history, "init", "-q")
    git(history, "add", ".")
    git(history, "commit", "-q", "-m", "the template of the attempt")
    llm = history / requests_view.TEMPLATE_PATHS["llm"]
    llm.write_text(llm.read_text() + "\nOne more line.\n")
    git(history, "commit", "-q", "-am", "changed later")
    monkeypatch.setattr(requests_view, "REPO_ROOT", history)
    assert show() == cli.EXIT_OK
    out = capsys.readouterr().out
    assert "prompt sha256 matches" in out and "warning: OLD TEMPLATE VERSION from git " in out
    assert (made / "out/request.json").exists()


def test_a_prompt_hash_that_differs_is_refused(made, capsys):
    edit_json(made / ATTEMPT, prompt_sha256="d" * 64)
    assert show() == cli.EXIT_DATA_FAILURE
    assert "it is not written as what was sent" in capsys.readouterr().err
    assert not (made / "out/request.json").exists()


def test_a_dataset_that_differs_from_its_manifest_is_refused(made, capsys):
    (made / "data/dataset/problems/1_A/enunciado.md").write_text("changed\n")
    assert show() == cli.EXIT_DATA_FAILURE
    assert not (made / "out/request.json").exists()


def test_a_damaged_combination_is_refused(made, capsys):
    (made / ATTEMPT.parent / "stray.txt").write_text("?")
    assert show() == cli.EXIT_DATA_FAILURE
    assert "nothing was written" in capsys.readouterr().err
    assert not (made / "out/request.json").exists()


def test_an_unfaithful_prompt_is_written_but_exits_with_1(made, monkeypatch, capsys):
    real = requests_view.check_fidelity

    def unfaithful(*args):
        result = real(*args)
        piece = requests_view.MissingPiece(
            piece="statement", file="enunciado.md", matched_chars=3, expected_chars=9
        )
        return requests_view.FidelityResult(result.checked, [piece], [])

    monkeypatch.setattr(requests_view, "check_fidelity", unfaithful)
    assert show() == cli.EXIT_DATA_FAILURE
    out = capsys.readouterr().out
    assert "dataset: UNFAITHFUL\n" in out
    assert "dataset: UNFAITHFUL — statement (enunciado.md) matched 3 of 9 chars" in out
    assert (made / "out/request.json").exists()


@pytest.mark.parametrize(
    "argv, message",
    [
        (["--attempt", "4"], "1_A black_box has no attempt 4 (attempts: 1)"),
        (["--attempt", "1", "--barred", "1"], "--attempt and --barred cannot be used together"),
    ],
)
def test_usage_errors(made, capsys, argv, message):
    assert show(*argv) == cli.EXIT_USAGE
    assert message in capsys.readouterr().err


def test_more_usage_errors(made, capsys):
    assert show("--barred", "1", model="slm") == cli.EXIT_USAGE
    assert "--barred is only for --model gpt or --model gemini" in capsys.readouterr().err
    argv = ["show-request", "--model", "gpt", "--problem", "9_Z", "--scenario", "black_box"]
    assert cli.main([*argv, "--output", "out/x.json"]) == cli.EXIT_USAGE
    assert "not in data/dataset: 9_Z" in capsys.readouterr().err
    assert cli.main(["show-request", "--model", "gpt", *ONE]) == cli.EXIT_USAGE  # no --output
    assert cli.main(["show-request", "--model", "x", *ONE, "--output", "o"]) == cli.EXIT_USAGE


def test_superseded_attempts_and_leftovers_are_not_read(providers, repo, capsys):
    attempt = repo / "data/suites/gpt/superseded/001/1_A/black_box/attempt_1.json"
    attempt.parent.mkdir(parents=True)
    attempt.write_text("{}")
    assert show() == cli.EXIT_OK  # no current attempt: a preview
    assert "preview, not sent (next: attempt 1)" in capsys.readouterr().out
    assert generate() == cli.EXIT_OK
    (repo / ATTEMPT.parent / ".attempt_2.json.abc.tmp").write_text("half written")
    capsys.readouterr()
    assert show("--force") == cli.EXIT_OK
    assert "attempt 1 (of 1)" in capsys.readouterr().out


def snapshot(folder: Path):
    return sorted(
        (str(p.relative_to(folder)), p.stat().st_size, p.stat().st_mtime_ns)
        for p in folder.rglob("*")
    )


def test_it_only_reads_and_never_opens_a_connection(made, monkeypatch, capsys):
    def no_network(*args, **kwargs):
        raise AssertionError("a connection was attempted")

    monkeypatch.setattr(socket, "socket", no_network)
    monkeypatch.setattr(socket, "create_connection", no_network)
    before = snapshot(made / "data")
    assert show() == cli.EXIT_OK
    assert show("--attempt", "1", output="out/again.json") == cli.EXIT_OK
    assert snapshot(made / "data") == before
