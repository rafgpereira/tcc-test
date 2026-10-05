"""Selection and validation of the incorrect submissions that become `WA_1..WA_100` (FR-012 to FR-014).

A candidate is retained only if it compiles, ends with the verdict WA (the FIRST failing test of the
suite decides, and that test finishes within the limits with a wrong answer) and gives the same
verdict AND the same deciding test on two independent runs (stability, decision D13). Candidates
are walked in a deterministic order (seed 42, one stream per problem), identical texts count once,
and the results are CONSUMED in candidate order, never in completion order, so the retained set
is the same with 1 or N workers (FR-014, FR-025).
"""

from collections import Counter, deque
from collections.abc import Callable
from concurrent.futures import Future
from dataclasses import dataclass, field
from typing import Literal

from dataset import config
from dataset.persistence import store
from dataset.schemas.pool import RawProblem
from dataset.schemas.validacao import DecidingTest, WaValidation
from dataset.validation.ac import sha256_of
from dataset.validation.engine import Engine
from dataset.validation.suite import Suite
from sandbox.types import ExecutionLimits, Verdict

Kind = Literal["wa", "ce", "tle", "mle", "re", "ac", "unstable"]
_NOT_WA: dict[Verdict, Kind] = {
    Verdict.AC: "ac",  # passes every official test: it is not a failure
    Verdict.TLE: "tle",
    Verdict.MLE: "mle",
    Verdict.RE: "re",
}


@dataclass(frozen=True)
class Candidate:
    order: int  # position in the deterministic walk
    source_index: int  # position in the dataset's `incorrect_solutions`
    source: str


@dataclass(frozen=True)
class CandidateOutcome:
    candidate: Candidate
    kind: Kind
    validation: WaValidation | None  # only for a retained WA; `file` is set on retention


@dataclass(frozen=True)
class Retained:
    source: str
    validation: WaValidation


@dataclass
class WaResult:
    retained: list[Retained]
    stats: Counter
    consumed: int  # candidates whose outcome was consumed
    total: int
    insufficient: bool = field(default=False)  # fewer than 100 WA can still be reached


def select_candidates(raw: RawProblem) -> tuple[list[Candidate], int]:
    """Deduplicate (first text kept, in the dataset order) and shuffle with the problem's stream.

    Returns the candidates and the number of raw incorrect C++ submissions BEFORE deduplication.
    """
    seen: set[str] = set()
    unique: list[tuple[int, str]] = []
    for item in raw.incorrect_solutions:
        text = store.normalize_text(item.source)
        if text not in seen:
            seen.add(text)
            unique.append((item.index, text))
    config.seeded_random(f"wa:{raw.problem_id}").shuffle(unique)
    candidates = [Candidate(order, index, text) for order, (index, text) in enumerate(unique)]
    return candidates, len(raw.incorrect_solutions)


def evaluate_candidate(
    candidate: Candidate,
    suite: Suite,
    limits: ExecutionLimits,
    engine: Engine,
    slot: int,
    runs: int = config.STABILITY_RUNS,
) -> CandidateOutcome:
    """Judge one candidate. ``InfraError`` of the engine propagates: it is never an outcome."""
    compiled = engine.compile(candidate.source, slot)
    if not compiled.ok or compiled.binary is None:
        return CandidateOutcome(candidate, "ce", None)
    first = engine.run_suite(compiled.binary, suite.tests, limits, slot)
    if first.verdict is not Verdict.WA:
        return CandidateOutcome(candidate, _NOT_WA[first.verdict], None)
    max_cpu, max_memory = first.max_cpu_time_s, first.max_memory_bytes
    for _ in range(runs - 1):  # independent re-runs of the same binary
        again = engine.run_suite(compiled.binary, suite.tests, limits, slot)
        if (again.verdict, again.deciding_index) != (first.verdict, first.deciding_index):
            return CandidateOutcome(candidate, "unstable", None)
        max_cpu = max(max_cpu, again.max_cpu_time_s)
        max_memory = max(max_memory, again.max_memory_bytes)
    assert first.deciding_index is not None
    group, index = suite.location(first.deciding_index)
    validation = WaValidation(
        file="",  # WA_<n>.cpp, assigned when the candidate is retained
        sha256=sha256_of(candidate.source),
        verdict=Verdict.WA,
        standard_used=compiled.standard_used,
        max_cpu_time_s=max_cpu,
        max_memory_bytes=max_memory,
        tests_run=first.tests_run,
        source_index=candidate.source_index,
        deciding_test=DecidingTest(group=group, index=index),  # type: ignore[arg-type]
        stable=True,
    )
    return CandidateOutcome(candidate, "wa", validation)


Submit = Callable[[Candidate], "Future[CandidateOutcome]"]


def inline_submit(evaluate: Callable[[Candidate], CandidateOutcome]) -> Submit:
    """A submitter that evaluates in this process, at the moment of the call."""

    def submit(candidate: Candidate) -> Future:
        future: Future = Future()
        try:
            future.set_result(evaluate(candidate))
        except BaseException as exc:  # noqa: BLE001 - re-raised by `.result()` like an executor
            future.set_exception(exc)
        return future

    return submit


def collect_wa(
    candidates: list[Candidate],
    submit: Submit,
    *,
    needed: int = config.WA_PER_PROBLEM,
    window: int = 1,
) -> WaResult:
    """Walk the candidates, keep the first ``needed`` WA in candidate order, stop early if hopeless.

    Up to ``window`` candidates are in flight at once; their outcomes are consumed strictly in
    order, so the result does not depend on how fast each worker is.
    """
    stats: Counter = Counter()
    retained: list[Retained] = []
    total = len(candidates)
    if total < needed:
        return WaResult(retained, stats, 0, total, insufficient=True)
    pending: deque[Future] = deque()
    next_index = consumed = 0
    insufficient = False
    try:
        while consumed < total:
            while next_index < total and len(pending) < max(1, window):
                pending.append(submit(candidates[next_index]))
                next_index += 1
            outcome: CandidateOutcome = pending.popleft().result()
            consumed += 1
            stats[outcome.kind] += 1
            if outcome.validation is not None:
                named = outcome.validation.model_copy(
                    update={"file": f"WA_{len(retained) + 1}.cpp"}
                )
                retained.append(Retained(outcome.candidate.source, named))
            if len(retained) >= needed:
                break
            if len(retained) + (total - consumed) < needed:
                insufficient = True  # even if every remaining candidate were WA
                break
    finally:
        for future in pending:
            future.cancel()
    return WaResult(retained, stats, consumed, total, insufficient)
