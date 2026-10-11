"""Tests for the exclusion of a problem that cannot reach 100 mutants (FR-009, FR-009a)."""

from dataset.persistence import store
from mutation import config, persistence
from mutation.orchestrator import select_mutants
from mutation.types import ExclusionAlert
from sandbox.types import Verdict

TINY = "int a, b;\nint main() { return a < b; }\n"
ONE_SITE = "int main() {\n  int x = 1;\n  x++;\n  return 0;\n}\n"  # one candidate: no pair
HUGE_QUOTA = 100_000  # more than pairs and triples of TINY can ever give


def test_a_problem_that_exhausts_pairs_and_triples_gets_an_alert(make_engine, suite, limits):
    engine = make_engine()
    selection = select_mutants(
        "1_A", TINY, suite, limits, engine=engine.as_engine(), quota=HUGE_QUOTA
    )
    assert isinstance(selection.alert, ExclusionAlert)
    assert selection.alert.problem_id == "1_A"
    assert 0 < selection.alert.mutants_reached < HUGE_QUOTA
    assert selection.alert.mutants_reached == len(selection.mutants)
    assert selection.alert.highest_order_attempted == 3


def test_a_source_with_no_site_is_excluded_without_trying_anything(make_engine, suite, limits):
    engine = make_engine()
    selection = select_mutants(
        "1_A", "int main() { return 0; }\n", suite, limits, engine=engine.as_engine()
    )
    assert selection.mutants == () and selection.alert.mutants_reached == 0
    assert sum(engine.compiles.values()) == 0


def test_a_single_valid_mutant_cannot_be_combined_and_is_still_an_alert(make_engine, suite, limits):
    from mutation.candidates import first_order_candidates
    from mutation.sites import find_sites

    everything = [c.source for c in first_order_candidates("1_A", TINY, find_sites(TINY))]
    script = {text: [Verdict.AC] for text in everything[1:]}  # only the first one is a mutant
    selection = select_mutants("1_A", TINY, suite, limits, engine=make_engine(script).as_engine())
    assert selection.alert.mutants_reached == 1 and selection.alert.highest_order_attempted == 3


def test_the_alert_never_persists_a_mutant_file_only_the_record(
    tmp_path, make_engine, suite, limits
):
    selection = select_mutants("1_A", ONE_SITE, suite, limits, engine=make_engine().as_engine())
    folder = persistence.write_selection(tmp_path, "1_A", selection)
    assert [p.name for p in folder.iterdir()] == [config.GENERATION_FILE]
    record = persistence.read_generation(tmp_path, "1_A")
    assert record.status == "excluded" and record.mutants == []
    assert record.exclusion.highest_order_attempted == 3
    assert record.exclusion.mutants_reached == selection.alert.mutants_reached == 1
    assert store.read_json(folder / config.GENERATION_FILE)["status"] == "excluded"


def test_an_excluded_problem_is_closed_so_it_is_not_retried(tmp_path, make_engine, suite, limits):
    selection = select_mutants("1_A", ONE_SITE, suite, limits, engine=make_engine().as_engine())
    persistence.write_selection(tmp_path, "1_A", selection)
    assert persistence.is_closed(tmp_path, "1_A")


def test_the_discards_of_every_order_are_recorded(make_engine, suite, limits):
    script = {}
    from mutation.candidates import first_order_candidates
    from mutation.sites import find_sites

    for i, candidate in enumerate(first_order_candidates("1_A", TINY, find_sites(TINY))):
        if i % 3 == 0:
            script[candidate.source] = ["CE"]
    selection = select_mutants("1_A", TINY, suite, limits, engine=make_engine(script).as_engine())
    assert {d.order for d in selection.discards} >= {1}


def test_a_problem_with_an_alert_does_not_stop_the_run(
    tmp_path, dataset_builder, dense_problem, sparse_problem, monkeypatch, make_engine
):
    import mutation.__main__ as cli
    from mutation import runtime

    dataset_builder(tmp_path, {"189_C": dense_problem, "189_D": sparse_problem})
    monkeypatch.chdir(tmp_path)
    engine = make_engine()
    monkeypatch.setattr(
        cli, "_make_runtime", lambda workers: runtime.InlineRuntime(engine.as_engine())
    )
    monkeypatch.setattr("sandbox.isolation.kill_slot_processes", lambda slot: 0)
    assert cli.main(["generate", "--workers", "1"]) == cli.EXIT_OK  # an alert is not a failure
    assert persistence.read_generation(tmp_path, "189_C").status == "complete"
    assert persistence.read_generation(tmp_path, "189_D").status == "excluded"
