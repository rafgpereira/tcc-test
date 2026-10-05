"""Verdict rules (decision D13, rules 1 and 2; contract: engine-api.md).

``outputs_equal`` is the ONLY comparison rule of the project. The token-based diagnostic of the
dataset module (`format_only`) never decides a verdict.
"""

import signal
from collections.abc import Callable, Sequence
from dataclasses import replace
from pathlib import Path

from sandbox.compiler import compile_cpp
from sandbox.runner import run_binary
from sandbox.types import (
    CompileResult,
    ExecutionLimits,
    RunResult,
    RunStatus,
    SuiteVerdict,
    Test,
    TestVerdict,
    Verdict,
)

_TRAILING_WHITESPACE = " \t\r\x0b\x0c"

Runner = Callable[[Path, bytes, ExecutionLimits, int], RunResult]
Compiler = Callable[[str, Path, int], CompileResult]


def _normalized_lines(text: str) -> list[str]:
    lines = [line.rstrip(_TRAILING_WHITESPACE) for line in text.split("\n")]
    while lines and not lines[-1]:
        lines.pop()
    return lines


def outputs_equal(expected: str, actual: str) -> bool:
    """Equal after ignoring whitespace at the end of each line and blank lines at the end of file.

    Anything else (leading or inner whitespace, case, blank lines in the middle) is a difference.
    """
    return _normalized_lines(expected) == _normalized_lines(actual)


def judge_test(run: RunResult, expected: str, limits: ExecutionLimits) -> Verdict:
    """The verdict of one execution: TLE, then MLE, then RE, then the comparison (AC or WA)."""
    if run.status is RunStatus.TIMEOUT or run.cpu_time_s > limits.time_limit_seconds:
        return Verdict.TLE
    if run.signal == signal.SIGABRT and b"bad_alloc" in run.stderr_tail:
        return Verdict.MLE
    if run.peak_rss_bytes >= limits.memory_limit_bytes:
        return Verdict.MLE
    if run.status is not RunStatus.OK:
        return Verdict.RE  # signal, non-zero exit or output limit
    actual = run.stdout.decode("utf-8", errors="replace")
    return Verdict.AC if outputs_equal(expected, actual) else Verdict.WA


def run_suite(
    binary: Path,
    tests: Sequence[Test],
    limits: ExecutionLimits,
    slot: int,
    *,
    runner: Runner = run_binary,
) -> SuiteVerdict:
    """Run the tests in the given order; the FIRST one that is not AC decides and stops (FR-012).

    ``InfraError`` from the runner propagates: it is never turned into a verdict.
    """
    max_cpu = 0.0
    max_memory = 0
    for index, test in enumerate(tests):
        run = runner(binary, test.input.encode("utf-8"), limits, slot)
        max_cpu = max(max_cpu, run.cpu_time_s)
        max_memory = max(max_memory, run.peak_rss_bytes)
        verdict = judge_test(run, test.output, limits)
        if verdict is not Verdict.AC:
            failure = TestVerdict(
                verdict=verdict,
                run=run,
                expected=test.output,
                actual=run.stdout.decode("utf-8", errors="replace"),
            )
            return SuiteVerdict(verdict, None, index, index + 1, max_cpu, max_memory, failure)
    return SuiteVerdict(Verdict.AC, None, None, len(tests), max_cpu, max_memory, None)


def judge_source(
    source: str,
    tests: Sequence[Test],
    limits: ExecutionLimits,
    slot: int,
    workdir: Path,
    *,
    compiler: Compiler = compile_cpp,
    runner: Runner = run_binary,
) -> SuiteVerdict:
    """Compile then run the suite; a compilation failure in every standard is ``CE``."""
    compiled = compiler(source, workdir, slot)
    if not compiled.ok or compiled.binary is None:
        return SuiteVerdict(Verdict.CE, None, None, 0, 0.0, 0, None)
    result = run_suite(compiled.binary, tests, limits, slot, runner=runner)
    return replace(result, standard_used=compiled.standard_used)
