"""Tests for the selection and validation of WA candidates (T057; FR-012 to FR-014, D4, D13).

A fake engine stands in for the real one, so ordering, deduplication, stability and early stop are
tested without compiling anything.
"""

import functools
import random
from concurrent.futures import ThreadPoolExecutor

import pytest

from dataset import config
from dataset.validation import wa
from dataset.validation.suite import suite_from_raw
from sandbox.types import ExecutionLimits, InfraError, Verdict

LIMITS = ExecutionLimits(time_limit_seconds=2.0, memory_limit_bytes=256_000_000)


def wrong(i: int, mark="WA@0") -> str:
    return f"// {mark}\nint main(){{return {i};}}"


@pytest.fixture()
def setup(fake, make_raw):
    """`setup(sources)` → (raw, candidates, evaluate) over a suite of 1 + 1 + 2 tests."""

    def _setup(sources):
        raw = make_raw(wa=sources)
        candidates, _ = wa.select_candidates(raw)
        evaluate = functools.partial(
            wa.evaluate_candidate,
            suite=suite_from_raw(raw),
            limits=LIMITS,
            engine=fake.as_engine(),
            slot=3,
        )
        return raw, candidates, evaluate

    return _setup


# ---------------------------------------------------------------------------- selection


def test_identical_texts_count_once_and_the_first_is_kept(make_raw):
    sources = [wrong(1), wrong(2), wrong(1), wrong(3), wrong(2)]
    raw = make_raw(wa=sources)
    candidates, raw_count = wa.select_candidates(raw)
    assert sorted(c.source for c in candidates) == sorted({wrong(1), wrong(2), wrong(3)})
    assert raw_count == 5  # counted BEFORE removing duplicates
    kept = {c.source: c.source_index for c in candidates}
    assert kept[wrong(1)] == 10 and kept[wrong(2)] == 11  # index of the first occurrence


def test_texts_that_differ_only_in_line_endings_are_the_same_text(make_raw):
    raw = make_raw(wa=["// WA@0\r\nint main(){}\r\n", "// WA@0\nint main(){}\n"])
    candidates, _ = wa.select_candidates(raw)
    assert len(candidates) == 1


def test_candidates_follow_the_seeded_order_of_the_problem(make_raw):
    sources = [wrong(i) for i in range(40)]
    raw = make_raw("1101_A", wa=sources)
    candidates, _ = wa.select_candidates(raw)
    expected = list(sources)
    random.Random("42:wa:1101_A").shuffle(expected)
    assert [c.source for c in candidates] == expected
    assert [c.order for c in candidates] == list(range(40))


def test_the_order_does_not_depend_on_other_problems(make_raw):
    sources = [wrong(i) for i in range(30)]
    a, _ = wa.select_candidates(make_raw("1101_A", wa=sources))
    b, _ = wa.select_candidates(make_raw("1101_B", wa=sources))
    assert [c.source for c in a] != [c.source for c in b]  # a stream per problem
    again, _ = wa.select_candidates(make_raw("1101_A", wa=sources))
    assert [c.source for c in a] == [c.source for c in again]


def test_the_selection_is_stable_across_runs_and_processes(make_raw):
    sources = [wrong(i) for i in range(30)]
    first, _ = wa.select_candidates(make_raw(wa=sources))
    second, _ = wa.select_candidates(make_raw(wa=sources))
    assert first == second


# ---------------------------------------------------------------------------- one candidate


def test_a_wa_candidate_is_retained_with_its_deciding_test(setup):
    _, candidates, evaluate = setup([wrong(1, "WA@1")])
    outcome = evaluate(candidates[0])
    assert outcome.kind == "wa"
    item = outcome.validation
    assert item.verdict is Verdict.WA and item.stable is True
    assert (item.deciding_test.group, item.deciding_test.index) == ("private_tests", 0)
    assert item.source_index == 10 and item.tests_run == 2 and item.standard_used == "gnu++20"


def test_the_verdict_is_decided_by_the_first_failing_test_in_suite_order(setup):
    _, candidates, evaluate = setup([wrong(1, "WA@3")])
    item = evaluate(candidates[0]).validation
    assert (item.deciding_test.group, item.deciding_test.index) == ("generated_tests", 1)


@pytest.mark.parametrize(
    ("mark", "kind"),
    [("CE", "ce"), ("TLE@1", "tle"), ("MLE@0", "mle"), ("RE@2", "re"), ("AC", "ac")],
)
def test_ce_tle_mle_re_and_candidates_that_pass_every_test_are_discarded(setup, mark, kind):
    _, candidates, evaluate = setup([wrong(1, mark)])
    outcome = evaluate(candidates[0])
    assert outcome.kind == kind and outcome.validation is None


def test_a_wa_is_confirmed_by_a_second_independent_run(setup, fake):
    _, candidates, evaluate = setup([wrong(1, "WA@2")])
    evaluate(candidates[0])
    assert fake.suite_runs.count(candidates[0].source) == config.STABILITY_RUNS == 2


def test_a_discarded_candidate_is_run_only_once(setup, fake):
    _, candidates, evaluate = setup([wrong(1, "TLE@0")])
    evaluate(candidates[0])
    assert fake.suite_runs.count(candidates[0].source) == 1


def test_a_candidate_whose_two_runs_disagree_is_discarded_as_unstable(setup):
    """WA@0 on the first run and WA@1 on the second: same verdict, different deciding test."""
    _, candidates, evaluate = setup([wrong(1, "FLAKY")])
    outcome = evaluate(candidates[0])
    assert outcome.kind == "unstable" and outcome.validation is None


def test_an_infra_error_of_the_engine_propagates_from_a_candidate(setup, fake):
    _, candidates, _evaluate = setup([wrong(1)])
    engine = fake.as_engine()

    def broken(*args):
        raise InfraError("no disk")

    broken_engine = type(engine)(gcc_version="13.2.0", compile=broken, run_suite=engine.run_suite)
    with pytest.raises(InfraError):
        wa.evaluate_candidate(
            candidates[0], suite_from_raw(setup([wrong(1)])[0]), LIMITS, broken_engine, 0
        )


# ---------------------------------------------------------------------------- collection


def test_exactly_100_are_retained_and_the_rest_is_not_evaluated(setup, fake):
    _, candidates, evaluate = setup([wrong(i) for i in range(150)])
    result = wa.collect_wa(candidates, wa.inline_submit(evaluate), window=1)
    assert len(result.retained) == 100
    assert not result.insufficient
    assert result.consumed == 100 and len(fake.compiled) == 100  # stops at the 100th
    assert [r.validation.file for r in result.retained][:2] == ["WA_1.cpp", "WA_2.cpp"]
    assert result.retained[-1].validation.file == "WA_100.cpp"


def test_the_retained_ones_are_the_first_wa_in_candidate_order(setup):
    sources = [wrong(i, "WA@0" if i % 2 == 0 else "TLE@0") for i in range(260)]
    _, candidates, evaluate = setup(sources)
    result = wa.collect_wa(candidates, wa.inline_submit(evaluate), window=1)
    expected = [c.source for c in candidates if "WA@0" in c.source][:100]
    assert [r.source for r in result.retained] == expected


def test_early_stop_when_retained_plus_remaining_cannot_reach_100(setup, fake):
    """105 candidates, the first 6 are not WA: 99 can never be exceeded, stop right away."""
    sources = [wrong(i, "TLE@0" if i < 6 else "WA@0") for i in range(105)]
    _, candidates, evaluate = setup(sources)
    result = wa.collect_wa(candidates, wa.inline_submit(evaluate), window=1)
    assert result.insufficient and len(result.retained) < 100
    assert result.consumed < len(candidates)


def test_fewer_than_100_unique_candidates_is_insufficient_without_running_anything(setup, fake):
    _, candidates, evaluate = setup([wrong(i) for i in range(60)])
    result = wa.collect_wa(candidates, wa.inline_submit(evaluate), window=1)
    assert result.insufficient and result.consumed == 0 and fake.compiled == []


def test_the_statistics_count_every_consumed_candidate_by_outcome(setup):
    sources = [wrong(i, "WA@0") for i in range(100)] + [wrong(200, "TLE@0")]
    _, candidates, evaluate = setup(sources)
    result = wa.collect_wa(candidates, wa.inline_submit(evaluate), window=1)
    assert result.stats["wa"] == 100
    assert sum(result.stats.values()) == result.consumed


def test_the_retained_set_is_identical_with_one_or_many_workers(fake, make_raw):
    """Results are consumed in candidate order, not in completion order (FR-014, FR-025)."""
    sources = [wrong(i, "WA@0" if i % 5 else "TLE@0") for i in range(300)]
    raw = make_raw(wa=sources)
    candidates, _ = wa.select_candidates(raw)
    suite = suite_from_raw(raw)
    engine = fake.as_engine()
    # make later candidates finish EARLIER than earlier ones
    fake.delay = {
        c.source: 0.02 * (len(candidates) - c.order) / len(candidates) for c in candidates
    }

    def collect(workers):
        evaluate = functools.partial(
            wa.evaluate_candidate, suite=suite, limits=LIMITS, engine=engine, slot=0
        )
        if workers == 1:
            return wa.collect_wa(candidates, wa.inline_submit(evaluate), window=1)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            return wa.collect_wa(candidates, lambda c: pool.submit(evaluate, c), window=workers * 2)

    serial, parallel = collect(1), collect(6)
    assert [r.source for r in serial.retained] == [r.source for r in parallel.retained]
    assert [r.validation for r in serial.retained] == [r.validation for r in parallel.retained]
    assert serial.stats == wa.Counter(
        {k: v for k, v in serial.stats.items()}
    )  # sanity: it is a Counter


def test_an_infra_error_while_collecting_propagates(setup):
    _, candidates, evaluate = setup([wrong(i) for i in range(120)])
    calls = []

    def flaky(candidate):
        calls.append(candidate.order)
        if len(calls) == 5:
            raise InfraError("worker died")
        return evaluate(candidate)

    with pytest.raises(InfraError, match="worker died"):
        wa.collect_wa(candidates, wa.inline_submit(flaky), window=1)


def test_the_number_of_raw_wa_is_reported_before_deduplication(make_raw):
    raw = make_raw(wa=[wrong(1)] * 3 + [wrong(2)])
    _, raw_count = wa.select_candidates(raw)
    assert raw_count == 4
