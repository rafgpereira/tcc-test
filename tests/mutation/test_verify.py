"""Tests for `verify`: recompute hashes and report `changed`/`missing`/`extra` (spec FR-014).

Works from the zip and the manifest alone, like right after cloning (no `data/mutants/` needed).
"""

import zipfile

import pytest

from mutation import config, integrity, manifest, packaging


@pytest.fixture()
def package(tmp_path, write_problem):
    """`(zip_path, manifest_path)` of a packaged run of two problems."""
    write_problem(tmp_path, "1_A")
    write_problem(tmp_path, "2_A")
    result = packaging.build_mutants_zip(tmp_path, tmp_path / config.MUTANTS_ZIP.name)
    manifest_path = manifest.write_manifest(tmp_path, manifest.build_manifest(result.zip_path))
    return result.zip_path, manifest_path


@pytest.fixture()
def extracted(tmp_path, package):
    """The package unzipped like `unzip data/mutants.zip -d data/`: the `mutants/` folder."""
    with zipfile.ZipFile(package[0]) as archive:
        archive.extractall(tmp_path / "data")
    return tmp_path / "data" / "mutants"


def test_a_pristine_package_verifies_ok(package):
    result = integrity.verify(*package)
    assert result.ok and (result.changed, result.missing, result.extra) == ([], [], [])


def test_a_changed_byte_of_the_zip_is_reported(package):
    zip_path, manifest_path = package
    with zip_path.open("r+b") as handle:
        handle.write(b"\x00")
    result = integrity.verify(zip_path, manifest_path)
    assert not result.ok and "data/mutants.zip" in result.changed


def test_a_missing_zip_is_reported(package):
    zip_path, manifest_path = package
    zip_path.unlink()
    assert "data/mutants.zip" in integrity.verify(zip_path, manifest_path).missing


def test_works_with_only_the_zip_and_the_manifest(tmp_path, package):
    """No `data/mutants/` at all, like right after a clone."""
    import shutil

    shutil.rmtree(tmp_path / config.MUTANTS_DIR)
    assert integrity.verify(*package).ok


def test_extracted_a_changed_byte_is_reported_with_its_path(package, extracted):
    (extracted / "problems" / "1_A" / "Mutant_5.cpp").write_bytes(b"tampered")
    result = integrity.verify(*package, extracted_dir=extracted)
    assert result.changed == ["mutants/problems/1_A/Mutant_5.cpp"]


def test_extracted_a_removed_file_is_reported_as_missing(package, extracted):
    (extracted / "problems" / "2_A" / "Mutant_9.cpp").unlink()
    result = integrity.verify(*package, extracted_dir=extracted)
    assert result.missing == ["mutants/problems/2_A/Mutant_9.cpp"]


def test_extracted_an_extra_mutant_is_reported_as_extra(package, extracted):
    (extracted / "problems" / "1_A" / "Mutant_101.cpp").write_text("extra")
    result = integrity.verify(*package, extracted_dir=extracted)
    assert result.extra == ["mutants/problems/1_A/Mutant_101.cpp"]


def test_extracted_a_whole_extra_problem_folder_is_reported(package, extracted):
    (extracted / "problems" / "9_Z").mkdir()
    (extracted / "problems" / "9_Z" / "Mutant_1.cpp").write_text("extra")
    assert integrity.verify(*package, extracted_dir=extracted).extra == [
        "mutants/problems/9_Z/Mutant_1.cpp"
    ]


def test_extracted_local_generation_leftovers_are_not_extras(package, extracted):
    """A tree that was generated locally has `generation.json`, `.lock` and `building/`."""
    (extracted / "problems" / "1_A" / config.GENERATION_FILE).write_text("{}")
    (extracted / config.LOCK_FILE).write_text("")
    (extracted / "building" / "3_A").mkdir(parents=True, exist_ok=True)
    assert integrity.verify(*package, extracted_dir=extracted).ok


def test_a_missing_extracted_tree_reports_every_file_missing(tmp_path, package):
    result = integrity.verify(*package, extracted_dir=tmp_path / "nowhere")
    assert len(result.missing) == 200 and not result.ok
