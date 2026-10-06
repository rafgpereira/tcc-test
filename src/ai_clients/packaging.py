"""The package of the final run: ``data/slm_suites.zip``, its manifest, and their verification.

Same conventions as the zips of the dataset and of the mutants (``dataset.integrity.packaging``):
entries sorted by path, a fixed modification time, fixed Unix permissions, ``deflate`` at a fixed
level, so the same tree gives the same zip bytes. The root inside the zip is ``suites/slm/``, so
``unzip data/slm_suites.zip -d data/`` lands exactly on ``data/suites/slm/``, where the commands
read. Every file of every combination goes in, and ``run.json`` (the provenance of the run); the
``.lock`` and the leftovers of an interrupted atomic write never do.

A package is only worth versioning if it is exactly what a whole run produced, so it is refused
while any problem × scenario of the dataset has no ``suite.json``, or if anything is damaged.
"""

import json
import os
import zipfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from ai_clients import config, store
from ai_clients.problem import list_problem_ids
from ai_clients.report import DamagedTreeError
from ai_clients.schemas.common import SuiteStatus
from ai_clients.schemas.manifest import FileHash, SlmSuitesManifest
from dataset.integrity.packaging import (
    COMPRESS_LEVEL,
    DIR_MODE,
    FILE_MODE,
    FIXED_DATE_TIME,
    SIZE_WARNING_BYTES,
)
from dataset.persistence import store as files
from mutation.integrity import VerifyResult
from mutation.manifest import sha256_of_bytes, sha256_of_file


class UnfinishedRunError(Exception):
    """Some combinations of the dataset have no ``suite.json`` yet, or the tree has extra entries."""


@dataclass(frozen=True)
class PackageResult:
    zip_path: Path
    size: int
    combinations: int
    statuses: dict[str, int]  # suite status -> combinations, every status present
    over_size_warning: bool


def _ignored(name: str) -> bool:
    """``.lock`` and the temporary files of atomic writes: local, never part of a run."""
    return name.startswith(".")


def check_finished(root: Path) -> dict[str, int]:
    """Suite status -> combinations of a finished run; refuses an unfinished or damaged one."""
    root = Path(root)
    run = store.read_run(root)
    problems = list_problem_ids(root)
    unfinished, awaiting, damaged = [], [], []
    statuses: Counter = Counter()
    for problem_id in problems:
        for scenario in config.SCENARIOS:
            try:
                state = store.combination_state(root, problem_id, scenario, run)
            except store.DamagedCombination as exc:
                damaged.append(exc)
                continue
            if state.kind == "awaiting_manual":
                awaiting.append(f"{problem_id} {scenario}")
            if state.kind != "terminal":
                unfinished.append(f"{problem_id} {scenario}")
            else:
                statuses[store.read_suite(root, problem_id, scenario).status.value] += 1
    if damaged:
        raise DamagedTreeError(damaged)
    total = len(problems) * len(config.SCENARIOS)
    if unfinished:
        shown = ", ".join(unfinished[:5]) + (", ..." if len(unfinished) > 5 else "")
        message = (
            f"{len(unfinished)} of {total} combinations have no suite.json ({shown}); finish the "
            "run (generate --resume and execute) before packaging"
        )
        if awaiting:
            message += (
                f"; {len(awaiting)} await manual handling ({', '.join(awaiting)}): close each "
                'with python -m ai_clients close --problem ID --scenario S --reason "..."'
            )
        raise UnfinishedRunError(message)
    extra = []
    for folder in sorted((root / config.PROBLEMS_DIR).iterdir()):
        if _ignored(folder.name):
            continue
        if folder.name not in problems or not folder.is_dir():
            extra.append(folder.name)
            continue
        for entry in sorted(folder.iterdir()):
            if not _ignored(entry.name) and entry.name not in config.SCENARIOS:
                extra.append(f"{folder.name}/{entry.name}")
    if extra:
        raise UnfinishedRunError(
            f"data/suites/slm/problems has entries that are not a problem × scenario of the "
            f"dataset: {', '.join(extra[:5])}"
        )
    return {status.value: statuses[status.value] for status in SuiteStatus}


def _dir_info(path: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(path, FIXED_DATE_TIME)
    info.external_attr = (0o40000 | DIR_MODE) << 16 | 0x10  # S_IFDIR + mode, MS-DOS dir bit
    info.compress_type = zipfile.ZIP_STORED
    return info


def _file_info(path: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(path, FIXED_DATE_TIME)
    info.external_attr = (0o100000 | FILE_MODE) << 16  # S_IFREG + mode
    info.compress_type = zipfile.ZIP_DEFLATED
    return info


def _tree(base: Path) -> list[Path]:
    """Every directory and file under ``base``, without the ignored names, sorted by path."""
    found = []
    for path in sorted(base.rglob("*")):
        if any(_ignored(part) for part in path.relative_to(base).parts):
            continue
        found.append(path)
    return found


def build_zip(root: Path, zip_path: Path) -> PackageResult:
    """Build the zip atomically (temporary file + ``os.replace``) from a finished run."""
    root, zip_path = Path(root), Path(zip_path)
    statuses = check_finished(root)
    base = root / config.SUITES_DIR
    entries: list[tuple[str, Path | None]] = [(f"{config.ZIP_ROOT}/", None)]
    for path in _tree(base):
        name = f"{config.ZIP_ROOT}/{path.relative_to(base).as_posix()}"
        entries.append((f"{name}/", None) if path.is_dir() else (name, path))
    entries.sort(key=lambda entry: entry[0])
    tmp_path = zip_path.with_name(f".{zip_path.name}.tmp")
    try:
        with zipfile.ZipFile(tmp_path, "w") as archive:
            for entry_path, source in entries:
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
    size = zip_path.stat().st_size
    return PackageResult(
        zip_path, size, sum(statuses.values()), statuses, size > SIZE_WARNING_BYTES
    )


def build_manifest(zip_path: Path) -> SlmSuitesManifest:
    """Recompute every hash straight from ``zip_path``; never trusts a previous manifest."""
    zip_path = Path(zip_path)
    entries = []
    with zipfile.ZipFile(zip_path) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            data = archive.read(info.filename)
            entries.append(
                FileHash(path=info.filename, size=len(data), sha256=sha256_of_bytes(data))
            )
    entries.sort(key=lambda item: item.path)
    return SlmSuitesManifest(
        slm_suites_zip=FileHash(
            path=config.ZIP_PATH.as_posix(),
            size=zip_path.stat().st_size,
            sha256=sha256_of_file(zip_path),
        ),
        files=entries,
    )


def write_manifest(root: Path, manifest: SlmSuitesManifest) -> Path:
    path = Path(root) / config.MANIFEST_PATH
    path.parent.mkdir(parents=True, exist_ok=True)  # `manifests/` is versioned, ordinary mode
    files.atomic_write_json(path, manifest)
    return path


def _check_zip(zip_path: Path, manifest: SlmSuitesManifest, result: VerifyResult) -> None:
    entry = manifest.slm_suites_zip
    if not zip_path.is_file():
        result.missing.append(entry.path)
        return
    if zip_path.stat().st_size != entry.size or sha256_of_file(zip_path) != entry.sha256:
        result.changed.append(entry.path)
        return
    # The zip is the one the manifest describes; its members are checked too, so a manifest that
    # was edited (not the zip) is caught as well.
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


def _check_extracted(extracted: Path, manifest: SlmSuitesManifest, result: VerifyResult) -> None:
    prefix = f"{config.ZIP_ROOT}/"
    expected = {item.path.removeprefix(prefix): item for item in manifest.files}
    for rel, item in expected.items():
        path = extracted / rel
        if not path.is_file():
            result.missing.append(item.path)
        elif path.stat().st_size != item.size or sha256_of_file(path) != item.sha256:
            result.changed.append(item.path)
    if extracted.is_dir():
        for path in _tree(extracted):
            rel = path.relative_to(extracted).as_posix()
            if path.is_file() and rel not in expected:
                result.extra.append(f"{prefix}{rel}")


def verify(zip_path: Path, manifest_path: Path, extracted: Path | None = None) -> VerifyResult:
    """Compare the zip (and, if given, the extracted tree) with the manifest, file by file."""
    data = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    manifest = SlmSuitesManifest.model_validate(data)
    result = VerifyResult()
    _check_zip(Path(zip_path), manifest, result)
    if extracted is not None:
        _check_extracted(Path(extracted), manifest, result)
    return result
