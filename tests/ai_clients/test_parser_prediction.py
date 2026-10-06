"""Reading a prediction answer (attempts 21 to 23): two blocks, strict, never "fixing" it."""

import pytest

from ai_clients.parser import parse_prediction
from ai_clients.schemas.generation import PredictionParse, UnparsedResponse

ANALYSIS = "<edge_cases_analysis>\nn = 1 is the smallest case.\n</edge_cases_analysis>\n"
TEST_1 = "<test>\n<input>\n1\n</input>\n<output>\nYES\n</output>\n</test>\n"
TEST_2 = "<test>\n<input>\n5\n1 2 3 4 5\n</input>\n<output>\nNO\n</output>\n</test>\n"
TESTS = f"<tests>\n{TEST_1}{TEST_2}</tests>\n"
GOOD = ANALYSIS + TESTS


def ok(raw) -> PredictionParse:
    result = parse_prediction(raw)
    assert isinstance(result, PredictionParse), getattr(result, "error", result)
    return result


def error(raw) -> str:
    result = parse_prediction(raw)
    assert isinstance(result, UnparsedResponse), result
    return result.error


def block_of(*tests: str) -> str:
    return "<tests>\n" + "".join(tests) + "</tests>\n"


def test_a_well_formed_answer():
    result = ok(GOOD)
    assert result.edge_cases_analysis == "n = 1 is the smallest case.\n"
    assert [t.model_dump() for t in result.tests] == [
        {"input": "1\n", "output": "YES\n"},
        {"input": "5\n1 2 3 4 5\n", "output": "NO\n"},
    ]
    assert (result.extraneous_chars, result.duplicate_inputs, result.empty_tests) == (0, 0, 0)


def test_text_outside_the_blocks_is_ignored_and_counted():
    result = ok("Here:\n" + ANALYSIS + "and\n" + TESTS + "Done.")
    assert len(result.tests) == 2
    assert result.extraneous_chars == len("Here:") + len("and") + len("Done.")


@pytest.mark.parametrize("block, tag", [(ANALYSIS, "edge_cases_analysis"), (TESTS, "tests")])
def test_a_missing_or_duplicated_block(block, tag):
    assert error(GOOD.replace(block, "")) == f"missing_block:{tag}"
    assert error(GOOD + block) == f"duplicated_block:{tag}"


def test_blocks_in_the_wrong_order():
    assert error(TESTS + ANALYSIS) == "wrong_order"


def test_tests_without_any_test():
    assert error(ANALYSIS + "<tests>\n\n</tests>\n") == "no_tests"


def test_text_between_tests():
    assert error(ANALYSIS + block_of(TEST_1, "and also\n", TEST_2)) == "text_between_tests"


@pytest.mark.parametrize(
    "content",
    [
        "<input>\n1\n</input>\n",  # no output
        "<output>\nYES\n</output>\n",  # no input
        "<output>\nYES\n</output>\n<input>\n1\n</input>\n",  # swapped
        "<input>\n1\n</input>\n<input>\n2\n</input>\n<output>\nYES\n</output>\n",  # two inputs
        "<input>\n1\n</input>\nso:\n<output>\nYES\n</output>\n",  # loose text
        "<input>\n1\n<output>\nYES\n</output>\n</input>\n",  # output inside the input
    ],
)
def test_a_malformed_test(content):
    assert error(ANALYSIS + block_of(f"<test>\n{content}</test>\n")) == "malformed_test"


def test_a_test_not_closed_or_nested():
    assert error(ANALYSIS + "<tests>\n<test>\n<input>\n1\n</input>\n</tests>\n") == (
        "unclosed_block:test"
    )
    assert error(ANALYSIS + block_of(f"<test>\n{TEST_1}</test>\n")) == "nested_test"


@pytest.mark.parametrize(
    "empty",
    [
        "<test>\n<input>\n \n</input>\n<output>\nYES\n</output>\n</test>\n",
        "<test>\n<input>\n1\n</input>\n<output>\n</output>\n</test>\n",
    ],
    ids=["empty_input", "empty_output"],
)
def test_a_test_with_an_empty_part_is_dropped_alone_and_counted(empty):
    result = ok(ANALYSIS + block_of(TEST_1, empty))
    assert [t.input for t in result.tests] == ["1\n"] and result.empty_tests == 1
    assert error(ANALYSIS + block_of(empty)) == "only_empty_tests"


def test_an_empty_analysis_fails_the_answer():
    raw = "<edge_cases_analysis>\n \n</edge_cases_analysis>\n" + TESTS
    assert error(raw) == "empty_block:edge_cases_analysis"


def test_repeated_inputs_are_kept_and_counted():
    result = ok(ANALYSIS + block_of(TEST_1, TEST_1, TEST_2))
    assert len(result.tests) == 3 and result.duplicate_inputs == 1


def test_windows_newlines_and_spaces_inside_lines():
    raw = ANALYSIS + block_of(
        "<test><input>\n\n  3  \n1  2\n \n</input><output>3 2 1</output></test>"
    )
    result = ok(raw.replace("\n", "\r\n"))
    assert result.tests[0].model_dump() == {"input": "  3  \n1  2\n", "output": "3 2 1\n"}


def test_less_than_and_ampersand_inside_an_output_are_fine():
    test = "<test>\n<input>\n1 2\n</input>\n<output>\n1 < 2 & 2 > 1\n</output>\n</test>\n"
    assert ok(ANALYSIS + block_of(test)).tests[0].output == "1 < 2 & 2 > 1\n"


def test_the_parser_is_deterministic_and_never_raises():
    assert parse_prediction(GOOD) == parse_prediction(GOOD)
    for raw in ["", "<", "</tests><tests>", "<test></test>" * 3, "\x00\udcff", GOOD[:60]]:
        assert isinstance(parse_prediction(raw), PredictionParse | UnparsedResponse)


@pytest.mark.parametrize("opening", ["```", "```text", "```txt", "```plaintext", "```text  "])
def test_a_fence_around_a_whole_input_or_output_is_removed_and_counted(opening):
    test = (
        f"<test>\n<input>\n{opening}\n3\n1 2 3\n```\n</input>\n"
        f"<output>\n{opening}\nYES\n```\n</output>\n</test>\n"
    )
    result = ok(ANALYSIS + block_of(test, TEST_1))
    assert result.tests[0].model_dump() == {"input": "3\n1 2 3\n", "output": "YES\n"}
    assert result.markdown_fences_removed == 2


@pytest.mark.parametrize(
    "body",
    [
        "```python\n3\n```\n",  # another language
        "```\n3\n",  # not closed
        "x\n```\n3\n```\n",  # not on the first line
        "  ```\n3\n  ```\n",  # indented
    ],
)
def test_any_other_fence_stays_as_data(body):
    test = f"<test>\n<input>\n{body}</input>\n<output>\nYES\n</output>\n</test>\n"
    result = ok(ANALYSIS + block_of(test))
    assert result.tests[0].input == body and result.markdown_fences_removed == 0


def test_a_fence_around_nothing_leaves_an_empty_test_that_is_dropped():
    test = "<test>\n<input>\n```\n```\n</input>\n<output>\nYES\n</output>\n</test>\n"
    result = ok(ANALYSIS + block_of(test, TEST_1))
    assert len(result.tests) == 1 and result.empty_tests == 1
