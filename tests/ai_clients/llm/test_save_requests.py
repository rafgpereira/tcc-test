"""``generate --dry-run --save-requests DIR``: the body of every pending request, flat, checked."""

import json
import socket
from pathlib import Path

import pytest

from ai_clients import __main__ as cli
from ai_clients import config as slm_config
from ai_clients import problem, requests_view
from ai_clients.llm import config
from ai_clients.llm import providers as llm_providers
from ai_clients.prompt import build_prompt, load_template, wire_bytes

MODELS = ("slm", *config.MODELS)


def dry_run(model, *extra, dest="out"):
    return cli.main(["generate", "--model", model, "--dry-run", "--save-requests", dest, *extra])


@pytest.fixture()
def here(providers, repo, monkeypatch):
    """Inside ``repo``, with the API keys set but no Ollama address: none of them is needed."""
    monkeypatch.delenv(slm_config.ENV_BASE_URL, raising=False)
    monkeypatch.delenv(slm_config.ENV_MODEL, raising=False)
    return repo


def expected_body(root, model, problem_id, scenario):
    loaded = problem.load_problem(root, problem_id)
    if model == "slm":
        text = build_prompt(load_template(), loaded, scenario)
        return cli._slm_request(None, 1, text)
    text = build_prompt(load_template(config.LLM_TEMPLATE_PATH), loaded, scenario)
    return llm_providers.request_body(model, text)


@pytest.mark.parametrize("model", MODELS)
def test_one_body_per_pending_combination_flat_with_a_summary(here, capsys, model):
    assert dry_run(model) == cli.EXIT_OK
    out = capsys.readouterr().out
    folder = here / "out" / model
    names = sorted(p.name for p in folder.iterdir())
    assert all(p.is_file() for p in folder.iterdir())  # flat: no folder per problem
    assert names == sorted(
        [f"{pid}.{s}.request.json" for pid in ("1_A", "2_B") for s in slm_config.SCENARIOS]
        + ["summary.json"]
    )
    for pid in ("1_A", "2_B"):
        for scenario in slm_config.SCENARIOS:
            text = (folder / f"{pid}.{scenario}.request.json").read_text(encoding="utf-8")
            body = expected_body(here, model, pid, scenario)
            assert json.loads(text) == json.loads(wire_bytes(body))
            assert text == requests_view.body_text(body)
    summary = requests_view.RequestsSummary.model_validate_json(
        (folder / "summary.json").read_text()
    )
    assert (summary.model, summary.combinations, summary.faithful) == (model, 6, 6)
    assert summary.unfaithful == [] and summary.damaged == []
    assert summary.requests[0].request_file == "1_A.black_box.request.json"
    if model == "slm":
        assert summary.requests[0].seed == 42 and summary.requests[0].temperature == 0.7
    assert out.index("dry run:") < out.index("requests: 6 saved in out/" + model + "; faithful 6/6")
    assert "exponent warnings 0 problems (0 combinations)" in out


@pytest.mark.parametrize("model", config.MODELS)
def test_nothing_is_called(here, model, providers):
    assert dry_run(model) == cli.EXIT_OK
    assert providers[model].requests == [] and providers["created"] == []


def test_the_selection_options_are_respected(here):
    assert dry_run("gpt", "--problem", "1_A", "--scenario", "hybrid") == cli.EXIT_OK
    assert sorted(p.name for p in (here / "out/gpt").iterdir()) == [
        "1_A.hybrid.request.json",
        "summary.json",
    ]
    assert dry_run("gemini", "--limit", "2") == cli.EXIT_OK
    assert len(list((here / "out/gemini").glob("*.request.json"))) == 2


def test_only_pending_combinations_are_written(here, capsys):
    argv = ["generate", "--model", "gpt", "--problem", "1_A", "--scenario", "black_box"]
    assert cli.main([*argv, "--confirm-spend", "10"]) == cli.EXIT_OK
    assert dry_run("gpt") == cli.EXIT_OK
    assert not (here / "out/gpt/1_A.black_box.request.json").exists()
    assert len(list((here / "out/gpt").glob("*.request.json"))) == 5


def test_an_unfaithful_prompt_is_listed_and_exits_with_1(here, monkeypatch, capsys):
    real = requests_view.check_fidelity

    def check(root, problem_id, scenario, text):
        result = real(root, problem_id, scenario, text)
        if (problem_id, scenario) != ("2_B", "white_box"):
            return result
        piece = requests_view.MissingPiece(
            piece="code", file="AC_ref.cpp", matched_chars=5, expected_chars=50
        )
        return requests_view.FidelityResult(result.checked, [piece], [])

    monkeypatch.setattr(requests_view, "check_fidelity", check)
    assert dry_run("gemini") == cli.EXIT_DATA_FAILURE
    err = capsys.readouterr().err
    assert "unfaithful: 2_B white_box: code (AC_ref.cpp) matched 5 of 50 chars" in err
    summary = json.loads((here / "out/gemini/summary.json").read_text())
    assert summary["faithful"] == 5 and len(summary["requests"]) == 6
    assert [(u["problem_id"], u["scenario"]) for u in summary["unfaithful"]] == [
        ("2_B", "white_box")
    ]


def test_an_exponent_warning_is_counted_per_problem(tmp_path, providers, monkeypatch, capsys):
    from tests.ai_clients.conftest import build_dataset
    from tests.ai_clients.conftest import problem as problem_files

    files = problem_files("1_A")
    files["enunciado.md"] = "# 1_A\n\nRead n (1 ≤ n ≤ 105) and print it.\n"
    root = build_dataset(tmp_path / "r", {"1_A": files})
    monkeypatch.chdir(root)
    assert dry_run("gpt") == cli.EXIT_OK
    out = capsys.readouterr().out
    assert "exponent warnings 1 problems (2 combinations)" in out
    assert 'exponent: 1_A: "' in out and "105" in out
    text = (root / "out/gpt/1_A.black_box.request.json").read_text(encoding="utf-8")
    assert "1 ≤ n ≤ 105" in text  # readable, as the authors asked


def test_a_folder_with_files_needs_force_which_replaces_only_that_model(here, capsys):
    assert dry_run("gpt") == cli.EXIT_OK
    assert dry_run("gemini") == cli.EXIT_OK
    (here / "out/gpt/extra.txt").write_text("old")
    capsys.readouterr()
    assert dry_run("gpt") == cli.EXIT_USAGE
    assert "out/gpt already has files; use --force to replace them" in capsys.readouterr().err
    assert dry_run("gpt", "--force") == cli.EXIT_OK
    assert not (here / "out/gpt/extra.txt").exists()
    assert (here / "out/gemini/summary.json").exists()


@pytest.mark.parametrize(
    "dest", ["data/suites/x", "data/suites", "data/dataset/x", "manifests/x", "data"]
)
def test_the_experiment_folders_are_refused(here, capsys, dest):
    assert dry_run("gpt", dest=dest) == cli.EXIT_USAGE
    assert "which is never written here" in capsys.readouterr().err


def test_the_options_need_each_other(here, capsys):
    argv = ["generate", "--model", "gpt", "--save-requests", "out", "--confirm-spend", "1"]
    assert cli.main(argv) == cli.EXIT_USAGE
    assert "--save-requests only works with --dry-run" in capsys.readouterr().err
    assert cli.main(["generate", "--model", "gpt", "--dry-run", "--force"]) == cli.EXIT_USAGE
    assert "--force only works with --save-requests" in capsys.readouterr().err


def snapshot(folder: Path):
    return sorted(
        (str(p.relative_to(folder)), p.stat().st_size, p.stat().st_mtime_ns)
        for p in folder.rglob("*")
    )


@pytest.mark.parametrize("model", MODELS)
def test_no_connection_and_nothing_else_written(here, monkeypatch, model):
    def no_network(*args, **kwargs):
        raise AssertionError("a connection was attempted")

    monkeypatch.setattr(socket, "socket", no_network)
    monkeypatch.setattr(socket, "create_connection", no_network)
    for name in (config.ENV_API_KEY["gpt"], config.ENV_API_KEY["gemini"]):
        monkeypatch.delenv(name, raising=False)
    before = snapshot(here / "data")
    assert dry_run(model) == cli.EXIT_OK
    assert snapshot(here / "data") == before
