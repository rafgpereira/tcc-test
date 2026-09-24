"""Tests for `python -m mutation package` and `verify` (contracts/cli.md; FR-012, FR-014)."""

import json
import shutil
import zipfile

import pytest

import mutation.__main__ as cli
from mutation import config

REVISION = "0123456789abcdef0123456789abcdef01234567"
PACKAGE = ["package", "--code-revision", REVISION]


@pytest.fixture()
def repo(tmp_path, dataset_builder, monkeypatch):
    """A repository with a two-problem dataset, the cwd of the commands."""
    dataset_builder(tmp_path, {"1_A": {"AC_ref.cpp": "a"}, "2_A": {"AC_ref.cpp": "b"}})
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture()
def generated(repo, write_problem):
    write_problem(repo, "1_A")
    write_problem(repo, "2_A")
    return repo


def test_package_writes_the_zip_the_manifest_and_the_report(generated, capsys):
    assert cli.main(PACKAGE) == 0
    out = capsys.readouterr().out
    assert "packaged 2 problems (0 excluded)" in out and "manifest:" in out and "report:" in out
    report = json.loads((generated / config.REPORT_PATH).read_text())
    assert report["code_revision"] == REVISION and report["problems"]["complete"] == 2
    assert (generated / config.MUTANTS_ZIP).is_file() and (
        generated / config.MANIFEST_PATH
    ).is_file()
    assert json.loads((generated / config.MANIFEST_PATH).read_text())["schema_version"] == 1


def test_package_then_verify_ok_and_exit_zero(generated, capsys):
    cli.main(PACKAGE)
    capsys.readouterr()
    assert cli.main(["verify"]) == 0
    assert capsys.readouterr().out.strip().endswith("OK")


def test_package_counts_an_excluded_problem_and_leaves_it_out(repo, write_problem, capsys):
    write_problem(repo, "1_A")
    write_problem(repo, "2_A", excluded=True)
    assert cli.main(PACKAGE) == 0
    assert "packaged 1 problems (1 excluded)" in capsys.readouterr().out
    with zipfile.ZipFile(repo / config.MUTANTS_ZIP) as archive:
        assert not any("2_A" in n for n in archive.namelist())


def test_package_refuses_a_pending_building_folder_with_code_one(generated, capsys):
    (generated / config.BUILDING_DIR / "2_A").mkdir(parents=True)
    assert cli.main(PACKAGE) == cli.EXIT_DATA_FAILURE
    assert "half-written" in capsys.readouterr().err
    assert not (generated / config.MUTANTS_ZIP).exists()


def test_package_refuses_when_problems_of_the_dataset_were_not_generated(
    repo, write_problem, capsys
):
    write_problem(repo, "1_A")  # 2_A is still missing
    assert cli.main(PACKAGE) == cli.EXIT_DATA_FAILURE
    err = capsys.readouterr().err
    assert "1 of 2 problems were not generated" in err and "2_A" in err
    assert not (repo / config.MUTANTS_ZIP).exists()


def test_allow_partial_packages_what_exists(repo, write_problem):
    write_problem(repo, "1_A")
    assert cli.main([*PACKAGE, "--allow-partial"]) == 0


def test_package_refuses_a_damaged_problem(generated, capsys):
    (generated / config.PROBLEMS_DIR / "1_A" / "Mutant_4.cpp").unlink()
    assert cli.main(PACKAGE) == cli.EXIT_DATA_FAILURE
    assert "1_A" in capsys.readouterr().err


def test_package_twice_gives_identical_files(generated):
    cli.main(PACKAGE)
    zip_bytes = (generated / config.MUTANTS_ZIP).read_bytes()
    manifest_text = (generated / config.MANIFEST_PATH).read_text()
    cli.main(PACKAGE)
    assert (generated / config.MUTANTS_ZIP).read_bytes() == zip_bytes
    assert (generated / config.MANIFEST_PATH).read_text() == manifest_text


def test_verify_reports_a_tampered_zip_with_code_one(generated, capsys):
    cli.main(PACKAGE)
    with (generated / config.MUTANTS_ZIP).open("r+b") as handle:
        handle.write(b"\x00")
    capsys.readouterr()
    assert cli.main(["verify"]) == cli.EXIT_DATA_FAILURE
    out = capsys.readouterr().out
    assert "changed: data/mutants.zip" in out and out.strip().endswith("FAIL")


def test_verify_without_a_manifest_is_a_usage_error(generated, capsys):
    assert cli.main(["verify"]) == cli.EXIT_USAGE
    assert "manifest not found" in capsys.readouterr().err


def test_the_other_author_flow_unzip_then_verify_extracted(generated, capsys):
    """`git pull`, drop any local generation, unzip into data/, verify the extracted tree."""
    cli.main(PACKAGE)
    shutil.rmtree(generated / config.MUTANTS_DIR)
    with zipfile.ZipFile(generated / config.MUTANTS_ZIP) as archive:
        archive.extractall(generated / "data")
    capsys.readouterr()
    assert cli.main(["verify", "--extracted", "data/mutants"]) == 0
    (generated / config.PROBLEMS_DIR / "1_A" / "Mutant_2.cpp").write_text("tampered")
    assert cli.main(["verify", "--extracted", "data/mutants"]) == cli.EXIT_DATA_FAILURE
    assert "changed: mutants/problems/1_A/Mutant_2.cpp" in capsys.readouterr().out


def test_generate_does_not_touch_what_was_received_from_the_package(
    generated, monkeypatch, make_engine
):
    """After unzip there is no generation.json: `generate` skips those folders (never rewrites)."""
    from mutation import persistence, runtime

    cli.main(PACKAGE)
    shutil.rmtree(generated / config.MUTANTS_DIR)
    with zipfile.ZipFile(generated / config.MUTANTS_ZIP) as archive:
        archive.extractall(generated / "data")
    engine = make_engine()
    monkeypatch.setattr(cli, "_make_runtime", lambda w: runtime.InlineRuntime(engine.as_engine()))
    monkeypatch.setattr("sandbox.isolation.kill_slot_processes", lambda slot: 0)
    assert cli.main(["generate", "--workers", "1"]) == 0
    assert sum(engine.compiles.values()) == 0
    assert persistence.closed_problems(generated) == []  # not ours: no generation.json
    assert cli.main(["verify", "--extracted", "data/mutants"]) == 0


def test_package_refuses_a_dataset_that_differs_from_its_manifest(generated, capsys):
    (generated / "data" / "dataset" / "problems" / "1_A" / "AC_ref.cpp").write_text("tampered")
    assert cli.main(PACKAGE) == cli.EXIT_DATA_FAILURE
    assert "manifest" in capsys.readouterr().err
    assert not (generated / config.MUTANTS_ZIP).exists()


def test_package_refuses_a_malformed_revision_before_any_work(generated, capsys):
    assert cli.main(["package", "--code-revision", "abc"]) == cli.EXIT_DATA_FAILURE
    assert "40-hex" in capsys.readouterr().err
    assert not (generated / config.MUTANTS_ZIP).exists()


def test_the_report_describes_exactly_what_was_packaged(generated):
    cli.main(PACKAGE)
    report = json.loads((generated / config.REPORT_PATH).read_text())
    assert report["problems"] == {
        "closed": 2,
        "complete": 2,
        "first_order_only": 0,
        "higher_order": 2,
        "excluded": 0,
    }
