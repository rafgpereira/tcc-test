"""Build and write the integrity manifest of ``data/mutants.zip`` (spec FR-012)."""

import hashlib
import zipfile
from pathlib import Path

from dataset.persistence import store
from mutation import config
from mutation.schemas.manifest import FileHash, Manifest

_CHUNK = 1024 * 1024


def sha256_of_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_of_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_manifest(zip_path: Path) -> Manifest:
    """Recompute every hash straight from ``zip_path``; never trusts a previous manifest."""
    zip_path = Path(zip_path)
    files = []
    with zipfile.ZipFile(zip_path) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            data = archive.read(info.filename)
            files.append(FileHash(path=info.filename, size=len(data), sha256=sha256_of_bytes(data)))
    files.sort(key=lambda item: item.path)
    return Manifest(
        mutants_zip=FileHash(
            path=config.MUTANTS_ZIP.as_posix(),
            size=zip_path.stat().st_size,
            sha256=sha256_of_file(zip_path),
        ),
        files=files,
    )


def write_manifest(root: Path, manifest: Manifest) -> Path:
    path = Path(root) / config.MANIFEST_PATH
    path.parent.mkdir(parents=True, exist_ok=True)  # `manifests/` is versioned, ordinary mode
    store.atomic_write_json(path, manifest)
    return path
