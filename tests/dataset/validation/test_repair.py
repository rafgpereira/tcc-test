"""Tests for repairing WA candidates that diverge on audit (T072 follow-up; decision D18).

A real run found 13 WA (in 12 of 200 complete problems) whose behavior is not reproducible run to
run: the source code has undefined behavior (reads past the end of an array, uses an uninitialized
variable) or sits right at the time limit boundary, so its exact result depends on things outside
the input (uninitialized memory content, scheduling jitter). Such a candidate is a bad "ground
truth" fault for the metrics, which assume a fixed, reproducible failure. The fix is not to loosen
`outputs_equal` or the engine: it is to require MORE independent confirmation before a candidate is
trusted, and to replace any candidate that fails that higher bar with the next untried candidate of
the SAME deterministic order used originally (FR-014), so the 100 count and the order never change,
only which texts fill it.
"""

import pytest

from dataset import config
from dataset.persistence import store
from dataset.schemas.validacao import Validacao
from dataset.validation import repair, wa
from dataset.validation.audit import WaMismatch
from dataset.validation.runtime import InlineRuntime

LIMITS_KW = {}  # engine limits come from the raw problem, as everywhere else


def wa_sources(n, mark="WA@0", tag=""):
    return [f"// {mark}\nint main(){{return {i};}} {tag}" for i in range(n)]


@pytest.fixture()
def built(tmp_path, fake, make_raw):
    """A complete problem on disk, its raw file, and how many candidates were consumed."""
    from dataset.validation import problem as validating

    store.ensure_work_dir(tmp_path)
    # 100 plain WA, then a run of untried candidates reserved for repair (some flaky, some fine).
    sources = wa_sources(100, tag="base") + wa_sources(30, tag="reserve")
    raw = make_raw("1_A", wa=sources)
    runtime = InlineRuntime(fake.as_engine())
    result = validating.validate_problem(tmp_path, raw, runtime)
    assert result.status == "complete"
    fake.compiled.clear()
    fake.suite_runs.clear()
    folder = tmp_path / config.PROBLEMS_DIR / "1_A"
    return tmp_path, "1_A", folder, runtime, raw, result.consumed


def test_a_mismatched_candidate_is_replaced_by_the_next_untried_one_in_order(built, fake):
    root, pid, folder, runtime, raw, consumed = built
    before = Validacao.from_folder(folder)
    replaced_index = 3  # WA_4.cpp
    mismatch = WaMismatch(file=f"WA_{replaced_index + 1}.cpp", recorded="wa", obtained="unstable")

    outcome = repair.repair_problem(root, pid, [mismatch], runtime, consumed=consumed, raw=raw)

    assert outcome.repaired == [mismatch.file]
    assert outcome.failed == []
    after = Validacao.from_folder(folder)
    assert len(after.wa) == 100
    assert [w.file for w in after.wa] == [f"WA_{i + 1}.cpp" for i in range(100)]
    changed = after.wa[replaced_index]
    assert changed.sha256 != before.wa[replaced_index].sha256
    # every other slot is untouched
    for i, (a, b) in enumerate(zip(after.wa, before.wa, strict=True)):
        if i != replaced_index:
            assert a == b
    # the new source is on disk, normalized, and is the FIRST untried candidate in the order
    candidates, _ = wa.select_candidates(raw)
    expected_source = candidates[consumed].source
    assert (folder / f"WA_{replaced_index + 1}.cpp").read_text() == expected_source


def test_the_candidate_order_used_for_repair_is_the_same_deterministic_order_as_validate(
    built, fake
):
    root, pid, folder, runtime, raw, consumed = built
    mismatch = WaMismatch(file="WA_1.cpp", recorded="wa", obtained="wa")
    repair.repair_problem(root, pid, [mismatch], runtime, consumed=consumed, raw=raw)
    candidates, _ = wa.select_candidates(raw)
    used_now = (folder / "WA_1.cpp").read_text()
    assert used_now == candidates[consumed].source  # not a random pick


def test_two_mismatches_in_the_same_problem_get_two_different_untried_candidates(built, fake):
    root, pid, folder, runtime, raw, consumed = built
    mismatches = [
        WaMismatch(file="WA_1.cpp", recorded="wa", obtained="unstable"),
        WaMismatch(file="WA_2.cpp", recorded="wa", obtained="tle"),
    ]
    repair.repair_problem(root, pid, mismatches, runtime, consumed=consumed, raw=raw)
    one = (folder / "WA_1.cpp").read_text()
    two = (folder / "WA_2.cpp").read_text()
    assert one != two
    candidates, _ = wa.select_candidates(raw)
    assert {one, two} == {candidates[consumed].source, candidates[consumed + 1].source}


def test_a_replacement_must_pass_two_independent_stability_checks_not_just_one(built, fake):
    """The next untried candidate is itself flaky; repair must skip it and try the one after."""
    root, pid, folder, runtime, raw, consumed = built
    candidates, _ = wa.select_candidates(raw)
    flaky_source = candidates[consumed].source
    fake.flaky_calls[flaky_source] = 10**6  # force FLAKY-style disagreement forever if re-marked
    # make the immediate next untried candidate unstable by monkeypatching its behavior via a mark
    import re

    marked = re.sub(r"^// \S+", "// FLAKY", flaky_source, count=1)
    # rewrite the raw problem so the first untried candidate is flaky, keep the rest as before
    raw2 = raw.model_copy(
        update={
            "incorrect_solutions": [
                (
                    item
                    if item.source != flaky_source
                    else item.model_copy(update={"source": marked})
                )
                for item in raw.incorrect_solutions
            ]
        }
    )
    mismatch = WaMismatch(file="WA_1.cpp", recorded="wa", obtained="unstable")
    outcome = repair.repair_problem(root, pid, [mismatch], runtime, consumed=consumed, raw=raw2)
    assert outcome.repaired == ["WA_1.cpp"]
    used = (folder / "WA_1.cpp").read_text()
    assert used != marked  # the flaky one was skipped
    fresh_candidates, _ = wa.select_candidates(raw2)
    assert used == fresh_candidates[consumed + 1].source


def test_repair_never_reuses_a_text_already_present_in_the_other_99(built, fake):
    root, pid, folder, runtime, raw, consumed = built
    before_texts = {(folder / f"WA_{i}.cpp").read_text() for i in range(2, 101)}
    mismatch = WaMismatch(file="WA_1.cpp", recorded="wa", obtained="wa")
    repair.repair_problem(root, pid, [mismatch], runtime, consumed=consumed, raw=raw)
    assert (folder / "WA_1.cpp").read_text() not in before_texts


def test_repair_is_deterministic_across_repeated_runs(tmp_path, fake, make_raw):
    from dataset.validation import problem as validating

    results = []
    for name in ("a", "b"):
        root = tmp_path / name
        store.ensure_work_dir(root)
        raw = make_raw("1_A", wa=wa_sources(100, tag="base") + wa_sources(30, tag="reserve"))
        rt = InlineRuntime(fake.as_engine())
        r = validating.validate_problem(root, raw, rt)
        mismatch = WaMismatch(file="WA_1.cpp", recorded="wa", obtained="unstable")
        repair.repair_problem(root, "1_A", [mismatch], rt, consumed=r.consumed, raw=raw)
        results.append((root / config.PROBLEMS_DIR / "1_A" / "WA_1.cpp").read_text())
    assert results[0] == results[1]


def test_repair_updates_the_validacao_invariants_and_the_model_still_validates(built, fake):
    root, pid, folder, runtime, raw, consumed = built
    mismatch = WaMismatch(file="WA_50.cpp", recorded="wa", obtained="re")
    repair.repair_problem(root, pid, [mismatch], runtime, consumed=consumed, raw=raw)
    validacao = Validacao.from_folder(folder)  # raises if any invariant breaks
    assert validacao.status == "complete"
    assert len({w.sha256 for w in validacao.wa}) == 100


def test_repair_raises_when_the_pool_of_untried_candidates_is_exhausted(built, fake, make_raw):
    root, pid, _folder, runtime, _raw, consumed = built
    # a raw problem whose candidates ran out right after what validate consumed
    starved = make_raw("1_A", wa=wa_sources(consumed, tag="base"))  # zero untried left
    mismatch = WaMismatch(file="WA_1.cpp", recorded="wa", obtained="unstable")
    with pytest.raises(repair.RepairExhausted, match="1_A"):
        repair.repair_problem(root, pid, [mismatch], runtime, consumed=consumed, raw=starved)


def test_repair_of_a_problem_with_no_mismatches_is_a_no_op(built, fake):
    root, pid, folder, runtime, raw, consumed = built
    before = {p.name: p.read_bytes() for p in folder.iterdir()}
    outcome = repair.repair_problem(root, pid, [], runtime, consumed=consumed, raw=raw)
    assert outcome.repaired == [] and outcome.failed == []
    assert {p.name: p.read_bytes() for p in folder.iterdir()} == before
