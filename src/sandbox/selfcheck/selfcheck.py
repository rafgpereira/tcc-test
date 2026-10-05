"""Suite of programs with a KNOWN verdict, run through the real engine (FR-010a, SC-013).

It is the entry gate of ``validate``: if the engine does not give the expected verdict to every
program (or gives different verdicts on repeated runs), no real code is validated. An
``InfraError`` is not a failed case: it propagates.
"""

import shutil
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from sandbox import isolation
from sandbox.judge import judge_source
from sandbox.types import ExecutionLimits, SuiteVerdict, Test, Verdict

PROGRAMS_DIR = Path(__file__).resolve().parent / "programs"
REPEATS = 2
SLOT = 0
MIB = 1024 * 1024


@dataclass(frozen=True)
class KnownCase:
    name: str
    program: str
    tests: tuple[Test, ...]
    limits: ExecutionLimits
    expected: Verdict
    expected_standard: str | None = None


@dataclass(frozen=True)
class CaseResult:
    name: str
    expected: Verdict
    obtained: Verdict
    standard_used: str | None
    stable: bool
    passed: bool


@dataclass(frozen=True)
class SelfCheckReport:
    ok: bool
    cases: tuple[CaseResult, ...]

    def render(self) -> str:
        lines = []
        for case in self.cases:
            status = "ok  " if case.passed else "FAIL"
            standard = f", standard {case.standard_used}" if case.standard_used else ""
            stability = "" if case.stable else ", UNSTABLE across runs"
            lines.append(
                f"{status} {case.name}: expected {case.expected.value}, "
                f"obtained {case.obtained.value}{standard}{stability}"
            )
        passed = sum(case.passed for case in self.cases)
        lines.append(f"selfcheck {'OK' if self.ok else 'FAIL'}: {passed}/{len(self.cases)} cases")
        return "\n".join(lines)


JudgeFn = Callable[[KnownCase, int], SuiteVerdict]


def default_cases() -> tuple[KnownCase, ...]:
    doubling = (Test("3\n", "6\n"), Test("5\n", "10\n"))
    return (
        KnownCase("ac", "ac.cpp", doubling, ExecutionLimits(2.0, 256 * MIB), Verdict.AC),
        KnownCase("wa", "wa.cpp", doubling, ExecutionLimits(2.0, 256 * MIB), Verdict.WA),
        KnownCase("tle", "tle.cpp", (Test("", ""),), ExecutionLimits(1.0, 256 * MIB), Verdict.TLE),
        KnownCase(
            "mle", "mle.cpp", (Test("", "1\n"),), ExecutionLimits(2.0, 128 * MIB), Verdict.MLE
        ),
        KnownCase("re", "re.cpp", (Test("", ""),), ExecutionLimits(2.0, 256 * MIB), Verdict.RE),
        KnownCase("ce", "ce.cpp", (Test("", ""),), ExecutionLimits(2.0, 256 * MIB), Verdict.CE),
        KnownCase(
            "deep_recursion",
            "deep_recursion.cpp",
            (Test("", "150000\n"),),
            ExecutionLimits(5.0, 1024 * MIB),
            Verdict.AC,
        ),
        KnownCase(
            "cascade_fallback",
            "cascade_fallback.cpp",
            (Test("", "ok\n"),),
            ExecutionLimits(2.0, 256 * MIB),
            Verdict.AC,
            "gnu++14",
        ),
        KnownCase(
            "stable",
            "stable.cpp",
            (Test("1 2 3\n", "6\n"), Test("10 20 30 40\n", "100\n"), Test("7\n", "7\n")),
            ExecutionLimits(2.0, 256 * MIB),
            Verdict.AC,
        ),
    )


def run_cases(
    cases: Sequence[KnownCase], judge: JudgeFn, repeats: int = REPEATS
) -> SelfCheckReport:
    """Run every case ``repeats`` times through ``judge`` and compare with the expected verdict."""
    results = []
    for case in cases:
        runs = [judge(case, SLOT) for _ in range(repeats)]
        first = runs[0]
        stable = all(
            (r.verdict, r.deciding_index, r.standard_used)
            == (first.verdict, first.deciding_index, first.standard_used)
            for r in runs
        )
        standard_ok = (
            case.expected_standard is None or first.standard_used == case.expected_standard
        )
        results.append(
            CaseResult(
                name=case.name,
                expected=case.expected,
                obtained=first.verdict,
                standard_used=first.standard_used,
                stable=stable,
                passed=stable and standard_ok and first.verdict is case.expected,
            )
        )
    return SelfCheckReport(ok=all(r.passed for r in results), cases=tuple(results))


def engine_judge(case: KnownCase, slot: int) -> SuiteVerdict:
    """Judge one program with the real engine, in a fresh workdir of the slot."""
    source = (PROGRAMS_DIR / case.program).read_text(encoding="utf-8")
    workdir = isolation.prepare_slot_workdir(slot)
    try:
        return judge_source(source, case.tests, case.limits, slot, workdir)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def selfcheck() -> SelfCheckReport:
    """The suite of known-verdict programs against the real engine (needs the `sandbox` service)."""
    return run_cases(default_cases(), engine_judge)
