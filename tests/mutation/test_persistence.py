"""Tests for the persistence of the mutants of a problem (research R5; Principle VII).

A problem is written in ``data/mutants/building/<id>/`` and closed with ONE atomic rename to
``data/mutants/problems/<id>/``; an interruption never leaves a half-written problem in
``problems/`` and a closed problem is never rewritten.
"""

import pytest

from dataset.persistence import store
from mutation import config, persistence
from mutation.schemas.generation import Generation
from mutation.types import (
    DiscardReason,
    DiscardRecord,
    ExclusionAlert,
    Mutant,
    MutationOperator,
    Selection,
    Site,
    SiteKind,
    Verdict,
)
from mutation.validation import sha256_of

SITE = Site(SiteKind.OPERATOR, "binary_expression", 0, 1, 0, (MutationOperator.ROR,))


def make_mutant(pid: str, index: int, order: int = 1) -> Mutant:
    source = f"// mutant {index}\nint main() {{ return {index}; }}\n"
    return Mutant(
        problem_id=pid,
        index=index,
        order=order,
        sites=(SITE,) * order,
        operators=((MutationOperator.ROR, 1),) * order,
        source=source,
        source_sha256=sha256_of(source),
        verdict=Verdict.WA,
        stability_runs=config.STABILITY_RUNS,
    )


def complete_selection(pid="1_A", n=100) -> Selection:
    mutants = tuple(make_mutant(pid, i, 1 if i <= 90 else 2) for i in range(1, n + 1))
    discards = (
        DiscardRecord(pid, 1, DiscardReason.COMPILE_ERROR),
        DiscardRecord(pid, 1, DiscardReason.COMPILE_ERROR),
        DiscardRecord(pid, 2, DiscardReason.EQUIVALENT),
    )
    return Selection(mutants, None, discards)


def excluded_selection(pid="2_A") -> Selection:
    reached = tuple(make_mutant(pid, i) for i in range(1, 8))
    return Selection(reached, ExclusionAlert(pid, 7, 3), ())


def test_a_complete_problem_is_written_as_100_numbered_files_plus_the_record(tmp_path):
    folder = persistence.write_selection(tmp_path, "1_A", complete_selection())
    assert folder == tmp_path / config.PROBLEMS_DIR / "1_A"
    names = sorted(p.name for p in folder.iterdir())
    assert names.count(config.GENERATION_FILE) == 1
    assert len([n for n in names if n.startswith("Mutant_")]) == 100
    assert (folder / "Mutant_1.cpp").read_text() == complete_selection().mutants[0].source
    assert (folder / "Mutant_100.cpp").is_file()


def test_the_record_summarizes_orders_operators_and_discards(tmp_path):
    persistence.write_selection(tmp_path, "1_A", complete_selection())
    record = persistence.read_generation(tmp_path, "1_A")
    assert isinstance(record, Generation) and record.status == "complete"
    assert [m.order for m in record.mutants].count(2) == 10
    assert record.mutants[0].sha256 == sha256_of(complete_selection().mutants[0].source)
    assert [(d.order, d.reason.value, d.count) for d in record.discards] == [
        (1, "compile_error", 2),
        (2, "equivalent", 1),
    ]


def test_an_excluded_problem_keeps_no_mutant_file_only_the_record(tmp_path):
    folder = persistence.write_selection(tmp_path, "2_A", excluded_selection())
    assert [p.name for p in folder.iterdir()] == [config.GENERATION_FILE]
    record = persistence.read_generation(tmp_path, "2_A")
    assert record.status == "excluded" and record.mutants == []
    assert (record.exclusion.mutants_reached, record.exclusion.highest_order_attempted) == (7, 3)


def test_the_work_happens_in_building_and_ends_with_no_leftover(tmp_path):
    persistence.write_selection(tmp_path, "1_A", complete_selection())
    assert not (tmp_path / config.BUILDING_DIR / "1_A").exists()
    assert persistence.pending_building(tmp_path) == []


def test_an_interruption_in_the_middle_leaves_nothing_in_problems(tmp_path, monkeypatch):
    real = store.write_problem_text
    calls = {"n": 0}

    def flaky(folder, name, text):
        calls["n"] += 1
        if calls["n"] == 4:
            raise KeyboardInterrupt  # Ctrl+C, or `docker stop`, halfway through the problem
        real(folder, name, text)

    monkeypatch.setattr(store, "write_problem_text", flaky)
    with pytest.raises(KeyboardInterrupt):
        persistence.write_selection(tmp_path, "1_A", complete_selection())
    assert not (tmp_path / config.PROBLEMS_DIR / "1_A").exists()
    assert not persistence.is_closed(tmp_path, "1_A")
    assert persistence.pending_building(tmp_path) == ["1_A"]  # partial, and known to be partial


def test_a_new_call_after_an_interruption_starts_over_and_completes(tmp_path, monkeypatch):
    real = store.write_problem_text
    monkeypatch.setattr(
        store, "write_problem_text", lambda *a: (_ for _ in ()).throw(KeyboardInterrupt)
    )
    with pytest.raises(KeyboardInterrupt):
        persistence.write_selection(tmp_path, "1_A", complete_selection())
    monkeypatch.setattr(store, "write_problem_text", real)
    persistence.write_selection(tmp_path, "1_A", complete_selection())
    assert persistence.is_closed(tmp_path, "1_A")
    assert persistence.pending_building(tmp_path) == []
    assert len(list((tmp_path / config.PROBLEMS_DIR / "1_A").glob("Mutant_*.cpp"))) == 100


def test_a_closed_problem_is_recognized_and_never_rewritten(tmp_path):
    persistence.write_selection(tmp_path, "1_A", complete_selection())
    assert persistence.is_closed(tmp_path, "1_A")
    assert persistence.closed_problems(tmp_path) == ["1_A"]
    with pytest.raises(FileExistsError):
        persistence.write_selection(tmp_path, "1_A", complete_selection())


def test_reset_building_removes_every_partial_problem(tmp_path):
    (tmp_path / config.BUILDING_DIR / "9_Z").mkdir(parents=True)
    (tmp_path / config.BUILDING_DIR / "9_Z" / "Mutant_1.cpp").write_text("x")
    assert persistence.reset_building(tmp_path) == 1
    assert persistence.pending_building(tmp_path) == []


def test_a_selection_that_is_neither_complete_nor_excluded_is_refused(tmp_path):
    partial = Selection(tuple(make_mutant("1_A", i) for i in range(1, 50)), None, ())
    with pytest.raises(ValueError):
        persistence.write_selection(tmp_path, "1_A", partial)
    assert not (tmp_path / config.PROBLEMS_DIR / "1_A").exists()


def test_mutant_indices_must_be_the_final_numbering(tmp_path):
    shuffled = complete_selection()
    swapped = Selection(tuple(reversed(shuffled.mutants)), None, ())
    with pytest.raises(ValueError):
        persistence.write_selection(tmp_path, "1_A", swapped)
