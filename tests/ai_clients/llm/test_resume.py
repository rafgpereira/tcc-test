"""Resuming exactly (US3, SC-005): no recorded attempt is asked again, no partial file."""

import _thread
import json
import time

import pytest

from ai_clients import __main__ as cli
from ai_clients.llm import config, store
from tests.ai_clients.llm.fakes import answer


def generate(*extra):
    return cli.main(["generate", "--model", "gpt", "--confirm-spend", "5", *extra])


def tree(repo, model="gpt"):
    base = store.base_dir(repo, model) / "problems"
    return {p.relative_to(base).as_posix(): p.read_bytes() for p in sorted(base.rglob("*.json"))}


def without_dates(snapshot):
    """The tree, without what depends on the clock or on the order of the threads."""
    out = {}
    for name, raw in snapshot.items():
        data = json.loads(raw)
        data.pop("requested_at", None)
        out[name] = data
    return out


@pytest.fixture()
def one_at_a_time(monkeypatch):
    monkeypatch.setenv(config.ENV_MAX_CONCURRENCY["gpt"], "1")


@pytest.mark.parametrize("stop_at", [1, 2, 3, 4, 5])
def test_an_interruption_anywhere_gives_the_same_tree(
    providers, repo, monkeypatch, one_at_a_time, stop_at
):
    providers["gpt"].table[("2_B", "white_box", 1)] = answer("gpt", text="bad")
    calls = {"n": 0}

    def interrupt(problem, scenario, n):
        # Ctrl+C reaches the main thread while this call is in flight.
        calls["n"] += 1
        if calls["n"] == stop_at:
            _thread.interrupt_main()
            time.sleep(0.05)

    providers["gpt"].on_call = interrupt
    assert generate() == cli.EXIT_INTERRUPTED
    leftovers = [p for p in store.base_dir(repo, "gpt").rglob(".*.tmp")]
    assert leftovers == []
    providers["gpt"].on_call = None
    assert generate("--resume") == cli.EXIT_OK
    # The call in flight when Ctrl+C came was recorded, so nothing is asked twice: 6
    # combinations + the format failure (SC-005 allows paying it twice; here it is paid once).
    counts = [providers["gpt"].calls_of(p, s) for p in ("1_A", "2_B") for s in config.SCENARIOS]
    assert sum(counts) == 7
    resumed = without_dates(tree(repo))
    # the same as a run without interruption
    for name in list(tree(repo)):
        (store.base_dir(repo, "gpt") / "problems" / name).unlink()
    (store.run_path(repo, "gpt")).unlink()
    providers["gpt"]._counts.clear()
    assert generate() == cli.EXIT_OK
    assert without_dates(tree(repo)) == resumed


def test_a_recorded_attempt_is_never_asked_again(providers, repo, one_at_a_time):
    providers["gpt"].default = answer("gpt", text="bad")
    assert generate("--problem", "1_A", "--scenario", "hybrid") == cli.EXIT_MANUAL
    assert providers["gpt"].calls_of("1_A", "hybrid") == 3
    assert generate("--resume", "--problem", "1_A", "--scenario", "hybrid") == cli.EXIT_MANUAL
    assert providers["gpt"].calls_of("1_A", "hybrid") == 3


def test_a_selection_touches_only_its_combinations(providers, repo):
    assert generate("--problem", "2_B", "--scenario", "white_box") == cli.EXIT_OK
    assert list(tree(repo)) == ["2_B/white_box/attempt_1.json", "2_B/white_box/suite.json"]


@pytest.mark.parametrize(
    "field, change",
    [
        ("model_requested", lambda run: {"model_requested": "gpt-5.4-mini"}),
        ("dataset_manifest_sha256", lambda run: {"dataset_manifest_sha256": "c" * 64}),
        (
            "request_parameters.max_output_tokens",
            lambda run: {
                "request_parameters": {**run["request_parameters"], "max_output_tokens": 8}
            },
        ),
        ("response_schema", lambda run: {"response_schema": {"type": "object"}}),
    ],
)
def test_resume_refuses_another_configuration(providers, repo, capsys, field, change):
    assert generate("--problem", "1_A", "--scenario", "hybrid") == cli.EXIT_OK
    path = store.run_path(repo, "gpt")
    data = json.loads(path.read_text())
    data.update(change(data))
    path.write_text(json.dumps(data))
    capsys.readouterr()
    assert generate("--resume") == cli.EXIT_USAGE
    err = capsys.readouterr().err
    assert "the configuration differs from data/suites/gpt/run.json" in err
    assert f"  {field}: recorded" in err


def test_resume_accepts_another_price_table_cap_concurrency_and_waits(providers, repo, monkeypatch):
    assert generate("--problem", "1_A", "--scenario", "hybrid") == cli.EXIT_OK
    path = store.run_path(repo, "gpt")
    data = json.loads(path.read_text())
    data["price_table"] = data["price_table"][:1]
    path.write_text(json.dumps(data))
    monkeypatch.setenv(config.ENV_MAX_CONCURRENCY["gpt"], "2")
    monkeypatch.setenv(config.ENV_MAX_INFRA_RETRIES["gpt"], "3")
    monkeypatch.setenv(config.ENV_HTTP_TIMEOUT_S, "60")
    assert cli.main(["generate", "--model", "gpt", "--resume", "--confirm-spend", "9"]) == 0


def test_resume_refuses_a_text_base_changed_without_change_template(
    providers, repo, monkeypatch, tmp_path, capsys
):
    assert generate("--problem", "1_A", "--scenario", "hybrid") == cli.EXIT_OK
    changed = tmp_path / "llm_prompt.txt"
    changed.write_text(config.LLM_TEMPLATE_PATH.read_text() + "\nOne more rule.\n")
    monkeypatch.setattr(config, "LLM_TEMPLATE_PATH", changed)
    capsys.readouterr()
    assert generate("--resume") == cli.EXIT_USAGE
    err = capsys.readouterr().err
    assert "template_sha256: recorded" in err
    assert "change-template --model gpt --template llm" in err
