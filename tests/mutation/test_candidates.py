"""Tests for the first-order candidates: one site, one operator, one variant (FR-003, FR-003a)."""

import hashlib

from mutation.candidates import first_order_candidates
from mutation.operators import apply
from mutation.sites import find_sites

SMALL = "int a, b;\nint main() { return a < b && b + 1 > a; }\n"


def rich_source(lines: int = 40) -> str:
    """A file with far more than 100 first-order candidates."""
    body = "\n".join(f"  x{i} = a{i} < b{i} + {i} * c;" for i in range(lines))
    return f"int a, b, c, x0;\nint main() {{\n{body}\n}}\n"


def digests(candidates) -> list[str]:
    return [hashlib.sha256(c.source.encode("utf-8")).hexdigest() for c in candidates]


def test_candidates_walk_site_by_site_and_variant_by_variant():
    sites = find_sites(SMALL)
    expected = []
    for site in sites:
        for operator in site.eligible_operators:
            for variant in range(6):
                text = apply(SMALL, site, operator, variant)
                if text is not None:
                    expected.append((site, operator, variant, text))
    got = list(first_order_candidates("1_A", SMALL, sites))
    assert [(c.sites[0], *c.operators[0], c.source) for c in got] == expected
    assert len(got) > 10


def test_a_first_order_candidate_has_one_site_and_one_operator():
    for candidate in first_order_candidates("1_A", SMALL, find_sites(SMALL)):
        assert candidate.problem_id == "1_A"
        assert candidate.order == 1 and len(candidate.operators) == 1
        assert candidate.source != SMALL


def test_truncation_keeps_exactly_the_first_hundred_in_discovery_order():
    source = rich_source()
    sites = find_sites(source)
    everything = list(first_order_candidates("1_A", source, sites))
    assert len(everything) > 300
    kept = list(first_order_candidates("1_A", source, sites, limit=100))
    assert len(kept) == 100
    assert kept == everything[:100]  # a prefix, never a sample
    discovery = [c.sites[0].discovery_index for c in kept]
    assert discovery == sorted(discovery)


def test_two_runs_give_the_same_candidates_byte_for_byte():
    source = rich_source()
    first = list(first_order_candidates("1_A", source, find_sites(source), limit=100))
    second = list(first_order_candidates("1_A", source, find_sites(source), limit=100))
    assert digests(first) == digests(second)


def test_the_generator_is_lazy():
    source = rich_source(2000)
    stream = first_order_candidates("1_A", source, find_sites(source))
    assert next(stream).order == 1  # the first candidate does not wait for the rest to be built


def test_a_file_without_sites_has_no_candidates():
    assert list(first_order_candidates("1_A", "int main() { return 0; }\n", [])) == []
