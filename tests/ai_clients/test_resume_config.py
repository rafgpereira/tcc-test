"""``generate --resume`` refuses a configuration that differs from ``run.json`` in any field."""

import dataclasses
import json

import pytest

from ai_clients import __main__ as cli
from ai_clients import config, generation, prompt
from tests.ai_clients.fakes import FakeClock, FakeSLMClient, completion, well_formed_response

GOOD = completion(well_formed_response(["1\n"]))


@pytest.fixture()
def started(monkeypatch, repo):
    """A run started with ``generate --limit 1``; returns the fake client, to be changed."""
    monkeypatch.chdir(repo)
    monkeypatch.setenv(config.ENV_BASE_URL, "http://ollama.test:11434")
    monkeypatch.setenv(config.ENV_HARDWARE_LABEL, "RTX 3060 12GB")
    monkeypatch.delenv(config.ENV_HTTP_TIMEOUT_S, raising=False)
    monkeypatch.delenv(config.ENV_MAX_INFRA_RETRIES, raising=False)
    table = {
        (pid, s, 42 + n): GOOD
        for pid in ("1_A", "2_B")
        for s in config.SCENARIOS
        for n in range(1, 7)
    }
    client = FakeSLMClient(table, problem_ids=["1_A", "2_B"])
    monkeypatch.setattr(cli, "make_client", lambda base_url, *, timeout_s: client)
    monkeypatch.setattr(cli, "make_clock", FakeClock)
    assert cli.main(["generate", "--limit", "1"]) == cli.EXIT_OK
    client.requests.clear()
    return client


def change_info(field, value):
    def apply(monkeypatch, client):
        client.info = dataclasses.replace(client.info, **{field: value})

    return apply


def change_config(name, value):
    def apply(monkeypatch, client):
        monkeypatch.setattr(config, name, value)

    return apply


def change_template(monkeypatch, client):
    real = prompt.load_template()
    edited = prompt.PromptTemplate(real.text + "\n", real.sha256[::-1])
    monkeypatch.setattr(cli.prompt, "load_template", lambda: edited)


def change_dataset_manifest(monkeypatch, client):
    monkeypatch.setattr(generation.dataset_gate, "dataset_manifest_sha256", lambda root: "c" * 64)


CHANGES = {
    "model": change_config("MODEL", "qwen2.5-coder:14b"),
    "model_digest": change_info("digest", "sha256:" + "f" * 64),
    "model_quantization": change_info("quantization_level", "Q8_0"),
    "ollama_version": change_info("ollama_version", "0.13.0"),
    "options.temperature": change_config("TEMPERATURE", 0.2),
    "options.top_p": change_config("TOP_P", 0.9),
    "options.top_k": change_config("TOP_K", 40),
    "options.repeat_penalty": change_config("REPEAT_PENALTY", 1.1),
    "options.num_ctx": change_config("NUM_CTX", 16384),
    "options.num_predict": change_config("NUM_PREDICT", 2048),
    "seed_base": change_config("SEED_BASE", 100),
    "max_attempts": change_config("MAX_ATTEMPTS", 5),
    "prompt_template_sha256": change_template,
    "dataset_manifest_sha256": change_dataset_manifest,
    "py_time_factor": change_config("PY_TIME_FACTOR", 5),
    "py_memory_factor": change_config("PY_MEMORY_FACTOR", 8),
}


@pytest.mark.parametrize("field", sorted(CHANGES))
def test_any_changed_field_refuses_the_resume(started, monkeypatch, capsys, field):
    CHANGES[field](monkeypatch, started)
    capsys.readouterr()
    assert cli.main(["generate", "--resume"]) == cli.EXIT_USAGE
    err = capsys.readouterr().err
    assert "the configuration differs from data/suites/slm/run.json" in err
    lines = [line.strip() for line in err.splitlines() if line.strip().startswith(f"{field}:")]
    assert len(lines) == 1 and "recorded " in lines[0] and "current " in lines[0]
    assert started.requests == []


def test_every_field_but_created_at_is_compared():
    from ai_clients.schemas.run import RunConfig, SamplingOptions

    compared = {f for f in RunConfig.model_fields if f not in ("created_at", "schema_version")}
    compared = (compared - {"options"}) | {f"options.{f}" for f in SamplingOptions.model_fields}
    assert compared == set(CHANGES)


@pytest.mark.parametrize(
    ("name", "value"),
    [
        (config.ENV_HARDWARE_LABEL, "another machine, CPU only"),
        (config.ENV_HTTP_TIMEOUT_S, "3600"),
        (config.ENV_MAX_INFRA_RETRIES, "5"),
    ],
)
def test_the_machine_and_the_waiting_are_not_part_of_the_run(started, monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    assert cli.main(["generate", "--resume", "--limit", "1"]) == cli.EXIT_OK
    assert len(started.requests) == 1


def test_created_at_is_not_compared(started, repo):
    path = repo / config.SUITES_DIR / config.RUN_FILE
    data = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(json.dumps(data | {"created_at": "2000-01-01T00:00:00Z"}), encoding="utf-8")
    assert cli.main(["generate", "--resume", "--limit", "1"]) == cli.EXIT_OK
