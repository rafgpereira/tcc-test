"""Respecting the request limits of the APIs: pacing, daily quota, waits that Ctrl+C ends."""

import json
import threading
import time

import pytest

from ai_clients import __main__ as cli
from ai_clients.llm import config, generation
from ai_clients.llm.providers import ProviderFatal, ProviderUnavailable, classify_http_error
from tests.ai_clients.llm.fakes import FakeClock, FakeProvider, answer, unavailable
from tests.ai_clients.llm.test_concurrency import COMBOS, run_with


def run_paced(repo, provider, per_minute, concurrency=1, clock=None, spend_cap=None):
    from ai_clients.llm import store
    from ai_clients.prompt import load_template

    template = load_template(config.LLM_TEMPLATE_PATH)
    clock = clock or FakeClock()
    if not store.run_exists(repo, "gemini"):
        current = generation.current_run_config(repo, "gemini", template, clock.utc_now())
        store.write_run(repo, "gemini", current)
    return clock, generation.generate(
        repo,
        "gemini",
        COMBOS,
        provider,
        template=template,
        run=store.read_run(repo, "gemini"),
        clock=clock,
        echo=lambda line: None,
        max_infra_retries=3,
        concurrency=concurrency,
        requests_per_minute=per_minute,
        spend_cap=spend_cap,
    )


# --------------------------------------------------------------------------------- pacing


def test_requests_are_spaced_to_the_limit_per_minute(repo):
    clock, result = run_paced(repo, FakeProvider("gemini", default=answer("gemini")), 5)
    assert result.suites == 6
    assert clock.sleeps == [12.0] * 5  # 6 starts, 60 / 5 seconds apart


def test_retries_are_paced_too(repo):
    provider = FakeProvider("gemini", default=answer("gemini"))
    provider.table[("1_A", "black_box", 1)] = unavailable("HTTP 503")
    clock, result = run_paced(repo, provider, 6)
    # the backoff of the retry (5 s) then the pacing of every start (10 s apart)
    assert result.suites == 6 and clock.elapsed >= 6 * 10


def test_pacing_holds_across_threads(repo):
    clock, result = run_paced(repo, FakeProvider("gemini", default=answer("gemini")), 5, 4)
    assert result.suites == 6 and clock.elapsed == pytest.approx(5 * 12.0)


def test_without_a_limit_nothing_waits(repo):
    clock, _ = run_paced(repo, FakeProvider("gemini", default=answer("gemini")), None)
    assert clock.sleeps == []


def test_the_limit_comes_from_the_env(providers, repo, monkeypatch, clock):
    monkeypatch.setenv(config.ENV_MAX_REQUESTS_PER_MINUTE["gemini"], "5")
    monkeypatch.setenv(config.ENV_MAX_CONCURRENCY["gemini"], "1")
    argv = ["generate", "--model", "gemini", "--problem", "1_A", "--confirm-spend", "1"]
    assert cli.main(argv) == cli.EXIT_OK
    assert clock.sleeps == [12.0, 12.0]
    monkeypatch.setenv(config.ENV_MAX_REQUESTS_PER_MINUTE["gemini"], "five")
    assert cli.main([*argv, "--resume"]) == cli.EXIT_USAGE


# ---------------------------------------------------------------------------- daily quota


def quota_body(quota_id, value="20"):
    return json.dumps(
        {
            "error": {
                "code": 429,
                "message": "You exceeded your current quota",
                "status": "RESOURCE_EXHAUSTED",
                "details": [
                    {
                        "@type": "type.googleapis.com/google.rpc.QuotaFailure",
                        "violations": [
                            {
                                "quotaMetric": "generativelanguage.googleapis.com/x",
                                "quotaId": quota_id,
                                "quotaValue": value,
                            }
                        ],
                    },
                    {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "52s"},
                ],
            }
        }
    )


def test_an_exhausted_daily_quota_stops_at_once():
    error = classify_http_error(
        "gemini", 429, quota_body("GenerateRequestsPerDayPerProjectPerModel-FreeTier")
    )
    assert isinstance(error, ProviderFatal)
    assert "daily request quota" in str(error) and "limit 20" in str(error)


def test_a_per_minute_quota_is_waited_for():
    error = classify_http_error(
        "gemini", 429, quota_body("GenerateRequestsPerMinutePerProjectPerModel-FreeTier", "5")
    )
    assert isinstance(error, ProviderUnavailable) and error.retry_after_s == 52


def test_the_daily_quota_stops_the_command_with_code_3(providers, repo, capsys):
    providers["gemini"].default = classify_http_error(
        "gemini", 429, quota_body("GenerateRequestsPerDayPerProjectPerModel-FreeTier")
    )
    argv = ["generate", "--model", "gemini", "--problem", "1_A", "--confirm-spend", "1"]
    assert cli.main(argv) == cli.EXIT_INFRA
    assert "daily request quota of the API is exhausted" in capsys.readouterr().err


# ------------------------------------------------------------------- waits that Ctrl+C ends


def test_a_long_wait_ends_when_the_invocation_stops():
    clock, wake = generation.SystemClock(), threading.Event()
    threading.Timer(0.05, wake.set).start()
    started = time.monotonic()
    clock.wait(30, wake)
    assert time.monotonic() - started < 5


class BlockingClock(FakeClock):
    """A clock whose waits really block (up to 5 s) until the invocation stops."""

    def wait(self, seconds, wake):
        started = time.monotonic()
        wake.wait(timeout=5)
        self.sleeps.append(round(time.monotonic() - started, 1))


def test_stopping_wakes_every_waiting_thread(repo):
    """A stop (spend cap, interruption) ends the waits of the other threads."""
    provider = FakeProvider("gemini", default=answer("gemini"))
    provider.on_call = lambda *_: time.sleep(0.5)  # the other thread is waiting by then
    clock, result = run_paced(repo, provider, 1, 2, clock=BlockingClock(), spend_cap=1e-9)
    assert result.stop == "spend_cap" and len(provider.requests) == 1
    assert clock.sleeps and all(s < 5 for s in clock.sleeps)  # woken by the stop, not timed out


def test_run_with_still_works_without_a_limit(repo):
    result = run_with(repo, FakeProvider("gpt", default=answer("gpt")), 2)
    assert result.suites == 6
