"""Deterministic combination of first-order mutants into pairs and triples (spec FR-004, FR-004a).

Used only when the first order does not reach the quota. The base is the list of first-order mutants
that were ACCEPTED, in the order they were accepted (which is the discovery order of their sites in
the syntax tree, research R3). Combinations are taken in the lexicographic order of that list
(``itertools.combinations``): the first mutant changes slowest, so ``(1, 2)``, ``(1, 3)`` ... come
before ``(2, 3)``. There is no search, no sampling and no randomness anywhere (FR-011): the same
list always gives the same stream, byte for byte.

Two rules keep a combination well defined. The changes must be on DIFFERENT sites, and on sites
whose byte ranges do not overlap: the left operand ``(a + b)`` of ``(a + b) * c`` contains the ``+``
site, and changing both at once has no meaning. A combination is then applied from the rightmost
site to the leftmost, so the offsets of the sites still to be applied stay valid.

Every combination goes through the same validation as any other candidate (compile, limits,
equivalence, stability): a pair whose two changes cancel out is discarded as equivalent by the
usual rule, with no logic of its own.
"""

from collections.abc import Iterator, Sequence
from itertools import combinations, pairwise
from typing import Protocol

from mutation import config
from mutation.operators import apply
from mutation.types import MutantCandidate, MutationOperator, Site


class Mutation(Protocol):
    """What a combination needs from a first-order mutant (a ``Mutant`` or a ``MutantCandidate``)."""

    problem_id: str
    sites: tuple[Site, ...]
    operators: tuple[tuple[MutationOperator, int], ...]


def _disjoint(sites: Sequence[Site]) -> bool:
    ordered = sorted(sites, key=lambda site: site.start_byte)
    return all(left.end_byte <= right.start_byte for left, right in pairwise(ordered))


def combine(source: str, parts: Sequence[Mutation]) -> str | None:
    """``source`` with every change of ``parts`` applied, or ``None`` if one does not apply."""
    changes = [
        (site, operator, variant)
        for part in parts
        for site, (operator, variant) in zip(part.sites, part.operators, strict=True)
    ]
    text = source
    for site, operator, variant in sorted(changes, key=lambda change: -change[0].start_byte):
        mutated = apply(text, site, operator, variant)
        if mutated is None:
            return None
        text = mutated
    return text


def higher_order_candidates(
    source: str, accepted: Sequence[Mutation], order: int
) -> Iterator[MutantCandidate]:
    """Pairs (``order`` 2) or triples (``order`` 3) of the accepted first-order mutants, in order."""
    if not 2 <= order <= config.HOM_MAX_ORDER:
        raise ValueError(f"order must be between 2 and {config.HOM_MAX_ORDER}, got {order}")
    for parts in combinations(accepted, order):
        sites = tuple(site for part in parts for site in part.sites)
        if len(sites) != order or not _disjoint(sites):
            continue  # a mutant that was not first order, or overlapping sites
        text = combine(source, parts)
        if text is None:
            continue
        yield MutantCandidate(
            problem_id=parts[0].problem_id,
            sites=sites,
            operators=tuple(pair for part in parts for pair in part.operators),
            source=text,
        )
