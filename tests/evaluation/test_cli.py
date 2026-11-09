"""``python -m evaluation``: run, resumption, report, package and verify (T021, T026, T029–T031)."""

import csv
import hashlib
import io
import json
import zipfile
from pathlib import Path

import pytest

import evaluation.__main__ as cli
from evaluation import config, report, store
from tests.evaluation.conftest import FakeEngine, double, make_tree, ok, solution_attempt

PROBLEMS = ("1_A", "2_B")


@pytest.fixture
def repo(tmp_path, monkeypatch):
    attempts = {
        (p, s, 1): solution_attempt(["1\n", "3\n"], ["2\n", "6\n"])
        for p in PROBLEMS
        for s in config.SCENARIOS
    }
    closed = {"status": "discarded_manual", "tests": []}
    make_tree(
        tmp_path, PROBLEMS, slm_attempts=attempts, suites={("claude", "2_B", "hybrid"): closed}
    )
    monkeypatch.chdir(tmp_path)
    fake = FakeEngine({"WA_1": lambda t, n: ok("0\n") if t == "3\n" else double(t)})
    monkeypatch.setattr(cli, "_make_engine", fake.engine)
    monkeypatch.setattr(cli, "_run_gates", lambda root, sets: [])
    return tmp_path, fake


def run(*args):
    return cli.main(["run", "--workers", "1", *args])


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_run_evaluates_every_set_and_problem(repo):
    root, _ = repo
    assert run() == 0
    for set_name in config.SETS:
        assert store.closed_problems(root / "data/evaluation", set_name) == list(PROBLEMS)
        recorded = json.loads((root / f"data/evaluation/{set_name}/run.json").read_text())
        assert recorded["set"] == set_name
    attempt = store.read_problem(root / "data/evaluation", "slm-attempt1", "1_A")["black_box"]
    assert attempt.suite_source.attempt == 1 and attempt.suite_source.status is None
    final = store.read_problem(root / "data/evaluation", "claude", "2_B")["hybrid"]
    assert final.no_suite_reason == "discarded_manual"


def test_gate_failure_runs_nothing(repo, monkeypatch):
    root, fake = repo
    monkeypatch.setattr(cli, "_run_gates", lambda root, sets: ["cli check failed"])
    assert run() == 1
    assert fake.runs == [] and not (root / "data/evaluation").exists()


def test_usage_errors(repo):
    assert run("--problem", "9_Z") == 2
    assert run("--scenario", "hybrid") == 2  # only in another --output-dir
    assert (
        run("--scenario", "hybrid", "--output-dir", "data/evaluation-conf", "--problem", "1_A") == 0
    )
    folder = Path("data/evaluation-conf/gpt/problems/1_A")
    assert sorted(p.name for p in folder.iterdir()) == ["hybrid.json"]


def test_resumption_evaluates_only_the_missing_sets(repo):
    root, fake = repo
    assert run("--set", "gpt") == 0
    gpt_file = root / "data/evaluation/gpt/problems/1_A/black_box.json"
    before = sha(gpt_file)
    fake.runs.clear()
    assert run() == 0
    assert sha(gpt_file) == before  # the closed gpt result is never rewritten
    assert store.closed_problems(root / "data/evaluation", "claude") == list(PROBLEMS)
    fake.runs.clear()
    assert run() == 0
    assert fake.runs == []  # everything closed: nothing runs again


def test_half_written_problem_is_redone_with_the_same_verdicts(repo):
    root, _ = repo
    assert run("--set", "gpt") == 0
    base = root / "data/evaluation"
    reference = {
        s: r.model_dump(exclude={"elapsed_s": True})
        for s, r in store.read_problem(base, "gpt", "2_B").items()
    }
    # simulate an interruption: 2_B never closed, a half-written copy left in building/
    store.problem_path(base, "gpt", "2_B").rename(store.building_path(base, "gpt", "2_B"))
    assert run("--set", "gpt") == 0
    redone = {
        s: r.model_dump(exclude={"elapsed_s": True})
        for s, r in store.read_problem(base, "gpt", "2_B").items()
    }
    assert redone == reference
    assert store.pending_building(base, "gpt") == []


def test_run_json_of_other_inputs_is_refused(repo):
    root, _ = repo
    assert run("--set", "gpt") == 0
    (root / "manifests/mutants.manifest.json").write_text('{"files": ["changed"]}\n')
    assert run("--set", "gpt") == 2


def test_report_writes_the_table_and_the_summary(repo):
    root, _ = repo
    assert run("--set", "claude") == 0
    assert cli.main(["report", "--set", "claude"]) == 0
    rows = list(csv.reader(io.StringIO((root / "data/evaluation/claude/results.csv").read_text())))
    assert tuple(rows[0]) == report.CSV_COLUMNS
    body = rows[1:]
    # 1_A: 3 scenarios × 4 targets; 2_B: 2 scenarios × 4 targets + 1 line without a suite
    assert len(body) == 3 * 4 + 2 * 4 + 1
    empty = [r for r in body if r[report.CSV_COLUMNS.index("target")] == ""]
    assert len(empty) == 1 and empty[0][2:4] == ["2_B", "hybrid"]
    summary = json.loads((root / "manifests/evaluation_claude_report.json").read_text())
    assert summary["without_suite"] == {"discarded_manual": 1}
    assert summary["ac_approved"] == 5
    assert summary["detected"]["declared_wa"] == 5  # WA_1 fails test "3\n" in every suite
    assert summary["complete"] is False  # 2 WAs and 2 mutants, not 100
    assert any("WAs" in m for m in summary["missing"])


def test_package_refuses_an_incomplete_set_and_verify_checks_the_package(repo, monkeypatch):
    root, _ = repo
    assert run("--set", "gpt") == 0
    assert cli.main(["package", "--set", "gpt"]) == 1  # 2 WAs and 2 mutants are not 100
    monkeypatch.setattr(config, "WA_PER_PROBLEM", 2)
    monkeypatch.setattr(config, "MUTANTS_PER_PROBLEM", 2)
    store.ensure_set_dir(root / "data/evaluation", "gpt")
    store.building_path(root / "data/evaluation", "gpt", "9_Z").mkdir()
    assert cli.main(["package", "--set", "gpt"]) == 1  # half-written problem
    store.reset_building(root / "data/evaluation", "gpt")
    assert cli.main(["package", "--set", "gpt"]) == 0
    zip_path = root / "data/evaluation_gpt.zip"
    with zipfile.ZipFile(zip_path) as archive:
        names = sorted(n for n in archive.namelist() if not n.endswith("/"))
    assert names[0] == "evaluation/gpt/problems/1_A/black_box.json"
    assert "evaluation/gpt/run.json" in names and "evaluation/gpt/results.csv" in names
    assert not any("building" in n for n in names)
    first = sha(zip_path)
    assert cli.main(["package", "--set", "gpt"]) == 0
    assert sha(zip_path) == first  # the same files give the same zip
    assert cli.main(["verify", "--set", "gpt"]) == 0
    assert cli.main(["verify", "--set", "gpt", "--extracted", "data/evaluation/gpt"]) == 0
    result = root / "data/evaluation/gpt/problems/1_A/hybrid.json"
    result.write_text(result.read_text().replace('"elapsed_s"', '"elapsed_s" ', 1))
    assert cli.main(["verify", "--set", "gpt", "--extracted", "data/evaluation/gpt"]) == 1
    assert cli.main(["verify", "--set", "claude"]) == 2  # no manifest


def test_the_report_of_another_tree_never_touches_manifests(repo):
    root, _ = repo
    assert run("--set", "gpt", "--output-dir", "data/evaluation-conf") == 0
    assert cli.main(["report", "--output-dir", "data/evaluation-conf"]) == 0
    assert (root / "data/evaluation-conf/evaluation_gpt_report.json").is_file()
    assert not list((root / "manifests").glob("evaluation_*"))
