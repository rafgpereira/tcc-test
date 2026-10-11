"""Tests for the deterministic mutants zip (spec FR-012; same conventions as the dataset zip)."""

import zipfile

import pytest

from mutation import config, packaging, persistence


def test_only_the_mutant_files_of_complete_problems_are_packaged(tmp_path, write_problem):
    write_problem(tmp_path, "1_A")
    write_problem(tmp_path, "2_A", excluded=True)  # an exclusion has no folder in the zip
    result = packaging.build_mutants_zip(tmp_path, tmp_path / "out.zip")
    assert result.problem_count == 1 and result.excluded_count == 1
    with zipfile.ZipFile(result.zip_path) as archive:
        names = archive.namelist()
    assert not any("2_A" in n for n in names)
    assert not any(config.GENERATION_FILE in n or config.LOCK_FILE in n for n in names)
    assert [n for n in names if n.endswith(".cpp")] == [
        f"mutants/problems/1_A/Mutant_{i}.cpp" for i in sorted(range(1, 101), key=str)
    ]


def test_the_root_inside_the_zip_is_mutants_problems(tmp_path, write_problem):
    """`unzip data/mutants.zip -d data/` lands on the very path `generate` writes."""
    write_problem(tmp_path, "1_A")
    result = packaging.build_mutants_zip(tmp_path, tmp_path / "out.zip")
    with zipfile.ZipFile(result.zip_path) as archive:
        assert archive.namelist()[:3] == ["mutants/", "mutants/problems/", "mutants/problems/1_A/"]
        archive.extractall(tmp_path / "unzipped")
    extracted = tmp_path / "unzipped" / "mutants" / "problems" / "1_A" / "Mutant_1.cpp"
    original = tmp_path / config.PROBLEMS_DIR / "1_A" / "Mutant_1.cpp"
    assert extracted.read_bytes() == original.read_bytes()


def test_an_empty_run_gives_an_empty_zip_with_only_the_root_directories(tmp_path):
    result = packaging.build_mutants_zip(tmp_path, tmp_path / "out.zip")
    assert result.problem_count == 0
    with zipfile.ZipFile(result.zip_path) as archive:
        assert archive.namelist() == ["mutants/", "mutants/problems/"]


def test_entries_are_sorted_by_path_with_fixed_metadata(tmp_path, write_problem):
    for pid in ("9_Z", "1_A", "5_C"):
        write_problem(tmp_path, pid)
    result = packaging.build_mutants_zip(tmp_path, tmp_path / "out.zip")
    with zipfile.ZipFile(result.zip_path) as archive:
        names = archive.namelist()
        assert names == sorted(names)
        assert {i.date_time for i in archive.infolist()} == {(1980, 1, 1, 0, 0, 0)}
        for info in archive.infolist():
            expected = 0o755 if info.is_dir() else 0o644
            assert (info.external_attr >> 16) & 0o777 == expected
            if not info.is_dir():
                assert info.compress_type == zipfile.ZIP_DEFLATED


def test_packaging_twice_gives_the_same_zip_bytes(tmp_path, write_problem):
    write_problem(tmp_path, "1_A")
    write_problem(tmp_path, "2_A")
    first = packaging.build_mutants_zip(tmp_path, tmp_path / "a.zip")
    second = packaging.build_mutants_zip(tmp_path, tmp_path / "b.zip")
    assert (tmp_path / "a.zip").read_bytes() == (tmp_path / "b.zip").read_bytes()
    assert first.size == second.size


def test_a_pending_building_folder_refuses_the_packaging(tmp_path, write_problem):
    write_problem(tmp_path, "1_A")
    (tmp_path / config.BUILDING_DIR / "2_A").mkdir(parents=True)
    with pytest.raises(packaging.PendingBuildError, match="2_A"):
        packaging.build_mutants_zip(tmp_path, tmp_path / "out.zip")
    assert not (tmp_path / "out.zip").exists()  # and nothing half-written is left


def test_a_damaged_problem_refuses_the_packaging(tmp_path, write_problem):
    write_problem(tmp_path, "1_A")
    (tmp_path / config.PROBLEMS_DIR / "1_A" / "Mutant_9.cpp").unlink()
    with pytest.raises(packaging.DamagedProblemError, match="1_A"):
        packaging.build_mutants_zip(tmp_path, tmp_path / "out.zip")


def test_the_zip_is_replaced_atomically_so_a_failure_keeps_the_previous_one(
    tmp_path, write_problem, monkeypatch
):
    write_problem(tmp_path, "1_A")
    packaging.build_mutants_zip(tmp_path, tmp_path / "out.zip")
    before = (tmp_path / "out.zip").read_bytes()
    monkeypatch.setattr(
        packaging, "_planned_entries", lambda *a: (_ for _ in ()).throw(OSError("disk"))
    )
    with pytest.raises(OSError):
        packaging.build_mutants_zip(tmp_path, tmp_path / "out.zip")
    assert (tmp_path / "out.zip").read_bytes() == before
    assert [p.name for p in tmp_path.glob(".*.tmp")] == []


def test_size_warning_when_the_zip_is_close_to_the_github_limit(
    tmp_path, write_problem, monkeypatch
):
    write_problem(tmp_path, "1_A")
    monkeypatch.setattr(packaging, "SIZE_WARNING_BYTES", 10)
    assert packaging.build_mutants_zip(tmp_path, tmp_path / "out.zip").over_size_warning is True


def test_packageable_lists_complete_and_excluded_problems_separately(tmp_path, write_problem):
    write_problem(tmp_path, "3_A")
    write_problem(tmp_path, "1_A")
    write_problem(tmp_path, "2_A", excluded=True)
    assert packaging.list_complete_problems(tmp_path) == ["1_A", "3_A"]
    assert persistence.closed_problems(tmp_path) == ["1_A", "2_A", "3_A"]
