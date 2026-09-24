"""Select the mutants of ONE problem (contracts/mutation-api.md, ``select_mutants``).

First-order candidates are tried in discovery order until the quota is met, each one through the
validation of ``mutation.validation``; the first ``quota`` valid and distinct ones are kept and the
rest of the stream is simply not consumed (spec FR-003a: a prefix, never a sample). If the first
order falls short, pairs and then triples of the accepted first-order mutants are tried in the
deterministic order of ``mutation.higher_order`` (spec FR-004); if that is not enough either, the
problem is excluded with an alert instead of being kept with fewer than 100 (FR-009). No randomness
anywhere: the outcome depends only on the text of ``AC_ref.cpp``, the official suite and the
verdicts of the engine (spec FR-011).

The set of hashes of every text evaluated for the problem starts with the original file, so a
candidate can never be equal to the original or to another candidate (spec FR-005a).
"""

from collections.abc import Callable, Iterable

from dataset.validation.engine import Engine
from dataset.validation.suite import Suite
from mutation import config
from mutation.candidates import first_order_candidates
from mutation.higher_order import higher_order_candidates
from mutation.sites import find_sites
from mutation.types import (
    DiscardRecord,
    ExclusionAlert,
    Mutant,
    MutantCandidate,
    Selection,
)
from mutation.validation import sha256_of, validate
from sandbox.types import ExecutionLimits, Verdict

Progress = Callable[[str], None]


def _as_mutant(candidate: MutantCandidate, index: int) -> Mutant:
    return Mutant(
        problem_id=candidate.problem_id,
        index=index,
        order=candidate.order,
        sites=candidate.sites,
        operators=candidate.operators,
        source=candidate.source,
        source_sha256=sha256_of(candidate.source),
        verdict=Verdict.WA,
        stability_runs=config.STABILITY_RUNS,
    )


def select_mutants(
    problem_id: str,
    source: str,
    suite: Suite,
    limits: ExecutionLimits,
    *,
    engine: Engine,
    slot: int = 0,
    quota: int = config.MUTANTS_PER_PROBLEM,
    max_attempts: int | None = None,
    progress: Progress | None = None,
) -> Selection:
    """The mutants of one problem: first order, then pairs, then triples, until ``quota``.

    ``max_attempts`` (``None`` = no limit) caps how many higher-order candidates are tried; when it
    is exhausted the problem ends like one that ran out of combinations. If the quota is still not
    met, the result carries an ``ExclusionAlert`` and the mutants reached so far (spec FR-009).
    """
    seen = {sha256_of(source)}
    accepted: list[Mutant] = []
    discards: list[DiscardRecord] = []
    attempts = 0

    def consume(stream: Iterable[MutantCandidate], *, counted: bool) -> None:
        nonlocal attempts
        for candidate in stream:
            if len(accepted) >= quota:
                return
            if counted:
                if max_attempts is not None and attempts >= max_attempts:
                    return
                attempts += 1
            outcome = validate(candidate, suite, limits, slot, engine=engine, seen=seen)
            if outcome.discard_reason is not None:
                discards.append(DiscardRecord(problem_id, candidate.order, outcome.discard_reason))
                continue
            accepted.append(_as_mutant(candidate, len(accepted) + 1))
            if progress is not None:
                progress(f"  {problem_id}: {len(accepted)}/{quota} mutants")

    consume(first_order_candidates(problem_id, source, find_sites(source)), counted=False)
    highest = 1
    base = tuple(accepted)  # pairs and triples combine FIRST-order mutants only
    for order in range(2, config.HOM_MAX_ORDER + 1):
        if len(accepted) >= quota or (max_attempts is not None and attempts >= max_attempts):
            break
        highest = order
        consume(higher_order_candidates(source, base, order), counted=True)
    alert = None
    if len(accepted) < quota:
        alert = ExclusionAlert(problem_id, len(accepted), highest)
    return Selection(tuple(accepted), alert, tuple(discards))
