"""Recompute hashes and compare with the manifest (FR-028, SC-009).

Works right after cloning the repository, with only `data/dataset.zip` and the manifest (no
extraction needed): it hashes the zip file itself and every file inside it. With `--extracted DIR`
it additionally checks the extracted tree, file by file, against the same manifest.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path

from dataset.integrity.manifest import sha256_of_file
from dataset.schemas.manifest import Manifest

ZIP_ROOT_PREFIX = "dataset/"


@dataclass
class VerifyResult:
    changed: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    extra: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not (self.changed or self.missing or self.extra)


def _strip_root(path: str) -> str:
    return path.removeprefix(ZIP_ROOT_PREFIX)


def _check_zip(zip_path: Path, manifest: Manifest, result: VerifyResult) -> None:
    if not zip_path.is_file():
        result.missing.append(manifest.dataset_zip.path)
        return
    if zip_path.stat().st_size != manifest.dataset_zip.size or (
        sha256_of_file(zip_path) != manifest.dataset_zip.sha256
    ):
        result.changed.append(manifest.dataset_zip.path)


def _check_extracted(extracted_dir: Path, manifest: Manifest, result: VerifyResult) -> None:
    seen: set[str] = set()
    for entry in manifest.files:
        rel = _strip_root(entry.path)
        seen.add(rel)
        file_path = extracted_dir / rel
        if not file_path.is_file():
            result.missing.append(entry.path)
            continue
        if file_path.stat().st_size != entry.size or sha256_of_file(file_path) != entry.sha256:
            result.changed.append(entry.path)
    if not extracted_dir.is_dir():
        return
    for file_path in sorted(extracted_dir.rglob("*")):
        if not file_path.is_file():
            continue
        rel = file_path.relative_to(extracted_dir).as_posix()
        if rel not in seen:
            result.extra.append(f"{ZIP_ROOT_PREFIX}{rel}")


def verify(zip_path: Path, manifest_path: Path, extracted_dir: Path | None = None) -> VerifyResult:
    manifest = Manifest.model_validate(json.loads(Path(manifest_path).read_text(encoding="utf-8")))
    result = VerifyResult()
    _check_zip(Path(zip_path), manifest, result)
    if extracted_dir is not None:
        _check_extracted(Path(extracted_dir), manifest, result)
    return result
