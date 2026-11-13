"""Base tables from results.csv, the cuts and the gate (T004–T008)."""

import json

import pytest

from metrics import cuts, gate, sources
from tests.metrics.conftest import per_problem_rows, row


def test_per_problem_from_results_csv(repo):
    per, detected = sources.load(repo)
    assert tuple(per.columns) == sources.PER_PROBLEM_COLUMNS
    assert len(per) == 5 * 2 * 3
    assert list(per["set"].unique()) == ["slm", "gpt", "gemini", "claude", "slm-attempt1"]
    for set_name in ("slm", "gpt", "gemini", "claude", "slm-attempt1"):
        report = json.loads((repo / f"manifests/evaluation_{set_name}_report.json").read_text())
        mine = per[per["set"] == set_name]
        assert mine["wa_declared"].sum() == report["detected"]["declared_wa"]
        assert mine["wa_corrected"].sum() == report["detected"]["corrected_wa"]
        assert mine["mutants_declared"].sum() == report["detected"]["declared_mutants"]
    closed = per[
        (per["set"] == "claude") & (per["problem"] == "2_B") & (per["scenario"] == "hybrid")
    ]
    assert not closed["has_suite"].item()
    assert (closed["n_wa"].item(), closed["n_mutants"].item(), closed["wa_declared"].item()) == (
        100,
        100,
        0,
    )
    assert set(per["macrocategoria"]) == {"matematica", "logica_direta"}
    assert set(detected["oracle"]) == {"declared", "corrected"}
    assert len(detected[detected["oracle"] == "declared"]) == per["wa_declared"].sum()


def test_cuts():
    table = per_problem_rows(
        [
            row(problem="1_A", macrocategoria="matematica"),
            row(problem="2_B", macrocategoria="logica_direta", status="accepted_predicted"),
            row(problem="3_C", macrocategoria="matematica"),
        ]
    )
    assert len(cuts.apply(table)) == 3
    assert len(cuts.apply(table, macrocategorias=["matematica"])) == 2
    with pytest.raises(cuts.CutError):
        cuts.apply(table, statuses=["accepted_predicted"])  # a single problem


def test_gate_requires_complete_evaluations_and_a_clean_check(repo):
    ok = gate.run_gate(repo, checks=lambda root, only: (True, ""))
    assert ok and "not complete" in ok[0]  # the test tree has 2 WAs, not 100
    for set_name in ("slm", "gpt", "gemini", "claude", "slm-attempt1"):
        path = repo / f"manifests/evaluation_{set_name}_report.json"
        report = json.loads(path.read_text())
        report["complete"] = True
        path.write_text(json.dumps(report))
    asked = []
    assert gate.run_gate(repo, checks=lambda root, only: (asked.append(only) or (True, ""))) == []
    assert "evaluation_slm_attempt1" in asked[0] and "dataset" in asked[0]
    failed = gate.run_gate(repo, checks=lambda root, only: (False, "[FALHA]"))
    assert "cli check" in failed[0]


# ------------------------------------------------------------------ rating (feature 012, T003)


def test_rating_column_comes_from_cf_rating(repo):
    per, _ = sources.load(repo)
    columns = list(per.columns)
    assert columns.index("rating") == columns.index("macrocategoria") + 1
    assert dict(zip(per["problem"], per["rating"], strict=True)) == {"1_A": 1000, "2_B": 1600}


def test_rating_is_empty_without_the_dataset(repo):
    import shutil

    shutil.rmtree(repo / "data/dataset")
    per, _ = sources.load(repo)
    assert per["rating"].isna().all()


def test_rating_cut():
    table = per_problem_rows(
        [
            row(problem="1_A", rating=1000),
            row(problem="2_B", rating=1600),
            row(problem="3_C", rating=1000),
        ]
    )
    assert len(cuts.apply(table, ratings=())) == 3
    assert set(cuts.apply(table, ratings=[1000])["problem"]) == {"1_A", "3_C"}
    with pytest.raises(cuts.CutError):
        cuts.apply(table, ratings=[1600])  # a single problem
    detected = table[["set", "scenario", "problem"]].assign(target="WA_1", oracle="declared")
    cut, det = cuts.apply(table, ratings=[1000], detected_wa=detected)
    assert set(cut["problem"]) == set(det["problem"]) == {"1_A", "3_C"}
