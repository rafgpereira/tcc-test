"""Tests for `scripts/verify_dataset.py` (T090): a thin CLI wrapper over `integrity.verify`."""

import importlib.util
import sys

import pytest

from dataset import config
from dataset.integrity import manifest as manifest_module
from dataset.integrity import packaging
from dataset.persistence import store
from dataset.schemas.report import Provenance

PROVENANCE = Provenance(hf_dataset=config.HF_DATASET, hf_revision=config.HF_REVISION, seed=42)


@pytest.fixture(scope="module")
def verify_dataset(repo_root):
    spec = importlib.util.spec_from_file_location(
        "verify_dataset_script", repo_root / "scripts" / "verify_dataset.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def root(tmp_path):
    store.ensure_work_dir(tmp_path)
    return tmp_path


def make_dataset(root):
    folder = store.start_building(root, "1_A")
    store.write_problem_text(folder, "AC_ref.cpp", "int main(){}")
    store.write_problem_json(folder, "validacao.json", {"problem_id": "1_A", "status": "complete"})
    store.finalize_building(root, "1_A")
    result = packaging.build_dataset_zip(root, root / "data" / "dataset.zip")
    m = manifest_module.build_manifest(root, result.zip_path, provenance=PROVENANCE)
    manifest_path = manifest_module.write_manifest(root, m)
    return result.zip_path, manifest_path


def test_ok_exits_0_and_prints_ok(verify_dataset, root, capsys):
    zip_path, manifest_path = make_dataset(root)
    code = verify_dataset.main(["--zip", str(zip_path), "--manifest", str(manifest_path)])
    assert code == 0
    assert capsys.readouterr().out.strip().splitlines()[-1] == "OK"


def test_a_missing_manifest_is_a_usage_error(verify_dataset, root, capsys):
    code = verify_dataset.main(["--manifest", str(root / "nope.json")])
    assert code == 2
    assert "not found" in capsys.readouterr().err


def test_divergence_exits_1_and_lists_the_file(verify_dataset, root, capsys):
    zip_path, manifest_path = make_dataset(root)
    zip_path.unlink()
    code = verify_dataset.main(["--zip", str(zip_path), "--manifest", str(manifest_path)])
    assert code == 1
    out = capsys.readouterr().out
    assert "missing: data/dataset.zip" in out and out.strip().splitlines()[-1] == "FAIL"


def test_extracted_option_checks_the_tree_too(verify_dataset, root, capsys):
    import zipfile

    zip_path, manifest_path = make_dataset(root)
    extracted = root / "extracted"
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(extracted)
    (extracted / "dataset" / "problems" / "1_A" / "AC_ref.cpp").write_text("tampered")
    code = verify_dataset.main(
        [
            "--zip",
            str(zip_path),
            "--manifest",
            str(manifest_path),
            "--extracted",
            str(extracted / "dataset"),
        ]
    )
    assert code == 1
    assert "changed: dataset/problems/1_A/AC_ref.cpp" in capsys.readouterr().out
