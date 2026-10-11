"""Tests for `verify`: recompute hashes and report divergence (T084; FR-028, SC-009)."""

import pytest

from dataset import config
from dataset.integrity import manifest as manifest_module
from dataset.integrity import packaging, verify
from dataset.persistence import store
from dataset.schemas.report import Provenance

PROVENANCE = Provenance(hf_dataset=config.HF_DATASET, hf_revision=config.HF_REVISION, seed=42)


@pytest.fixture()
def root(tmp_path):
    store.ensure_work_dir(tmp_path)
    return tmp_path


def make_problem(root, pid, files=None):
    folder = store.start_building(root, pid)
    for name, content in (files or {"AC_ref.cpp": f"solution {pid}"}).items():
        store.write_problem_text(folder, name, content)
    store.write_problem_json(folder, "validacao.json", {"problem_id": pid, "status": "complete"})
    return store.finalize_building(root, pid)


@pytest.fixture()
def dataset(root):
    """A packaged, manifested dataset of two problems: `(zip_path, manifest_path)`."""
    make_problem(root, "1_A", files={"AC_ref.cpp": "alfa"})
    make_problem(root, "2_A", files={"AC_ref.cpp": "beta"})
    result = packaging.build_dataset_zip(root, root / "data" / "dataset.zip")
    m = manifest_module.build_manifest(root, result.zip_path, provenance=PROVENANCE)
    manifest_path = manifest_module.write_manifest(root, m)
    return result.zip_path, manifest_path


def test_a_pristine_dataset_verifies_ok(dataset):
    zip_path, manifest_path = dataset
    result = verify.verify(zip_path, manifest_path)
    assert result.ok is True
    assert result.changed == [] and result.missing == [] and result.extra == []


def test_a_changed_zip_is_reported_as_a_mismatch(dataset):
    zip_path, manifest_path = dataset
    with zip_path.open("r+b") as handle:
        handle.seek(0)
        handle.write(b"\x00")  # corrupt one byte of the zip itself
    result = verify.verify(zip_path, manifest_path)
    assert result.ok is False
    assert "data/dataset.zip" in result.changed


def test_a_missing_zip_is_reported_as_missing(dataset):
    zip_path, manifest_path = dataset
    zip_path.unlink()
    result = verify.verify(zip_path, manifest_path)
    assert result.ok is False
    assert "data/dataset.zip" in result.missing


def test_verify_works_right_after_a_clone_without_extraction(dataset):
    """No `--extracted`: only the zip and the manifest are needed, exactly like a fresh clone."""
    zip_path, manifest_path = dataset
    result = verify.verify(zip_path, manifest_path, extracted_dir=None)
    assert result.ok is True


def test_extracted_a_changed_byte_is_reported_with_the_file_path(dataset, tmp_path):
    import zipfile

    zip_path, manifest_path = dataset
    extracted = tmp_path / "extracted"
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(extracted)
    target = extracted / "dataset" / "problems" / "1_A" / "AC_ref.cpp"
    target.write_bytes(b"tampered")
    result = verify.verify(zip_path, manifest_path, extracted_dir=extracted / "dataset")
    assert result.ok is False
    assert "dataset/problems/1_A/AC_ref.cpp" in result.changed


def test_extracted_a_removed_file_is_missing(dataset, tmp_path):
    import zipfile

    zip_path, manifest_path = dataset
    extracted = tmp_path / "extracted"
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(extracted)
    (extracted / "dataset" / "problems" / "1_A" / "AC_ref.cpp").unlink()
    result = verify.verify(zip_path, manifest_path, extracted_dir=extracted / "dataset")
    assert result.ok is False
    assert "dataset/problems/1_A/AC_ref.cpp" in result.missing


def test_extracted_an_extra_file_is_reported(dataset, tmp_path):
    import zipfile

    zip_path, manifest_path = dataset
    extracted = tmp_path / "extracted"
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(extracted)
    extra_file = extracted / "dataset" / "problems" / "1_A" / "sneaky.cpp"
    extra_file.write_text("not part of the dataset")
    result = verify.verify(zip_path, manifest_path, extracted_dir=extracted / "dataset")
    assert result.ok is False
    assert "dataset/problems/1_A/sneaky.cpp" in result.extra


def test_extracted_pristine_tree_verifies_ok(dataset, tmp_path):
    import zipfile

    zip_path, manifest_path = dataset
    extracted = tmp_path / "extracted"
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(extracted)
    result = verify.verify(zip_path, manifest_path, extracted_dir=extracted / "dataset")
    assert result.ok is True
