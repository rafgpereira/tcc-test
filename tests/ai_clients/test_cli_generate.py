"""``python -m ai_clients generate``: options, environment, run.json and exit codes."""

import json

import pytest

from ai_clients import __main__ as cli
from ai_clients import config, store
from ai_clients.ollama import OllamaUnavailable
from tests.ai_clients.fakes import FakeClock, FakeSLMClient, completion, well_formed_response

GOOD = completion(well_formed_response(["1\n"]))
BAD = completion("no blocks here")


@pytest.fixture()
def env(monkeypatch):
    monkeypatch.setenv(config.ENV_BASE_URL, "http://ollama.test:11434")
    monkeypatch.setenv(config.ENV_HARDWARE_LABEL, "RTX 3060 12GB")
    monkeypatch.delenv(config.ENV_HTTP_TIMEOUT_S, raising=False)
    monkeypatch.delenv(config.ENV_MAX_INFRA_RETRIES, raising=False)
    monkeypatch.delenv(config.ENV_MODEL, raising=False)


@pytest.fixture()
def fake(monkeypatch, repo, env):
    """``generate`` inside ``repo`` with a fake client (answers GOOD to everything by default)."""
    monkeypatch.chdir(repo)
    table = {
        (pid, s, 42 + n): GOOD
        for pid in ("1_A", "2_B")
        for s in config.SCENARIOS
        for n in range(1, 7)
    }
    client = FakeSLMClient(table, problem_ids=["1_A", "2_B"])
    made = {}

    def make_client(base_url, *, timeout_s):
        made.update(base_url=base_url, timeout_s=timeout_s)
        return client

    monkeypatch.setattr(cli, "make_client", make_client)
    monkeypatch.setattr(cli, "make_clock", FakeClock)
    client.made = made
    return client


def test_a_first_run_creates_run_json_and_records_every_combination(fake, repo, capsys):
    assert cli.main(["generate"]) == cli.EXIT_OK
    run = store.read_run(repo)
    assert run.model == "qwen2.5-coder:7b" and run.model_digest == fake.info.digest
    assert fake.made == {"base_url": "http://ollama.test:11434", "timeout_s": 900}
    assert len(fake.requests) == 6
    assert capsys.readouterr().out.splitlines()[-1] == (
        "done: 6 calls, 6 parsed, 0 unparseable, 0 repetition, 0 discarded suites; "
        "6 pending execution"
    )


def test_an_existing_run_needs_resume(fake, capsys):
    assert cli.main(["generate", "--problem", "1_A", "--scenario", "black_box"]) == cli.EXIT_OK
    capsys.readouterr()
    assert cli.main(["generate"]) == cli.EXIT_USAGE
    assert "a run already exists in data/suites/slm; use --resume to continue it" in (
        capsys.readouterr().err
    )
    assert cli.main(["generate", "--resume"]) == cli.EXIT_OK
    assert len(fake.requests) == 6  # 1 + the 5 still pending


def test_resume_without_a_run_is_a_usage_error(fake, capsys):
    assert cli.main(["generate", "--resume"]) == cli.EXIT_USAGE
    assert "nothing to resume" in capsys.readouterr().err
    assert fake.requests == []


@pytest.mark.parametrize("missing", [config.ENV_BASE_URL, config.ENV_HARDWARE_LABEL])
def test_the_required_variables_are_checked(fake, monkeypatch, capsys, missing):
    monkeypatch.delenv(missing)
    assert cli.main(["generate"]) == cli.EXIT_USAGE
    assert missing in capsys.readouterr().err
    assert fake.requests == []


@pytest.mark.parametrize("name", [config.ENV_HTTP_TIMEOUT_S, config.ENV_MAX_INFRA_RETRIES])
def test_an_optional_variable_must_be_a_positive_integer(fake, monkeypatch, name):
    monkeypatch.setenv(name, "zero")
    assert cli.main(["generate"]) == cli.EXIT_USAGE


def test_the_timeout_comes_from_the_environment(fake, monkeypatch):
    monkeypatch.setenv(config.ENV_HTTP_TIMEOUT_S, "1800")
    cli.main(["generate", "--limit", "1"])
    assert fake.made["timeout_s"] == 1800


def test_another_model_comes_from_the_environment_and_is_recorded(fake, monkeypatch, repo):
    monkeypatch.setenv(config.ENV_MODEL, " qwen2.5-coder:14b ")
    assert cli.main(["generate", "--problem", "1_A", "--scenario", "black_box"]) == cli.EXIT_OK
    assert store.read_run(repo).model == "qwen2.5-coder:14b"
    assert {request["model"] for request in fake.requests} == {"qwen2.5-coder:14b"}


def test_resume_refuses_a_model_other_than_the_recorded_one(fake, monkeypatch, capsys):
    assert cli.main(["generate", "--problem", "1_A", "--scenario", "black_box"]) == cli.EXIT_OK
    monkeypatch.setenv(config.ENV_MODEL, "qwen2.5-coder:14b")
    assert cli.main(["generate", "--resume"]) == cli.EXIT_USAGE
    assert "model: recorded 'qwen2.5-coder:7b', current 'qwen2.5-coder:14b'" in (
        capsys.readouterr().err
    )
    assert len(fake.requests) == 1


def test_the_retry_ceiling_exits_with_3(fake, monkeypatch, repo, capsys):
    monkeypatch.setenv(config.ENV_MAX_INFRA_RETRIES, "2")
    fake.table[("1_A", "black_box", 43)] = OllamaUnavailable("connection refused")
    assert cli.main(["generate", "--problem", "1_A", "--scenario", "black_box"]) == cli.EXIT_INFRA
    err = capsys.readouterr().err
    assert "ollama unavailable after 2 consecutive retries" in err
    assert "run generate --resume when the service is back" in err
    assert not store.combination_dir(repo, "1_A", "black_box").exists()


def test_dry_run_writes_nothing_and_calls_nothing(repo, monkeypatch, capsys):
    monkeypatch.chdir(repo)
    monkeypatch.delenv(config.ENV_BASE_URL, raising=False)  # not needed for a dry run
    monkeypatch.delenv(config.ENV_HARDWARE_LABEL, raising=False)
    monkeypatch.setattr(cli, "make_client", lambda *a, **k: pytest.fail("no client in a dry run"))
    assert cli.main(["generate", "--dry-run"]) == cli.EXIT_OK
    out = capsys.readouterr().out.splitlines()
    assert out[0].startswith("1_A black_box attempt 1 seed 43: prompt ") and out[0].endswith(
        " chars"
    )
    assert len([line for line in out if " attempt " in line]) == 6
    assert "dry run: 6 calls planned" in out
    assert any(line.startswith("largest prompt: hybrid ") for line in out)
    assert not (repo / "data" / "suites").exists()


def test_limit_takes_the_first_pending_combinations_in_canonical_order(fake):
    fake.table[("1_A", "black_box", 43)] = BAD
    assert cli.main(["generate", "--limit", "2"]) == cli.EXIT_OK
    assert [r["key"] for r in fake.requests] == [
        ("1_A", "black_box", 43),
        ("1_A", "black_box", 44),
        ("1_A", "white_box", 43),
    ]


def test_problem_and_scenario_filter_the_calls(fake):
    assert cli.main(["generate", "--problem", "2_B", "--scenario", "hybrid"]) == cli.EXIT_OK
    assert [r["key"] for r in fake.requests] == [("2_B", "hybrid", 43)]


def test_an_unknown_problem_is_a_usage_error(fake):
    assert cli.main(["generate", "--problem", "9_Z"]) == cli.EXIT_USAGE
    assert fake.requests == []


def test_a_changed_dataset_stops_before_any_call(fake, repo):
    (repo / "data" / "dataset" / "problems" / "1_A" / "enunciado.md").write_text("x\n")
    assert cli.main(["generate"]) == cli.EXIT_DATA_FAILURE
    assert fake.requests == []


def test_a_missing_dataset_manifest_stops_with_1(fake, repo):
    (repo / config.DATASET_MANIFEST_PATH).unlink()
    assert cli.main(["generate"]) == cli.EXIT_DATA_FAILURE


def test_run_json_is_valid_deterministic_json(fake, repo):
    cli.main(["generate", "--limit", "1"])
    data = json.loads((repo / config.SUITES_DIR / config.RUN_FILE).read_text(encoding="utf-8"))
    assert data["schema_version"] == 1 and data["seed_base"] == 42
