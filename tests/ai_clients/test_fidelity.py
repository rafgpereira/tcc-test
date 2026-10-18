"""The prompt checked against the raw files of the dataset, and the lost exponents (R4, R5)."""

import pytest

from ai_clients import config, problem
from ai_clients.prompt import build_prompt, load_template
from ai_clients.requests_view import check_fidelity, exponent_warning
from tests.ai_clients.conftest import build_dataset
from tests.ai_clients.conftest import problem as problem_files

CHECKED = {
    "black_box": ["statement", "example_input", "example_output"],
    "white_box": ["code", "example_input", "example_output"],
    "hybrid": ["statement", "code", "example_input", "example_output"],
}


def prompt_of(root, problem_id, scenario):
    return build_prompt(load_template(), problem.load_problem(root, problem_id), scenario)


@pytest.mark.parametrize("scenario", config.SCENARIOS)
def test_a_prompt_built_from_the_dataset_is_faithful(repo, scenario):
    result = check_fidelity(repo, "1_A", scenario, prompt_of(repo, "1_A", scenario))
    assert result.faithful and result.checked == CHECKED[scenario]
    assert result.missing == [] and result.scenario_leak == []


def test_a_crlf_in_the_statement_file_is_a_difference(tmp_path):
    files = problem_files("1_A")
    files["enunciado.md"] = "# 1_A\r\n\r\nRead an integer n and print it.\r\n"
    root = build_dataset(tmp_path, {"1_A": files})
    # The dataset store normalizes on write: put the CRLF back in the extracted file itself.
    statement = root / "data/dataset/problems/1_A/enunciado.md"
    statement.write_bytes(files["enunciado.md"].encode())
    text = prompt_of(root, "1_A", "black_box")  # read_text turns \r\n into \n
    result = check_fidelity(root, "1_A", "black_box", text)
    assert not result.faithful
    (piece,) = result.missing
    assert (piece.piece, piece.file) == ("statement", "enunciado.md")
    assert 0 < piece.matched_chars < piece.expected_chars


def test_a_cut_prompt_misses_the_code(repo):
    text = prompt_of(repo, "1_A", "white_box")
    cut = text.replace("std::cout<<n;}", "")
    result = check_fidelity(repo, "1_A", "white_box", cut)
    assert [m.piece for m in result.missing] == ["code"]


def test_only_final_newlines_of_the_example_may_be_dropped(tmp_path):
    files = problem_files("1_A", public=[("1 \n", "1\n"), ("2\n", "2\n")])
    root = build_dataset(tmp_path, {"1_A": files})
    text = prompt_of(root, "1_A", "black_box")
    assert check_fidelity(root, "1_A", "black_box", text).faithful  # "1 " kept, "\n" dropped
    wrong = text.replace("Input: 1 \n", "Input: 1\n")
    assert [m.piece for m in check_fidelity(root, "1_A", "black_box", wrong).missing] == [
        "example_input"
    ]


def test_a_black_box_prompt_with_code_leaks_the_other_scenario(repo):
    text = prompt_of(repo, "1_A", "black_box") + "\n<reference_solution_cpp>\nint main(){}\n"
    result = check_fidelity(repo, "1_A", "black_box", text)
    assert result.scenario_leak == ["<reference_solution_cpp>"] and not result.faithful


def test_a_white_box_prompt_with_the_statement_leaks_the_other_scenario(repo):
    text = prompt_of(repo, "1_A", "white_box") + "\n<problem_statement>\nx\n</problem_statement>"
    assert check_fidelity(repo, "1_A", "white_box", text).scenario_leak == ["<problem_statement>"]


def with_statement(tmp_path, statement):
    files = problem_files("1_A")
    files["enunciado.md"] = f"# 1_A\n\n{statement}\n"
    return build_dataset(tmp_path, {"1_A": files})


@pytest.mark.parametrize(
    "statement",
    [
        "The first line has n (1 ≤ n ≤ 105).",
        "Each a_i < 109 holds.",
        "Print the answer modulo (109 + 7).",
        "The sum does not exceed 104 in total.",
        "Values from 1 to 106 inclusive.",
        "n·105 operations",
    ],
)
def test_a_lost_exponent_is_warned(tmp_path, statement):
    root = with_statement(tmp_path, statement)
    warning = exponent_warning(root, "1_A", "black_box")
    assert warning is not None and warning.problem_id == "1_A"
    assert all(len(m) <= 40 for m in warning.matches)


@pytest.mark.parametrize(
    "statement",
    [
        "The first line has n (1 ≤ n ≤ 10^5).",
        "n is at most 100000.",
        "Print the answer modulo 1000000007.",
        "There are 105 apples.",
        "Each a_i ≤ 10^{9}.",
    ],
)
def test_a_kept_exponent_is_not_warned(tmp_path, statement):
    assert exponent_warning(with_statement(tmp_path, statement), "1_A", "black_box") is None


def test_the_warning_quotes_each_match_in_the_order_of_the_text(tmp_path):
    root = with_statement(tmp_path, "1 ≤ n ≤ 105 and 1 ≤ a_i ≤ 109 hold")
    matches = exponent_warning(root, "1_A", "hybrid").matches
    assert len(matches) == 2 and "105" in matches[0] and "109" in matches[1]


def test_a_white_box_prompt_has_no_statement_so_no_warning(tmp_path):
    root = with_statement(tmp_path, "1 ≤ n ≤ 105")
    assert exponent_warning(root, "1_A", "white_box") is None
