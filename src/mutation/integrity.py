"""Recompute hashes and compare them with the manifest of the mutants zip (spec FR-014).

Works right after cloning, with only ``data/mutants.zip`` and the manifest (nothing extracted): it
hashes the zip file itself and every file inside it. With an extracted tree (``--extracted
data/mutants``) it also checks that tree, file by file, against the same manifest. In the extracted
tree only the ``Mutant_<n>.cpp`` of ``problems/<id>/`` count: the ``generation.json``, ``.lock`` and
``building/`` of a local generation are not extras.
"""

import json
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from mutation import config
from mutation.manifest import sha256_of_bytes, sha256_of_file
from mutation.schemas.manifest import Manifest

ZIP_ROOT_PREFIX = "mutants/"


@dataclass
class VerifyResult:
    changed: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    extra: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not (self.changed or self.missing or self.extra)


def _check_zip(zip_path: Path, manifest: Manifest, result: VerifyResult) -> None:
    entry = manifest.mutants_zip
    if not zip_path.is_file():
        result.missing.append(entry.path)
        return
    if zip_path.stat().st_size != entry.size or sha256_of_file(zip_path) != entry.sha256:
        result.changed.append(entry.path)
        return
    # The zip is the one the manifest describes; its members are then checked too, so a manifest
    # that was edited (not the zip) is caught as well.
    with zipfile.ZipFile(zip_path) as archive:
        inside = {i.filename: i for i in archive.infolist() if not i.is_dir()}
        for item in manifest.files:
            member = inside.get(item.path)
            if member is None:
                result.missing.append(item.path)
            elif (
                member.file_size != item.size
                or sha256_of_bytes(archive.read(member)) != item.sha256
            ):
                result.changed.append(item.path)
        result.extra.extend(sorted(set(inside) - {item.path for item in manifest.files}))


def _check_extracted(extracted_dir: Path, manifest: Manifest, result: VerifyResult) -> None:
    expected = {item.path.removeprefix(ZIP_ROOT_PREFIX): item for item in manifest.files}
    for rel, item in expected.items():
        path = extracted_dir / rel
        if not path.is_file():
            result.missing.append(item.path)
        elif path.stat().st_size != item.size or sha256_of_file(path) != item.sha256:
            result.changed.append(item.path)
    problems = extracted_dir / "problems"
    if not problems.is_dir():
        return
    pattern = f"{config.MUTANT_FILE_PREFIX}*{config.MUTANT_FILE_SUFFIX}"
    for path in sorted(problems.glob(f"*/{pattern}")):
        rel = path.relative_to(extracted_dir).as_posix()
        if rel not in expected:
            result.extra.append(f"{ZIP_ROOT_PREFIX}{rel}")


def verify(zip_path: Path, manifest_path: Path, extracted_dir: Path | None = None) -> VerifyResult:
    manifest = Manifest.model_validate(json.loads(Path(manifest_path).read_text(encoding="utf-8")))
    result = VerifyResult()
    _check_zip(Path(zip_path), manifest, result)
    if extracted_dir is not None:
        _check_extracted(Path(extracted_dir), manifest, result)
    return result
