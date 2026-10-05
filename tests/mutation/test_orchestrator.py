"""Tests for the selection of the mutants of one problem, first order only (FR-003a, FR-005)."""

from mutation import config
from mutation.candidates import first_order_candidates
from mutation.orchestrator import select_mutants
from mutation.sites import find_sites
from mutation.validation import sha256_of
from sandbox.types import Verdict

SOURCE = (
    "int a, b, c;\nint main() {\n"
    + "\n".join(f"  a = b < c + {i} * b;" for i in range(30))
    + "\n}\n"
)


def texts(source: str) -> list[str]:
    return [c.source for c in first_order_candidates("1_A", source, find_sites(source))]


def run(make_engine, suite, limits, source=SOURCE, quota=20, script=None, **kw):
    engine = make_engine(script)
    return engine, select_mutants(
        "1_A", source, suite, limits, engine=engine.as_engine(), quota=quota, **kw
    )


def test_the_first_accepted_candidates_are_kept_in_discovery_order(make_engine, suite, limits):
    _, selection = run(make_engine, suite, limits)
    assert [m.source for m in selection.mutants] == texts(SOURCE)[:20]  # a prefix, not a sample
    assert selection.alert is None and selection.discards == ()


def test_mutants_are_numbered_from_one_in_the_order_of_acceptance(make_engine, suite, limits):
    _, selection = run(make_engine, suite, limits)
    assert [m.index for m in selection.mutants] == list(range(1, 21))
    assert {m.order for m in selection.mutants} == {1}
    assert {m.verdict for m in selection.mutants} == {Verdict.WA}
    assert {m.stability_runs for m in selection.mutants} == {config.STABILITY_RUNS}


def test_the_stream_is_not_consumed_beyond_the_quota(make_engine, suite, limits):
    engine, _ = run(make_engine, suite, limits)
    assert len(engine.compiles) == 20  # no candidate past the twentieth was even compiled


def test_discarded_candidates_are_recorded_and_skipped(make_engine, suite, limits):
    everything = texts(SOURCE)
    script = {everything[0]: ["CE"], everything[2]: [Verdict.AC], everything[3]: [Verdict.TLE]}
    _, selection = run(make_engine, suite, limits, script=script)
    assert [m.source for m in selection.mutants] == [
        t for i, t in enumerate(everything[:23]) if i not in (0, 2, 3)
    ][:20]
    assert sorted((d.order, d.reason.value) for d in selection.discards) == [
        (1, "compile_error"),
        (1, "equivalent"),
        (1, "tle"),
    ]


def test_a_text_equal_to_the_original_or_to_another_candidate_is_never_accepted(
    make_engine, suite, limits
):
    source = "int a, b;\nint main() { return a < b; }\n"
    assert sha256_of(source) not in {sha256_of(t) for t in texts(source)}  # never the original
    _, selection = run(make_engine, suite, limits, source=source, quota=5)
    hashes = [m.source_sha256 for m in selection.mutants]
    assert len(set(hashes)) == len(hashes) == 5


def test_running_twice_gives_the_same_mutants_in_the_same_order(make_engine, suite, limits):
    _, first = run(make_engine, suite, limits)
    _, second = run(make_engine, suite, limits)
    assert [m.source_sha256 for m in first.mutants] == [m.source_sha256 for m in second.mutants]


def test_progress_is_reported_after_each_accepted_mutant(make_engine, suite, limits):
    lines: list[str] = []
    run(make_engine, suite, limits, quota=3, progress=lines.append)
    assert lines == ["  1_A: 1/3 mutants", "  1_A: 2/3 mutants", "  1_A: 3/3 mutants"]


def test_when_no_combination_can_close_the_quota_the_result_is_an_alert(make_engine, suite, limits):
    source = "int a, b;\nint main() { return a < b; }\n"
    _, selection = run(make_engine, suite, limits, source=source, quota=500)
    assert selection.alert is not None and selection.alert.problem_id == "1_A"
    assert selection.alert.mutants_reached == len(selection.mutants) < 500
