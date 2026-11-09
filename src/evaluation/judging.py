"""Judge a suite against the AC (every test) and against one target (both oracles in one pass).

contracts/evaluation-api.md, ``evaluation.judging``. The engine's ``run_suite`` stops at the first
failing test, which serves neither the AC (FR-004) nor the two oracles (research R2), so the tests
are run one by one here over the same ``run_binary`` and the same verdict rules (``judge_test`` and
``outputs_equal``, the only comparison rule of the project). The engine itself is not changed.

A runtime error (RE, TLE or MLE) is run ``ERROR_RUNS`` times in total, always (FR-005a, FR-006a): it
only counts if every run is an error; otherwise the first run without an error decides and the test
is unstable. A wrong output is never repeated: the comparison is deterministic.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from evaluation import config
from evaluation.schemas.result import (
    NOT_DETECTED,
    AcResult,
    AcTest,
    Detection,
    RunOutcome,
    TargetResult,
)
from sandbox.judge import judge_test, outputs_equal
from sandbox.types import ExecutionLimits, RunResult, Test, Verdict

Run = Callable[[Path, bytes, ExecutionLimits, int], RunResult]

_ERRORS = {Verdict.RE: "RE", Verdict.TLE: "TLE", Verdict.MLE: "MLE"}


def error_kind(run: RunResult, limits: ExecutionLimits) -> str | None:
    """``RE``, ``TLE`` or ``MLE`` if the execution failed by itself, whatever the expected output."""
    return _ERRORS.get(judge_test(run, "", limits))


def stdout_of(run: RunResult) -> str:
    return run.stdout.decode("utf-8", errors="replace")


@dataclass(frozen=True)
class Attempted:
    """One test executed with the repetition rule."""

    final: RunResult  # the run that decides
    error: str | None  # the error kind when every run was an error (that of the first run)
    runs: tuple[RunResult, ...] | None  # the 3 runs, only when the first one was an error
    unstable: bool  # the first run was an error and a repetition was not


def run_with_repetition(
    run: Run, binary: Path, test: Test, limits: ExecutionLimits, slot: int
) -> Attempted:
    first = run(binary, test.input.encode("utf-8"), limits, slot)
    first_error = error_kind(first, limits)
    if first_error is None:
        return Attempted(first, None, None, False)
    runs = [first] + [
        run(binary, test.input.encode("utf-8"), limits, slot) for _ in range(config.ERROR_RUNS - 1)
    ]  # always made, even when the second one has no error
    for later in runs[1:]:
        if error_kind(later, limits) is None:
            return Attempted(later, None, tuple(runs), True)
    return Attempted(first, first_error, tuple(runs), False)


def _run_outcome(result: RunResult, expected: str, limits: ExecutionLimits) -> RunOutcome:
    kind = error_kind(result, limits)
    if kind is not None:
        verdict = kind
    else:
        verdict = "passed" if outputs_equal(expected, stdout_of(result)) else "wrong_output"
    return RunOutcome(
        verdict=verdict, cpu_time_s=result.cpu_time_s, peak_memory_bytes=result.peak_rss_bytes
    )


def judge_ac(
    binary: Path,
    tests: Sequence[Test],
    limits: ExecutionLimits,
    slot: int,
    *,
    run: Run,
    standard_used: str,
) -> AcResult:
    """Every test of the suite against the AC, never stopping early (FR-004, FR-005, FR-005a)."""
    results = []
    for index, test in enumerate(tests):
        attempted = run_with_repetition(run, binary, test, limits, slot)
        final = attempted.final
        if attempted.error is not None:
            verdict, actual = "runtime_error", ""
        else:
            actual = stdout_of(final)
            verdict = "passed" if outputs_equal(test.output, actual) else "wrong_output"
        runs = None
        if attempted.runs is not None:
            runs = [_run_outcome(r, test.output, limits) for r in attempted.runs]
        results.append(
            AcTest(
                index=index,
                verdict=verdict,
                error_kind=attempted.error,
                actual_output=actual,
                cpu_time_s=final.cpu_time_s,
                peak_memory_bytes=final.peak_rss_bytes,
                unstable=attempted.unstable,
                runs=runs,
            )
        )
    return AcResult(
        approved=all(t.verdict == "passed" for t in results),
        standard_used=standard_used,
        tests=results,
    )


def judge_target(
    binary: Path,
    tests: Sequence[Test],
    ac: AcResult,
    limits: ExecutionLimits,
    slot: int,
    *,
    run: Run,
    target: str,
    kind: str,
) -> TargetResult:
    """Both oracles of one target in a single pass (research R3; FR-006, FR-006a, FR-007, FR-008).

    Each test runs at most once (plus the repetitions of an error). The declared oracle compares
    with the output written in the suite; the corrected one with the AC's real output, only on the
    tests where the AC ended without an error. The pass stops when both oracles have detected the
    target or the tests are over; a test that only the corrected oracle still needs, and that is
    not valid for it, is not run at all.
    """
    declared: Detection | None = None
    corrected: Detection | None = None
    unstable: list[int] = []
    tests_run = 0
    for index, test in enumerate(tests):
        valid_corrected = ac.tests[index].verdict != "runtime_error"
        needs_declared = declared is None
        needs_corrected = corrected is None and valid_corrected
        if declared is not None and corrected is not None:
            break
        if not needs_declared and not needs_corrected:
            continue
        attempted = run_with_repetition(run, binary, test, limits, slot)
        tests_run += 1
        if attempted.unstable:
            unstable.append(index)
        if attempted.error is not None:
            found = Detection(detected=True, test_index=index, verdict=attempted.error)
            if needs_declared:
                declared = found
            if needs_corrected:
                corrected = found
            continue
        actual = stdout_of(attempted.final)
        if needs_declared and not outputs_equal(test.output, actual):
            declared = Detection(detected=True, test_index=index, verdict="wrong_output")
        if needs_corrected and not outputs_equal(ac.tests[index].actual_output, actual):
            corrected = Detection(detected=True, test_index=index, verdict="wrong_output")
    return TargetResult(
        target=target,
        kind=kind,
        compiled=True,
        declared=declared or NOT_DETECTED,
        corrected=corrected or NOT_DETECTED,
        tests_run=tests_run,
        unstable_tests=unstable,
    )


def not_compiled(target: str, kind: str) -> TargetResult:
    """A target that failed to compile in every standard (``CE``): nothing runs, never detected."""
    return TargetResult(
        target=target,
        kind=kind,
        compiled=False,
        declared=NOT_DETECTED,
        corrected=NOT_DETECTED,
        tests_run=0,
        unstable_tests=[],
    )
