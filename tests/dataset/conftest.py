"""Shared fixtures for the dataset tests: synthetic code_contests rows (no network)."""

import pytest

CPP = 2  # ClassLabel index of language C++ in code_contests
PYTHON3 = 3


def _solutions(cpp: int, other: int = 1) -> dict:
    return {
        "language": [CPP] * cpp + [PYTHON3] * other,
        "solution": [f"int main() {{ return {i}; }}" for i in range(cpp)]
        + [f"print({i})" for i in range(other)],
    }


def make_row(**overrides) -> dict:
    """A code_contests row that is ELIGIBLE by default; ``overrides`` replace single fields.

    ``cpp_ac`` and ``cpp_wa`` are shortcuts for the number of C++ correct and incorrect solutions.
    """
    cpp_ac = overrides.pop("cpp_ac", 2)
    cpp_wa = overrides.pop("cpp_wa", 100)
    row = {
        "name": "1101_A. Minimum Integer",
        "description": "Read n and print the answer.",
        "source": 2,  # CODEFORCES
        "cf_contest_id": 1101,
        "cf_index": "A",
        "cf_rating": 1200,
        "cf_points": 500.0,
        "cf_tags": ["dp"],
        "is_description_translated": False,
        "time_limit": {"seconds": 2, "nanos": 0},
        "memory_limit_bytes": 256_000_000,
        "input_file": "",
        "output_file": "",
        "solutions": _solutions(cpp_ac),
        "incorrect_solutions": _solutions(cpp_wa),
        "public_tests": {"input": ["1\n"], "output": ["1\n"]},
        "private_tests": {"input": ["2\n"], "output": ["2\n"]},
        "generated_tests": {"input": ["3\n", "4\n"], "output": ["3\n", "4\n"]},
    }
    row.update(overrides)
    return row


@pytest.fixture
def row_factory():
    return make_row
