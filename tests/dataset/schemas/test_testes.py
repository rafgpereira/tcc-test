"""Tests for `Testes` (T053; data-model.md section 1.2)."""

import json

import pytest
from pydantic import ValidationError

from dataset.schemas.testes import TestCase, Testes

CASE = {"input": "5\n", "output": "15\n"}


def make(**changes) -> dict:
    base = {
        "schema_version": 1,
        "problem_id": "1101_A",
        "public_tests": [CASE],
        "private_tests": [{"input": "1\n", "output": "7\n"}],
        "generated_tests": [{"input": "2\n", "output": "6\n"}],
    }
    return {**base, **changes}


def test_a_valid_suite_is_accepted():
    testes = Testes.model_validate(make())
    assert testes.public_tests[0] == TestCase(input="5\n", output="15\n")


@pytest.mark.parametrize(
    "changes",
    [{"schema_version": 2}, {"problem_id": "nope"}, {"surprise": []}],
)
def test_invalid_header_fields_are_rejected(changes):
    with pytest.raises(ValidationError):
        Testes.model_validate(make(**changes))


def test_the_three_groups_keep_the_original_order():
    cases = [{"input": str(i), "output": str(i * 2)} for i in (5, 3, 9, 1)]
    testes = Testes.model_validate(make(public_tests=cases))
    assert [c.input for c in testes.public_tests] == ["5", "3", "9", "1"]


def test_a_test_case_needs_an_input_and_an_output():
    with pytest.raises(ValidationError):
        Testes.model_validate(make(public_tests=[{"input": "x"}]))


def test_individual_groups_may_be_empty():
    testes = Testes.model_validate(make(public_tests=[], generated_tests=[]))
    assert len(testes.private_tests) == 1


def test_at_least_one_test_in_total_is_required():
    with pytest.raises(ValidationError, match="at least one"):
        Testes.model_validate(make(public_tests=[], private_tests=[], generated_tests=[]))


def test_from_raw_groups_rejects_parallel_lists_of_different_length():
    with pytest.raises(ValueError, match="same length"):
        Testes.from_parallel_lists(
            "1101_A",
            public=(["a", "b"], ["1"]),
            private=([], []),
            generated=([], []),
        )


def test_from_raw_groups_zips_the_parallel_lists_in_order():
    testes = Testes.from_parallel_lists(
        "1101_A",
        public=(["a", "b"], ["1", "2"]),
        private=(["c"], ["3"]),
        generated=([], []),
    )
    assert [(c.input, c.output) for c in testes.public_tests] == [("a", "1"), ("b", "2")]
    assert testes.private_tests[0].output == "3"


def test_the_problem_id_must_equal_the_folder_name(tmp_path):
    folder = tmp_path / "9999_Z"
    folder.mkdir()
    (folder / "testes.json").write_text(json.dumps(make()))
    with pytest.raises(ValueError, match="folder"):
        Testes.from_folder(folder)
