"""``show-request --model slm``: the body sent to Ollama, with the seed and temperature of the
attempt and the template of its kind (solution 1 to 12, prediction 13 to 15)."""

import dataclasses
import json

import pytest

from ai_clients import __main__ as cli
from ai_clients import config, generation, problem, requests_view
from ai_clients.prompt import build_prompt, load_template, prompt_sha256
from ai_clients.schemas.generation import GenerationRecord
from ai_clients.store import AttemptFiles
from tests.ai_clients.fakes import (
    FakeClock,
    FakeSLMClient,
    completion,
    start_run,
    well_formed_response,
)
from tests.ai_clients.test_schemas import generation as generation_record

GOOD = completion(well_formed_response(["1\n"]))
ONE = ["--problem", "1_A", "--scenario", "black_box"]


@pytest.fixture()
def fake(monkeypatch, repo):
    monkeypatch.chdir(repo)
    monkeypatch.setenv(config.ENV_BASE_URL, "http://ollama.test:11434")
    monkeypatch.setenv(config.ENV_HARDWARE_LABEL, "RTX 3060 12GB")
    monkeypatch.delenv(config.ENV_MODEL, raising=False)
    table = {(pid, s, 1): GOOD for pid in ("1_A", "2_B") for s in config.SCENARIOS}
    client = FakeSLMClient(table, problem_ids=["1_A", "2_B"])
    monkeypatch.setattr(cli, "make_client", lambda base_url, *, timeout_s: client)
    monkeypatch.setattr(cli, "make_clock", FakeClock)
    return client


def test_an_attempt_made_by_generate_is_written_as_the_body_sent(fake, repo, capsys):
    assert cli.main(["generate", *ONE]) == cli.EXIT_OK
    sent = fake.requests[0]
    capsys.readouterr()
    argv = ["show-request", "--model", "slm", *ONE, "--output", "out/slm.json"]
    assert cli.main(argv) == cli.EXIT_OK
    body = json.loads((repo / "out/slm.json").read_text(encoding="utf-8"))
    assert body == {
        "model": sent["model"],
        "messages": [{"role": "user", "content": sent["prompt"]}],
        "stream": True,
        "options": sent["options"],
    }
    assert body["options"]["seed"] == 42 and body["options"]["temperature"] == 0.7
    out = capsys.readouterr().out
    assert "slm 1_A black_box attempt 1 (of 1); prompt sha256 matches; dataset: faithful" in out
    assert sent["prompt"] not in out


@pytest.fixture()
def records(repo, monkeypatch):
    """``make(last, null_template_sha=False)``: attempts 1..last of 1_A black_box, each with the
    prompt hash of its own template, served to the view as the store would (run.json started)."""
    run = start_run(repo)
    loaded = problem.load_problem(repo, "1_A")
    templates = {
        "solution": load_template(),
        "prediction": load_template(config.PREDICT_TEMPLATE_PATH),
    }

    def make(last, *, null_template_sha=False):
        made = []
        for n in range(1, last + 1):
            template = templates[config.attempt_kind(n)]
            text = build_prompt(template, loaded, "black_box")
            made.append(
                GenerationRecord(
                    **generation_record(
                        attempt=n,
                        model_digest=run.model_digest,
                        prompt_sha256=prompt_sha256(text),
                        template_sha256=None if null_template_sha else template.sha256,
                    )
                )
            )
        monkeypatch.setattr(
            requests_view.store, "attempt_files", lambda *a, **k: AttemptFiles(made, {}, None)
        )
        return run, made

    return make


@pytest.mark.parametrize("attempt", [1, 12, 13, 15])
def test_each_attempt_has_its_seed_temperature_and_template(repo, records, attempt):
    run, made = records(15)
    view = requests_view.build_view(repo, "slm", "1_A", "black_box", attempt=attempt)
    spec = run.spec(attempt)
    assert view.body["options"] == dataclasses.asdict(generation.generation_options(run, attempt))
    assert (view.body["options"]["seed"], view.body["options"]["temperature"]) == (
        spec.seed,
        spec.temperature,
    )
    assert view.body["model"] == run.model
    name = "slm_predict_prompt.txt" if attempt >= 13 else "slm_prompt.txt"
    assert view.template.path.endswith(name)
    assert view.prompt_sha256 == made[attempt - 1].prompt_sha256
    assert view.body["messages"] == [{"role": "user", "content": view.prompt}]


def test_an_attempt_without_template_hash_uses_the_one_of_run_json(repo, records):
    run, _ = records(1, null_template_sha=True)
    view = requests_view.build_view(repo, "slm", "1_A", "black_box")
    assert view.template.expected_sha256 == run.prompt_template_sha256
    assert view.template.origin == "current"
