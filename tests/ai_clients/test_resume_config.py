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
        (pid, s, n): GOOD
        for pid in ("1_A", "2_B")
        for s in config.SCENARIOS
        for n in range(1, config.MAX_ATTEMPTS + 1)
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


def change_policy_row(attempt, **fields):
    """The attempt policy of the code with one row changed (it stays coherent)."""

    def apply(monkeypatch, client):
        rows = list(config.ATTEMPT_POLICY)
        rows[attempt - 1] = rows[attempt - 1]._replace(**fields)
        monkeypatch.setattr(config, "ATTEMPT_POLICY", tuple(rows))

    return apply


def change_template_at(changed_path):
    """Load the template at ``changed_path`` with one more line (so another hash)."""

    def apply(monkeypatch, client):
        real_load = prompt.load_template

        def load(path=config.PROMPT_TEMPLATE_PATH):
            real = real_load(path)
            if path != changed_path:
                return real
            return prompt.PromptTemplate(real.text + "\n", real.sha256[::-1])

        monkeypatch.setattr(cli.prompt, "load_template", load)

    return apply


def change_dataset_manifest(monkeypatch, client):
    monkeypatch.setattr(generation.dataset_gate, "dataset_manifest_sha256", lambda root: "c" * 64)


CHANGES = {
    "model": change_config("MODEL", "qwen2.5-coder:7b"),
    "model_digest": change_info("digest", "sha256:" + "f" * 64),
    "model_quantization": change_info("quantization_level", "Q8_0"),
    "ollama_version": change_info("ollama_version", "0.13.0"),
    "options.top_p": change_config("TOP_P", 0.9),
    "options.top_k": change_config("TOP_K", 40),
    "options.repeat_penalty": change_config("REPEAT_PENALTY", 1.1),
    "options.num_ctx": change_config("NUM_CTX", 16384),
    "options.num_predict": change_config("NUM_PREDICT", 2048),
    "attempt_policy[9].temperature": change_policy_row(9, temperature=0.45),
    "attempt_policy[3].seed": change_policy_row(3, seed=144),
    "prompt_template_sha256": change_template_at(config.PROMPT_TEMPLATE_PATH),
    "predict_template_sha256": change_template_at(config.PREDICT_TEMPLATE_PATH),
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
    compared = (compared - {"attempt_policy"}) | {
        key for key in CHANGES if key.startswith("attempt_policy[")
    }
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
