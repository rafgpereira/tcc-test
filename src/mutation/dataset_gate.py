"""Refuse to generate anything from a dataset that is not the versioned one (spec FR-010).

The mutants are derived from ``data/dataset/problems/<id>/AC_ref.cpp``; if that tree differs from
``manifests/dataset.manifest.json`` (a changed byte, a removed or an extra file), every result would
be built on a different dataset than the one the thesis describes. The check reuses
``dataset.integrity.verify`` and only turns its answer into an error that says what diverges.
"""

from pathlib import Path

from dataset.integrity import manifest as dataset_manifest
from dataset.integrity import verify as dataset_verify
from dataset.schemas.manifest import Manifest
from mutation import config


class DatasetMismatchError(Exception):
    """``data/dataset`` does not match ``manifests/dataset.manifest.json``."""

    def __init__(self, changed: list[str], missing: list[str], extra: list[str]) -> None:
        self.changed, self.missing, self.extra = changed, missing, extra
        lines = ["data/dataset does not match manifests/dataset.manifest.json:"]
        lines += [f"  changed: {path}" for path in changed]
        lines += [f"  missing: {path}" for path in missing]
        lines += [f"  extra: {path}" for path in extra]
        lines.append("restore the versioned dataset with: unzip data/dataset.zip -d data/")
        super().__init__("\n".join(lines))


def verify_dataset(root: Path) -> None:
    """Raise ``DatasetMismatchError`` unless ``<root>/data/dataset`` matches the manifest.

    Only the extracted tree is checked, not ``data/dataset.zip`` itself: the zip is not an input of
    this module. ``FileNotFoundError`` if the manifest is absent (nothing to compare against).
    """
    root = Path(root)
    manifest_path = root / config.DATASET_MANIFEST_PATH
    manifest = Manifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    zip_entry = manifest.dataset_zip.path
    # ``verify`` also reports the zip; the extracted tree is all this gate is about.
    zip_path = root / zip_entry
    result = dataset_verify.verify(zip_path, manifest_path, extracted_dir=root / config.DATASET_DIR)
    changed = [path for path in result.changed if path != zip_entry]
    missing = [path for path in result.missing if path != zip_entry]
    if changed or missing or result.extra:
        raise DatasetMismatchError(changed, missing, list(result.extra))


def dataset_manifest_sha256(root: Path) -> str:
    """Hash of the dataset manifest: ties a mutation report to the exact dataset it consumed."""
    return dataset_manifest.sha256_of_file(Path(root) / config.DATASET_MANIFEST_PATH)
