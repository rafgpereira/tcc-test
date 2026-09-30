"""Reading one problem of the dataset: the existing readers of ``dataset``, composed."""

import json

import pytest

from ai_clients.problem import list_problem_ids, load_problem
from tests.ai_clients.conftest import build_dataset, problem


def test_load_problem_returns_the_four_inputs(repo):
    loaded = load_problem(repo, "1_A")
    assert loaded.problem_id == "1_A"
    assert loaded.statement.startswith("# 1_A")
    assert "// problem 1_A" in loaded.ac_ref
    assert loaded.metadata.time_limit_seconds == 1.0
    assert [case.input for case in loaded.testes.public_tests] == ["1\n", "2\n"]


def test_a_problem_without_public_tests_is_an_error(tmp_path):
    root = build_dataset(tmp_path, {"3_C": problem("3_C", public=[])})
    with pytest.raises(ValueError, match="public test"):
        load_problem(root, "3_C")


def test_a_problem_id_different_from_the_folder_is_an_error(repo):
    path = repo / "data" / "dataset" / "problems" / "1_A" / "testes.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["problem_id"] = "2_B"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="differs from the folder name"):
        load_problem(repo, "1_A")


def test_the_problem_ids_are_listed_in_alphabetical_order(tmp_path):
    root = build_dataset(tmp_path, {pid: problem(pid) for pid in ["20_B", "100_A", "3_C"]})
    assert list_problem_ids(root) == ["100_A", "20_B", "3_C"]


def test_no_dataset_means_no_problems(tmp_path):
    assert list_problem_ids(tmp_path) == []
