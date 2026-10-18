"""``show-request --suite-attempts``: the request of the attempt every suite came from, at once."""

import json

import pytest

from ai_clients import __main__ as cli
from ai_clients import requests_view
from tests.ai_clients.llm.fakes import answer

BAD = answer("gpt", text="not json")


def bulk(*extra, model="gpt", dest="out"):
    argv = ["show-request", "--model", model, "--suite-attempts", "--output-dir", dest, *extra]
    return cli.main(argv)


@pytest.fixture()
def suites(providers, repo, capsys):
    """1_A with a suite in the three scenarios (black_box from attempt 2), 2_B with none."""
    providers["gpt"].table = {("1_A", "black_box", 1): BAD}
    argv = ["generate", "--model", "gpt", "--problem", "1_A", "--confirm-spend", "10"]
    assert cli.main(argv) == cli.EXIT_OK
    capsys.readouterr()
    return providers["gpt"].requests


def test_the_attempt_each_suite_came_from_is_written(suites, repo, capsys):
    assert bulk() == cli.EXIT_OK
    out = capsys.readouterr().out
    folder = repo / "out/gpt"
    assert sorted(p.name for p in folder.iterdir()) == [
        "1_A.black_box.request.json",
        "1_A.hybrid.request.json",
        "1_A.white_box.request.json",
        "summary.json",
    ]
    sent = {(p, s): [] for p, s, _ in suites}
    for p, s, body in suites:
        sent[(p, s)].append(body)
    written = json.loads((folder / "1_A.black_box.request.json").read_text())
    assert written == sent[("1_A", "black_box")][1]  # attempt 2, the one the suite came from
    summary = requests_view.RequestsSummary.model_validate_json(
        (folder / "summary.json").read_text()
    )
    assert summary.source == "suite_attempt" and summary.combinations == 3
    assert [r.attempt for r in summary.requests] == [2, 1, 1]
    assert summary.skipped == [
        f"2_B {s}: no suite.json yet" for s in ("black_box", "white_box", "hybrid")
    ]
    assert (
        "suite attempts: 3 saved in out/gpt; prompt sha256 matches in all; faithful 3/3; "
        "3 skipped" in out
    )
    assert "Read an integer n" not in out  # the requests are never printed


def test_a_request_that_cannot_be_checked_is_refused_and_not_written(suites, repo, capsys):
    path = repo / "data/suites/gpt/problems/1_A/hybrid/attempt_1.json"
    data = json.loads(path.read_text())
    data["prompt_sha256"] = "d" * 64
    path.write_text(json.dumps(data))
    assert bulk() == cli.EXIT_DATA_FAILURE
    err = capsys.readouterr().err
    assert "refused: 1_A hybrid: the rebuilt prompt has sha256" in err
    assert not (repo / "out/gpt/1_A.hybrid.request.json").exists()
    summary = json.loads((repo / "out/gpt/summary.json").read_text())
    assert summary["combinations"] == 2 and len(summary["damaged"]) == 1


def test_the_selection_and_the_destination(suites, repo, capsys):
    assert bulk("--problem", "1_A", "--scenario", "white_box") == cli.EXIT_OK
    assert sorted(p.name for p in (repo / "out/gpt").iterdir()) == [
        "1_A.white_box.request.json",
        "summary.json",
    ]
    assert bulk() == cli.EXIT_USAGE  # the folder already has files
    assert bulk("--force") == cli.EXIT_OK
    assert bulk(dest="data/suites/x") == cli.EXIT_USAGE


@pytest.mark.parametrize(
    "argv, message",
    [
        (["--suite-attempts"], "--suite-attempts needs --output-dir DIR"),
        (
            ["--suite-attempts", "--output-dir", "o", "--output", "f.json"],
            "--suite-attempts takes --output-dir, not --output, --attempt or --barred",
        ),
        (["--output-dir", "o"], "--output-dir only works with --suite-attempts"),
        (["--problem", "1_A"], "show-request needs --problem, --scenario and --output"),
    ],
)
def test_usage_errors(providers, repo, capsys, argv, message):
    assert cli.main(["show-request", "--model", "gpt", *argv]) == cli.EXIT_USAGE
    assert message in capsys.readouterr().err


def test_without_a_run_it_is_a_usage_error(providers, repo, capsys):
    assert bulk() == cli.EXIT_USAGE
    assert "no run in data/suites/gpt (no run.json)" in capsys.readouterr().err
