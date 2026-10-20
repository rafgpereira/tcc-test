"""``package --merge-from``: the package of revision 2 joins the new run (only the combinations the
revision affected) and the previous one, with the origin of every combination (specs/007, R6)."""

import json
import shutil
import zipfile
from pathlib import Path

import pytest

from ai_clients import __main__ as cli
from ai_clients import config, store
from ai_clients.schemas.provenance import SlmProvenance
from dataset import config as dataset_config
from dataset.integrity import manifest as manifest_module
from dataset.integrity import packaging as dataset_packaging
from dataset.persistence import store as files
from dataset.schemas.manifest import RevisedManifest, RevisionOf, parse_manifest
from dataset.schemas.revision import ChangedStatement, DatasetRevision
from tests.ai_clients.fakes import start_run
from tests.ai_clients.test_packaging import finish

SHA = "a" * 64
AFFECTED = [("1_A", "black_box"), ("1_A", "hybrid")]


def make_revision_2(repo: Path) -> None:
    """Keep revision 1, change the statement of 1_A, write revision 2 and its record."""
    shutil.move(repo / dataset_config.DATASET_ZIP, repo / dataset_config.REVISION1_ZIP)
    shutil.move(repo / dataset_config.MANIFEST_PATH, repo / dataset_config.REVISION1_MANIFEST)
    statement = repo / "data/dataset/problems/1_A/enunciado.md"
    before = statement.read_bytes()
    statement.write_text(statement.read_text() + "\nn ≤ 10^{5}\n")
    zip_path = repo / dataset_config.DATASET_ZIP
    dataset_packaging.build_dataset_zip(repo, zip_path, Path("data/dataset/problems"))
    old = parse_manifest((repo / dataset_config.REVISION1_MANIFEST).read_bytes())
    built = manifest_module.build_manifest(repo, zip_path, provenance=old.provenance)
    revised = RevisedManifest(
        **built.model_dump(exclude={"schema_version"}),
        revision=2,
        revision_of=RevisionOf(
            previous_manifest_sha256=SHA,
            fidelity_report_sha256=SHA,
            originals_manifest_sha256=SHA,
            revision_record_sha256=SHA,
            created_at="2026-10-18T00:00:00Z",
        ),
    )
    files.atomic_write_json(repo / dataset_config.MANIFEST_PATH, revised)
    record = DatasetRevision(
        revision=2,
        previous_manifest_sha256=SHA,
        changed=[
            ChangedStatement(
                problem_id="1_A",
                origin="automatic",
                markups={"lost_exponent": 1},
                sha256_before=files_sha(before),
                sha256_after=files_sha(statement.read_bytes()),
            )
        ],
        kept=[],
    )
    files.atomic_write_json(repo / dataset_config.REVISION_RECORD, record)


def files_sha(data: bytes) -> str:
    import hashlib

    return hashlib.sha256(data).hexdigest()


@pytest.fixture()
def revised(repo, monkeypatch):
    """Revision 1 run finished and moved aside; revision 2; a new run with only the affected."""
    monkeypatch.chdir(repo)
    finish(repo, start_run(repo))
    make_revision_2(repo)
    shutil.move(repo / "data/suites/slm", repo / "data/suites/slm-rev1")
    finish(repo, start_run(repo), combos=AFFECTED)
    return repo


def merge():
    return cli.main(["package", "--merge-from", "data/suites/slm-rev1"])


def test_the_merged_package_says_where_each_combination_comes_from(revised, capsys):
    assert merge() == cli.EXIT_OK
    out = capsys.readouterr().out
    assert (
        "merged: 2 combinations from suites/slm (the current dataset revision), 4 from suites/slm-rev1"
        in out
    )
    provenance = SlmProvenance.model_validate_json(
        (revised / config.SUITES_DIR / "provenance.json").read_bytes()
    )
    in_force = provenance.in_force()
    assert len(in_force) == 6
    for key in AFFECTED:
        assert (in_force[key].tree, in_force[key].dataset_revision) == ("suites/slm", 2)
    assert in_force[("2_B", "white_box")].tree == "suites/slm-rev1"
    assert in_force[("2_B", "white_box")].dataset_revision == 1
    superseded = [c for c in provenance.combinations if c.superseded_in]
    assert {(c.problem_id, c.scenario) for c in superseded} == set(AFFECTED)
    with zipfile.ZipFile(revised / config.ZIP_PATH) as archive:
        names = archive.namelist()
    assert "suites/slm/provenance.json" in names
    assert "suites/slm/problems/1_A/hybrid/suite.json" in names
    assert "suites/slm-rev1/run.json" in names
    assert "suites/slm-rev1/problems/2_B/black_box/suite.json" in names
    manifest = json.loads((revised / config.MANIFEST_PATH).read_text())
    assert [f["path"] for f in manifest["files"]] == sorted(n for n in names if not n.endswith("/"))


def test_a_missing_affected_combination_is_refused(revised, capsys):
    shutil.rmtree(store.combination_dir(revised, "1_A", "hybrid"))
    assert merge() == cli.EXIT_DATA_FAILURE
    assert "without suite.json (data/suites/slm 1_A hybrid)" in capsys.readouterr().err


def test_a_combination_the_revision_did_not_affect_is_refused_in_the_new_run(revised, capsys):
    shutil.copytree(
        revised / "data/suites/slm-rev1/problems/2_B/black_box",
        store.combination_dir(revised, "2_B", "black_box"),
    )
    assert merge() == cli.EXIT_DATA_FAILURE
    assert "that revision 2 did not affect (2_B black_box)" in capsys.readouterr().err


def test_a_damaged_previous_run_is_refused(revised, capsys):
    (revised / "data/suites/slm-rev1/problems/2_B/white_box/stray.txt").write_text("?")
    assert merge() == cli.EXIT_DATA_FAILURE


def test_without_a_revision_record_there_is_nothing_to_merge(revised, capsys):
    (revised / dataset_config.REVISION_RECORD).unlink()
    assert merge() == cli.EXIT_DATA_FAILURE
    assert "there is no dataset revision to merge for" in capsys.readouterr().err


def test_merge_from_is_only_for_the_local_model(revised, capsys):
    argv = ["package", "--model", "gpt", "--merge-from", "data/suites/slm-rev1"]
    assert cli.main(argv) == cli.EXIT_USAGE


def test_the_consistency_check_reads_the_merged_layout(revised):
    from cli import consistency

    assert merge() == cli.EXIT_OK
    report = consistency.run_checks(revised, only=["slm_suites"], deep=True)
    assert report.ok, report.render()
    provenance = revised / config.SUITES_DIR / "provenance.json"
    data = json.loads(provenance.read_text())
    data["combinations"] = [c for c in data["combinations"] if c["problem_id"] != "2_B"]
    provenance.write_text(json.dumps(data))
    assert not consistency.run_checks(revised, only=["slm_suites"]).ok
