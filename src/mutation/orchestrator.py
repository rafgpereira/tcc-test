"""Select the mutants of ONE problem (contracts/mutation-api.md, ``select_mutants``).

First-order candidates are tried in discovery order until the quota is met, each one through the
validation of ``mutation.validation``; the first ``quota`` valid and distinct ones are kept and the
rest of the stream is simply not consumed (spec FR-003a: a prefix, never a sample). No randomness
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
from mutation.sites import find_sites
from mutation.types import (
    DiscardRecord,
    Mutant,
    MutantCandidate,
    Selection,
)
from mutation.validation import sha256_of, validate
from sandbox.types import ExecutionLimits, Verdict

Progress = Callable[[str], None]


class HigherOrderNotAvailable(NotImplementedError):
    """The first order did not reach the quota and combining mutations is not implemented yet."""


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
    progress: Progress | None = None,
) -> Selection:
    """Validate first-order candidates in order and keep the first ``quota`` that are accepted."""
    seen = {sha256_of(source)}
    accepted: list[Mutant] = []
    discards: list[DiscardRecord] = []

    def consume(stream: Iterable[MutantCandidate]) -> None:
        for candidate in stream:
            if len(accepted) >= quota:
                return
            outcome = validate(candidate, suite, limits, slot, engine=engine, seen=seen)
            if outcome.discard_reason is not None:
                discards.append(DiscardRecord(problem_id, candidate.order, outcome.discard_reason))
                continue
            accepted.append(_as_mutant(candidate, len(accepted) + 1))
            if progress is not None:
                progress(f"  {problem_id}: {len(accepted)}/{quota} mutants")

    consume(first_order_candidates(problem_id, source, find_sites(source)))
    if len(accepted) < quota:
        raise HigherOrderNotAvailable(
            f"{problem_id}: first order reached {len(accepted)} of {quota} mutants and the "
            "combination of mutations (higher order) is not implemented yet"
        )
    return Selection(tuple(accepted), None, tuple(discards))
