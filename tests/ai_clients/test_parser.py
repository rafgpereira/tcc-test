"""Reading the three blocks of an answer: deterministic, strict, never "fixing" the answer."""

import pytest

from ai_clients.parser import parse_response
from ai_clients.schemas.generation import ParsedResponse, UnparsedResponse

ANALYSIS = "<edge_cases_analysis>\nn = 1 is the smallest case.\n</edge_cases_analysis>\n"
INPUTS = "<inputs>\n<input>\n1\n</input>\n<input>\n5\n1 2 3 4 5\n</input>\n</inputs>\n"
CODE = "<reference_py>\nimport sys\nprint(sys.stdin.read())\n</reference_py>\n"
GOOD = ANALYSIS + INPUTS + CODE


def ok(raw) -> ParsedResponse:
    result = parse_response(raw)
    assert isinstance(result, ParsedResponse), getattr(result, "error", result)
    return result


def error(raw) -> str:
    result = parse_response(raw)
    assert isinstance(result, UnparsedResponse), result
    return result.error


def test_a_well_formed_answer():
    result = ok(GOOD)
    assert result.edge_cases_analysis == "n = 1 is the smallest case.\n"
    assert result.inputs == ["1\n", "5\n1 2 3 4 5\n"]
    assert result.reference_py == "import sys\nprint(sys.stdin.read())\n"
    assert result.extraneous_chars == 0 and result.duplicate_inputs == 0


def test_text_outside_the_blocks_is_ignored_and_counted():
    result = ok("Sure! Here it is:\n" + ANALYSIS + "ok\n" + INPUTS + CODE + "Hope it helps.")
    assert result.inputs == ["1\n", "5\n1 2 3 4 5\n"]
    assert result.extraneous_chars == len("Sure!Hereitis:") + len("ok") + len("Hopeithelps.")


@pytest.mark.parametrize(
    "block, tag",
    [(ANALYSIS, "edge_cases_analysis"), (INPUTS, "inputs"), (CODE, "reference_py")],
)
def test_a_missing_block(block, tag):
    assert error(GOOD.replace(block, "")) == f"missing_block:{tag}"


@pytest.mark.parametrize(
    "block, tag",
    [(ANALYSIS, "edge_cases_analysis"), (INPUTS, "inputs"), (CODE, "reference_py")],
)
def test_a_duplicated_block(block, tag):
    assert error(GOOD + block) == f"duplicated_block:{tag}"


def test_blocks_in_the_wrong_order():
    assert error(INPUTS + ANALYSIS + CODE) == "wrong_order"
    assert error(ANALYSIS + CODE + INPUTS) == "wrong_order"


def test_a_block_that_is_not_closed():
    assert error(ANALYSIS + INPUTS + "<reference_py>\nprint(1)\n") == "unclosed_block:reference_py"
    assert error(GOOD.replace("<reference_py>", "")) == "unclosed_block:reference_py"


def test_overlapping_blocks():
    raw = (
        ANALYSIS
        + "<inputs>\n<input>\n1\n</input>\n<reference_py>\n</inputs>\nprint(1)\n</reference_py>"
    )
    assert error(raw) == "overlapping_blocks"


def test_inputs_without_any_input():
    assert error(ANALYSIS + "<inputs>\n\n</inputs>\n" + CODE) == "no_inputs"


@pytest.mark.parametrize("body", ["", "   ", "\n\n", " \n \t\n"])
def test_an_empty_input(body):
    raw = ANALYSIS + f"<inputs>\n<input>1</input><input>{body}</input>\n</inputs>\n" + CODE
    assert error(raw) == "empty_input"


def test_text_between_inputs():
    raw = ANALYSIS + "<inputs>\n<input>1</input>\nand also\n<input>2</input>\n</inputs>\n" + CODE
    assert error(raw) == "text_between_inputs"
    raw = ANALYSIS + "<inputs>\nfirst:\n<input>1</input>\n</inputs>\n" + CODE
    assert error(raw) == "text_between_inputs"


def test_an_input_that_is_not_closed_or_is_nested():
    raw = ANALYSIS + "<inputs>\n<input>1\n</inputs>\n" + CODE
    assert error(raw) == "unclosed_block:input"
    raw = ANALYSIS + "<inputs>\n<input>1<input>2</input></input>\n</inputs>\n" + CODE
    assert error(raw) == "nested_input"


@pytest.mark.parametrize("tag", ["edge_cases_analysis", "reference_py"])
def test_a_block_with_only_whitespace(tag):
    raw = GOOD.replace(
        ANALYSIS if tag == "edge_cases_analysis" else CODE, f"<{tag}>\n  \n</{tag}>\n"
    )
    assert error(raw) == f"empty_block:{tag}"


def test_windows_newlines_are_normalized():
    result = ok(GOOD.replace("\n", "\r\n"))
    assert result.inputs == ["1\n", "5\n1 2 3 4 5\n"]
    assert "\r" not in result.reference_py and "\r" not in result.edge_cases_analysis


def test_blank_lines_at_the_ends_of_an_input_go_inner_spaces_stay():
    raw = ANALYSIS + "<inputs>\n<input>\n\n  3  \n1  2\n \n</input>\n</inputs>\n" + CODE
    assert ok(raw).inputs == ["  3  \n1  2\n"]


def test_an_input_on_one_line_gets_its_final_newline():
    raw = ANALYSIS + "<inputs><input>7</input></inputs>" + CODE
    assert ok(raw).inputs == ["7\n"]


def test_a_markdown_fence_inside_the_code_is_kept():
    code = "<reference_py>\n```python\nprint(1)\n```\n</reference_py>\n"
    assert ok(ANALYSIS + INPUTS + code).reference_py == "```python\nprint(1)\n```\n"


def test_repeated_inputs_are_kept_and_counted():
    raw = ANALYSIS + "<inputs><input>1</input><input>2</input><input>1</input>"
    raw += "<input>1</input></inputs>" + CODE
    result = ok(raw)
    assert result.inputs == ["1\n", "2\n", "1\n", "1\n"]
    assert result.duplicate_inputs == 2


def test_less_than_and_ampersand_inside_the_code_are_fine():
    code = (
        "<reference_py>\na, b = 1, 2\nif a < b and a & b == 0:\n    print('<ok>')\n</reference_py>"
    )
    assert "a & b" in ok(ANALYSIS + INPUTS + code).reference_py


def test_the_parser_is_deterministic_and_never_raises():
    assert parse_response(GOOD) == parse_response(GOOD)
    for raw in ["", "<", "</inputs><inputs>", "<input></input>" * 3, "\x00\udcff", GOOD[:57]]:
        assert isinstance(parse_response(raw), ParsedResponse | UnparsedResponse)
