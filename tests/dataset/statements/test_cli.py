"""``check-statements`` and ``correct-statements``: outputs, exit codes, the dataset untouched."""

import json
from pathlib import Path

import pytest

from dataset import __main__ as cli
from dataset import config
from dataset.schemas.statements import CorrectionSummary, FidelityReport
from tests.dataset.statements.conftest import FakeClock, path_of


@pytest.fixture(autouse=True)
def no_wait(monkeypatch):
    monkeypatch.setattr(cli, "make_statements_clock", FakeClock)


def snapshot(root: Path):
    paths = [root / "data/dataset", root / config.DATASET_ZIP, root / config.MANIFEST_PATH]
    out = []
    for p in paths:
        for f in [p] if p.is_file() else sorted(p.rglob("*")):
            if f.is_file():
                out.append((str(f), f.read_bytes()))
    return out


def test_check_writes_the_report_and_the_package(dataset_root, serving, capsys):
    before = snapshot(dataset_root)
    assert cli.main(["check-statements"]) == cli.EXIT_OK
    out = capsys.readouterr().out
    assert "fetch: 1_A ok" in out
    assert "statements: 2 checked; faithful 1, with losses 1, unchecked 0" in out
    assert "lost_exponent: 1 in 1 problems; lost_index: 1 in 1 problems; formula: 0" in out
    report = FidelityReport.model_validate_json(
        (dataset_root / config.STATEMENT_FIDELITY_REPORT).read_bytes()
    )
    assert [p.status for p in report.problems] == ["losses", "faithful"]
    assert (dataset_root / config.STATEMENT_ORIGINALS_ZIP).is_file()
    assert snapshot(dataset_root) == before  # FR-006

    serving.requests.clear()
    first = (dataset_root / config.STATEMENT_FIDELITY_REPORT).read_bytes()
    assert cli.main(["check-statements"]) == cli.EXIT_OK
    assert serving.requests == []  # SC-003
    assert (dataset_root / config.STATEMENT_FIDELITY_REPORT).read_bytes() == first


def test_with_problem_the_result_is_printed_and_the_report_not_written(
    dataset_root, serving, capsys
):
    assert cli.main(["check-statements", "--problem", "1_A"]) == cli.EXIT_OK
    out = capsys.readouterr().out
    assert "1_A: losses lost_exponent 1 lost_index 1" in out
    assert not (dataset_root / config.STATEMENT_FIDELITY_REPORT).exists()
    assert [p for p, _ in serving.requests] == ["/problem/1/A?locale=en"]


def test_exit_codes(dataset_root, serving, site, capsys):
    assert cli.main(["check-statements", "--problem", "9_Z"]) == cli.EXIT_USAGE
    assert cli.main(["check-statements"]) == cli.EXIT_OK
    page = dataset_root / "data/statements/originals/1_A.html"
    page.write_bytes(page.read_bytes() + b"x")
    assert cli.main(["check-statements"]) == cli.EXIT_DATA_FAILURE  # a changed copy
    page.unlink()
    site.pages[path_of("1_A")] = [(503, b"")]
    assert cli.main(["check-statements", "--refetch", "--problem", "1_A"]) == cli.EXIT_INFRA


def test_a_dataset_that_differs_from_its_manifest_is_refused(dataset_root, serving):
    (dataset_root / "data/dataset/problems/1_A/enunciado.md").write_text("changed\n")
    assert cli.main(["check-statements"]) == cli.EXIT_DATA_FAILURE


def test_correct_writes_the_corrections_for_review(dataset_root, serving, capsys):
    assert cli.main(["correct-statements", "--output-dir", "out"]) == cli.EXIT_DATA_FAILURE
    assert "run python -m dataset check-statements first" in capsys.readouterr().err
    assert cli.main(["check-statements"]) == cli.EXIT_OK
    before = snapshot(dataset_root)
    capsys.readouterr()
    assert cli.main(["correct-statements", "--output-dir", "out"]) == cli.EXIT_OK
    out = capsys.readouterr().out
    assert "corrected: 1 (lost_exponent 1, lost_index 1); unchanged: 1; review: 0" in out
    folder = dataset_root / "out"
    assert sorted(p.name for p in folder.iterdir()) == ["1_A.md", "summary.json"]
    text = (folder / "1_A.md").read_text()
    assert "Read n (1 ≤ n ≤ 10^{5}) and the numbers a_{i}." in text
    assert "Examples\n\nInput\n\n1" in text  # the rest is the current text
    summary = CorrectionSummary.model_validate_json((folder / "summary.json").read_bytes())
    assert summary.unchanged == ["2_B"] and summary.corrected[0].checks.passed
    assert snapshot(dataset_root) == before
    assert cli.main(["correct-statements", "--output-dir", "out"]) == cli.EXIT_USAGE
    assert cli.main(["correct-statements", "--output-dir", "out", "--force"]) == cli.EXIT_OK
    for forbidden in ("data/dataset/x", "data/suites/x", "manifests/x", "data"):
        assert cli.main(["correct-statements", "--output-dir", forbidden]) == cli.EXIT_USAGE


def test_correct_refuses_a_report_of_another_dataset(dataset_root, serving, capsys):
    assert cli.main(["check-statements"]) == cli.EXIT_OK
    path = dataset_root / config.STATEMENT_FIDELITY_REPORT
    data = json.loads(path.read_text())
    data["dataset_manifest_sha256"] = "b" * 64
    path.write_text(json.dumps(data))
    assert cli.main(["correct-statements", "--output-dir", "out"]) == cli.EXIT_DATA_FAILURE
    assert "another dataset" in capsys.readouterr().err
