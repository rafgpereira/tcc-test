"""``show-request`` before any attempt (a preview) and the protection of the output file."""

import json

import pytest

from ai_clients import __main__ as cli
from ai_clients import config as slm_config
from ai_clients import generation, requests_view, template_history
from ai_clients.llm import config
from ai_clients.llm import providers as llm_providers
from tests.ai_clients.llm.fakes import answer

ONE = ["--problem", "1_A", "--scenario", "hybrid"]


def show(model, *extra, output="out/request.json"):
    return cli.main(["show-request", "--model", model, *ONE, "--output", output, *extra])


@pytest.mark.parametrize("model", config.MODELS)
def test_without_attempts_the_next_request_is_a_preview(providers, repo, capsys, model):
    assert show(model) == cli.EXIT_OK
    out = capsys.readouterr().out
    assert f"{model} 1_A hybrid preview, not sent (next: attempt 1); dataset: faithful" in out
    body = json.loads((repo / "out/request.json").read_text())
    assert body == llm_providers.request_body(model, prompt_in(model, body))


def test_the_slm_preview_needs_no_run_and_no_ollama(repo, monkeypatch, capsys):
    monkeypatch.chdir(repo)
    monkeypatch.delenv(slm_config.ENV_MODEL, raising=False)
    monkeypatch.delenv(slm_config.ENV_BASE_URL, raising=False)
    assert show("slm") == cli.EXIT_OK
    body = json.loads((repo / "out/request.json").read_text())
    spec = slm_config.attempt_spec(1)
    assert body["model"] == slm_config.MODEL
    assert body["options"] == {
        **generation.sampling_options().model_dump(),
        "temperature": spec.temperature,
        "seed": spec.seed,
    }
    assert "preview, not sent (next: attempt 1)" in capsys.readouterr().out


def test_a_pending_combination_with_an_attempt_shows_the_attempt(providers, repo, capsys):
    # One attempt failed by format, then the spend cap stops the command: still pending.
    providers["gpt"].default = answer("gpt", text="not json")
    argv = ["generate", "--model", "gpt", *ONE, "--confirm-spend", "0.000001"]
    assert cli.main(argv) == cli.EXIT_SPEND_CAP
    capsys.readouterr()
    assert show("gpt") == cli.EXIT_OK
    out = capsys.readouterr().out
    assert "attempt 1 (of 1); prompt sha256 matches" in out and "preview" not in out


def test_asking_for_an_attempt_that_does_not_exist_yet_writes_nothing(providers, repo, capsys):
    assert show("gpt", "--attempt", "1") == cli.EXIT_USAGE
    assert "1_A hybrid has no attempt 1 (no attempt yet)" in capsys.readouterr().err
    assert not (repo / "out/request.json").exists()


def test_a_preview_never_looks_in_git(providers, repo, monkeypatch):
    def no_git(*args, **kwargs):
        raise AssertionError("the preview looked in git")

    monkeypatch.setattr(template_history, "_git", no_git)
    assert show("gemini") == cli.EXIT_OK


# ------------------------------------------------------------------- the output file (US3)


def test_an_existing_file_is_not_overwritten_without_force(providers, repo, capsys):
    target = repo / "out/request.json"
    target.parent.mkdir()
    target.write_text("keep me")
    assert show("gpt") == cli.EXIT_USAGE
    assert "out/request.json already exists; use --force to overwrite it" in (
        capsys.readouterr().err
    )
    assert target.read_text() == "keep me"
    assert show("gpt", "--force") == cli.EXIT_OK
    assert json.loads(target.read_text())["model"] == config.MODEL_ID["gpt"]


@pytest.mark.parametrize(
    "output",
    ["data/suites/x.json", "data/suites/gpt/x.json", "data/dataset/x.json", "manifests/x.json"],
)
def test_the_experiment_folders_are_never_written(providers, repo, capsys, output):
    assert show("gpt", output=output) == cli.EXIT_USAGE
    assert "which is never written here" in capsys.readouterr().err
    assert not (repo / output).exists()


def test_a_refusal_does_not_touch_an_existing_file_even_with_force(providers, repo, monkeypatch):
    target = repo / "out/request.json"
    target.parent.mkdir()
    target.write_text("keep me")

    def refuse(*args, **kwargs):
        raise requests_view.ViewRefused("refused")

    monkeypatch.setattr(requests_view, "build_view", refuse)
    assert show("gpt", "--force") == cli.EXIT_DATA_FAILURE
    assert target.read_text() == "keep me"


def prompt_in(model, body):
    if model == "gpt":
        return body["input"]
    if model == "claude":
        return body["messages"][0]["content"]
    return body["contents"][0]["parts"][0]["text"]
