"""Package an evaluation set and check it against its manifest (FR-018; research R7).

``data/evaluation_<set>.zip`` holds ``evaluation/<set>/run.json``, ``results.csv`` and
``problems/<id>/<scenario>.json`` only (never ``building/`` or the lock), with fixed dates and modes
so the same files always give the same zip. ``package`` rebuilds ``results.csv`` and the report
first, so what is packaged is always described by them. ``verify`` works right after cloning
(the zip and the manifest only) and, with ``--extracted``, also checks the extracted tree.
"""

import hashlib
import json
import os
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from dataset.persistence import store as base_store
from dataset.schemas.manifest import FileHash
from evaluation import config, store
from evaluation.schemas.report import EvaluationManifest

FIXED_DATE_TIME = (1980, 1, 1, 0, 0, 0)
FILE_MODE, DIR_MODE, COMPRESS_LEVEL = 0o644, 0o755, 9


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class PackageRefused(Exception):
    """The set is not complete, or still has half-written problems."""


def _zip_root(set_name: str) -> str:
    return f"evaluation/{set_name}"


def _dir_info(path: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(path, FIXED_DATE_TIME)
    info.external_attr = (0o40000 | DIR_MODE) << 16 | 0x10
    info.compress_type = zipfile.ZIP_STORED
    return info


def _file_info(path: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(path, FIXED_DATE_TIME)
    info.external_attr = (0o100000 | FILE_MODE) << 16
    info.compress_type = zipfile.ZIP_DEFLATED
    return info


def _entries(base: Path, set_name: str) -> list[tuple[str, Path | None]]:
    root = _zip_root(set_name)
    folder = store.set_dir(base, set_name)
    entries: list[tuple[str, Path | None]] = [
        (f"{root}/", None),
        (f"{root}/{config.RUN_FILE}", folder / config.RUN_FILE),
        (f"{root}/{config.RESULTS_CSV}", folder / config.RESULTS_CSV),
        (f"{root}/{config.PROBLEMS}/", None),
    ]
    for problem_id in store.closed_problems(base, set_name):
        entries.append((f"{root}/{config.PROBLEMS}/{problem_id}/", None))
        for path in sorted(store.problem_path(base, set_name, problem_id).glob("*.json")):
            entries.append((f"{root}/{config.PROBLEMS}/{problem_id}/{path.name}", path))
    entries.sort(key=lambda entry: entry[0])
    return entries


def check_packable(base: Path, set_name: str, complete: bool, missing: list[str]) -> None:
    pending = store.pending_building(base, set_name)
    if pending:
        raise PackageRefused(
            f"{len(pending)} problem(s) half-written in {set_name}/building "
            f"({', '.join(pending[:5])}); run `run` again to finish them"
        )
    if not complete:
        shown = "; ".join(missing[:5]) + (" ..." if len(missing) > 5 else "")
        raise PackageRefused(f"{set_name} is not complete ({len(missing)} missing: {shown})")
    if not (store.set_dir(base, set_name) / config.RUN_FILE).is_file():
        raise PackageRefused(f"{set_name} has no run.json")


def build_zip(base: Path, set_name: str, zip_path: Path) -> Path:
    zip_path = Path(zip_path)
    tmp_path = zip_path.with_name(f".{zip_path.name}.tmp")
    try:
        with zipfile.ZipFile(tmp_path, "w") as archive:
            for entry_path, source in _entries(base, set_name):
                if source is None:
                    archive.writestr(_dir_info(entry_path), b"")
                else:
                    archive.writestr(
                        _file_info(entry_path), source.read_bytes(), compresslevel=COMPRESS_LEVEL
                    )
        os.replace(tmp_path, zip_path)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise
    return zip_path


def build_manifest(set_name: str, zip_path: Path) -> EvaluationManifest:
    zip_path = Path(zip_path)
    files = []
    with zipfile.ZipFile(zip_path) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            data = archive.read(info.filename)
            files.append(FileHash(path=info.filename, size=len(data), sha256=_sha256_bytes(data)))
    files.sort(key=lambda item: item.path)
    return EvaluationManifest(
        set=set_name,
        evaluation_zip=FileHash(
            path=config.zip_path(set_name).as_posix(),
            size=zip_path.stat().st_size,
            sha256=store.sha256_of_file(zip_path),
        ),
        files=files,
    )


def write_manifest(root: Path, manifest: EvaluationManifest) -> Path:
    path = Path(root) / config.manifest_path(manifest.set)
    path.parent.mkdir(parents=True, exist_ok=True)
    base_store.atomic_write_json(path, manifest)
    return path


@dataclass
class VerifyResult:
    changed: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    extra: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not (self.changed or self.missing or self.extra)


def verify(
    zip_path: Path, manifest_path: Path, extracted_dir: Path | None = None, *, check_zip=True
) -> VerifyResult:
    manifest = EvaluationManifest.model_validate(
        json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    )
    result = VerifyResult()
    zip_path = Path(zip_path)
    entry = manifest.evaluation_zip
    if check_zip:
        if not zip_path.is_file():
            result.missing.append(entry.path)
        elif (
            zip_path.stat().st_size != entry.size or store.sha256_of_file(zip_path) != entry.sha256
        ):
            result.changed.append(entry.path)
        else:
            with zipfile.ZipFile(zip_path) as archive:
                inside = {i.filename: i for i in archive.infolist() if not i.is_dir()}
                for item in manifest.files:
                    member = inside.get(item.path)
                    if member is None:
                        result.missing.append(item.path)
                    elif (
                        member.file_size != item.size
                        or _sha256_bytes(archive.read(member)) != item.sha256
                    ):
                        result.changed.append(item.path)
                result.extra.extend(sorted(set(inside) - {i.path for i in manifest.files}))
    if extracted_dir is not None:
        prefix = f"{_zip_root(manifest.set)}/"
        expected = {item.path.removeprefix(prefix): item for item in manifest.files}
        extracted_dir = Path(extracted_dir)
        for rel, item in expected.items():
            path = extracted_dir / rel
            if not path.is_file():
                result.missing.append(item.path)
            elif path.stat().st_size != item.size or store.sha256_of_file(path) != item.sha256:
                result.changed.append(item.path)
        problems = extracted_dir / config.PROBLEMS
        if problems.is_dir():
            for path in sorted(problems.glob("*/*.json")):
                rel = path.relative_to(extracted_dir).as_posix()
                if rel not in expected:
                    result.extra.append(prefix + rel)
    return result
