"""Tests for the judge: comparison rule, per-test verdict and suite verdict (T038; D13 rules 1, 2).

These are unit tests with a fake runner, so they run anywhere. The engine is the ONLY place where
outputs are compared to decide a verdict: the token-based diagnostic of the dataset module
(`format_only`) never lives here.
"""

import signal
from pathlib import Path

import pytest

from sandbox import judge
from sandbox.types import (
    CompileAttempt,
    CompileResult,
    ExecutionLimits,
    InfraError,
    RunResult,
    RunStatus,
    Test,
    Verdict,
)

LIMITS = ExecutionLimits(time_limit_seconds=1.0, memory_limit_bytes=256 * 1024 * 1024)


def make_run(
    status=RunStatus.OK,
    *,
    stdout=b"",
    stderr=b"",
    exit_code=0,
    sig=None,
    cpu=0.1,
    wall=0.1,
    rss=1_000_000,
) -> RunResult:
    return RunResult(
        status=status,
        exit_code=exit_code,
        signal=sig,
        stdout=stdout,
        stderr_tail=stderr,
        cpu_time_s=cpu,
        wall_time_s=wall,
        peak_rss_bytes=rss,
    )


# ---------------------------------------------------------------------------- outputs_equal


@pytest.mark.parametrize(
    ("expected", "actual"),
    [
        ("1 2\n", "1 2\n"),
        ("1 2\n", "1 2   \n"),  # trailing spaces on a line
        ("1 2\n", "1 2\t\n"),  # trailing tab
        ("1 2\n", "1 2\r\n"),  # Windows line ending
        ("1\n2\n", "1  \n2\t\n"),
        ("1 2\n", "1 2"),  # no final newline
        ("1 2\n", "1 2\n\n\n"),  # trailing blank lines
        ("1 2\n", "1 2\n   \n\t\n"),  # trailing blank lines with spaces
        ("1 2", "1 2\n\n"),
        ("", ""),
        ("", "\n"),
        ("", "  \n \n"),
    ],
)
def test_outputs_equal_ignores_trailing_whitespace_and_trailing_blank_lines(expected, actual):
    assert judge.outputs_equal(expected, actual)
    assert judge.outputs_equal(actual, expected)


@pytest.mark.parametrize(
    ("expected", "actual"),
    [
        ("1 2\n", "1  2\n"),  # inner whitespace differs
        ("1 2\n", " 1 2\n"),  # leading whitespace differs
        ("1 2\n", "\n1 2\n"),  # leading blank line differs
        ("1\n2\n", "1\n\n2\n"),  # blank line between lines differs
        ("1\n2\n", "1 2\n"),  # different line structure
        ("1 2\n", "1 3\n"),
        ("YES\n", "yes\n"),  # case matters
        ("1 2\n", "1\n"),  # missing content
        ("1\n", "1\n2\n"),  # extra line with content
        ("", "0\n"),
    ],
)
def test_outputs_equal_treats_any_other_difference_as_different(expected, actual):
    assert not judge.outputs_equal(expected, actual)


# ---------------------------------------------------------------------------- judge_test


def test_ac_when_the_output_matches():
    assert judge.judge_test(make_run(stdout=b"6\n"), "6\n", LIMITS) is Verdict.AC


def test_ac_ignores_trailing_whitespace_of_the_output():
    assert judge.judge_test(make_run(stdout=b"6  \n\n"), "6\n", LIMITS) is Verdict.AC


def test_wa_when_the_output_differs():
    assert judge.judge_test(make_run(stdout=b"7\n"), "6\n", LIMITS) is Verdict.WA


def test_tle_when_cpu_time_exceeds_the_limit():
    run = make_run(stdout=b"6\n", cpu=1.01)
    assert judge.judge_test(run, "6\n", LIMITS) is Verdict.TLE


def test_cpu_time_equal_to_the_limit_is_not_tle():
    assert judge.judge_test(make_run(stdout=b"6\n", cpu=1.0), "6\n", LIMITS) is Verdict.AC


def test_tle_when_the_wall_clock_reserve_was_exceeded():
    run = make_run(RunStatus.TIMEOUT, cpu=0.0, wall=4.5, exit_code=None, sig=signal.SIGKILL)
    assert judge.judge_test(run, "6\n", LIMITS) is Verdict.TLE


def test_tle_wins_over_a_wrong_answer():
    run = make_run(stdout=b"wrong\n", cpu=2.0)
    assert judge.judge_test(run, "6\n", LIMITS) is Verdict.TLE


def test_mle_on_sigabrt_with_bad_alloc_in_stderr():
    run = make_run(
        RunStatus.SIGNALED,
        exit_code=None,
        sig=signal.SIGABRT,
        stderr=b"terminate called after throwing an instance of 'std::bad_alloc'\n  what():  std::bad_alloc\n",
    )
    assert judge.judge_test(run, "6\n", LIMITS) is Verdict.MLE


def test_sigabrt_without_bad_alloc_is_a_runtime_error():
    run = make_run(
        RunStatus.SIGNALED, exit_code=None, sig=signal.SIGABRT, stderr=b"assertion failed"
    )
    assert judge.judge_test(run, "6\n", LIMITS) is Verdict.RE


def test_mle_when_the_peak_memory_reaches_the_limit():
    run = make_run(stdout=b"6\n", rss=LIMITS.memory_limit_bytes)
    assert judge.judge_test(run, "6\n", LIMITS) is Verdict.MLE


def test_peak_memory_just_below_the_limit_is_not_mle():
    run = make_run(stdout=b"6\n", rss=LIMITS.memory_limit_bytes - 1)
    assert judge.judge_test(run, "6\n", LIMITS) is Verdict.AC


def test_re_on_a_signal():
    run = make_run(RunStatus.SIGNALED, exit_code=None, sig=signal.SIGSEGV)
    assert judge.judge_test(run, "6\n", LIMITS) is Verdict.RE


def test_re_on_a_non_zero_exit():
    run = make_run(RunStatus.NONZERO_EXIT, exit_code=3, stdout=b"6\n")
    assert judge.judge_test(run, "6\n", LIMITS) is Verdict.RE


def test_re_when_the_output_limit_was_exceeded():
    run = make_run(RunStatus.OUTPUT_LIMIT, sig=signal.SIGKILL, exit_code=None)
    assert judge.judge_test(run, "6\n", LIMITS) is Verdict.RE


# ---------------------------------------------------------------------------- run_suite


class FakeRunner:
    """Answers each call from a list of RunResult and records the order of the inputs."""

    def __init__(self, results):
        self.results = list(results)
        self.calls = []

    def __call__(self, binary, stdin, limits, slot):
        self.calls.append((binary, stdin, slot))
        result = self.results[len(self.calls) - 1]
        if isinstance(result, Exception):
            raise result
        return result


def ok(out: str, **kw) -> RunResult:
    return make_run(stdout=out.encode(), **kw)


TESTS = [Test("a\n", "1\n"), Test("b\n", "2\n"), Test("c\n", "3\n")]


def test_all_ac_gives_ac_and_runs_every_test_in_the_given_order():
    runner = FakeRunner([ok("1\n"), ok("2\n"), ok("3\n")])
    result = judge.run_suite(Path("/bin/x"), TESTS, LIMITS, 0, runner=runner)
    assert result.verdict is Verdict.AC
    assert result.deciding_index is None
    assert result.first_failure is None
    assert result.tests_run == 3
    assert [call[1] for call in runner.calls] == [b"a\n", b"b\n", b"c\n"]


def test_the_first_test_that_is_not_ac_decides_and_stops_the_suite():
    runner = FakeRunner([ok("1\n"), ok("WRONG\n"), ok("3\n")])
    result = judge.run_suite(Path("/bin/x"), TESTS, LIMITS, 0, runner=runner)
    assert result.verdict is Verdict.WA
    assert result.deciding_index == 1
    assert result.tests_run == 2
    assert len(runner.calls) == 2  # the third test never ran (curto-circuito, FR-012)
    assert result.first_failure is not None
    assert result.first_failure.expected == "2\n"
    assert result.first_failure.actual == "WRONG\n"


def test_tle_on_an_earlier_test_wins_over_a_wrong_answer_on_a_later_one():
    runner = FakeRunner([ok("1\n", cpu=2.0), ok("WRONG\n")])
    result = judge.run_suite(Path("/bin/x"), TESTS, LIMITS, 0, runner=runner)
    assert result.verdict is Verdict.TLE
    assert result.deciding_index == 0
    assert len(runner.calls) == 1


def test_wa_on_an_earlier_test_wins_over_a_tle_on_a_later_one():
    runner = FakeRunner([ok("BAD\n"), ok("2\n", cpu=9.0)])
    result = judge.run_suite(Path("/bin/x"), TESTS, LIMITS, 0, runner=runner)
    assert result.verdict is Verdict.WA
    assert result.deciding_index == 0


def test_the_suite_reports_the_largest_cpu_time_and_memory_seen():
    runner = FakeRunner(
        [ok("1\n", cpu=0.2, rss=5_000_000), ok("2\n", cpu=0.7, rss=3_000_000), ok("3\n", cpu=0.1)]
    )
    result = judge.run_suite(Path("/bin/x"), TESTS, LIMITS, 0, runner=runner)
    assert result.max_cpu_time_s == pytest.approx(0.7)
    assert result.max_memory_bytes == 5_000_000


def test_an_empty_suite_is_ac():
    result = judge.run_suite(Path("/bin/x"), [], LIMITS, 0, runner=FakeRunner([]))
    assert result.verdict is Verdict.AC
    assert result.tests_run == 0


def test_the_slot_is_passed_to_the_runner():
    runner = FakeRunner([ok("1\n")])
    judge.run_suite(Path("/bin/x"), TESTS[:1], LIMITS, 7, runner=runner)
    assert runner.calls[0][2] == 7


def test_infra_error_from_the_runner_propagates_and_is_never_a_verdict():
    runner = FakeRunner([ok("1\n"), InfraError("tmpfs is full")])
    with pytest.raises(InfraError, match="tmpfs is full"):
        judge.run_suite(Path("/bin/x"), TESTS, LIMITS, 0, runner=runner)


# ---------------------------------------------------------------------------- judge_source


def compiled(standard="gnu++20") -> CompileResult:
    return CompileResult(
        ok=True,
        binary=Path("/sandbox/slot0/main"),
        standard_used=standard,
        attempts=(CompileAttempt(standard, True, ""),),
    )


def test_a_compile_failure_is_ce_and_nothing_is_run():
    failed = CompileResult(
        ok=False,
        binary=None,
        standard_used=None,
        attempts=tuple(CompileAttempt(s, False, "error") for s in ("gnu++20", "gnu++17")),
    )
    runner = FakeRunner([])
    result = judge.judge_source(
        "x", TESTS, LIMITS, 0, Path("/w"), compiler=lambda *a: failed, runner=runner
    )
    assert result.verdict is Verdict.CE
    assert result.tests_run == 0
    assert result.standard_used is None
    assert runner.calls == []


def test_judge_source_compiles_then_runs_and_records_the_standard():
    runner = FakeRunner([ok("1\n"), ok("2\n"), ok("3\n")])
    result = judge.judge_source(
        "x", TESTS, LIMITS, 0, Path("/w"), compiler=lambda *a: compiled("gnu++14"), runner=runner
    )
    assert result.verdict is Verdict.AC
    assert result.standard_used == "gnu++14"


def test_infra_error_from_the_compiler_propagates():
    def broken(*args):
        raise InfraError("g++ not found")

    with pytest.raises(InfraError):
        judge.judge_source(
            "x", TESTS, LIMITS, 0, Path("/w"), compiler=broken, runner=FakeRunner([])
        )
