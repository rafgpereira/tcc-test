"""The versioned JSON contracts of the SLM suites (data-model.md, sections 2 and 3)."""

import pytest
from pydantic import ValidationError

from ai_clients.schemas.execution import ExecutionRecord
from ai_clients.schemas.generation import GenerationRecord
from ai_clients.schemas.run import RunConfig
from ai_clients.schemas.suite import SlmSuite

DIGEST = "sha256:" + "a" * 64
HEX = "b" * 64


def ollama_meta():
    return dict(
        model="qwen2.5-coder:7b",
        created_at="2026-10-01T12:00:00.000Z",
        done_reason="stop",
        prompt_eval_count=1000,
        eval_count=500,
        total_duration_ns=1,
        load_duration_ns=1,
        prompt_eval_duration_ns=1,
        eval_duration_ns=1,
    )


def parsed(**overrides):
    base = dict(
        ok=True,
        edge_cases_analysis="n = 1 is the smallest case.",
        inputs=["1\n", "5\n1 2 3 4 5\n"],
        reference_py="print(1)\n",
        extraneous_chars=0,
        duplicate_inputs=0,
    )
    return base | overrides


def generation(**overrides):
    base = dict(
        schema_version=1,
        problem_id="1_A",
        scenario="black_box",
        attempt=1,
        seed=43,
        model_digest=DIGEST,
        prompt_sha256=HEX,
        raw_response="<edge_cases_analysis>…",
        ollama=ollama_meta(),
        hardware_label="RTX 3060 12GB",
        requested_at="2026-10-01T12:00:00Z",
        parse=parsed(),
    )
    return base | overrides


def kept(index, output="1\n"):
    return dict(
        index=index,
        kept=True,
        output=output,
        discard=None,
        verdict=None,
        cpu_time_s=0.01,
        peak_rss_bytes=1,
        stderr_tail="",
    )


def dropped(index, discard="timeout", verdict="TLE"):
    return dict(
        index=index,
        kept=False,
        output=None,
        discard=discard,
        verdict=verdict,
        cpu_time_s=10.0,
        peak_rss_bytes=1,
        stderr_tail="",
    )


def execution(**overrides):
    base = dict(
        schema_version=1,
        problem_id="1_A",
        scenario="black_box",
        attempt=1,
        limits=dict(
            time_limit_seconds=10.0,
            memory_limit_bytes=1_073_741_824,
            problem_time_limit_seconds=1.0,
            problem_memory_limit_bytes=268_435_456,
        ),
        interpreter="/opt/python/bin/python3.11 (3.11.16)",
        public_tests=dict(total=2, passed=2, failed_index=None, failed_verdict=None),
        inputs=[kept(0), dropped(1)],
        outcome="accepted",
    )
    return base | overrides


def summary(attempt, failure=None, detail="x"):
    return dict(
        attempt=attempt,
        seed=42 + attempt,
        hardware_label="RTX 3060 12GB",
        failure=failure,
        detail=detail,
    )


def accepted_suite(**overrides):
    base = dict(
        schema_version=1,
        problem_id="1_A",
        scenario="hybrid",
        model="qwen2.5-coder:7b",
        model_digest=DIGEST,
        status="accepted",
        attempts=[summary(1, "public_test_failed"), summary(2)],
        accepted_attempt=2,
        tests=[{"input": "1\n", "output": "1\n"}],
        suite_size=1,
        discarded_inputs=[{"index": 1, "discard": "timeout", "verdict": "TLE"}],
        duplicate_inputs=0,
    )
    return base | overrides


def discarded_suite(**overrides):
    base = dict(
        schema_version=1,
        problem_id="1_A",
        scenario="white_box",
        model="qwen2.5-coder:7b",
        model_digest=DIGEST,
        status="discarded",
        attempts=[summary(n, "unparseable_response") for n in range(1, 7)],
        accepted_attempt=None,
        tests=[],
        suite_size=0,
        discarded_inputs=[],
        duplicate_inputs=0,
    )
    return base | overrides


def run_config(**overrides):
    base = dict(
        schema_version=1,
        model="qwen2.5-coder:7b",
        model_digest=DIGEST,
        model_quantization="Q4_K_M",
        ollama_version="0.12.0",
        options=dict(
            temperature=0.7,
            top_p=0.8,
            top_k=20,
            repeat_penalty=1.05,
            num_ctx=8192,
            num_predict=4096,
        ),
        seed_base=42,
        max_attempts=6,
        prompt_template_sha256=HEX,
        dataset_manifest_sha256=HEX,
        py_time_factor=10,
        py_memory_factor=4,
        created_at="2026-10-01T12:00:00Z",
    )
    return base | overrides


VALID = {
    "generation": (GenerationRecord, generation),
    "execution": (ExecutionRecord, execution),
    "accepted suite": (SlmSuite, accepted_suite),
    "discarded suite": (SlmSuite, discarded_suite),
    "run": (RunConfig, run_config),
}


# ------------------------------------------------------------------------------ all the schemas


@pytest.mark.parametrize("name", VALID)
def test_the_valid_example_is_accepted(name):
    model, build = VALID[name]
    model.model_validate(build())


@pytest.mark.parametrize("name", VALID)
def test_an_unknown_field_is_an_error(name):
    model, build = VALID[name]
    with pytest.raises(ValidationError):
        model.model_validate(build(typo=1))


@pytest.mark.parametrize("name", VALID)
def test_only_schema_version_1_exists(name):
    model, build = VALID[name]
    with pytest.raises(ValidationError):
        model.model_validate(build(schema_version=2))


# ---------------------------------------------------------------------------- GenerationRecord


@pytest.mark.parametrize("attempt", [0, 7])
def test_the_attempt_is_between_1_and_6(attempt):
    with pytest.raises(ValidationError):
        GenerationRecord.model_validate(generation(attempt=attempt, seed=42 + attempt))


def test_the_seed_must_be_seed_base_plus_attempt():
    GenerationRecord.model_validate(generation(attempt=3, seed=45))
    with pytest.raises(ValidationError):
        GenerationRecord.model_validate(generation(attempt=3, seed=43))


def test_the_model_digest_is_required_and_not_empty():
    with pytest.raises(ValidationError):
        GenerationRecord.model_validate(generation(model_digest=""))
    record = generation()
    del record["model_digest"]
    with pytest.raises(ValidationError):
        GenerationRecord.model_validate(record)


def test_an_unknown_scenario_is_an_error():
    with pytest.raises(ValidationError):
        GenerationRecord.model_validate(generation(scenario="grey_box"))


def test_an_unparseable_response_keeps_only_the_error():
    record = GenerationRecord.model_validate(
        generation(parse={"ok": False, "error": "missing_block:reference_py"})
    )
    assert record.parse.ok is False and record.parse.error == "missing_block:reference_py"
    with pytest.raises(ValidationError):  # a failure never carries inputs
        GenerationRecord.model_validate(
            generation(parse={"ok": False, "error": "wrong_order", "inputs": ["1\n"]})
        )


@pytest.mark.parametrize(
    "inputs",
    [
        [],  # at least one input
        [""],  # not empty
        [" \n"],  # not only whitespace
        ["1"],  # ends with a newline
        ["1\n\n"],  # with exactly one
    ],
)
def test_parsed_inputs_are_non_empty_and_end_with_exactly_one_newline(inputs):
    with pytest.raises(ValidationError):
        GenerationRecord.model_validate(generation(parse=parsed(inputs=inputs)))


@pytest.mark.parametrize("field_name", ["reference_py", "edge_cases_analysis"])
def test_parsed_blocks_are_not_empty(field_name):
    with pytest.raises(ValidationError):
        GenerationRecord.model_validate(generation(parse=parsed(**{field_name: "  \n"})))


@pytest.mark.parametrize("field_name", ["extraneous_chars", "duplicate_inputs"])
def test_parse_counters_are_not_negative(field_name):
    with pytest.raises(ValidationError):
        GenerationRecord.model_validate(generation(parse=parsed(**{field_name: -1})))


# ----------------------------------------------------------------------------- ExecutionRecord


def test_a_public_test_failure_runs_no_input():
    failed = dict(total=2, passed=0, failed_index=0, failed_verdict="WA")
    ExecutionRecord.model_validate(
        execution(public_tests=failed, inputs=[], outcome="public_test_failed")
    )
    with pytest.raises(ValidationError):
        ExecutionRecord.model_validate(
            execution(public_tests=failed, inputs=[kept(0)], outcome="public_test_failed")
        )


def test_public_test_failed_if_and_only_if_there_is_a_failed_index():
    with pytest.raises(ValidationError):  # outcome says failed, but no public test failed
        ExecutionRecord.model_validate(execution(inputs=[], outcome="public_test_failed"))
    failed = dict(total=2, passed=0, failed_index=0, failed_verdict="WA")
    with pytest.raises(ValidationError):  # a public test failed, but outcome says accepted
        ExecutionRecord.model_validate(execution(public_tests=failed, inputs=[]))


def test_all_inputs_failed_if_and_only_if_nothing_was_kept():
    ExecutionRecord.model_validate(
        execution(
            inputs=[dropped(0), dropped(1, "runtime_error", "RE")], outcome="all_inputs_failed"
        )
    )
    with pytest.raises(ValidationError):  # nothing kept can never be accepted (no empty suite)
        ExecutionRecord.model_validate(execution(inputs=[dropped(0)], outcome="accepted"))
    with pytest.raises(ValidationError):  # something kept is not a failure of all inputs
        ExecutionRecord.model_validate(execution(outcome="all_inputs_failed"))


def test_a_kept_input_has_an_output_and_no_discard():
    with pytest.raises(ValidationError):
        ExecutionRecord.model_validate(execution(inputs=[kept(0) | {"output": None}]))
    with pytest.raises(ValidationError):
        ExecutionRecord.model_validate(execution(inputs=[kept(0) | {"discard": "timeout"}]))


def test_a_discarded_input_has_a_reason_and_no_output():
    with pytest.raises(ValidationError):
        ExecutionRecord.model_validate(execution(inputs=[kept(0), dropped(1) | {"discard": None}]))
    with pytest.raises(ValidationError):
        ExecutionRecord.model_validate(execution(inputs=[kept(0), dropped(1) | {"output": "1\n"}]))


def test_inputs_are_listed_in_the_order_of_the_generation():
    with pytest.raises(ValidationError):
        ExecutionRecord.model_validate(execution(inputs=[kept(1), dropped(0)]))


# -------------------------------------------------------------------------------------- SlmSuite


def test_an_accepted_suite_names_its_attempt():
    with pytest.raises(ValidationError):
        SlmSuite.model_validate(accepted_suite(accepted_attempt=None))
    with pytest.raises(ValidationError):  # the accepted attempt is the last one
        SlmSuite.model_validate(accepted_suite(accepted_attempt=1))


def test_an_accepted_suite_is_never_empty():
    with pytest.raises(ValidationError):
        SlmSuite.model_validate(accepted_suite(tests=[], suite_size=0))


def test_the_suite_size_is_the_number_of_tests():
    with pytest.raises(ValidationError):
        SlmSuite.model_validate(accepted_suite(suite_size=2))


def test_only_the_last_attempt_of_an_accepted_suite_succeeded():
    with pytest.raises(ValidationError):  # an earlier attempt without a failure
        SlmSuite.model_validate(
            accepted_suite(attempts=[summary(1), summary(2)], accepted_attempt=2)
        )
    with pytest.raises(ValidationError):  # the last attempt with a failure
        SlmSuite.model_validate(
            accepted_suite(attempts=[summary(1, "public_test_failed")], accepted_attempt=1)
        )


def test_a_discarded_suite_has_exactly_six_failed_attempts():
    with pytest.raises(ValidationError):
        SlmSuite.model_validate(discarded_suite(attempts=discarded_suite()["attempts"][:5]))
    with pytest.raises(ValidationError):
        attempts = discarded_suite()["attempts"][:5] + [summary(6)]
        SlmSuite.model_validate(discarded_suite(attempts=attempts))


def test_a_discarded_suite_has_no_tests_and_no_accepted_attempt():
    with pytest.raises(ValidationError):
        SlmSuite.model_validate(
            discarded_suite(tests=[{"input": "1\n", "output": "1\n"}], suite_size=1)
        )
    with pytest.raises(ValidationError):
        SlmSuite.model_validate(discarded_suite(accepted_attempt=6))


def test_attempts_are_numbered_from_1_without_gaps_and_with_their_seed():
    with pytest.raises(ValidationError):
        SlmSuite.model_validate(
            accepted_suite(
                attempts=[summary(1, "public_test_failed"), summary(3)], accepted_attempt=3
            )
        )
    with pytest.raises(ValidationError):
        wrong_seed = summary(2) | {"seed": 43}
        SlmSuite.model_validate(
            accepted_suite(attempts=[summary(1, "public_test_failed"), wrong_seed])
        )


def test_the_tests_have_exactly_the_shape_of_the_dataset_test_case():
    with pytest.raises(ValidationError):
        SlmSuite.model_validate(accepted_suite(tests=[{"input": "1\n", "expected_output": "1\n"}]))
    with pytest.raises(ValidationError):
        SlmSuite.model_validate(
            accepted_suite(tests=[{"input": "1\n", "output": "1\n", "note": "x"}])
        )
