"""Tests for the integrity manifest of the mutants zip (data-model.md, "Pacote de mutantes")."""

import json

import pytest
from pydantic import ValidationError

from mutation import config, manifest, packaging
from mutation.schemas.manifest import FileHash, Manifest


def sample_files():
    return [
        FileHash(path="mutants/problems/1_A/Mutant_1.cpp", size=3, sha256="a" * 64),
        FileHash(path="mutants/problems/1_A/Mutant_2.cpp", size=4, sha256="b" * 64),
    ]


def make(**overrides):
    fields = dict(
        mutants_zip=FileHash(path="data/mutants.zip", size=10, sha256="c" * 64),
        files=sample_files(),
    )
    fields.update(overrides)
    return Manifest(**fields)


def test_the_schema_version_is_one():
    assert make().schema_version == 1
    with pytest.raises(ValidationError):
        make(schema_version=2)


def test_the_zip_path_is_fixed():
    with pytest.raises(ValidationError, match="data/mutants.zip"):
        make(mutants_zip=FileHash(path="data/other.zip", size=1, sha256="c" * 64))


def test_files_must_be_ordered_by_path():
    with pytest.raises(ValidationError, match="ordered"):
        make(files=list(reversed(sample_files())))


def test_every_file_must_be_a_mutant_under_mutants_problems():
    bad = [FileHash(path="mutants/problems/1_A/generation.json", size=1, sha256="a" * 64)]
    with pytest.raises(ValidationError, match="Mutant_"):
        make(files=bad)
    outside = [FileHash(path="dataset/problems/1_A/Mutant_1.cpp", size=1, sha256="a" * 64)]
    with pytest.raises(ValidationError):
        make(files=outside)


def test_unknown_fields_are_errors():
    with pytest.raises(ValidationError):
        make(extra_field=1)


def test_the_manifest_lists_every_file_of_the_zip_with_its_hash(tmp_path, write_problem):
    write_problem(tmp_path, "1_A")
    write_problem(tmp_path, "2_A")
    result = packaging.build_mutants_zip(tmp_path, tmp_path / "data_mutants.zip")
    built = manifest.build_manifest(tmp_path / "data_mutants.zip")
    assert len(built.files) == 200 and [f.path for f in built.files] == sorted(
        f.path for f in built.files
    )
    assert built.mutants_zip.size == result.size
    assert built.mutants_zip.path == "data/mutants.zip"
    first = built.files[0]
    original = (tmp_path / config.PROBLEMS_DIR / "1_A" / "Mutant_1.cpp").read_bytes()
    entry = next(f for f in built.files if f.path == "mutants/problems/1_A/Mutant_1.cpp")
    assert entry.size == len(original) and entry.sha256 == manifest.sha256_of_bytes(original)
    assert first.path.startswith("mutants/problems/1_A/")


def test_the_same_bytes_give_the_same_manifest_hash_after_repackaging(tmp_path, write_problem):
    write_problem(tmp_path, "1_A")
    packaging.build_mutants_zip(tmp_path, tmp_path / "a.zip")
    packaging.build_mutants_zip(tmp_path, tmp_path / "b.zip")
    one, two = manifest.build_manifest(tmp_path / "a.zip"), manifest.build_manifest(
        tmp_path / "b.zip"
    )
    assert one.files == two.files and one.mutants_zip.sha256 == two.mutants_zip.sha256


def test_written_manifest_is_deterministic_json_with_a_final_newline(tmp_path, write_problem):
    write_problem(tmp_path, "1_A")
    packaging.build_mutants_zip(tmp_path, tmp_path / "z.zip")
    path = manifest.write_manifest(tmp_path, manifest.build_manifest(tmp_path / "z.zip"))
    text = path.read_text(encoding="utf-8")
    assert path == tmp_path / config.MANIFEST_PATH and text.endswith("}\n")
    assert json.loads(text)["schema_version"] == 1
    assert (
        text
        == manifest.write_manifest(
            tmp_path, manifest.build_manifest(tmp_path / "z.zip")
        ).read_text()
    )
