"""The spend cap of an invocation (FR-022a, SC-004a) and the cost records (SC-003)."""

import threading

import pytest

from ai_clients import __main__ as cli
from ai_clients.llm import config, store
from tests.ai_clients.llm.fakes import answer

# Each well-formed gpt answer of the fakes costs (2000 x 0.75 + 1500 x 4.50) / 1e6 = 0.00825.
CALL = 0.00825


def generate(*extra, model="gpt"):
    return cli.main(["generate", "--model", model, *extra])


def test_the_cap_stops_sending_new_calls(providers, repo, monkeypatch, capsys):
    monkeypatch.setenv(config.ENV_MAX_CONCURRENCY["gpt"], "1")
    # 2.5 calls of budget: the 3rd call is sent (2 x 0.00825 < cap), then the cap is reached.
    assert generate("--confirm-spend", str(CALL * 2.5)) == cli.EXIT_SPEND_CAP
    captured = capsys.readouterr()
    assert len(providers["gpt"].requests) == 3
    assert "spend cap reached: spent US$ 0.0248 of US$ 0.020625" in captured.err
    assert "(US$ 0.0041 over the cap by the calls already in flight)" in captured.err
    assert "--model gpt --resume --confirm-spend <new cap>" in captured.err


def test_the_calls_in_flight_finish_and_are_recorded(providers, repo, monkeypatch):
    """With 4 calls at a time and a cap reached by the first one to end, the 3 others in flight
    finish and are recorded, and nothing else is sent (SC-004a)."""
    monkeypatch.setenv(config.ENV_MAX_CONCURRENCY["gpt"], "4")
    started, release = threading.Barrier(4), threading.Event()

    def on_call(problem, scenario, n):
        if len(providers["gpt"].requests) <= 4:
            started.wait(timeout=5)  # the 4 first calls are in flight together
            if (problem, scenario) != ("1_A", "black_box"):
                release.wait(timeout=5)  # they end after the first one

    def first_then_release():
        result = answer("gpt")
        return result

    providers["gpt"].on_call = on_call
    original = providers["gpt"].call

    def call(prompt):
        result = original(prompt)
        release.set()
        return result

    providers["gpt"].call = call
    assert generate("--confirm-spend", str(CALL / 2)) == cli.EXIT_SPEND_CAP
    assert len(providers["gpt"].requests) == 4
    attempts = [
        store.read_attempt(repo, "gpt", p, s, 1) for p in ("1_A", "2_B") for s in config.SCENARIOS
    ]
    assert sum(a is not None for a in attempts) == 4
    assert providers["gpt"].overlaps == []


def test_resume_continues_with_a_new_cap(providers, repo, monkeypatch, capsys):
    monkeypatch.setenv(config.ENV_MAX_CONCURRENCY["gpt"], "1")
    assert generate("--confirm-spend", str(CALL)) == cli.EXIT_SPEND_CAP
    capsys.readouterr()
    assert generate("--resume", "--confirm-spend", "1") == cli.EXIT_OK
    out = capsys.readouterr().out
    assert "suites: 5 accepted_predicted" in out
    assert len(providers["gpt"].requests) == 6


def test_a_barred_answer_counts_in_the_spending(providers, repo, monkeypatch, capsys):
    monkeypatch.setenv(config.ENV_MAX_CONCURRENCY["gpt"], "1")
    providers["gpt"].table[("1_A", "black_box", 1)] = answer("gpt", reasoning=0)
    assert generate("--confirm-spend", "1") == cli.EXIT_NO_REASONING
    assert f"spent US$ {CALL:.4f}" in capsys.readouterr().out


def test_barred_wins_over_the_spend_cap(providers, repo, monkeypatch):
    monkeypatch.setenv(config.ENV_MAX_CONCURRENCY["gpt"], "1")
    providers["gpt"].table[("1_A", "black_box", 1)] = answer("gpt", reasoning=0)
    assert generate("--confirm-spend", str(CALL / 2)) == cli.EXIT_NO_REASONING


@pytest.mark.parametrize("model", config.MODELS)
def test_every_call_records_tokens_cost_and_time(providers, repo, capsys, model):
    assert generate("--confirm-spend", "1", model=model) == cli.EXIT_OK
    total = 0.0
    for p in ("1_A", "2_B"):
        for s in config.SCENARIOS:
            record = store.read_attempt(repo, model, p, s, 1)
            assert record.usage.output_tokens > 0 and record.latency_s > 0
            assert record.price_row.model_key == model and record.cost_usd > 0
            total += record.cost_usd
    assert f"spent US$ {total:.4f}" in capsys.readouterr().out
