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
from mutation.types import DiscardReason, MutantCandidate
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
    # The generator no longer offers stream mutations (they never compile), so the candidate that
    # is broken on purpose is built by hand.
    source = ORIGINAL.replace("std::cin >> n", "std::cin << n")
    candidate = MutantCandidate("1_A", (), (), source)
    assert judge(engine, candidate).discard_reason is DiscardReason.COMPILE_ERROR


def test_the_real_pool_gives_the_same_selection_as_running_in_this_process(engine):
    """Two forked workers, each in its own slot, against the in-process runtime (real engine)."""
    from mutation import runtime

    tasks = [
        runtime.ProblemTask(f"1_{letter}", ORIGINAL, SUITE, LIMITS, quota=4) for letter in "AB"
    ]
    inline = runtime.InlineRuntime(engine, slot=SLOT)
    expected = [inline.submit(t).result() for t in tasks]
    pool = runtime.PoolRuntime(2)
    try:
        got = [f.result() for f in [pool.submit(t) for t in tasks]]
    finally:
        pool.close()
    for one, other in zip(got, expected, strict=True):
        assert [m.source_sha256 for m in one.mutants] == [m.source_sha256 for m in other.mutants]
        assert len(one.mutants) == 4


def test_pairs_of_first_order_mutants_are_compiled_and_really_wrong(engine):
    """Beyond the first order, with the real engine: every accepted pair fails the real suite."""
    from mutation.candidates import first_order_candidates
    from mutation.orchestrator import select_mutants
    from mutation.sites import find_sites

    first_order = len(list(first_order_candidates("1_A", ORIGINAL, find_sites(ORIGINAL))))
    selection = select_mutants(
        "1_A", ORIGINAL, SUITE, LIMITS, engine=engine, slot=SLOT, quota=first_order + 1
    )
    pairs = [m for m in selection.mutants if m.order == 2]
    assert pairs and len({m.source_sha256 for m in selection.mutants}) == len(selection.mutants)
    for mutant in pairs[:2]:
        compiled = engine.compile(mutant.source, SLOT)
        assert compiled.ok
        assert engine.run_suite(compiled.binary, SUITE.tests, LIMITS, SLOT).verdict is Verdict.WA


def test_aborting_the_real_pool_returns_at_once_and_leaves_no_worker_behind():
    """Ctrl+C must not wait minutes for the problems in flight (nothing of them is on disk)."""
    import multiprocessing
    import time

    from mutation import runtime

    tasks = [runtime.ProblemTask(f"1_{c}", ORIGINAL, SUITE, LIMITS, quota=30) for c in "ABC"]
    pool = runtime.PoolRuntime(2)
    futures = [pool.submit(t) for t in tasks]
    time.sleep(3)  # workers are compiling by now
    started = time.monotonic()
    pool.close(abort=True)
    assert time.monotonic() - started < 15
    assert multiprocessing.active_children() == []
    assert not any(f.done() and not f.cancelled() and f.exception() is None for f in futures[2:])
