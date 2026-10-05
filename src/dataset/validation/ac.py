"""Choice and validation of `AC_ref` (FR-011, FR-011b, decisions D8 and D13).

`AC_ref` is the first correct C++ solution in the dataset's original order, run through the same
engine as everything else. ANY failure interrupts the problem at once and becomes a triage record:
no second solution is tried, nothing is discarded silently, and there is no tolerance threshold.
Infrastructure failure is not an AC failure: `InfraError` propagates.
"""

import hashlib
from dataclasses import dataclass

from dataset.persistence import store
from dataset.schemas.pool import RawProblem
from dataset.schemas.validacao import CodeValidation, Divergence, TriageRecord, truncate_text
from dataset.validation.engine import Engine, Judged, judge_code
from dataset.validation.suite import Suite
from sandbox.types import ExecutionLimits, RunResult, Verdict

AC_REF_FILE = "AC_ref.cpp"
AC_CANDIDATE_FILE = "AC_candidate.cpp"


def sha256_of(source: str) -> str:
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def choose_ac_source(raw: RawProblem) -> str:
    """The first correct C++ solution in the original order, normalized like the persisted file."""
    if not raw.correct_solutions:
        raise ValueError(f"{raw.problem_id}: no correct C++ solution to choose `AC_ref` from")
    return store.normalize_text(raw.correct_solutions[0])


@dataclass(frozen=True)
class AcOutcome:
    source: str
    code: CodeValidation
    triage: TriageRecord | None

    @property
    def passed(self) -> bool:
        return self.triage is None


def _code_validation(source: str, file_name: str, judged: Judged) -> CodeValidation:
    suite = judged.suite
    if suite is None:  # compilation failed in every standard
        return CodeValidation(
            file=file_name,
            sha256=sha256_of(source),
            verdict=Verdict.CE,
            standard_used=None,
            max_cpu_time_s=0.0,
            max_memory_bytes=0,
            tests_run=0,
        )
    return CodeValidation(
        file=file_name,
        sha256=sha256_of(source),
        verdict=suite.verdict,
        standard_used=judged.compiled.standard_used,
        max_cpu_time_s=suite.max_cpu_time_s,
        max_memory_bytes=suite.max_memory_bytes,
        tests_run=suite.tests_run,
    )


def _run_diagnostic(run: RunResult, limits: ExecutionLimits) -> str:
    parts = [
        f"status {run.status.value}, exit code {run.exit_code}, signal {run.signal}",
        f"CPU time {run.cpu_time_s:.3f} s (limit {limits.time_limit_seconds} s)",
        f"peak memory {run.peak_rss_bytes} bytes (limit {limits.memory_limit_bytes} bytes)",
    ]
    tail = run.stderr_tail.decode("utf-8", errors="replace").strip()
    if tail:
        parts.append(f"stderr (tail):\n{tail}")
    return "\n".join(parts)


def _triage(
    problem_id: str,
    stage: str,
    judged: Judged,
    suite: Suite,
    limits: ExecutionLimits,
) -> TriageRecord:
    verdict_suite = judged.suite
    if verdict_suite is None:
        diagnostics = "\n".join(
            f"[{attempt.standard}] {attempt.diagnostic}".rstrip()
            for attempt in judged.compiled.attempts
        )
        return TriageRecord(
            problem_id=problem_id,
            stage=stage,
            verdict="CE",
            reason=f"AC does not compile in any of the four standards (verdict CE, stage {stage})",
            divergence=None,
            engine_diagnostic=truncate_text(diagnostics)[0],
        )
    failure = verdict_suite.first_failure
    assert failure is not None and verdict_suite.deciding_index is not None
    group, index = suite.location(verdict_suite.deciding_index)
    verdict = verdict_suite.verdict.value
    where = f"{group}[{index}]"
    if verdict_suite.verdict is Verdict.WA:
        return TriageRecord(
            problem_id=problem_id,
            stage=stage,
            verdict="WA",
            reason=f"AC diverged from the official answer on {where} (verdict WA, stage {stage})",
            divergence=Divergence.build(
                group,  # type: ignore[arg-type]
                index,
                input_=suite.tests[verdict_suite.deciding_index].input,
                expected=failure.expected,
                actual=failure.actual,
            ),
            engine_diagnostic=None,
        )
    return TriageRecord(
        problem_id=problem_id,
        stage=stage,
        verdict=verdict,
        reason=f"AC ended with {verdict} on {where} (stage {stage})",
        divergence=None,
        engine_diagnostic=truncate_text(_run_diagnostic(failure.run, limits))[0],
    )


def run_ac(
    problem_id: str,
    source: str,
    suite: Suite,
    limits: ExecutionLimits,
    engine: Engine,
    slot: int,
    *,
    stage: str,
    file_name: str,
) -> AcOutcome:
    """Run ``source`` over the whole official suite; any failure yields a triage record."""
    judged = judge_code(engine, source, suite.tests, limits, slot)
    code = _code_validation(source, file_name, judged)
    if code.verdict is Verdict.AC:
        return AcOutcome(source, code, None)
    return AcOutcome(source, code, _triage(problem_id, stage, judged, suite, limits))
