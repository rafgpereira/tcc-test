"""The schemas of the commercial models (data-model.md, sections 2 and 3)."""

import pytest
from pydantic import ValidationError

from ai_clients.llm import schemas
from ai_clients.llm.schemas import (
    BarredResponse,
    LlmAnswer,
    LlmAttempt,
    LlmRunConfig,
    LlmSuite,
    LlmTemplateChange,
    PriceRow,
)
from ai_clients.schemas.generation import GenerationRecord
from ai_clients.schemas.template_change import TemplateChange
from tests.ai_clients.llm import builders as b

ALL = [
    (LlmRunConfig, b.run_config),
    (LlmAttempt, b.attempt),
    (LlmSuite, b.llm_suite),
]


@pytest.mark.parametrize("schema, build", ALL)
def test_every_schema_forbids_unknown_fields(schema, build):
    schema.model_validate(build())
    with pytest.raises(ValidationError):
        schema.model_validate({**build(), "extra": 1})


# ----------------------------------------------------------------------------------- run.json


def test_run_config_only_version_1_and_3_attempts():
    with pytest.raises(ValidationError):
        LlmRunConfig.model_validate(b.run_config(schema_version=2))
    with pytest.raises(ValidationError):
        LlmRunConfig.model_validate(b.run_config(max_attempts=4))


@pytest.mark.parametrize(
    "key",
    [
        "temperature",
        "top_p",
        "top_k",
        "seed",
        "instructions",
        "systemInstruction",
        "safetySettings",
        "previous_response_id",
    ],
)
def test_run_config_refuses_every_forbidden_parameter_even_nested(key):
    params = b.run_config()["request_parameters"]
    with pytest.raises(ValidationError, match=key):
        LlmRunConfig.model_validate(b.run_config(request_parameters={**params, key: 1}))
    nested = {**params, "generationConfig": {key: 0.5}}
    with pytest.raises(ValidationError, match=key):
        LlmRunConfig.model_validate(b.run_config(request_parameters=nested))


def test_differences_compare_parameters_key_by_key_but_never_prices_nor_dates():
    recorded = LlmRunConfig.model_validate(b.run_config())
    params = {**recorded.request_parameters, "max_output_tokens": 999}
    current = LlmRunConfig.model_validate(
        b.run_config(
            request_parameters=params, price_table=b.run_config()["price_table"][:1], created_at="x"
        )
    )
    assert recorded.differences(current) == [("request_parameters.max_output_tokens", 32768, 999)]


# ------------------------------------------------------------------------------ an attempt


@pytest.mark.parametrize("n", [0, 4])
def test_an_attempt_is_numbered_1_to_3(n):
    with pytest.raises(ValidationError):
        LlmAttempt.model_validate(b.attempt(n))


def test_usage_is_never_negative():
    usage = {**b.attempt()["usage"], "output_tokens": -1}
    with pytest.raises(ValidationError):
        LlmAttempt.model_validate(b.attempt(usage=usage))


@pytest.mark.parametrize("reasoning", [0, None])
def test_an_attempt_without_reasoning_tokens_is_refused(reasoning):
    usage = {**b.attempt()["usage"], "reasoning_tokens": reasoning}
    with pytest.raises(ValidationError, match="BarredResponse"):
        LlmAttempt.model_validate(b.attempt(usage=usage))
    BarredResponse.model_validate(
        {**b.call_record(usage=usage), "reason": "no_reasoning_tokens", "barred_at": "t"}
    )


def test_a_barred_response_has_no_attempt_nor_parse_and_no_reasoning():
    record = {**b.call_record(), "reason": "no_reasoning_tokens", "barred_at": "t"}
    with pytest.raises(ValidationError, match="never barred"):
        BarredResponse.model_validate(record)
    with pytest.raises(ValidationError):
        BarredResponse.model_validate({**record, "attempt": 1})


@pytest.mark.parametrize(
    "tests, message",
    [
        ([], "at least 1"),
        ([("1", "1\n")], "exactly one newline"),
        ([("1\n", "1\n\n")], "exactly one newline"),
        ([(" \n", "1\n")], "empty"),
        ([("1\n", "1\n"), ("1\n", "2\n")], "twice"),
    ],
)
def test_a_parsed_answer_keeps_only_complete_and_distinct_tests(tests, message):
    with pytest.raises(ValidationError, match=message):
        LlmAttempt.model_validate(b.attempt(parse=b.parsed(tests=tests)))


def test_a_blank_analysis_is_refused():
    with pytest.raises(ValidationError, match="analysis"):
        LlmAttempt.model_validate(b.attempt(parse=b.parsed(edge_cases_analysis=" \n")))


@pytest.mark.parametrize("failure", [f.value for f in schemas.FormatFailure])
def test_the_seven_format_failures(failure):
    LlmAttempt.model_validate(b.attempt(parse=b.failed(failure)))


def test_an_unknown_failure_is_refused():
    with pytest.raises(ValidationError):
        LlmAttempt.model_validate(b.attempt(parse=b.failed("too_short")))


# --------------------------------------------------------------------------------- suite.json


def test_a_suite_has_the_top_level_keys_of_the_slm_suite():
    from ai_clients.schemas.suite import SlmSuite

    # barred_close only appears in a suite closed after answers without reasoning (omitted
    # otherwise); the common reader ignores it.
    assert set(LlmSuite.model_fields) - {"barred_close"} == set(SlmSuite.model_fields)


def test_accepted_phase_is_always_null_and_discarded_inputs_always_empty():
    with pytest.raises(ValidationError):
        LlmSuite.model_validate(b.llm_suite(accepted_phase=4))
    with pytest.raises(ValidationError):
        LlmSuite.model_validate(b.llm_suite(discarded_inputs=[{"index": 0}]))


def test_an_accepted_predicted_suite():
    suite = LlmSuite.model_validate(b.llm_suite())
    assert suite.accepted_attempt == 1 and suite.suite_size == 1
    with pytest.raises(ValidationError):
        LlmSuite.model_validate(b.llm_suite(suite_size=2))
    with pytest.raises(ValidationError):
        LlmSuite.model_validate(b.llm_suite(tests=[], suite_size=0))
    with pytest.raises(ValidationError):  # the last attempt failed
        LlmSuite.model_validate(b.llm_suite(attempts=[b.summary(1, failure="not_json")]))
    with pytest.raises(ValidationError):  # an earlier attempt succeeded
        LlmSuite.model_validate(
            b.llm_suite(attempts=[b.summary(1), b.summary(2)], accepted_attempt=2)
        )
    with pytest.raises(ValidationError):  # numbered with a gap
        LlmSuite.model_validate(
            b.llm_suite(
                attempts=[b.summary(1, failure="not_json"), b.summary(3)], accepted_attempt=3
            )
        )


def test_a_discarded_manual_suite_has_exactly_three_failed_attempts():
    LlmSuite.model_validate(b.llm_suite("discarded_manual"))
    two = b.llm_suite("discarded_manual")
    two["attempts"] = two["attempts"][:2]
    with pytest.raises(ValidationError):
        LlmSuite.model_validate(two)
    with pytest.raises(ValidationError):
        LlmSuite.model_validate(b.llm_suite("discarded_manual", manual_close=None))
    with pytest.raises(ValidationError):
        LlmSuite.model_validate(b.llm_suite("discarded_manual", model_digest="x"))


@pytest.mark.parametrize("status", ["accepted", "accepted_fallback"])
def test_a_commercial_model_never_has_the_statuses_of_an_executed_solution(status):
    with pytest.raises(ValidationError):
        LlmSuite.model_validate(b.llm_suite(status=status))


# ------------------------------------------------------------------- answer, prices, changes


def test_the_answer_is_exactly_the_two_fields():
    LlmAnswer.model_validate({"edge_cases_analysis": "x", "tests": [{"input": "1", "output": "1"}]})
    with pytest.raises(ValidationError):
        LlmAnswer.model_validate({"edge_cases_analysis": "x", "tests": [], "note": "y"})
    with pytest.raises(ValidationError):
        LlmAnswer.model_validate(
            {"edge_cases_analysis": "x", "tests": [{"input": "1", "output": "1", "why": "z"}]}
        )


def test_the_response_schema_puts_the_analysis_first_and_forbids_extra_fields():
    schema = schemas.response_schema()
    assert list(schema["properties"]) == ["edge_cases_analysis", "tests"]
    assert schema["required"] == ["edge_cases_analysis", "tests"]
    assert schema["additionalProperties"] is False
    assert schema["properties"]["tests"]["items"]["additionalProperties"] is False
    text = str(schema)
    assert "minItems" not in text and "minLength" not in text


def test_price_rows():
    rows = schemas.price_table()
    assert [(r.model_key, r.valid_from.isoformat()) for r in rows] == [
        ("gpt", "2026-10-15"),
        ("gemini", "2026-10-15"),
        ("gemini", "2027-01-01"),
        ("claude", "2026-10-20"),
    ]
    with pytest.raises(ValidationError):
        PriceRow.model_validate({**rows[0].model_dump(), "output_per_mtok": -1})


def change(template="llm") -> dict:
    return {
        "number": 1,
        "template": template,
        "from_sha256": b.SHA,
        "to_sha256": b.OTHER_SHA,
        "changed_at": "t",
        "reason": "fix",
        "superseded": [],
    }


def test_template_changes_of_the_two_modules_never_mix():
    LlmTemplateChange.model_validate(change())
    for kind in ("solution", "prediction"):
        with pytest.raises(ValidationError):
            LlmTemplateChange.model_validate(change(kind))
    with pytest.raises(ValidationError):
        TemplateChange.model_validate({**change(), "schema_version": 2})


def test_the_slm_generation_record_still_refuses_the_llm_template():
    from tests.ai_clients.test_schemas import generation

    with pytest.raises(ValidationError):
        GenerationRecord.model_validate(generation(template="llm"))
