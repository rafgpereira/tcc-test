"""First-order candidates: one site changed by one operator variant (spec FR-003, FR-003a).

Candidates are produced lazily, site by site (discovery order), operator by operator (the order of
``Site.eligible_operators``) and variant by variant (table order). Nothing is sampled: keeping "the
first 100" of a longer list is a prefix of this same stream, which is what makes the choice
reproducible without a seed (FR-011).
"""

from collections.abc import Iterator
from itertools import islice

from mutation.operators import apply, variant_count
from mutation.types import MutantCandidate, Site


def _all_first_order(problem_id: str, source: str, sites: list[Site]) -> Iterator[MutantCandidate]:
    for site in sites:
        for operator in site.eligible_operators:
            for variant in range(variant_count(operator)):
                mutated = apply(source, site, operator, variant)
                if mutated is None:
                    continue  # this variant does not apply to this site
                yield MutantCandidate(
                    problem_id=problem_id,
                    sites=(site,),
                    operators=((operator, variant),),
                    source=mutated,
                )


def first_order_candidates(
    problem_id: str, source: str, sites: list[Site], *, limit: int | None = None
) -> Iterator[MutantCandidate]:
    """The first-order candidates of ``source`` in the deterministic order; at most ``limit``."""
    stream = _all_first_order(problem_id, source, sites)
    return stream if limit is None else islice(stream, limit)
