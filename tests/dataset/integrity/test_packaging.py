"""Tests for the deterministic dataset zip (T082; FR-026, FR-029, SC-008, research R14/R15)."""

import zipfile

import pytest

from dataset.integrity import packaging
from dataset.persistence import store


@pytest.fixture()
def root(tmp_path):
    store.ensure_work_dir(tmp_path)
    return tmp_path


def make_problem(root, pid, status="complete", files=None):
    """Write a minimal problem folder directly (bypasses the engine; packaging only reads status
    and the files already on disk)."""
    folder = store.start_building(root, pid)
    files = files if files is not None else {"enunciado.md": "texto", "AC_ref.cpp": "int main(){}"}
    for name, content in files.items():
        store.write_problem_text(folder, name, content)
    store.write_problem_json(folder, "validacao.json", {"problem_id": pid, "status": status})
    return store.finalize_building(root, pid)


def test_only_complete_problems_are_packaged(root):
    make_problem(root, "1_A", status="complete")
    make_problem(root, "2_A", status="pending_triage")
    make_problem(root, "3_A", status="discarded")
    assert packaging.list_complete_problems(root) == ["1_A"]


def test_complete_problems_are_listed_sorted_by_id(root):
    for pid in ("9_Z", "1_A", "5_C"):
        make_problem(root, pid)
    assert packaging.list_complete_problems(root) == ["1_A", "5_C", "9_Z"]


def test_empty_pool_gives_an_empty_zip_with_only_the_root_directories(root):
    result = packaging.build_dataset_zip(root, root / "out.zip")
    assert result.problem_count == 0
    with zipfile.ZipFile(result.zip_path) as zf:
        assert zf.namelist() == ["dataset/", "dataset/problems/"]


def test_zip_entries_are_sorted_by_path_with_fixed_metadata(root):
    make_problem(root, "1_A", files={"AC_ref.cpp": "a", "WA_1.cpp": "b"})
    make_problem(root, "2_A", files={"AC_ref.cpp": "c"})
    result = packaging.build_dataset_zip(root, root / "out.zip")
    with zipfile.ZipFile(result.zip_path) as zf:
        names = zf.namelist()
        assert names == sorted(names)
        assert names == [
            "dataset/",
            "dataset/problems/",
            "dataset/problems/1_A/",
            "dataset/problems/1_A/AC_ref.cpp",
            "dataset/problems/1_A/WA_1.cpp",
            "dataset/problems/1_A/validacao.json",
            "dataset/problems/2_A/",
            "dataset/problems/2_A/AC_ref.cpp",
            "dataset/problems/2_A/validacao.json",
        ]
        for info in zf.infolist():
            assert info.date_time == (1980, 1, 1, 0, 0, 0)
            mode = (info.external_attr >> 16) & 0o777
            if info.filename.endswith("/"):
                assert mode == 0o755
                assert info.compress_type == zipfile.ZIP_STORED
            else:
                assert mode == 0o644
                assert info.compress_type == zipfile.ZIP_DEFLATED
        assert zf.comment == b""


def test_unzip_at_the_repository_root_yields_the_expected_layout(root):
    make_problem(root, "1101_A")
    result = packaging.build_dataset_zip(root, root / "out.zip")
    with zipfile.ZipFile(result.zip_path) as zf:
        zf.extractall(root / "extracted")
    assert (root / "extracted" / "dataset" / "problems" / "1101_A" / "validacao.json").is_file()


def test_file_content_is_byte_identical_to_what_was_on_disk(root):
    make_problem(root, "1_A", files={"AC_ref.cpp": "conteúdo exato\n"})
    result = packaging.build_dataset_zip(root, root / "out.zip")
    with zipfile.ZipFile(result.zip_path) as zf:
        assert zf.read("dataset/problems/1_A/AC_ref.cpp") == "conteúdo exato\n".encode()


def test_packaging_the_same_input_twice_gives_the_same_zip_bytes(root):
    for pid in ("3_A", "1_A", "2_A"):
        make_problem(root, pid, files={"AC_ref.cpp": f"solution for {pid}"})
    first = packaging.build_dataset_zip(root, root / "first.zip")
    second = packaging.build_dataset_zip(root, root / "second.zip")
    assert first.zip_path.read_bytes() == second.zip_path.read_bytes()


def test_the_result_reports_size_and_problem_count(root):
    make_problem(root, "1_A")
    make_problem(root, "2_A")
    result = packaging.build_dataset_zip(root, root / "out.zip")
    assert result.problem_count == 2
    assert result.size == result.zip_path.stat().st_size
    assert result.size > 0
    assert result.over_size_warning is False


def test_a_warning_flag_is_set_when_the_zip_exceeds_95_mb(root, monkeypatch):
    monkeypatch.setattr(packaging, "SIZE_WARNING_BYTES", 10)  # force the warning with tiny data
    make_problem(root, "1_A")
    result = packaging.build_dataset_zip(root, root / "out.zip")
    assert result.over_size_warning is True


def test_the_zip_is_written_atomically(root, monkeypatch):
    make_problem(root, "1_A")
    target = root / "out.zip"

    def boom(*a, **k):
        raise RuntimeError("disk full")

    monkeypatch.setattr(packaging.os, "replace", boom)
    with pytest.raises(RuntimeError):
        packaging.build_dataset_zip(root, target)
    assert not target.exists()  # a failed write never leaves a partial zip at the final path
