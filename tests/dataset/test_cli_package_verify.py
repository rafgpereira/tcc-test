"""Tests for the `package` and `verify` subcommands (T091; contracts/cli.md)."""

import json

import pytest

from dataset import __main__ as cli
from dataset import config
from dataset.filtering.classification import classify
from dataset.persistence import store
from dataset.schemas.pool import Pool, PoolCounts, PoolProblem


@pytest.fixture()
def in_tmp(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    store.ensure_work_dir(tmp_path)
    return tmp_path


@pytest.fixture(autouse=True)
def fake_gcc(monkeypatch):
    monkeypatch.setattr(cli, "gcc_version", lambda: "13.2.0")


def write_pool(root, problem_ids):
    problems = {
        pid: PoolProblem(
            split="train",
            shard_index=0,
            macrocategoria=classify(["math"]),
            raw_wa_count=120,
            raw_ac_count=1,
            source_row=i,
        )
        for i, pid in enumerate(problem_ids)
    }
    pool = Pool(
        hf_dataset=config.HF_DATASET,
        hf_revision=config.HF_REVISION,
        seed=42,
        counts=PoolCounts(
            funnel={"read": len(problem_ids)}, rejections={}, eligible=len(problem_ids)
        ),
        order=list(problem_ids),
        problems=problems,
    )
    store.atomic_write_json(root / config.STAGING_DIR / "pool.json", pool)


def make_complete_problem(root, pid):
    folder = store.start_building(root, pid)
    store.write_problem_text(folder, "AC_ref.cpp", f"solution {pid}")
    store.write_problem_json(folder, "validacao.json", {"problem_id": pid, "status": "complete"})
    store.finalize_building(root, pid)


def test_package_refuses_when_the_target_is_not_reached(in_tmp, capsys):
    write_pool(in_tmp, ["1_A"])
    make_complete_problem(in_tmp, "1_A")
    code = cli.main(["package", "--target", "2"])
    assert code == 1
    assert "only 1 of 2" in capsys.readouterr().err
    assert not config.DATASET_ZIP.is_file()


def test_package_allow_partial_packages_anyway(in_tmp):
    write_pool(in_tmp, ["1_A"])
    make_complete_problem(in_tmp, "1_A")
    code = cli.main(["package", "--target", "2", "--allow-partial"])
    assert code == 0
    assert config.DATASET_ZIP.is_file()
    assert config.MANIFEST_PATH.is_file()


def test_package_without_a_pool_is_a_data_failure(in_tmp, capsys):
    code = cli.main(["package"])
    assert code == 1
    assert "extract" in capsys.readouterr().err


def test_package_then_verify_round_trips_ok(in_tmp):
    write_pool(in_tmp, ["1_A", "2_A"])
    make_complete_problem(in_tmp, "1_A")
    make_complete_problem(in_tmp, "2_A")
    assert cli.main(["package", "--target", "2"]) == 0
    assert cli.main(["verify"]) == 0


def test_verify_reports_divergence_and_exits_1(in_tmp, capsys):
    write_pool(in_tmp, ["1_A"])
    make_complete_problem(in_tmp, "1_A")
    cli.main(["package", "--target", "1"])
    config.DATASET_ZIP.unlink()
    code = cli.main(["verify"])
    assert code == 1
    out = capsys.readouterr().out
    assert "missing: data/dataset.zip" in out and out.strip().splitlines()[-1] == "FAIL"


def test_verify_without_a_manifest_is_a_usage_error(in_tmp, capsys):
    code = cli.main(["verify"])
    assert code == 2
    assert "not found" in capsys.readouterr().err


def test_the_manifest_provenance_comes_from_the_pool(in_tmp):
    write_pool(in_tmp, ["1_A"])
    make_complete_problem(in_tmp, "1_A")
    cli.main(["package", "--target", "1"])
    manifest = json.loads(config.MANIFEST_PATH.read_text())
    assert manifest["provenance"] == {
        "hf_dataset": config.HF_DATASET,
        "hf_revision": config.HF_REVISION,
        "seed": 42,
        "gcc_version": "13.2.0",
    }


def test_package_and_verify_are_registered_and_listed_in_the_help(capsys):
    assert cli.main(["--help"]) == 0
    out = capsys.readouterr().out
    assert "package" in out and "verify" in out
