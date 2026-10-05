"""Build and write the integrity manifest from a packaged zip (FR-027, FR-018b)."""

import hashlib
import zipfile
from pathlib import Path

from dataset import config
from dataset.persistence import store
from dataset.schemas.manifest import FileHash, Manifest
from dataset.schemas.report import Provenance

_CHUNK = 1024 * 1024

MANIFEST_DIR = Path("manifests")
EXTRACTION_REPORT_DEST = MANIFEST_DIR / "extraction_report.json"


def sha256_of_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_of_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_manifest(root: Path, zip_path: Path, *, provenance: Provenance) -> Manifest:
    """Recompute every hash straight from `zip_path`; never trusts a previous manifest."""
    zip_path = Path(zip_path)
    files = []
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            data = zf.read(info.filename)
            files.append(FileHash(path=info.filename, size=len(data), sha256=sha256_of_bytes(data)))
    files.sort(key=lambda item: item.path)
    problem_ids = {
        parts[2]
        for item in files
        if len(parts := item.path.split("/")) >= 3
        and parts[0] == "dataset"
        and parts[1] == "problems"
    }
    return Manifest(
        dataset_zip=FileHash(
            path=str(config.DATASET_ZIP),
            size=zip_path.stat().st_size,
            sha256=sha256_of_file(zip_path),
        ),
        files=files,
        problem_count=len(problem_ids),
        provenance=provenance,
    )


def write_manifest(root: Path, manifest: Manifest) -> Path:
    path = Path(root) / config.MANIFEST_PATH
    path.parent.mkdir(parents=True, exist_ok=True)  # `manifests/` is versioned, ordinary mode
    store.atomic_write_json(path, manifest)
    return path


def copy_extraction_report(root: Path) -> Path:
    """Copy the working extraction report into the versioned `manifests/` (FR-018b)."""
    source = Path(root) / config.REPORTS_DIR / "extraction_report.json"
    dest = Path(root) / EXTRACTION_REPORT_DEST
    dest.parent.mkdir(parents=True, exist_ok=True)
    store.atomic_write_text(dest, source.read_text(encoding="utf-8"))
    return dest
