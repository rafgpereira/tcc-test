"""Tests for the integrity manifest: schema (T086) and building it from a real zip (T088)."""

import json

import pytest
from pydantic import ValidationError

from dataset import config
from dataset.integrity import manifest as manifest_module
from dataset.integrity import packaging
from dataset.persistence import store
from dataset.schemas.manifest import FileHash, Manifest
from dataset.schemas.report import Provenance

PROVENANCE = Provenance(
    hf_dataset=config.HF_DATASET, hf_revision=config.HF_REVISION, seed=42, gcc_version="13.2.0"
)


def a_manifest(**overrides):
    base = dict(
        dataset_zip=FileHash(path="data/dataset.zip", size=10, sha256="a" * 64),
        files=[
            FileHash(path="dataset/problems/1_A/AC_ref.cpp", size=5, sha256="b" * 64),
            FileHash(path="dataset/problems/2_A/AC_ref.cpp", size=5, sha256="c" * 64),
        ],
        problem_count=2,
        provenance=PROVENANCE,
    )
    base.update(overrides)
    return Manifest(**base)


# ---------------------------------------------------------------------------------- schema (T086)


def test_schema_version_is_1():
    assert a_manifest().schema_version == 1
    with pytest.raises(ValidationError):
        a_manifest(schema_version=2)


def test_dataset_zip_path_must_be_the_fixed_path():
    with pytest.raises(ValidationError, match="data/dataset.zip"):
        a_manifest(dataset_zip=FileHash(path="data/other.zip", size=1, sha256="a" * 64))


def test_files_must_be_ordered_by_path():
    with pytest.raises(ValidationError, match="ordered"):
        a_manifest(
            files=[
                FileHash(path="dataset/problems/2_A/AC_ref.cpp", size=1, sha256="a" * 64),
                FileHash(path="dataset/problems/1_A/AC_ref.cpp", size=1, sha256="b" * 64),
            ]
        )


def test_problem_count_must_match_the_distinct_ids_in_files():
    with pytest.raises(ValidationError, match="problem_count"):
        a_manifest(problem_count=3)


def test_provenance_never_enters_a_hash_and_has_no_timestamp():
    dumped = a_manifest().model_dump(mode="json")
    assert set(dumped["provenance"]) == {"hf_dataset", "hf_revision", "seed", "gcc_version"}
    assert "timestamp" not in json.dumps(dumped) and "date" not in dumped


def test_extra_fields_are_rejected():
    with pytest.raises(ValidationError):
        a_manifest(unexpected="field")


# ------------------------------------------------------------------------- building it (T088)


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


def test_the_manifest_lists_every_file_of_the_zip_with_its_real_hash(root):
    make_problem(root, "1_A", files={"AC_ref.cpp": "hello"})
    result = packaging.build_dataset_zip(root, root / "out.zip")
    manifest = manifest_module.build_manifest(root, result.zip_path, provenance=PROVENANCE)
    entry = next(f for f in manifest.files if f.path.endswith("AC_ref.cpp"))
    assert entry.sha256 == manifest_module.sha256_of_bytes(b"hello")
    assert entry.size == len("hello")
    # directory entries of the zip are not files
    assert not any(f.path.endswith("/") for f in manifest.files)


def test_the_manifest_hashes_the_zip_itself(root):
    make_problem(root, "1_A")
    result = packaging.build_dataset_zip(root, root / "out.zip")
    manifest = manifest_module.build_manifest(root, result.zip_path, provenance=PROVENANCE)
    assert manifest.dataset_zip.path == "data/dataset.zip"
    assert manifest.dataset_zip.size == result.zip_path.stat().st_size
    assert manifest.dataset_zip.sha256 == manifest_module.sha256_of_file(result.zip_path)


def test_manifest_hash_bate_apos_regeneracao_do_zip(root):
    """Regenerate the zip from the same files (T093's real workflow) and confirm the recomputed
    hashes equal a fresh manifest built from that regenerated zip."""
    make_problem(root, "1_A", files={"AC_ref.cpp": "a"})
    make_problem(root, "2_A", files={"AC_ref.cpp": "b"})
    first_zip = packaging.build_dataset_zip(root, root / "first.zip")
    first_manifest = manifest_module.build_manifest(root, first_zip.zip_path, provenance=PROVENANCE)

    second_zip = packaging.build_dataset_zip(root, root / "second.zip")
    second_manifest = manifest_module.build_manifest(
        root, second_zip.zip_path, provenance=PROVENANCE
    )
    assert first_manifest.model_dump() == second_manifest.model_dump()


def test_writing_the_manifest_is_atomic_and_deterministic(root):
    make_problem(root, "1_A")
    result = packaging.build_dataset_zip(root, root / "out.zip")
    manifest = manifest_module.build_manifest(root, result.zip_path, provenance=PROVENANCE)
    path = manifest_module.write_manifest(root, manifest)
    assert path.is_file()
    first_bytes = path.read_bytes()
    manifest_module.write_manifest(root, manifest)  # regenerating from the same object
    assert path.read_bytes() == first_bytes  # identical bytes: no timestamp anywhere


def test_extraction_report_is_copied_into_manifests(root):
    store.atomic_write_json(root / config.REPORTS_DIR / "extraction_report.json", {"a": 1})
    dest = manifest_module.copy_extraction_report(root)
    assert dest == root / "manifests" / "extraction_report.json"
    assert json.loads(dest.read_text()) == {"a": 1}
