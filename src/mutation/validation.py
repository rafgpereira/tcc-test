"""Validation of ONE candidate with the shared execution engine (spec FR-005 to FR-007).

The engine is the one of the ``sandbox`` module, unchanged: same flags, same standard cascade, same
limits (read from the problem by the caller) and same comparison rule as when the dataset was
validated. A candidate goes through the cheap checks first and pays for the expensive one (the
stability re-runs) only if it survives them:

1. duplicate text (already seen for this problem): discarded before anything is compiled;
2. compiles in some standard of the cascade;
3. first run of the official suite: ``TLE``, ``MLE`` and ``RE`` are discarded as such, ``AC`` (all
   tests pass, so the mutant behaves like the original) is discarded as equivalent;
4. only a ``WA`` is re-run, to check that the same verdict AND the same deciding test come back
   ``STABILITY_RUNS`` times in all (decision D5).

The mutant is compiled once and the same binary is re-run. The instability being guarded against
is that of the runtime (a program that reads uninitialized memory, sits at the time limit), which
recompiling would not exercise any better.

``InfraError`` of the engine propagates: a broken environment is never a verdict (FR-010 of the
dataset feature).
"""

import hashlib
from pathlib import Path

from dataset.validation.engine import Engine
from dataset.validation.suite import Suite
from mutation import config
from mutation.types import DiscardReason, MutantCandidate, ValidationOutcome
from sandbox.types import ExecutionLimits, SuiteVerdict, Verdict

_NOT_WA: dict[Verdict, DiscardReason] = {
    Verdict.TLE: DiscardReason.TLE,
    Verdict.MLE: DiscardReason.MLE,
    Verdict.RE: DiscardReason.RE,
    Verdict.AC: DiscardReason.EQUIVALENT,  # passes the whole official suite: same behavior
}


def sha256_of(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def confirm_stability(
    engine: Engine,
    binary: Path,
    suite: Suite,
    limits: ExecutionLimits,
    slot: int,
    first: SuiteVerdict,
    *,
    runs: int = config.STABILITY_RUNS,
) -> bool:
    """Re-run the compiled candidate until ``runs`` executions in total (``first`` included) agree.

    Agreement is the same verdict AND the same deciding test. Returns at the first disagreement.
    """
    for _ in range(runs - 1):
        again = engine.run_suite(binary, suite.tests, limits, slot)
        if (again.verdict, again.deciding_index) != (first.verdict, first.deciding_index):
            return False
    return True


def validate(
    candidate: MutantCandidate,
    suite: Suite,
    limits: ExecutionLimits,
    slot: int,
    *,
    engine: Engine,
    seen: set[str],
    runs: int = config.STABILITY_RUNS,
) -> ValidationOutcome:
    """Judge a candidate: accepted with verdict ``WA``, or discarded with the reason.

    ``seen`` holds the hashes of every text already evaluated for the problem (the original
    ``AC_ref.cpp`` included); the candidate's hash is added to it, whatever the outcome, so no text
    is ever evaluated twice.
    """
    digest = sha256_of(candidate.source)
    if digest in seen:
        return ValidationOutcome(discard_reason=DiscardReason.DUPLICATE)
    seen.add(digest)
    compiled = engine.compile(candidate.source, slot)
    if not compiled.ok or compiled.binary is None:
        return ValidationOutcome(discard_reason=DiscardReason.COMPILE_ERROR)
    first = engine.run_suite(compiled.binary, suite.tests, limits, slot)
    if first.verdict is not Verdict.WA:
        return ValidationOutcome(discard_reason=_NOT_WA[first.verdict])
    if not confirm_stability(engine, compiled.binary, suite, limits, slot, first, runs=runs):
        return ValidationOutcome(discard_reason=DiscardReason.UNSTABLE)
    return ValidationOutcome(verdict=Verdict.WA, deciding_index=first.deciding_index)
