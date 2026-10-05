"""The prompt: the template of the authors with only ``<context_data>`` varying by scenario."""

import hashlib
import re

import pytest

from ai_clients import config
from ai_clients.problem import load_problem
from ai_clients.prompt import (
    MARKER_CONTEXT,
    MARKER_EXAMPLE_INPUT,
    MARKER_EXAMPLE_OUTPUT,
    build_prompt,
    context_data,
    load_template,
)
from tests.ai_clients.conftest import build_dataset, problem

TEMPLATE = (
    "<system_rules>\nrules\n</system_rules>\n\n"
    "<context_data>\n(scenario-dependent content)\n</context_data>\n\n"
    "<few_shot_example>\nInput: (dataset example input)\n"
    "Expected Output: (dataset example output)\n</few_shot_example>\n\n<task>\ndo it\n</task>"
)


@pytest.fixture()
def template_file(tmp_path):
    path = tmp_path / "prompt.txt"
    path.write_text(TEMPLATE, encoding="utf-8")
    return path


def outside_context(prompt: str) -> str:
    return re.sub(r"<context_data>.*</context_data>", "<context_data/>", prompt, flags=re.DOTALL)


@pytest.mark.parametrize("marker", [MARKER_CONTEXT, MARKER_EXAMPLE_INPUT, MARKER_EXAMPLE_OUTPUT])
def test_a_missing_marker_is_an_error(tmp_path, marker):
    path = tmp_path / "prompt.txt"
    path.write_text(TEMPLATE.replace(marker, "gone"), encoding="utf-8")
    with pytest.raises(ValueError, match="exactly once"):
        load_template(path)


@pytest.mark.parametrize("marker", [MARKER_CONTEXT, MARKER_EXAMPLE_INPUT, MARKER_EXAMPLE_OUTPUT])
def test_a_duplicated_marker_is_an_error(tmp_path, marker):
    path = tmp_path / "prompt.txt"
    path.write_text(TEMPLATE + "\n" + marker, encoding="utf-8")
    with pytest.raises(ValueError, match="exactly once"):
        load_template(path)


def test_the_template_hash_is_of_the_file_with_unix_newlines(tmp_path, template_file):
    expected = hashlib.sha256(TEMPLATE.encode("utf-8")).hexdigest()
    assert load_template(template_file).sha256 == expected
    windows = tmp_path / "windows.txt"  # a Windows checkout has CRLF: same template, same hash
    windows.write_bytes(TEMPLATE.replace("\n", "\r\n").encode("utf-8"))
    assert load_template(windows).sha256 == expected
    assert "\r" not in load_template(windows).text


def test_context_data_of_each_scenario(repo):
    p = load_problem(repo, "1_A")
    black = f"<problem_statement>\n{p.statement}\n</problem_statement>"
    white = f"<reference_solution_cpp>\n{p.ac_ref}\n</reference_solution_cpp>"
    assert context_data(p, "black_box") == black
    assert context_data(p, "white_box") == white
    assert context_data(p, "hybrid") == black + "\n\n" + white


def test_the_three_prompts_differ_only_inside_context_data(repo, template_file):
    template = load_template(template_file)
    p = load_problem(repo, "1_A")
    prompts = [build_prompt(template, p, s) for s in config.SCENARIOS]
    assert len({outside_context(x) for x in prompts}) == 1
    assert len(set(prompts)) == 3


def test_black_box_has_no_code_and_white_box_has_no_statement(repo, template_file):
    template = load_template(template_file)
    p = load_problem(repo, "1_A")
    black = build_prompt(template, p, "black_box")
    white = build_prompt(template, p, "white_box")
    assert p.ac_ref.strip() not in black and "<reference_solution_cpp>" not in black
    assert "Read an integer n" not in white and "<problem_statement>" not in white


def test_hybrid_contains_both_contexts_literally(repo, template_file):
    template = load_template(template_file)
    p = load_problem(repo, "1_A")
    hybrid = build_prompt(template, p, "hybrid")
    assert context_data(p, "black_box") in hybrid and context_data(p, "white_box") in hybrid


def test_the_example_is_the_first_public_test_in_every_scenario(tmp_path, template_file):
    public = [("3\n1 2 3\n", "6\n"), ("1\n5\n", "5\n")]
    root = build_dataset(tmp_path, {"4_D": problem("4_D", public=public)})
    template = load_template(template_file)
    p = load_problem(root, "4_D")
    for scenario in config.SCENARIOS:
        prompt = build_prompt(template, p, scenario)
        assert "Input: 3\n1 2 3\nExpected Output: 6\n</few_shot_example>" in prompt
        assert "1\n5\n" not in prompt.split("<few_shot_example>")[1]


def test_no_marker_is_left_and_no_other_problem_leaks(repo, template_file):
    template = load_template(template_file)
    p = load_problem(repo, "1_A")
    for scenario in config.SCENARIOS:
        prompt = build_prompt(template, p, scenario)
        for marker in (MARKER_CONTEXT, MARKER_EXAMPLE_INPUT, MARKER_EXAMPLE_OUTPUT):
            assert marker not in prompt
        assert "2_B" not in prompt


def test_a_marker_inside_the_statement_is_not_replaced_again(tmp_path, template_file):
    files = problem("5_E")
    files["enunciado.md"] = "Statement quoting (dataset example input) literally.\n"
    root = build_dataset(tmp_path, {"5_E": files})
    prompt = build_prompt(load_template(template_file), load_problem(root, "5_E"), "black_box")
    assert "quoting (dataset example input) literally" in prompt


def test_the_real_template_loads_and_keeps_the_fr007_wording():
    template = load_template()
    assert template.text == config.PROMPT_TEMPLATE_PATH.read_text(encoding="utf-8").replace(
        "\r\n", "\n"
    )
    assert "Every value in every input MUST respect the constraints stated in the context." in (
        template.text
    )
    text = " ".join(template.text.split())  # the wording, whatever the line breaks
    assert (
        "Use values up to the maximum allowed by the constraints, but keep the NUMBER of elements "
        "in each input small enough to write out fully (e.g., at most ~100 elements)."
    ) in text
    assert "the maximum size allowed by the constraints" not in text
    assert "the largest case you can write out IN FULL" not in text
    assert "including empty input" not in text
