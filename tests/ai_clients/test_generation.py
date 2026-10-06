"""The generation phase: one stateless call per attempt, parse failures chain, outages wait."""

import pytest

from ai_clients import config, generation, store
from ai_clients.errors import InfrastructureError
from ai_clients.ollama import ModelRepetition, OllamaConfigError, OllamaUnavailable
from ai_clients.prompt import load_template
from tests.ai_clients.fakes import (
    FakeClock,
    FakeSLMClient,
    completion,
    predicted_response,
    well_formed_response,
)

NOW = "2026-10-01T12:00:00Z"
GOOD = completion(well_formed_response(["1\n", "2\n"]))
BAD = completion("I cannot help with that.")
PREDICTED = completion(predicted_response([("3\n", "3\n"), ("4\n", "4\n")]))


@pytest.fixture()
def template():
    return load_template()


def make_client(table):
    return FakeSLMClient(table, problem_ids=["1_A", "2_B"])


def run_config(client, template, root):
    return generation.current_run_config(
        client, template, root, now=lambda: NOW, clock=FakeClock(), max_infra_retries=3, echo=print
    )


def generate(root, client, template, combos, *, clock=None, labels=None, retries=3, limit=None):
    labels = iter(labels) if labels else None
    lines = []
    result = generation.generate(
        root,
        combos,
        client,
        template=template,
        run=run_config(client, template, root),
        hardware_label=(lambda: next(labels)) if labels else (lambda: "RTX 3060 12GB"),
        max_infra_retries=retries,
        clock=clock or FakeClock(),
        echo=lines.append,
        limit=limit,
        now=lambda: NOW,
    )
    return result, lines


def files(root, pid="1_A", scenario="black_box"):
    folder = store.combination_dir(root, pid, scenario)
    return sorted(p.name for p in folder.iterdir()) if folder.is_dir() else []


def test_the_run_config_identifies_model_options_template_and_dataset(repo, template):
    client = make_client({})
    run = run_config(client, template, repo)
    assert run.model == config.MODEL and run.model_digest == client.info.digest
    assert run.model_quantization == "Q4_K_M" and run.ollama_version == "0.12.0"
    assert run.options.model_dump() == {
        "temperature": 0.7,
        "top_p": 0.8,
        "top_k": 20,
        "repeat_penalty": 1.05,
        "num_ctx": 8192,
        "num_predict": config.NUM_PREDICT,
    }
    assert (
        run.seed_base,
        run.strict_attempts,
        run.solution_attempts,
        run.predict_attempts,
        run.max_attempts,
        run.py_time_factor,
        run.py_memory_factor,
    ) == (42, 8, 20, 3, 23, 10, 4)
    assert run.prompt_template_sha256 == template.sha256
    assert run.predict_template_sha256 == load_template(config.PREDICT_TEMPLATE_PATH).sha256
    assert len(run.dataset_manifest_sha256) == 64 and run.created_at == NOW


def test_a_parsed_answer_is_recorded_and_nothing_runs(repo, template):
    client = make_client({("1_A", "black_box", 43): GOOD})
    result, lines = generate(repo, client, template, [("1_A", "black_box")])
    assert files(repo) == ["attempt_1.generation.json"]
    record = store.read_generation(repo, "1_A", "black_box", 1)
    assert record.seed == 43 and record.parse.ok and record.parse.inputs == ["1\n", "2\n"]
    assert record.raw_response == GOOD.content and record.model_digest == client.info.digest
    assert record.hardware_label == "RTX 3060 12GB" and record.requested_at == NOW
    assert record.ollama.prompt_eval_count == 1000 and record.ollama.done_reason == "stop"
    assert (result.calls, result.parsed, result.unparseable, result.pending_execution) == (
        1,
        1,
        0,
        1,
    )
    assert lines == [
        "1_A black_box attempt 1 seed 43: parsed (2 inputs) — 1000+500 tokens, stop, 2.0 s"
    ]


def test_an_unparseable_answer_chains_the_next_seed_at_once(repo, template):
    client = make_client({("1_A", "black_box", 43): BAD, ("1_A", "black_box", 44): GOOD})
    result, lines = generate(repo, client, template, [("1_A", "black_box")])
    assert files(repo) == ["attempt_1.generation.json", "attempt_2.generation.json"]
    first = store.read_generation(repo, "1_A", "black_box", 1)
    assert first.parse.ok is False and first.parse.error == "missing_block:edge_cases_analysis"
    assert [r["options"]["seed"] for r in client.requests] == [43, 44]
    assert (result.calls, result.parsed, result.unparseable) == (2, 1, 1)
    assert "unparseable (missing_block:edge_cases_analysis)" in lines[0]


def bad_solutions(extra=None):
    """Every solution attempt unparseable, plus ``extra``."""
    table = {("1_A", "black_box", 42 + n): BAD for n in range(1, config.SOLUTION_ATTEMPTS + 1)}
    return make_client(table | (extra or {}))


def test_twenty_unparseable_answers_go_to_a_prediction_that_is_the_suite(repo, template):
    client = bad_solutions({("1_A", "black_box", 63): PREDICTED})
    result, lines = generate(repo, client, template, [("1_A", "black_box")])
    assert files(repo) == sorted(
        [f"attempt_{n}.generation.json" for n in range(1, 22)] + ["suite.json"]
    )
    suite = store.read_suite(repo, "1_A", "black_box")
    assert suite.status == "accepted_predicted" and suite.accepted_attempt == 21
    assert [t.model_dump() for t in suite.tests] == [
        {"input": "3\n", "output": "3\n"},
        {"input": "4\n", "output": "4\n"},
    ]
    assert [a.kind for a in suite.attempts] == ["solution"] * 20 + ["prediction"]
    assert [a.seed for a in suite.attempts] == list(range(43, 64))
    assert suite.attempts[-1].detail == "2 tests predicted"
    # the prediction is asked with the second template, the solutions with the main one
    prompts = [r["prompt"] for r in client.requests]
    assert all("<reference_py>" in prompt for prompt in prompts[:20])
    assert "<tests>" in prompts[20] and "<reference_py>" not in prompts[20]
    assert result.suites["accepted_predicted"] == 1 and result.pending_execution == 0
    assert result.awaiting_manual == []
    assert lines[-2].startswith("1_A black_box attempt 21 seed 63: parsed (2 tests)")
    assert lines[-1] == "1_A black_box: suite recorded (accepted_predicted)"


def test_an_unparseable_prediction_chains_the_next_seed(repo, template):
    client = bad_solutions({("1_A", "black_box", 63): BAD, ("1_A", "black_box", 64): PREDICTED})
    result, _ = generate(repo, client, template, [("1_A", "black_box")])
    suite = store.read_suite(repo, "1_A", "black_box")
    assert suite.status == "accepted_predicted" and suite.accepted_attempt == 22
    assert suite.attempts[20].detail == "missing_block:edge_cases_analysis"
    assert result.calls == 22


def test_three_unparseable_predictions_await_manual_handling(repo, template):
    client = make_client(
        {("1_A", "black_box", 42 + n): BAD for n in range(1, config.MAX_ATTEMPTS + 1)}
    )
    result, lines = generate(repo, client, template, [("1_A", "black_box")])
    assert files(repo) == sorted(f"attempt_{n}.generation.json" for n in range(1, 24))
    state = store.combination_state(repo, "1_A", "black_box")
    assert state.kind == "awaiting_manual"
    assert result.awaiting_manual == [("1_A", "black_box")]
    assert sum(result.suites.values()) == 0 and result.calls == config.MAX_ATTEMPTS
    assert lines[-1] == "1_A black_box: awaiting manual handling"
    # a second generate calls nothing for it, and still reports it
    client = make_client({})
    result, _ = generate(repo, client, template, [("1_A", "black_box")])
    assert client.requests == [] and result.awaiting_manual == [("1_A", "black_box")]


REPEAT = ModelRepetition('HTTP 500 from /api/chat: {"error":"token repeat limit reached"}')


def test_the_token_repeat_limit_fails_the_attempt_and_goes_to_the_next_seed(repo, template):
    client = make_client({("1_A", "black_box", 43): REPEAT, ("1_A", "black_box", 44): GOOD})
    clock = FakeClock()
    result, lines = generate(repo, client, template, [("1_A", "black_box")], clock=clock)
    assert [r["options"]["seed"] for r in client.requests] == [43, 44]  # never the same seed again
    assert clock.sleeps == []
    first = store.read_generation(repo, "1_A", "black_box", 1)
    assert first.model_failure.reason == "repetition" and "token repeat limit" in (
        first.model_failure.detail
    )
    assert first.ollama is None and first.raw_response == ""
    assert first.parse.ok is False and first.parse.error == "repetition"
    assert (result.calls, result.parsed, result.unparseable, result.repetition) == (2, 1, 0, 1)
    assert lines[0].startswith("1_A black_box attempt 1 seed 43: model failure (repetition)")


def test_23_repetitions_await_manual_handling_with_that_reason(repo, template):
    client = make_client(
        {("1_A", "black_box", 42 + n): REPEAT for n in range(1, config.MAX_ATTEMPTS + 1)}
    )
    result, _ = generate(repo, client, template, [("1_A", "black_box")])
    assert store.combination_state(repo, "1_A", "black_box").kind == "awaiting_manual"
    assert result.repetition == config.MAX_ATTEMPTS
    assert result.awaiting_manual == [("1_A", "black_box")]


def test_an_outage_retries_the_same_call_without_consuming_an_attempt(repo, template):
    down = OllamaUnavailable("connection refused")
    client = make_client({("1_A", "black_box", 43): [down, down, down, GOOD]})
    clock = FakeClock()
    result, lines = generate(repo, client, template, [("1_A", "black_box")], clock=clock)
    assert files(repo) == ["attempt_1.generation.json"]
    assert clock.sleeps == [5, 10, 20]
    assert [r["options"]["seed"] for r in client.requests] == [43] * 4
    assert result.calls == 1
    assert lines[0] == (
        "ollama unavailable (connection refused); retrying the same call (seed 43) in 5 s "
        "(retry 1 of 3)"
    )


def test_the_wait_doubles_up_to_60_seconds(repo, template):
    down = OllamaUnavailable("timed out")
    client = make_client({("1_A", "black_box", 43): [down] * 7 + [GOOD]})
    clock = FakeClock()
    generate(repo, client, template, [("1_A", "black_box")], clock=clock, retries=10)
    assert clock.sleeps == [5, 10, 20, 40, 60, 60, 60]


def test_reaching_the_retry_ceiling_stops_without_recording_or_consuming(repo, template):
    down = OllamaUnavailable("connection refused")
    client = make_client({("1_A", "black_box", 43): down})
    with pytest.raises(InfrastructureError) as caught:
        generate(repo, client, template, [("1_A", "black_box")], retries=3)
    assert len(client.requests) == 4  # the call and 3 retries
    assert str(caught.value) == (
        "ollama unavailable after 3 consecutive retries (connection refused); nothing was recorded "
        "for 1_A black_box attempt 1; run generate --resume when the service is back"
    )
    assert files(repo) == []
    # A new run makes the same call, with the same seed.
    client = make_client({("1_A", "black_box", 43): GOOD})
    generate(repo, client, template, [("1_A", "black_box")])
    assert store.read_generation(repo, "1_A", "black_box", 1).seed == 43


def test_the_retry_counter_restarts_after_an_answer(repo, template):
    down = OllamaUnavailable("connection refused")
    client = make_client(
        {
            ("1_A", "black_box", 43): [down, down, down, BAD],
            ("1_A", "black_box", 44): [down, down, down, GOOD],
        }
    )
    generate(repo, client, template, [("1_A", "black_box")], retries=3)
    assert files(repo) == ["attempt_1.generation.json", "attempt_2.generation.json"]


def test_a_configuration_error_records_nothing(repo, template):
    client = make_client({("1_A", "black_box", 43): OllamaConfigError("model not found")})
    with pytest.raises(OllamaConfigError):
        generate(repo, client, template, [("1_A", "black_box")])
    assert files(repo) == []


def test_a_possibly_truncated_prompt_stops_the_run(repo, template):
    client = make_client(
        {("1_A", "black_box", 43): completion(GOOD.content, prompt_eval_count=4097)}
    )
    with pytest.raises(OllamaConfigError, match="num_ctx"):
        generate(repo, client, template, [("1_A", "black_box")])
    assert files(repo) == []


def test_every_call_is_one_new_request_with_the_options_of_the_design(repo, template):
    client = make_client({(pid, s, 43): GOOD for pid in ("1_A", "2_B") for s in config.SCENARIOS})
    combos = [(pid, s) for pid in ("1_A", "2_B") for s in config.SCENARIOS]
    generate(repo, client, template, combos)
    assert [r["key"] for r in client.requests] == [(pid, s, 43) for pid, s in combos]
    for request in client.requests:
        assert request["model"] == "qwen2.5-coder:7b"
        assert request["options"] == {
            "temperature": 0.7,
            "top_p": 0.8,
            "top_k": 20,
            "repeat_penalty": 1.05,
            "num_ctx": 8192,
            "num_predict": config.NUM_PREDICT,
            "seed": 43,
        }
    prompts = [r["prompt"] for r in client.requests]
    assert len(set(prompts)) == len(prompts)  # nothing of one call leaks into another


def test_the_hardware_label_is_read_at_each_call(repo, template):
    client = make_client({("1_A", "black_box", 43): BAD, ("1_A", "black_box", 44): GOOD})
    generate(repo, client, template, [("1_A", "black_box")], labels=["machine A", "machine B"])
    labels = [store.read_generation(repo, "1_A", "black_box", n).hardware_label for n in (1, 2)]
    assert labels == ["machine A", "machine B"]


def test_terminal_and_pending_execution_combinations_are_not_called(repo, template):
    client = make_client({("1_A", "black_box", 43): GOOD})
    generate(repo, client, template, [("1_A", "black_box")])  # now pending execution
    client = make_client(
        {("1_A", "white_box", 42 + n): BAD for n in range(1, config.MAX_ATTEMPTS + 1)}
    )
    generate(repo, client, template, [("1_A", "white_box")])  # now awaiting manual handling
    client = make_client({})
    result, _ = generate(repo, client, template, [("1_A", "black_box"), ("1_A", "white_box")])
    assert client.requests == [] and result.calls == 0 and result.pending_execution == 1


def test_limit_counts_combinations_not_calls(repo, template):
    client = make_client(
        {
            ("1_A", "black_box", 43): BAD,
            ("1_A", "black_box", 44): GOOD,
            ("1_A", "white_box", 43): GOOD,
        }
    )
    combos = [("1_A", s) for s in config.SCENARIOS]
    result, _ = generate(repo, client, template, combos, limit=2)
    assert result.calls == 3
    assert files(repo, scenario="hybrid") == []


def test_an_unparseable_8th_answer_ends_the_attempts_with_a_fallback_among_the_8(repo, template):
    from ai_clients import execution
    from tests.ai_clients.fakes import FakePythonRunner, record_generation, run_result, start_run

    run = start_run(repo)
    wrong = FakePythonRunner(default=lambda code, stdin: run_result(b"0\n"))  # WA, inputs kept
    for n in range(1, config.STRICT_ATTEMPTS):
        record_generation(repo, attempt=n, code="print(0)\n")
        execution.execute(repo, [("1_A", "black_box")], run=run, runner=wrong, echo=print)
    client = make_client({("1_A", "black_box", 42 + config.STRICT_ATTEMPTS): BAD})
    result, lines = generate(repo, client, template, [("1_A", "black_box")])
    suite = store.read_suite(repo, "1_A", "black_box")
    assert suite.status == "accepted_fallback" and suite.accepted_attempt == 1
    assert len(client.requests) == 1  # never a 9th call
    assert lines[-1] == "1_A black_box: suite recorded (accepted_fallback)"
    assert result.suites == {"accepted_fallback": 1}
