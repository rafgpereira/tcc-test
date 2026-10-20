"""``show-request --model gpt|gemini``: the body of a recorded attempt, written, never printed."""

import json
import shutil

import pytest

from ai_clients import __main__ as cli
from ai_clients.llm import config
from tests.ai_clients.conftest import problem
from tests.ai_clients.llm.fakes import answer

ONE = ["--problem", "1_A", "--scenario", "black_box"]
STATEMENT = "# 1_A\n\nRead an integer n (1 ≤ n ≤ 105) and print it.\n"


@pytest.fixture()
def problem_files():
    files = problem("1_A")
    files["enunciado.md"] = STATEMENT
    return {"1_A": files, "2_B": problem("2_B")}


def generate(model, *extra):
    argv = ["generate", "--model", model, *ONE, "--confirm-spend", "10", *extra]
    return cli.main(argv)


def show(model, output="out/request.json", *extra):
    return cli.main(["show-request", "--model", model, *ONE, "--output", output, *extra])


def prompt_in(model, body):
    if model == "gpt":
        return body["input"]
    if model == "claude":
        return body["messages"][0]["content"]
    return body["contents"][0]["parts"][0]["text"]


@pytest.mark.parametrize("model", config.MODELS)
def test_the_last_attempt_is_written_as_the_body_that_was_sent(providers, repo, capsys, model):
    bad = answer(model, text="not json")
    providers[model].table = {("1_A", "black_box", 1): bad, ("1_A", "black_box", 2): bad}
    assert generate(model) == cli.EXIT_OK
    sent = [body for _, _, body in providers[model].requests]
    capsys.readouterr()

    assert show(model) == cli.EXIT_OK
    out, err = capsys.readouterr()
    written = (repo / "out/request.json").read_text(encoding="utf-8")
    # The same JSON as sent (the recorded parameters keep their keys sorted: only the order of
    # the keys may differ from the bytes sent).
    assert json.loads(written) == sent[2]
    assert written == json.dumps(json.loads(written), indent=2, ensure_ascii=False) + "\n"
    assert "≤" in written and "\\u2264" not in written
    assert out.splitlines()[0] == (
        f"written: out/request.json — {model} 1_A black_box attempt 3 (of 3); prompt sha256 "
        "matches; dataset: faithful"
    )
    assert 'warning: lost exponent in enunciado.md: "' in out
    assert prompt_in(model, sent[2]) not in out + err  # the request is never printed
    assert "Read an integer n" not in out + err

    assert show(model, "out/2.json", "--attempt", "2") == cli.EXIT_OK
    assert json.loads((repo / "out/2.json").read_text(encoding="utf-8")) == sent[1]
    assert "attempt 2 (of 3)" in capsys.readouterr().out


@pytest.mark.parametrize("model", config.MODELS)
def test_the_answer_and_the_key_are_never_written(providers, repo, capsys, model):
    assert generate(model) == cli.EXIT_OK
    capsys.readouterr()
    assert show(model) == cli.EXIT_OK
    written = (repo / "out/request.json").read_text(encoding="utf-8")
    out, err = capsys.readouterr()
    for text in (written, out, err):
        assert f"secret-{model}-key" not in text
        for word in ("raw_body", "model_returned", "reasoning_tokens", "cost_usd", "smallest case"):
            assert word not in text  # "smallest case": the analysis the fake model answered


def test_the_recorded_parameters_are_used_even_if_the_code_changed(providers, repo, capsys):
    assert generate("gpt") == cli.EXIT_OK
    for path in (
        repo / "data/suites/gpt/run.json",
        repo / "data/suites/gpt/problems/1_A/black_box/attempt_1.json",
    ):
        data = json.loads(path.read_text())
        data["request_parameters"]["max_output_tokens"] = 1000
        path.write_text(json.dumps(data))
    capsys.readouterr()
    assert show("gpt") == cli.EXIT_OK
    body = json.loads((repo / "out/request.json").read_text())
    assert body["max_output_tokens"] == 1000
    assert "warning: parameters changed since this attempt: max_output_tokens" in (
        capsys.readouterr().out
    )


@pytest.mark.parametrize("model", config.MODELS)
def test_a_barred_response_can_be_written(providers, repo, capsys, model):
    providers[model].default = answer(model, reasoning=0)
    assert generate(model) == cli.EXIT_OK  # 3 barred answers, then accepted_barred
    capsys.readouterr()
    assert show(model, "out/b.json", "--barred", "1") == cli.EXIT_OK
    assert "barred response 1 (no reasoning tokens); prompt sha256 matches" in (
        capsys.readouterr().out
    )
    assert json.loads((repo / "out/b.json").read_text()) == providers[model].requests[0][2]
    assert show(model, "out/c.json", "--barred", "4") == cli.EXIT_USAGE
    assert "has no barred response 4 (barred responses: 1–3)" in capsys.readouterr().err
    assert show(model, "out/d.json", "--barred", "1", "--attempt", "1") == cli.EXIT_USAGE


def test_an_archived_tree_is_read_with_suites_dir(providers, repo, capsys):
    assert generate("gemini") == cli.EXIT_OK
    shutil.move(repo / "data/suites/gemini", repo / "data/suites/gemini-piloto9")
    capsys.readouterr()
    assert show("gemini") == cli.EXIT_OK  # nothing in data/suites/gemini: a preview
    assert "preview, not sent (next: attempt 1)" in capsys.readouterr().out
    argv = ["out/archived.json", "--suites-dir", "data/suites/gemini-piloto9"]
    assert show("gemini", *argv) == cli.EXIT_OK
    assert "attempt 1 (of 1); prompt sha256 matches" in capsys.readouterr().out
    assert (
        json.loads((repo / "out/archived.json").read_text()) == providers["gemini"].requests[0][2]
    )
