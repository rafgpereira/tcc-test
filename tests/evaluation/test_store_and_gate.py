"""Atomic persistence, the lock, run.json and the gates (T008, T010, T029)."""

import json

import pytest

from evaluation import gate, store
from evaluation.schemas.result import CombinationResult, SuiteSource, detected_sets
from tests.evaluation.conftest import make_tree


def no_suite(set_name="gpt", problem="1_A", scenario="black_box"):
    return CombinationResult(
        set=set_name,
        model="slm" if set_name.startswith("slm") else set_name,
        problem_id=problem,
        scenario=scenario,
        suite_source=SuiteSource(status="discarded_manual", tree=f"suites/{set_name}"),
        has_suite=False,
        no_suite_reason="discarded_manual",
        suite_size=0,
        ac=None,
        corrected_oracle_tests=0,
        corrected_oracle_excluded=0,
        targets=[],
        detected=detected_sets([]),
        elapsed_s=0.0,
    )


def three(set_name="gpt", problem="1_A"):
    return {s: no_suite(set_name, problem, s) for s in ("black_box", "white_box", "hybrid")}


def test_write_closes_with_one_rename_and_never_overwrites(tmp_path):
    folder = store.write_problem(tmp_path, "gpt", "1_A", three())
    assert sorted(p.name for p in folder.iterdir()) == [
        "black_box.json",
        "hybrid.json",
        "white_box.json",
    ]
    assert store.pending_building(tmp_path, "gpt") == []
    assert store.is_closed(tmp_path, "gpt", "1_A")
    with pytest.raises(FileExistsError):
        store.write_problem(tmp_path, "gpt", "1_A", three())
    assert store.read_problem(tmp_path, "gpt", "1_A")["hybrid"] == no_suite(scenario="hybrid")


def test_a_result_of_another_combination_is_refused(tmp_path):
    with pytest.raises(ValueError):
        store.write_problem(tmp_path, "gpt", "2_B", three())
    assert not store.is_closed(tmp_path, "gpt", "2_B")


def test_reset_building_removes_half_written_problems(tmp_path):
    store.ensure_set_dir(tmp_path, "gpt")
    (store.building_path(tmp_path, "gpt", "1_A")).mkdir()
    assert store.reset_building(tmp_path, "gpt") == 1
    assert store.pending_building(tmp_path, "gpt") == []


def test_only_one_run_at_a_time(tmp_path):
    with (
        store.exclusive_run(tmp_path),
        pytest.raises(store.AlreadyRunningError),
        store.exclusive_run(tmp_path),
    ):
        pass


def test_run_json_is_written_once_and_checked_on_resumption(tmp_path):
    make_tree(tmp_path)
    base = tmp_path / "data/evaluation"
    first = store.current_run(tmp_path, "slm-attempt1", "13.2.0")
    assert (first.model, first.attempt, first.dataset_revision) == ("slm", 1, 2)
    store.open_run(base, "slm-attempt1", first)
    again = store.current_run(tmp_path, "slm-attempt1", "13.2.0")  # another created_at
    assert store.open_run(base, "slm-attempt1", again) == first
    (tmp_path / "manifests/slm_suites.manifest.json").write_text('{"changed": true}\n')
    changed = store.current_run(tmp_path, "slm-attempt1", "13.2.0")
    with pytest.raises(store.RunMismatchError, match="suites_manifest_sha256"):
        store.open_run(base, "slm-attempt1", changed)
    with pytest.raises(store.RunMismatchError, match="gcc_version"):
        store.open_run(base, "slm-attempt1", first.model_copy(update={"gcc_version": "14"}))


def test_gates_stop_on_selfcheck_and_on_cli_check(tmp_path):
    asked = []

    def checks(root, only):
        asked.append(only)
        return True, "ok"

    assert (
        gate.run_gates(
            tmp_path, ["slm-attempt1", "gpt"], selfcheck=lambda: (True, ""), checks=checks
        )
        == []
    )
    assert asked == [["dataset", "mutants", "gpt_suites", "slm_suites"]]
    failed = gate.run_gates(tmp_path, ["gpt"], selfcheck=lambda: (False, "FAIL tle"), checks=checks)
    assert len(failed) == 1 and "selfcheck" in failed[0]
    failed = gate.run_gates(
        tmp_path, ["gpt"], selfcheck=lambda: (True, ""), checks=lambda r, o: (False, "[FALHA]")
    )
    assert "cli check" in failed[0]


def test_run_json_records_the_dataset_revision_one_when_absent(tmp_path):
    make_tree(tmp_path)
    (tmp_path / "manifests/dataset.manifest.json").write_text(json.dumps({"problem_count": 1}))
    assert store.current_run(tmp_path, "gpt", "13").dataset_revision == 1
