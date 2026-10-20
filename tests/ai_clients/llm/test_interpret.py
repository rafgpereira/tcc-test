"""Reading an answer (research R6): the order of the checks, the 7 failures, the rules of FR-013."""

import json

import pytest

from ai_clients.llm.interpret import interpret, needs_barrier
from ai_clients.llm.providers import answer_from_body
from ai_clients.llm.schemas import FormatFailure
from dataset.schemas.testes import TestCase
from tests.ai_clients.llm.fakes import answer, answer_json, gemini_body, openai_body

EXAMPLE = TestCase(input="1\n", output="1\n")


def gpt(**kwargs):
    return answer_from_body("gpt", openai_body(**kwargs), 1.0)


def gem(**kwargs):
    return answer_from_body("gemini", gemini_body(**kwargs), 1.0)


def failure(answer):
    result = interpret(answer, EXAMPLE)
    assert not result.ok, result
    return result.failure.value, result.detail


def parsed(answer):
    result = interpret(answer, EXAMPLE)
    assert result.ok, result
    return result


def with_tests(*tests, analysis="ok"):
    return gpt(text=answer_json(tests, analysis))


def test_a_well_formed_answer():
    result = parsed(with_tests(("2\n", "2\n"), ("3", "3")))
    assert [(t.input, t.output) for t in result.tests] == [("2\n", "2\n"), ("3\n", "3\n")]
    assert result.edge_cases_analysis == "ok"


@pytest.mark.parametrize("reasoning", [0, None])
def test_the_barrier_comes_first(reasoning):
    assert needs_barrier(gpt(reasoning=reasoning))
    assert needs_barrier(gem(thoughts=reasoning))
    assert not needs_barrier(gpt(reasoning=1))


@pytest.mark.parametrize(
    "answer, expected",
    [
        (lambda: gpt(status="incomplete", reason="max_output_tokens"), "truncated"),
        (lambda: gem(finish="MAX_TOKENS"), "truncated"),
        (lambda: gpt(refusal="no"), "refusal"),
        (lambda: gpt(status="incomplete", reason="content_filter"), "safety_block"),
        (lambda: gem(block_reason="OTHER"), "safety_block"),
        (lambda: gem(finish="SAFETY", blocked=("HARM_CATEGORY_HARASSMENT",)), "safety_block"),
        (lambda: gpt(text=""), "empty_response"),
        (lambda: gem(text="", with_thought_part=True), "empty_response"),
        (lambda: gpt(text="not { json"), "not_json"),
        (lambda: gpt(text=json.dumps({"tests": []})), "schema_violation"),
        (
            lambda: gpt(text=json.dumps({"edge_cases_analysis": "x", "tests": [], "n": 1})),
            "schema_violation",
        ),
        (lambda: gpt(text=answer_json((), "  ")), "schema_violation"),
        (
            lambda: gpt(
                text=answer_json(()),
            ),
            "no_usable_test",
        ),
        (lambda: with_tests(("", "1"), ("1 2 ... 9", "3")), "no_usable_test"),
    ],
)
def test_each_failure(answer, expected):
    assert failure(answer())[0] == expected


def test_the_categories_of_a_gemini_safety_block_are_in_the_detail():
    detail = failure(gem(finish="SAFETY", blocked=("HARM_CATEGORY_HARASSMENT",)))[1]
    assert "HARM_CATEGORY_HARASSMENT" in detail


def test_a_cut_answer_is_truncated_even_if_its_text_would_parse():
    assert failure(gpt(status="incomplete", reason="max_output_tokens"))[0] == "truncated"


def test_fences_newlines_empty_and_abbreviated_tests():
    result = parsed(
        with_tests(
            ("```\n4\n```", "```text\n4\n```"),
            ("5\n\n\n", "5"),
            ("", "6\n"),
            ("1 1 … 1", "3\n"),
            ("7\n", "1 2 ... 9\n"),
        )
    )
    assert [(t.input, t.output) for t in result.tests] == [("4\n", "4\n"), ("5\n", "5\n")]
    assert (result.markdown_fences_removed, result.empty_tests, result.abbreviated_tests) == (
        2,
        1,
        2,
    )


def test_repeated_inputs_keep_the_first_and_count_conflicts():
    result = parsed(with_tests(("2\n", "2\n"), ("2\n", "2\n"), ("2\n", "9\n")))
    assert [(t.input, t.output) for t in result.tests] == [("2\n", "2\n")]
    assert (result.duplicate_inputs, result.conflicting_outputs) == (2, 1)


def test_a_copy_of_the_example_is_kept_and_counted():
    result = parsed(with_tests(("1", "1"), ("2\n", "2\n")))
    assert len(result.tests) == 2 and result.example_copies == 1


@pytest.mark.parametrize(
    "text",
    [
        "null",
        "[]",
        '"text"',
        "123",
        '{"edge_cases_analysis": 1, "tests": "x"}',
        '{"edge_cases_analysis": "x", "tests": [null, 3, {"input": 1}]}',
        '{"edge_cases_analysis": "x", "tests": [{"input": "\\u0000", "output": "\\ud800"}]}',
        "{" * 5000,
    ],
)
def test_the_interpretation_never_raises(text):
    result = interpret(gpt(text=text), EXAMPLE)
    assert result.ok in (True, False)


def test_a_text_that_is_not_utf8_is_a_schema_violation_that_can_be_recorded():
    raw = '{"edge_cases_analysis": "x", "tests": [{"input": "1\\n", "output": "\\ud800"}]}'
    result = interpret(gpt(text=raw), EXAMPLE)
    assert (result.failure.value, result.detail) == (
        "schema_violation",
        "a text is not valid UTF-8",
    )
    result.model_dump_json().encode("utf-8")  # what the attempt file needs


def test_the_interpretation_is_deterministic():
    raw = with_tests(("2\n", "2\n"), ("2\n", "3\n"))
    assert interpret(raw, EXAMPLE) == interpret(raw, EXAMPLE)


# ----------------------------------------------------------------------- Claude (specs/008)


@pytest.mark.parametrize("stop", ["max_tokens", "model_context_window_exceeded"])
def test_a_claude_answer_cut_short_is_truncated(stop):
    parse = interpret(answer("claude", '{"edge', stop_reason=stop), EXAMPLE)
    assert parse.failure is FormatFailure.TRUNCATED and stop in parse.detail


def test_a_claude_refusal_is_a_refusal():
    parse = interpret(answer("claude", "No.", stop_reason="refusal", category="bio"), EXAMPLE)
    assert parse.failure is FormatFailure.REFUSAL


def test_a_normal_claude_answer_is_parsed():
    assert interpret(answer("claude"), EXAMPLE).ok
