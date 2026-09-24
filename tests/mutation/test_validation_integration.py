"""Integration test: candidates of a tiny program are compiled and run for real (service `sandbox`).

Nothing here is faked: the mutants go through the real engine (GCC 13.2, isolation, limits), so this
is the test that a mutant known to be wrong is accepted with the verdict WA and that the other
outcomes of the funnel are what the engine really says.
"""

import pytest

from dataset.validation.engine import real_engine
from dataset.validation.suite import Suite
from mutation.candidates import first_order_candidates
from mutation.sites import find_sites
from mutation.types import DiscardReason
from mutation.validation import sha256_of, validate
from sandbox import isolation
from sandbox.types import ExecutionLimits, Test, Verdict

pytestmark = pytest.mark.integration

SLOT = 0
ORIGINAL = """#include <iostream>
int main() {
    int n;
    std::cin >> n;
    int s = 0;
    for (int i = 0; i < n; i++) s += i;
    std::cout << s << "\\n";
    return 0;
}
"""
SUITE = Suite(
    tests=(Test("5\n", "10\n"), Test("3\n", "3\n"), Test("0\n", "0\n")),
    locations=(("public_tests", 0), ("private_tests", 0), ("generated_tests", 0)),
)
LIMITS = ExecutionLimits(time_limit_seconds=2.0, memory_limit_bytes=256 * 1024 * 1024)


@pytest.fixture(scope="module")
def engine():
    isolation.prepare_slot_workdir(SLOT)
    return real_engine()


def candidate_with(text_from: str, text_to: str):
    """The first-order candidate whose source is ORIGINAL with ``text_from`` replaced by ``text_to``."""
    wanted = ORIGINAL.replace(text_from, text_to, 1)
    for candidate in first_order_candidates("1_A", ORIGINAL, find_sites(ORIGINAL)):
        if candidate.source == wanted:
            return candidate
    raise AssertionError(f"no candidate turns {text_from!r} into {text_to!r}")


def judge(engine, candidate):
    return validate(candidate, SUITE, LIMITS, SLOT, engine=engine, seen={sha256_of(ORIGINAL)})


def test_the_original_program_really_passes_the_suite(engine):
    compiled = engine.compile(ORIGINAL, SLOT)
    assert compiled.ok
    assert engine.run_suite(compiled.binary, SUITE.tests, LIMITS, SLOT).verdict is Verdict.AC


def test_a_known_wrong_mutant_is_accepted_with_verdict_wa(engine):
    outcome = judge(engine, candidate_with("i < n", "i <= n"))  # sums one term too many
    assert outcome.accepted and outcome.verdict is Verdict.WA
    assert outcome.deciding_index == 0  # the first test (n = 5) already differs


def test_a_loop_that_never_runs_is_also_wrong(engine):
    outcome = judge(engine, candidate_with("i < n", "i >= n"))
    assert outcome.accepted and outcome.verdict is Verdict.WA


def test_a_mutant_that_behaves_like_the_original_is_equivalent(engine):
    # `i != n` stops at the same point for every n of the suite (5, 3, 0)
    outcome = judge(engine, candidate_with("i < n", "i != n"))
    assert outcome.discard_reason is DiscardReason.EQUIVALENT


def test_a_mutant_that_does_not_compile_is_a_compile_error(engine):
    outcome = judge(engine, candidate_with("std::cin >> n", "std::cin << n"))
    assert outcome.discard_reason is DiscardReason.COMPILE_ERROR
