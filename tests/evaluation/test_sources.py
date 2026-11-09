"""What a problem gives to the evaluation (T006, T025)."""

import hashlib

import pytest

from evaluation import sources
from tests.evaluation.conftest import make_tree, solution_attempt


def test_problem_targets_reads_the_programs_and_the_limits(tmp_path):
    make_tree(tmp_path, was=3, mutants=2)
    problem = sources.problem_targets(tmp_path, "1_A")
    assert problem.ac_source == "prog:AC"
    assert [t.name for t in problem.targets] == ["WA_1", "WA_2", "WA_3", "Mutant_1", "Mutant_2"]
    assert [t.kind for t in problem.targets] == ["wa"] * 3 + ["mutant"] * 2
    assert problem.limits.time_limit_seconds == 1.0  # from metadata.json, never a constant
    assert problem.limits.memory_limit_bytes == 1 << 28


def test_numbering_with_a_gap_is_refused(tmp_path):
    make_tree(tmp_path, was=3)
    (tmp_path / "data/dataset/problems/1_A/WA_2.cpp").unlink()
    with pytest.raises(ValueError, match="without a gap"):
        sources.problem_targets(tmp_path, "1_A")


def test_final_suite_of_a_commercial_model(tmp_path):
    make_tree(tmp_path)
    suite = sources.final_suite(tmp_path, "gpt", "1_A", "black_box")
    raw = (tmp_path / "data/suites/gpt/problems/1_A/black_box/suite.json").read_bytes()
    assert [t.input for t in suite.tests] == ["1\n", "3\n"]
    assert suite.source.status == "accepted"
    assert suite.source.tree == "suites/gpt"
    assert suite.source.suite_sha256 == hashlib.sha256(raw).hexdigest()
    assert suite.no_suite_reason is None


def test_discarded_manual_is_a_combination_without_a_suite(tmp_path):
    closed = {"status": "discarded_manual", "tests": []}
    make_tree(tmp_path, suites={("claude", "1_A", "hybrid"): closed})
    suite = sources.final_suite(tmp_path, "claude", "1_A", "hybrid")
    assert suite.tests == ()
    assert suite.no_suite_reason == "discarded_manual"
    assert suite.source.status == "discarded_manual"


def test_the_local_model_reads_the_tree_of_provenance(tmp_path):
    rev1 = {"status": "accepted_fallback", "tests": [{"input": "5\n", "output": "10\n"}]}
    make_tree(
        tmp_path,
        provenance={("1_A", "black_box"): "suites/slm-rev1"},
        suites={("slm", "1_A", "black_box"): rev1},
    )
    suite = sources.final_suite(tmp_path, "slm", "1_A", "black_box")
    assert suite.source.tree == "suites/slm-rev1"
    assert suite.source.status == "accepted_fallback"
    assert [t.output for t in suite.tests] == ["10\n"]


# ------------------------------------------------------------------- first attempt (US3, T025)


def test_attempt_tests_are_the_kept_inputs_with_the_solution_outputs(tmp_path):
    attempt = solution_attempt(["1\n", "2\n", "3\n"], ["2\n", None, "7\n"])  # rejected answer kept
    make_tree(tmp_path, slm_attempts={("1_A", "black_box", 1): attempt})
    suite = sources.attempt_suite(tmp_path, "1_A", "black_box", 1)
    assert [(t.input, t.output) for t in suite.tests] == [("1\n", "2\n"), ("3\n", "7\n")]
    assert suite.source.attempt == 1
    assert suite.source.status is None
    assert suite.no_suite_reason is None


def test_attempt_without_a_suite_says_why(tmp_path):
    prediction = solution_attempt(["1\n"], ["2\n"], template="prediction")
    nothing_kept = solution_attempt(["1\n"], [None])
    unparsed = ({"attempt": 1, "template": "solution", "parse": {"ok": False}}, None)
    make_tree(
        tmp_path,
        slm_attempts={
            ("1_A", "black_box", 1): prediction,
            ("1_A", "white_box", 1): nothing_kept,
            ("1_A", "hybrid", 1): unparsed,
        },
    )
    reasons = {
        s: sources.attempt_suite(tmp_path, "1_A", s, 1).no_suite_reason
        for s in ("black_box", "white_box", "hybrid")
    }
    assert reasons == {
        "black_box": "prediction_attempt",
        "white_box": "attempt_without_tests",
        "hybrid": "attempt_without_tests",
    }
    assert sources.attempt_suite(tmp_path, "1_A", "black_box", 2).no_suite_reason == (
        "attempt_missing"
    )


def test_attempt_is_read_from_the_tree_of_provenance(tmp_path):
    attempt = solution_attempt(["4\n"], ["8\n"])
    make_tree(
        tmp_path,
        provenance={("1_A", "hybrid"): "suites/slm-rev1"},
        slm_attempts={("1_A", "hybrid", 1): attempt},
    )
    suite = sources.suite_for(tmp_path, "slm-attempt1", "1_A", "hybrid")
    assert suite.source.tree == "suites/slm-rev1"
    assert [t.output for t in suite.tests] == ["8\n"]
