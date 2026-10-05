"""Tests for the validation of one candidate with a fake engine (FR-005, FR-006, FR-007).

The fake engine answers from a script, so each discard reason and the stability rule are checked
without compiling anything, and the calls to the engine can be counted.
"""

import hashlib

import pytest

from mutation import config
from mutation.types import DiscardReason, MutantCandidate, MutationOperator, Site, SiteKind
from mutation.validation import confirm_stability, sha256_of, validate
from sandbox.types import InfraError, Verdict

SITE = Site(SiteKind.OPERATOR, "binary_expression", 0, 1, 0, (MutationOperator.ROR,))


def candidate(source: str = "// m1\nint main(){}") -> MutantCandidate:
    return MutantCandidate("1_A", (SITE,), ((MutationOperator.ROR, 0),), source)


def check(engine, suite, limits, cand=None, seen=None, **kw):
    return validate(
        cand or candidate(),
        suite,
        limits,
        3,
        engine=engine.as_engine(),
        seen=seen if seen is not None else set(),
        **kw,
    )


def test_sha256_is_the_hash_of_the_utf8_text():
    assert sha256_of("ação") == hashlib.sha256("ação".encode()).hexdigest()


def test_a_wrong_answer_candidate_is_accepted_with_its_deciding_test(make_engine, suite, limits):
    engine = make_engine(deciding={"// m1\nint main(){}": [1]})
    outcome = check(engine, suite, limits)
    assert outcome.accepted and outcome.verdict is Verdict.WA
    assert outcome.deciding_index == 1 and outcome.discard_reason is None


@pytest.mark.parametrize(
    ("verdict", "reason"),
    [
        (Verdict.TLE, DiscardReason.TLE),
        (Verdict.MLE, DiscardReason.MLE),
        (Verdict.RE, DiscardReason.RE),
        (Verdict.AC, DiscardReason.EQUIVALENT),
    ],
)
def test_each_engine_verdict_other_than_wa_maps_to_its_discard_reason(
    make_engine, suite, limits, verdict, reason
):
    outcome = check(make_engine(default=verdict), suite, limits)
    assert not outcome.accepted and outcome.discard_reason is reason and outcome.verdict is None


def test_a_candidate_that_does_not_compile_is_a_compile_error(make_engine, suite, limits):
    outcome = check(make_engine(default="CE"), suite, limits)  # type: ignore[arg-type]
    assert outcome.discard_reason is DiscardReason.COMPILE_ERROR


def test_a_duplicate_is_discarded_before_any_compilation_or_execution(make_engine, suite, limits):
    engine = make_engine()
    seen = {sha256_of(candidate().source)}
    outcome = check(engine, suite, limits, seen=seen)
    assert outcome.discard_reason is DiscardReason.DUPLICATE
    assert sum(engine.compiles.values()) == 0 and sum(engine.runs.values()) == 0


def test_validating_the_same_text_twice_makes_the_second_a_duplicate(make_engine, suite, limits):
    seen: set[str] = set()
    engine = make_engine()
    assert check(engine, suite, limits, seen=seen).accepted
    assert check(engine, suite, limits, seen=seen).discard_reason is DiscardReason.DUPLICATE


def test_a_discarded_text_is_remembered_so_it_is_never_evaluated_again(make_engine, suite, limits):
    seen: set[str] = set()
    engine = make_engine(default=Verdict.TLE)
    check(engine, suite, limits, seen=seen)
    again = check(engine, suite, limits, seen=seen)
    assert again.discard_reason is DiscardReason.DUPLICATE
    assert engine.compiles[candidate().source] == 1


def test_an_accepted_candidate_runs_the_suite_exactly_six_times_on_one_compilation(
    make_engine, suite, limits
):
    engine = make_engine()
    assert check(engine, suite, limits).accepted
    source = candidate().source
    assert engine.runs[source] == config.STABILITY_RUNS == 6
    assert engine.compiles[source] == 1


def test_one_disagreeing_run_out_of_six_makes_the_candidate_unstable(make_engine, suite, limits):
    source = candidate().source
    script = {source: [Verdict.WA] * 5 + [Verdict.AC]}  # the sixth run disagrees
    outcome = check(make_engine(script), suite, limits)
    assert outcome.discard_reason is DiscardReason.UNSTABLE


def test_a_different_deciding_test_also_counts_as_disagreement(make_engine, suite, limits):
    source = candidate().source
    engine = make_engine(deciding={source: [0, 0, 1, 0, 0, 0]})
    assert check(engine, suite, limits).discard_reason is DiscardReason.UNSTABLE


def test_stability_is_never_checked_for_a_candidate_discarded_by_the_first_filter(
    make_engine, suite, limits
):
    for verdict in (Verdict.TLE, Verdict.MLE, Verdict.RE, Verdict.AC):
        engine = make_engine(default=verdict)
        check(engine, suite, limits)
        assert sum(engine.runs.values()) == 1  # the first execution decided; no re-runs
    engine = make_engine(default="CE")  # type: ignore[arg-type]
    check(engine, suite, limits)
    assert sum(engine.runs.values()) == 0


def test_confirm_stability_is_true_when_every_run_agrees(make_engine, suite, limits):
    engine = make_engine()
    fake = engine.as_engine()
    compiled = fake.compile("x", 3)
    first = fake.run_suite(compiled.binary, suite.tests, limits, 3)
    assert confirm_stability(fake, compiled.binary, suite, limits, 3, first) is True
    assert engine.runs["x"] == 6  # the first run plus five re-runs


def test_confirm_stability_is_false_when_any_run_disagrees(make_engine, suite, limits):
    engine = make_engine({"x": [Verdict.WA, Verdict.WA, Verdict.WA, Verdict.RE]})
    fake = engine.as_engine()
    compiled = fake.compile("x", 3)
    first = fake.run_suite(compiled.binary, suite.tests, limits, 3)
    assert confirm_stability(fake, compiled.binary, suite, limits, 3, first) is False


def test_the_number_of_runs_is_a_parameter(make_engine, suite, limits):
    engine = make_engine()
    assert check(engine, suite, limits, runs=2).accepted
    assert engine.runs[candidate().source] == 2


def test_an_infrastructure_failure_is_never_turned_into_a_discard(make_engine, suite, limits):
    engine = make_engine()

    def broken(binary, tests, limits, slot):
        raise InfraError("tmpfs full")

    fake = engine.as_engine()
    fake = type(fake)(fake.gcc_version, fake.compile, broken)
    with pytest.raises(InfraError):
        validate(candidate(), suite, limits, 3, engine=fake, seen=set())
