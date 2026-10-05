"""The engine as the validation sees it: two callables and the compiler version.

Keeping it a tiny value lets the tests inject a fake engine (no root, no container) while the real
one is the module `sandbox`. The engine never knows the dataset (Principle IX); everything about
what a verdict MEANS for a problem lives in `dataset.validation`.
"""

import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from sandbox import isolation, judge
from sandbox.compiler import compile_cpp
from sandbox.types import CompileResult, ExecutionLimits, InfraError, SuiteVerdict, Test


@dataclass(frozen=True)
class Engine:
    gcc_version: str
    compile: Callable[[str, int], CompileResult]
    run_suite: Callable[[Path, Sequence[Test], ExecutionLimits, int], SuiteVerdict]


@dataclass(frozen=True)
class Judged:
    """A source judged over a suite: how it compiled and, when it did, how the suite ended."""

    compiled: CompileResult
    suite: SuiteVerdict | None  # None when the compilation failed in every standard


def judge_code(
    engine: Engine, source: str, tests: Sequence[Test], limits: ExecutionLimits, slot: int
) -> Judged:
    """Compile ``source`` and run the suite once (the first non-AC test decides)."""
    compiled = engine.compile(source, slot)
    if not compiled.ok or compiled.binary is None:
        return Judged(compiled, None)
    result = engine.run_suite(compiled.binary, tests, limits, slot)
    return Judged(compiled, _with_standard(result, compiled.standard_used))


def _with_standard(result: SuiteVerdict, standard: str | None) -> SuiteVerdict:
    if result.standard_used == standard:
        return result
    from dataclasses import replace

    return replace(result, standard_used=standard)


def gcc_version() -> str:
    try:
        done = subprocess.run(
            ["g++", "-dumpfullversion"], capture_output=True, text=True, check=False, timeout=30
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise InfraError(f"cannot run g++: {exc}") from exc
    if done.returncode != 0 or not done.stdout.strip():
        raise InfraError(f"g++ -dumpfullversion failed: {done.stderr.strip()}")
    return done.stdout.strip()


def real_engine() -> Engine:
    """The real engine. Each compilation starts in a fresh, empty workdir of the slot."""

    def compile_(source: str, slot: int) -> CompileResult:
        workdir = isolation.prepare_slot_workdir(slot)
        return compile_cpp(source, workdir, slot)

    return Engine(gcc_version=gcc_version(), compile=compile_, run_suite=judge.run_suite)
