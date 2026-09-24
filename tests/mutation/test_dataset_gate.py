"""Tests for the consistency gate against the dataset manifest (FR-010).

The same three tampering cases already proven for the dataset itself: a changed byte, a removed
file and an extra file.
"""

import pytest

from dataset.integrity import manifest as manifest_module
from mutation import dataset_gate
from mutation.dataset_gate import DatasetMismatchError


@pytest.fixture()
def root(tmp_path, dataset_builder):
    """A repository root with a packaged, manifested and extracted dataset of two problems."""
    return dataset_builder(tmp_path, {"1_A": {"AC_ref.cpp": "alfa"}, "2_A": {"AC_ref.cpp": "beta"}})


def problem_file(root, pid="1_A", name="AC_ref.cpp"):
    return root / "data" / "dataset" / "problems" / pid / name


def test_an_intact_dataset_passes(root):
    dataset_gate.verify_dataset(root)  # raises nothing


def test_a_changed_byte_is_reported_with_the_file(root):
    problem_file(root).write_bytes(b"tampered")
    with pytest.raises(DatasetMismatchError) as caught:
        dataset_gate.verify_dataset(root)
    assert caught.value.changed == ["dataset/problems/1_A/AC_ref.cpp"]
    assert "dataset/problems/1_A/AC_ref.cpp" in str(caught.value)


def test_a_removed_file_is_reported_as_missing(root):
    problem_file(root, "2_A").unlink()
    with pytest.raises(DatasetMismatchError) as caught:
        dataset_gate.verify_dataset(root)
    assert caught.value.missing == ["dataset/problems/2_A/AC_ref.cpp"]


def test_an_extra_file_is_reported_as_extra(root):
    problem_file(root, "1_A", "AC_extra.cpp").write_text("extra", encoding="utf-8")
    with pytest.raises(DatasetMismatchError) as caught:
        dataset_gate.verify_dataset(root)
    assert caught.value.extra == ["dataset/problems/1_A/AC_extra.cpp"]


def test_the_message_tells_the_author_how_to_fix_it(root):
    problem_file(root).write_bytes(b"tampered")
    with pytest.raises(DatasetMismatchError, match="unzip data/dataset.zip"):
        dataset_gate.verify_dataset(root)


def test_a_missing_extracted_tree_is_a_mismatch_not_a_crash(root):
    import shutil

    shutil.rmtree(root / "data" / "dataset")
    with pytest.raises(DatasetMismatchError) as caught:
        dataset_gate.verify_dataset(root)
    assert len(caught.value.missing) == 4  # AC_ref.cpp and validacao.json of both problems


def test_a_missing_manifest_is_reported(root):
    (root / "manifests" / "dataset.manifest.json").unlink()
    with pytest.raises(FileNotFoundError):
        dataset_gate.verify_dataset(root)


def test_the_gate_does_not_require_the_zip_itself(root):
    (root / "data" / "dataset.zip").unlink()  # only the extracted tree matters here
    dataset_gate.verify_dataset(root)


def test_the_manifest_hash_links_a_report_to_the_dataset_version(root):
    digest = dataset_gate.dataset_manifest_sha256(root)
    assert len(digest) == 64 and digest == manifest_module.sha256_of_file(
        root / "manifests" / "dataset.manifest.json"
    )
