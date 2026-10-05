"""Shared types of the execution engine (see specs/001-dataset-extraction/contracts/engine-api.md).

Infrastructure failure is expressed ONLY by ``InfraError``. It is never a verdict, so a broken
environment can never be mistaken for a TLE, MLE or RE of the code under evaluation (FR-010).
"""

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from sandbox.limits import STACK_LIMIT_BYTES, validate_stack_limit_bytes


class Verdict(str, Enum):
    """Verdict of a program over a test or a suite. There is deliberately no INFRA member."""

    AC = "AC"
    WA = "WA"
    TLE = "TLE"
    MLE = "MLE"
    RE = "RE"
    CE = "CE"


class RunStatus(str, Enum):
    OK = "OK"
    TIMEOUT = "TIMEOUT"
    SIGNALED = "SIGNALED"
    NONZERO_EXIT = "NONZERO_EXIT"
    OUTPUT_LIMIT = "OUTPUT_LIMIT"


class InfraError(Exception):
    """Failure of the environment (fork, full tmpfs, missing compiler, isolation setup, ...)."""


@dataclass(frozen=True)
class ExecutionLimits:
    """Limits of one execution. Time and memory have NO default: they come from the problem."""

    time_limit_seconds: float
    memory_limit_bytes: int
    stack_limit_bytes: int = STACK_LIMIT_BYTES

    def __post_init__(self) -> None:
        if not self.time_limit_seconds > 0:
            raise ValueError(f"time limit must be positive, got {self.time_limit_seconds}")
        if not self.memory_limit_bytes > 0:
            raise ValueError(f"memory limit must be positive, got {self.memory_limit_bytes}")
        validate_stack_limit_bytes(self.stack_limit_bytes)


@dataclass(frozen=True)
class CompileAttempt:
    standard: str
    ok: bool
    diagnostic: str


@dataclass(frozen=True)
class CompileResult:
    ok: bool
    binary: Path | None
    standard_used: str | None
    attempts: tuple[CompileAttempt, ...]


@dataclass(frozen=True)
class RunResult:
    status: RunStatus
    exit_code: int | None
    signal: int | None
    stdout: bytes
    stderr_tail: bytes
    cpu_time_s: float
    wall_time_s: float
    peak_rss_bytes: int


@dataclass(frozen=True)
class Test:
    """One official test: the input given on stdin and the expected output."""

    __test__ = False  # not a pytest test class

    input: str
    output: str


@dataclass(frozen=True)
class TestVerdict:
    """Result of one test."""

    __test__ = False  # not a pytest test class

    verdict: Verdict
    run: RunResult
    expected: str
    actual: str


@dataclass(frozen=True)
class SuiteVerdict:
    """Result of one program over an ordered suite; the first failing test decides."""

    verdict: Verdict
    standard_used: str | None
    deciding_index: int | None
    tests_run: int
    max_cpu_time_s: float
    max_memory_bytes: int
    first_failure: TestVerdict | None
