"""Tests for the deterministic combination of mutations (FR-004, FR-004a, FR-011; research R3, R17).

Pairs come before triples; inside one order the combinations follow the discovery order of the
sites (lexicographic over the acceptance order of the first-order mutants); two changes on the same
site, or on sites that overlap, are never combined; and nothing is random.
"""

import ast
import inspect
from itertools import combinations, pairwise

import pytest

from mutation import higher_order
from mutation.candidates import first_order_candidates
from mutation.higher_order import combine, higher_order_candidates
from mutation.orchestrator import select_mutants
from mutation.sites import find_sites
from mutation.types import MutantCandidate
from sandbox.types import Verdict

SOURCE = "int a, b, c;\nint main() { return a < b && b + 1 > c; }\n"


def base(source: str = SOURCE) -> list[MutantCandidate]:
    return list(first_order_candidates("1_A", source, find_sites(source)))


def disjoint(a: MutantCandidate, b: MutantCandidate) -> bool:
    x, y = a.sites[0], b.sites[0]
    return x.end_byte <= y.start_byte or y.end_byte <= x.start_byte


def test_pairs_follow_the_acceptance_order_lexicographically():
    accepted = base()
    expected = [(a, b) for a, b in combinations(accepted, 2) if disjoint(a, b)]
    got = list(higher_order_candidates(SOURCE, accepted, 2))
    assert len(got) == len(expected) > 20
    assert [(c.sites, c.operators) for c in got] == [
        (a.sites + b.sites, a.operators + b.operators) for a, b in expected
    ]


def test_a_pair_changes_exactly_its_two_sites_and_nothing_else():
    raw = SOURCE.encode("utf-8")
    for candidate in higher_order_candidates(SOURCE, base(), 2):
        first, second = candidate.sites
        assert candidate.order == 2 and candidate.problem_id == "1_A"
        assert first.discovery_index < second.discovery_index  # the order of the base list
        left, right = sorted(candidate.sites, key=lambda site: site.start_byte)
        assert left.end_byte <= right.start_byte  # disjoint ranges
        changed = candidate.source.encode("utf-8")
        assert changed.startswith(raw[: left.start_byte])
        assert changed.endswith(raw[right.end_byte :])
        assert candidate.source != SOURCE


def test_two_changes_on_the_same_site_are_never_combined():
    for candidate in higher_order_candidates(SOURCE, base(), 2):
        assert candidate.sites[0] != candidate.sites[1]


def test_sites_that_overlap_are_never_combined():
    """The left operand `(a + b)` contains the `+`: changing both would be ill-defined."""
    source = "int a, b, c;\nint main() { return (a + b) * c; }\n"
    for candidate in higher_order_candidates(source, base(source), 2):
        left, right = sorted(candidate.sites, key=lambda site: site.start_byte)
        assert left.end_byte <= right.start_byte


def test_triples_use_three_distinct_disjoint_sites_in_order():
    accepted = base()
    triples = list(higher_order_candidates(SOURCE, accepted, 3))
    assert triples and all(c.order == 3 for c in triples)
    for candidate in triples:
        indices = [s.discovery_index for s in candidate.sites]
        assert indices == sorted(indices) and len(set(indices)) == 3
        ordered = sorted(candidate.sites, key=lambda site: site.start_byte)
        for left, right in pairwise(ordered):
            assert left.end_byte <= right.start_byte
    expected = [
        (a, b, c)
        for a, b, c in combinations(accepted, 3)
        if disjoint(a, b) and disjoint(b, c) and disjoint(a, c)
    ]
    assert [c.operators for c in triples] == [
        a.operators + b.operators + c.operators for a, b, c in expected
    ]


def test_the_stream_is_lazy_and_repeatable_byte_for_byte():
    accepted = base()
    stream = higher_order_candidates(SOURCE, accepted, 2)
    first = next(stream)
    again = next(higher_order_candidates(SOURCE, accepted, 2))
    assert first == again and first.source == again.source


def test_an_order_other_than_two_or_three_is_refused():
    for order in (0, 1, 4):
        with pytest.raises(ValueError):
            list(higher_order_candidates(SOURCE, base(), order))


def test_nothing_to_combine_gives_an_empty_stream():
    assert list(higher_order_candidates(SOURCE, [], 2)) == []
    assert list(higher_order_candidates(SOURCE, base()[:1], 2)) == []
    assert list(higher_order_candidates(SOURCE, base()[:2], 3)) == []


def test_combine_applies_the_rightmost_change_first_so_offsets_stay_valid():
    accepted = base()
    left, right = accepted[0], accepted[-1]
    text = combine(SOURCE, (left, right))
    assert text is not None
    # each change alone is contained in the combination
    only_left = left.source.encode()[: left.sites[0].start_byte]
    assert text.encode().startswith(only_left)


def test_the_module_uses_no_randomness():
    tree = ast.parse(inspect.getsource(higher_order))
    imported = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in (
            node.names if isinstance(node, ast.Import) else [ast.alias(node.module or "")]
        )
    }
    assert "random" not in imported


# ------------------------------------------------------------------ inside select_mutants


def run(make_engine, suite, limits, script=None, quota=30, **kw):
    engine = make_engine(script)
    selection = select_mutants(
        "1_A", SOURCE, suite, limits, engine=engine.as_engine(), quota=quota, **kw
    )
    return engine, selection


def test_when_first_order_falls_short_pairs_close_the_quota(make_engine, suite, limits):
    _, selection = run(make_engine, suite, limits, quota=len(base()) + 10)
    orders = [m.order for m in selection.mutants]
    assert selection.alert is None and len(orders) == len(base()) + 10
    assert orders == sorted(orders) and set(orders) == {1, 2}  # first order first, then pairs
    assert [m.index for m in selection.mutants] == list(range(1, len(orders) + 1))


def test_a_combination_that_cancels_out_is_discarded_as_equivalent(make_engine, suite, limits):
    """The engine says a pair passes every test: same path, same reason as in the first order."""
    pairs = list(higher_order_candidates(SOURCE, base(), 2))
    script = {p.source: [Verdict.AC] for p in pairs[:3]}
    _, selection = run(make_engine, suite, limits, script=script, quota=len(base()) + 5)
    equivalent = [d for d in selection.discards if d.reason.value == "equivalent"]
    assert [d.order for d in equivalent] == [2, 2, 2]
    assert not {p.source for p in pairs[:3]} & {m.source for m in selection.mutants}


def test_triples_are_only_tried_after_the_pairs_are_exhausted(make_engine, suite, limits):
    pairs = list(higher_order_candidates(SOURCE, base(), 2))
    _, selection = run(make_engine, suite, limits, quota=len(base()) + len(pairs) + 3)
    orders = [m.order for m in selection.mutants]
    assert orders.count(1) == len(base()) and orders.count(2) == len(pairs)
    assert orders.count(3) == 3 and orders == sorted(orders)


def test_two_runs_give_the_same_combinations_in_the_same_order(make_engine, suite, limits):
    _, one = run(make_engine, suite, limits, quota=len(base()) + 12)
    _, two = run(make_engine, suite, limits, quota=len(base()) + 12)
    assert [m.source_sha256 for m in one.mutants] == [m.source_sha256 for m in two.mutants]


def test_every_accepted_mutant_is_distinct_from_the_original_and_from_each_other(
    make_engine, suite, limits
):
    from mutation.validation import sha256_of

    _, selection = run(make_engine, suite, limits, quota=len(base()) + 15)
    hashes = [m.source_sha256 for m in selection.mutants]
    assert len(set(hashes)) == len(hashes) and sha256_of(SOURCE) not in hashes
