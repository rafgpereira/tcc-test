"""``data/metrics.zip`` and its manifest (FR-014): tables, ``run.json`` and default figures."""

import hashlib
import json
import os
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from dataset.persistence import store as base_store
from metrics import config

FIXED_DATE_TIME = (1980, 1, 1, 0, 0, 0)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _files(folder: Path) -> list[Path]:
    """The packaged files: the tables, ``run.json`` and the figures WITHOUT filters, in PNG and SVG.

    Filtered figures (``<figure>__<filter>...``) are exploration; any of them is redrawn by
    ``figures`` with the filter its name carries, so they are never packaged.
    """
    files = []
    for path in sorted(folder.rglob("*")):
        if not path.is_file() or path.name.startswith("."):
            continue
        if path.parent.name == "figures" and "__" in path.stem:
            continue
        if path.parent.name == "figures" and path.suffix[1:] not in config.PACKAGED_FIGURE_FORMATS:
            continue  # the PDF is not the same bytes on every call (``metrics.figures``)
        files.append(path)
    return files


def build_zip(root: Path) -> Path:
    root = Path(root)
    folder = root / config.METRICS_DIR
    zip_path = root / config.METRICS_ZIP
    tmp = zip_path.with_name(f".{zip_path.name}.tmp")
    try:
        with zipfile.ZipFile(tmp, "w") as archive:
            for path in _files(folder):
                info = zipfile.ZipInfo(
                    "metrics/" + path.relative_to(folder).as_posix(), FIXED_DATE_TIME
                )
                info.external_attr = (0o100000 | 0o644) << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(info, path.read_bytes(), compresslevel=9)
        os.replace(tmp, zip_path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return zip_path


def build_manifest(root: Path, zip_path: Path) -> dict:
    files = []
    with zipfile.ZipFile(zip_path) as archive:
        for info in archive.infolist():
            data = archive.read(info.filename)
            files.append({"path": info.filename, "sha256": _sha(data), "size": len(data)})
    files.sort(key=lambda f: f["path"])
    data = Path(zip_path).read_bytes()
    manifest = {
        "schema_version": 1,
        "metrics_zip": {
            "path": config.METRICS_ZIP.as_posix(),
            "sha256": _sha(data),
            "size": len(data),
        },
        "files": files,
    }
    path = Path(root) / config.METRICS_MANIFEST
    path.parent.mkdir(parents=True, exist_ok=True)
    base_store.atomic_write_json(path, manifest)
    return manifest


@dataclass
class VerifyResult:
    changed: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    extra: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not (self.changed or self.missing or self.extra)


def verify(root: Path, extracted: Path | None = None) -> VerifyResult:
    root = Path(root)
    manifest = json.loads((root / config.METRICS_MANIFEST).read_text(encoding="utf-8"))
    result = VerifyResult()
    zip_path = root / config.METRICS_ZIP
    entry = manifest["metrics_zip"]
    if not zip_path.is_file():
        result.missing.append(entry["path"])
    elif _sha(zip_path.read_bytes()) != entry["sha256"]:
        result.changed.append(entry["path"])
    else:
        with zipfile.ZipFile(zip_path) as archive:
            inside = {i.filename for i in archive.infolist()}
            for item in manifest["files"]:
                if item["path"] not in inside:
                    result.missing.append(item["path"])
                elif _sha(archive.read(item["path"])) != item["sha256"]:
                    result.changed.append(item["path"])
            result.extra += sorted(inside - {i["path"] for i in manifest["files"]})
    if extracted is not None:
        expected = {item["path"].removeprefix("metrics/"): item for item in manifest["files"]}
        for rel, item in expected.items():
            path = Path(extracted) / rel
            if not path.is_file():
                result.missing.append(item["path"])
            elif _sha(path.read_bytes()) != item["sha256"]:
                result.changed.append(item["path"])
        for path in _files(Path(extracted)):
            rel = path.relative_to(extracted).as_posix()
            if rel not in expected:
                result.extra.append("metrics/" + rel)
    return result
