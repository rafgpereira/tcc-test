"""AC without short circuit, targets with short circuit, two oracles in one pass (T012, T013, T022)."""

from pathlib import Path

import pytest

from evaluation import judging
from sandbox.types import InfraError
from tests.evaluation.conftest import LIMITS, FakeEngine, double, ok, re_, suite_of, tle

SUITE = suite_of(("1\n", "2\n"), ("2\n", "4\n"), ("3\n", "6\n"), ("4\n", "8\n"), ("5\n", "10\n"))


def judge_ac(fake, tests=SUITE):
    return judging.judge_ac(Path("AC"), tests, LIMITS, 0, run=fake.run, standard_used="gnu++20")


def judge(fake, ac, name="WA_1", tests=SUITE):
    return judging.judge_target(
        Path(name), tests, ac, LIMITS, 0, run=fake.run, target=name, kind="wa"
    )


# ------------------------------------------------------------------------------------ AC


def test_ac_passing_every_test_is_approved(fake):
    ac = judge_ac(fake)
    assert ac.approved
    assert [t.verdict for t in ac.tests] == ["passed"] * 5
    assert [t.actual_output for t in ac.tests] == ["2\n", "4\n", "6\n", "8\n", "10\n"]
    assert all(t.runs is None for t in ac.tests)


def test_ac_runs_every_test_even_after_a_failure(fake):
    tests = suite_of(
        ("1\n", "2\n"), ("2\n", "5\n"), ("3\n", "6\n"), ("4\n", "8\n"), ("9\n", "18\n")
    )
    fake.programs["AC"] = lambda text, n: tle() if text == "9\n" else double(text)
    ac = judge_ac(fake, tests)
    assert not ac.approved
    assert [t.verdict for t in ac.tests] == [
        "passed",
        "wrong_output",
        "passed",
        "passed",
        "runtime_error",
    ]
    assert ac.tests[1].actual_output == "4\n"  # the real output, base of the corrected oracle
    assert ac.tests[4].error_kind == "TLE"
    assert ac.tests[4].actual_output == ""
    assert len(fake.runs_of("AC")) == 4 + 3  # every test, the TLE three times


def test_a_wrong_output_is_never_repeated(fake):
    ac = judge_ac(fake, suite_of(("1\n", "3\n")))
    assert ac.tests[0].verdict == "wrong_output"
    assert len(fake.runs_of("AC")) == 1


def test_an_error_in_the_three_runs_keeps_the_kind_of_the_first(fake):
    kinds = [tle, re_, re_]
    fake.programs["AC"] = lambda text, n: kinds[n]()
    ac = judge_ac(fake, suite_of(("1\n", "2\n")))
    test = ac.tests[0]
    assert (test.verdict, test.error_kind, test.unstable) == ("runtime_error", "TLE", False)
    assert [r.verdict for r in test.runs] == ["TLE", "RE", "RE"]


def test_an_error_that_does_not_repeat_is_unstable_and_the_third_run_still_happens(fake):
    fake.programs["AC"] = lambda text, n: tle() if n == 0 else double(text)
    ac = judge_ac(fake, suite_of(("1\n", "2\n")))
    test = ac.tests[0]
    assert (test.verdict, test.unstable, test.actual_output) == ("passed", True, "2\n")
    assert [r.verdict for r in test.runs] == ["TLE", "passed", "passed"]
    assert len(fake.runs_of("AC")) == 3  # the 2 repetitions are always made
    assert ac.approved


def test_infrastructure_failure_is_never_a_verdict(fake):
    def broken(text, n):
        raise InfraError("disk full")

    fake.programs["AC"] = broken
    with pytest.raises(InfraError):
        judge_ac(fake)


# ------------------------------------------------------------------- targets, declared oracle


def test_target_detected_stops_at_the_first_failing_test(fake):
    fake.programs["WA_1"] = lambda text, n: ok("0\n") if text == "3\n" else double(text)
    result = judge(fake, judge_ac(fake))
    assert result.declared.model_dump() == {
        "detected": True,
        "test_index": 2,
        "verdict": "wrong_output",
    }
    assert fake.runs_of("WA_1") == ["1\n", "2\n", "3\n"]  # tests 4 and 5 never run
    assert result.tests_run == 3


def test_target_passing_every_test_survives(fake):
    result = judge(fake, judge_ac(fake))
    assert not result.declared.detected and not result.corrected.detected
    assert result.tests_run == 5


def test_target_error_counts_only_if_repeated(fake):
    fake.programs["WA_1"] = lambda text, n: tle() if text == "2\n" else double(text)
    result = judge(fake, judge_ac(fake))
    assert result.declared.verdict == "TLE" and result.declared.test_index == 1
    assert fake.runs_of("WA_1").count("2\n") == 3


def test_target_unstable_error_goes_on_to_the_next_test(fake):
    def wa(text, n):
        if text == "2\n" and n == 0:
            return tle()
        return ok("0\n") if text == "4\n" else double(text)

    fake.programs["WA_1"] = wa
    result = judge(fake, judge_ac(fake))
    assert result.unstable_tests == [1]
    assert result.declared.test_index == 3 and result.declared.verdict == "wrong_output"
    assert fake.runs_of("WA_1").count("2\n") == 3  # the repetitions are always made


def test_unstable_error_followed_by_a_wrong_output_detects_with_it(fake):
    fake.programs["WA_1"] = lambda text, n: (
        (tle() if n == 0 else ok("0\n")) if text == "1\n" else double(text)
    )
    result = judge(fake, judge_ac(fake))
    assert result.unstable_tests == [0]
    assert result.declared.verdict == "wrong_output" and result.declared.test_index == 0


# ------------------------------------------------------------------ corrected oracle (US2)


def test_both_oracles_agree_when_the_declared_outputs_are_right(fake):
    fake.programs["WA_1"] = lambda text, n: ok("0\n") if text == "4\n" else double(text)
    result = judge(fake, judge_ac(fake))
    assert result.declared == result.corrected


def test_a_wrong_declared_output_detects_only_in_the_declared_oracle(fake):
    tests = suite_of(("1\n", "2\n"), ("2\n", "5\n"), ("3\n", "6\n"))  # test 1 declares 5, AC says 4
    ac = judge_ac(fake, tests)
    result = judge(fake, ac, tests=tests)  # WA_1 behaves exactly like the AC
    assert result.declared.detected and result.declared.test_index == 1
    assert not result.corrected.detected
    assert fake.runs_of("WA_1") == ["1\n", "2\n", "3\n"]  # one pass: each test once


def test_tests_where_the_ac_failed_are_ignored_by_the_corrected_oracle(fake):
    tests = suite_of(("1\n", "2\n"), ("9\n", "18\n"), ("3\n", "6\n"))
    fake.programs["AC"] = lambda text, n: tle() if text == "9\n" else double(text)
    fake.programs["WA_1"] = lambda text, n: tle() if text == "9\n" else double(text)
    ac = judge_ac(fake, tests)
    result = judge(fake, ac, tests=tests)
    assert result.declared.verdict == "TLE" and result.declared.test_index == 1
    assert not result.corrected.detected  # the only failure is on a test excluded from it


def test_ac_failing_every_test_leaves_nothing_for_the_corrected_oracle(fake):
    tests = suite_of(("1\n", "2\n"), ("2\n", "4\n"))
    fake.programs["AC"] = lambda text, n: re_()
    fake.programs["WA_1"] = lambda text, n: ok("0\n")
    result = judge(fake, judge_ac(fake, tests), tests=tests)
    assert result.declared.detected and not result.corrected.detected
    assert fake.runs_of("WA_1") == ["1\n"]  # test 2 is useless to both oracles: never run


def _two_passes(tests, ac_tests, behaviour):
    """A naive reference: each oracle in its own pass with short circuit."""

    def first(expected_of):
        for i, test in enumerate(tests):
            expected = expected_of(i, test)
            if expected is None:
                continue
            run = behaviour(test.input, 1)  # a stable behaviour: any call gives the same
            kind = judging.error_kind(run, LIMITS)
            if kind or run.stdout.decode() != expected:
                return i, kind or "wrong_output"
        return None

    declared = first(lambda i, t: t.output)
    corrected = first(
        lambda i, t: None if ac_tests[i].verdict == "runtime_error" else ac_tests[i].actual_output
    )
    return declared, corrected


@pytest.mark.parametrize(
    "behaviour",
    [
        lambda text, n: double(text),
        lambda text, n: ok("0\n") if text == "2\n" else double(text),
        lambda text, n: tle() if text in ("3\n", "9\n") else double(text),
        lambda text, n: ok("1\n"),
        lambda text, n: re_() if text == "5\n" else ok(f"{2 * int(text) + 1}\n"),
    ],
)
def test_one_pass_equals_two_independent_passes(behaviour):
    tests = suite_of(
        ("1\n", "2\n"), ("2\n", "5\n"), ("9\n", "18\n"), ("3\n", "6\n"), ("5\n", "1\n")
    )
    fake = FakeEngine({"AC": lambda t, n: tle() if t == "9\n" else double(t), "WA_1": behaviour})
    ac = judge_ac(fake, tests)
    result = judge(fake, ac, tests=tests)
    declared, corrected = _two_passes(tests, ac.tests, behaviour)

    def as_pair(detection):
        return (detection.test_index, detection.verdict) if detection.detected else None

    assert (as_pair(result.declared), as_pair(result.corrected)) == (declared, corrected)
    # never more runs than the longest of the two passes (plus the repetitions of an error)
    assert result.tests_run <= len(tests)
