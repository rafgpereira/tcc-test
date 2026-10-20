"""``report --model gpt|gemini`` (FR-025, SC-003)."""

import json

import pytest

from ai_clients import __main__ as cli
from ai_clients.llm import config, store
from tests.ai_clients.llm.fakes import answer, answer_json


@pytest.fixture()
def finished(providers, repo, monkeypatch):
    """GPT: one format failure then success, one truncated x3 (awaiting), one barred, the rest ok."""
    monkeypatch.setenv(config.ENV_MAX_CONCURRENCY["gpt"], "1")
    table = providers["gpt"].table
    table[("1_A", "white_box", 1)] = answer("gpt", text="bad")
    table[("1_A", "white_box", 2)] = answer(
        "gpt", text=answer_json((("2\n", "2\n"), ("2\n", "3\n"), ("", "1")))
    )
    for n in (1, 2, 3):
        table[("2_B", "hybrid", n)] = answer("gpt", status="incomplete", reason="max_output_tokens")
    cli.main(["generate", "--model", "gpt", "--confirm-spend", "5"])
    return providers


def report(repo, model="gpt"):
    assert cli.main(["report", "--model", model]) == cli.EXIT_OK
    return json.loads((repo / config.report_path(model)).read_text())


def test_the_report_counts_every_combination(finished, repo, capsys):
    data = report(repo)
    assert data["combinations"]["total"] == {
        "total": 6,
        "accepted_predicted": 5,
        "discarded_manual": 0,
        "accepted_barred": 0,
        "awaiting_manual": 1,
        "pending": 0,
    }
    assert data["attempts_by_number"] == {"1": 6, "2": 2, "3": 1}
    assert data["failures"] == {
        "not_json": {"1": 1, "2": 0, "3": 0},
        "truncated": {"1": 1, "2": 1, "3": 1},
    }
    assert data["truncated"]["hybrid"] == 3 and data["truncated"]["total"] == 3
    discards = data["test_discards"]["white_box"]
    assert (
        discards["duplicate_inputs"],
        discards["conflicting_outputs"],
        discards["empty_tests"],
    ) == (1, 1, 1)
    assert data["suite_size"]["total"]["count"] == 5
    assert data["models_returned"] == {"gpt-5.4-mini-2026-03-17": 9}
    assert data["safety_blocks_by_category"] is None
    assert (
        "6 combinations: 5 accepted_predicted, 0 accepted_barred, 0 discarded_manual, 1 awaiting_manual"
        in (capsys.readouterr().out)
    )


def test_the_total_cost_is_the_sum_of_every_call(finished, repo):
    data = report(repo)
    attempts = [
        store.read_attempt(repo, "gpt", p, s, n)
        for p in ("1_A", "2_B")
        for s in config.SCENARIOS
        for n in (1, 2, 3)
    ]
    total = sum(a.cost_usd for a in attempts if a is not None)
    assert data["cost_usd"]["total"] == pytest.approx(total)
    assert data["cost_usd"]["by_group"]["total"] == pytest.approx(total)
    assert data["latency_s"]["calls"] == 9


def test_barred_answers_are_counted_apart(providers, repo, monkeypatch):
    monkeypatch.setenv(config.ENV_MAX_CONCURRENCY["gemini"], "1")
    for n in range(1, config.MAX_BARRED + 1):  # the same attempt, asked again
        providers["gemini"].table[("1_A", "black_box", n)] = answer("gemini", reasoning=0)
    cli.main(["generate", "--model", "gemini", "--confirm-spend", "5"])
    data = report(repo, "gemini")
    assert data["barred"] == {"count": 3, "combinations": ["1_A black_box"] * 3}
    assert data["combinations"]["total"]["accepted_barred"] == 1
    assert data["combinations"]["black_box"]["accepted_barred"] == 1
    assert data["cost_usd"]["barred_cost_usd"] > 0
    assert data["cost_usd"]["total"] == pytest.approx(
        data["cost_usd"]["by_group"]["total"] + data["cost_usd"]["barred_cost_usd"]
    )
    assert data["safety_blocks_by_category"] == {}


def test_safety_blocks_of_gemini_by_category(providers, repo):
    providers["gemini"].default = answer(
        "gemini", finish="SAFETY", blocked=("HARM_CATEGORY_HARASSMENT",)
    )
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
    assert report(repo, "gemini")["safety_blocks_by_category"] == {"HARM_CATEGORY_HARASSMENT": 3}


def test_the_same_tree_gives_the_same_bytes(finished, repo):
    report(repo)
    first = (repo / config.report_path("gpt")).read_bytes()
    report(repo)
    assert (repo / config.report_path("gpt")).read_bytes() == first


def test_report_works_on_an_unfinished_run(providers, repo):
    cli.main(["generate", "--model", "gpt", "--problem", "1_A", "--confirm-spend", "5"])
    assert report(repo)["combinations"]["total"]["pending"] == 3
