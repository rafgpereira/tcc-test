"""``generate --model gpt|gemini`` with one call at a time (US1): attempts, suites, failures."""

import json

import pytest

from ai_clients import __main__ as cli
from ai_clients.llm import config, store
from ai_clients.llm.providers import ProviderFatal
from tests.ai_clients.llm.fakes import answer, answer_json, unavailable

ONE = ["--problem", "1_A", "--scenario", "black_box"]


def run(*extra, model="gpt"):
    return cli.main(["generate", "--model", model, *ONE, "--confirm-spend", "10", *extra])


def bad(model="gpt"):
    return answer(model, text="not json")


@pytest.mark.parametrize("model", config.MODELS)
def test_one_combination_from_the_call_to_the_suite(providers, repo, capsys, model):
    assert run(model=model) == cli.EXIT_OK
    out = capsys.readouterr().out
    assert "1_A black_box attempt 1: parsed (1 tests)" in out
    assert "1_A black_box: suite recorded (accepted_predicted)" in out
    record = store.read_attempt(repo, model, "1_A", "black_box", 1)
    assert record.model_returned == config.MODEL_ID[model] and record.raw_body
    assert record.usage.reasoning_tokens == 1200 and record.cost_usd > 0 and record.latency_s == 2
    suite = store.read_suite(repo, model, "1_A", "black_box")
    assert suite.status.value == "accepted_predicted" and suite.model_digest
    run_json = store.read_run(repo, model)
    assert run_json.model_requested == config.MODEL_ID[model]
    assert providers[model].calls_of("1_A", "black_box") == 1
    assert providers["created"] == [(model, f"secret-{model}-key", 900)]


def test_each_attempt_is_one_self_contained_request(providers, repo):
    providers["gpt"].table = {("1_A", "black_box", 1): bad(), ("1_A", "black_box", 2): bad()}
    assert run() == cli.EXIT_OK
    bodies = [body for _, _, body in providers["gpt"].requests]
    assert len(bodies) == 3 and bodies[0] == bodies[1] == bodies[2]
    for body in bodies:
        assert set(body) == {"input", "max_output_tokens", "model", "reasoning", "store", "text"}
        assert body["store"] is False


def test_the_raw_answer_is_kept_whole_so_reading_it_again_never_calls_the_api(providers, repo):
    # FR-010, as in the SLM: the raw body goes into the attempt record, so the interpretation can
    # always be redone from the file (the interpreter is pure and never raises: test_interpret.py).
    from ai_clients.llm.interpret import interpret
    from ai_clients.llm.providers import answer_from_body
    from dataset.schemas.testes import TestCase

    sent = answer("gpt", text=answer_json((("2\n", "2\n"),)))
    providers["gpt"].default = sent
    assert run() == cli.EXIT_OK
    record = store.read_attempt(repo, "gpt", "1_A", "black_box", 1)
    assert record.raw_body == sent.raw_body
    again = interpret(
        answer_from_body("gpt", record.raw_body, 0), TestCase(input="1\n", output="1\n")
    )
    assert again == record.parse


def test_three_format_failures_await_the_authors(providers, repo, capsys):
    providers["gpt"].default = bad()
    assert run() == cli.EXIT_MANUAL
    err = capsys.readouterr().err
    assert (
        "manual: 1_A black_box: 3 attempts failed by format; close it with: docker compose run "
        "--rm app python -m ai_clients close --model gpt --problem 1_A --scenario black_box "
        '--reason "<reason>"'
    ) in err
    assert providers["gpt"].calls_of("1_A", "black_box") == 3
    assert store.read_attempt(repo, "gpt", "1_A", "black_box", 3).parse.failure.value == "not_json"


def test_only_the_context_changes_between_scenarios_and_models_get_the_same_prompt(providers):
    cli.main(["generate", "--model", "gpt", "--problem", "1_A", "--confirm-spend", "10"])
    cli.main(["generate", "--model", "gemini", "--problem", "1_A", "--confirm-spend", "10"])
    gpt = {s: body["input"] for _, s, body in providers["gpt"].requests}
    gem = {
        s: body["contents"][0]["parts"][0]["text"] for _, s, body in providers["gemini"].requests
    }
    assert gpt == gem
    head = gpt["black_box"].split("<context_data>")[0]
    tail = gpt["black_box"].split("</context_data>")[1]
    for prompt in gpt.values():
        assert prompt.startswith(head) and prompt.endswith(tail)
    assert len(set(gpt.values())) == 3


# ---------------------------------------------------------------------------- infrastructure


def test_an_outage_repeats_the_same_call_without_consuming_an_attempt(providers, repo, clock):
    table = providers["gpt"].table
    table[("1_A", "black_box", 1)] = unavailable()
    table[("1_A", "black_box", 2)] = unavailable(retry_after=90)
    table[("1_A", "black_box", 3)] = answer("gpt")
    assert run() == cli.EXIT_OK
    assert clock.sleeps == [5, 90]  # the API asked for more than the 10 s of the backoff
    assert store.read_attempt(repo, "gpt", "1_A", "black_box", 1).parse.ok
    assert store.read_attempt(repo, "gpt", "1_A", "black_box", 2) is None


def test_the_retry_ceiling_stops_with_code_3_and_records_nothing(
    providers, repo, monkeypatch, capsys
):
    monkeypatch.setenv(config.ENV_MAX_INFRA_RETRIES["gpt"], "2")
    providers["gpt"].default = unavailable()
    assert run() == cli.EXIT_INFRA
    assert "gpt unavailable after 2 consecutive retries" in capsys.readouterr().err
    assert store.read_attempt(repo, "gpt", "1_A", "black_box", 1) is None


def test_an_error_that_does_not_go_away_stops_at_once(providers, repo, capsys):
    providers["gpt"].default = ProviderFatal("gpt: the API key in OPENAI_API_KEY was refused")
    assert run() == cli.EXIT_INFRA
    assert "OPENAI_API_KEY was refused" in capsys.readouterr().err
    assert providers["gpt"].calls_of("1_A", "black_box") == 1


# ------------------------------------------------------------------------------------ barrier


@pytest.mark.parametrize("model", config.MODELS)
@pytest.mark.parametrize("reasoning", [0, None])
def test_an_answer_without_reasoning_is_barred(providers, repo, capsys, model, reasoning):
    providers[model].default = answer(model, reasoning=reasoning)
    assert run(model=model) == cli.EXIT_NO_REASONING
    captured = capsys.readouterr()
    assert "barred: 1_A black_box" in captured.out
    barred = store.read_barred(repo, model)
    assert len(barred) == 1 and barred[0].cost_usd > 0
    assert store.combination_state(repo, model, "1_A", "black_box").kind == "pending"
    assert providers[model].calls_of("1_A", "black_box") == 1  # nothing new was sent
    assert "spent US$" in captured.out and barred[0].cost_usd > 0


def test_nothing_new_is_sent_after_a_barred_answer(providers, repo, monkeypatch):
    # One call at a time: with more, the calls already in flight finish (test_concurrency.py).
    monkeypatch.setenv(config.ENV_MAX_CONCURRENCY["gpt"], "1")
    providers["gpt"].table[("1_A", "black_box", 1)] = answer("gpt", reasoning=0)
    code = cli.main(["generate", "--model", "gpt", "--problem", "1_A", "--confirm-spend", "10"])
    assert code == cli.EXIT_NO_REASONING
    assert [(p, s) for p, s, _ in providers["gpt"].requests] == [("1_A", "black_box")]


# -------------------------------------------------------------------------------- the command


def test_the_key_of_the_other_model_is_not_needed(providers, monkeypatch):
    monkeypatch.delenv(config.ENV_API_KEY["gemini"])
    assert run() == cli.EXIT_OK


def test_a_missing_key_or_a_bad_option_is_a_usage_error(providers, monkeypatch, capsys):
    monkeypatch.setenv(config.ENV_MAX_CONCURRENCY["gpt"], "zero")
    assert run() == cli.EXIT_USAGE
    monkeypatch.delenv(config.ENV_MAX_CONCURRENCY["gpt"])
    monkeypatch.delenv(config.ENV_API_KEY["gpt"])
    assert run() == cli.EXIT_USAGE
    assert "OPENAI_API_KEY is not set" in capsys.readouterr().err


def test_a_second_run_needs_resume_and_resume_needs_a_run(providers, capsys):
    assert cli.main(["generate", "--model", "gpt", *ONE, "--resume", "--confirm-spend", "1"]) == 2
    assert run() == cli.EXIT_OK
    assert run() == cli.EXIT_USAGE
    assert "use --resume" in capsys.readouterr().err


def test_a_changed_dataset_is_refused_before_any_call(providers, repo):
    statement = repo / "data" / "dataset" / "problems" / "1_A" / "enunciado.md"
    statement.write_text(statement.read_text() + "changed\n")
    assert run() == cli.EXIT_DATA_FAILURE
    assert providers["gpt"].requests == []


def test_the_suite_json_is_what_the_attempts_give(providers, repo):
    providers["gpt"].table[("1_A", "black_box", 1)] = bad()
    providers["gpt"].table[("1_A", "black_box", 2)] = answer(
        "gpt", text=answer_json((("2\n", "2\n"), ("3\n", "3\n")))
    )
    assert run() == cli.EXIT_OK
    suite = json.loads(
        (store.combination_dir(repo, "gpt", "1_A", "black_box") / "suite.json").read_text()
    )
    assert suite["accepted_attempt"] == 2 and suite["suite_size"] == 2
    assert [a["failure"] for a in suite["attempts"]] == ["not_json", None]
