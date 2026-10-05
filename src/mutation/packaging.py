"""Deterministic packaging of the mutants of the final run into ``data/mutants.zip`` (FR-012).

Same conventions as the dataset zip (``dataset.integrity.packaging``): entries sorted by path, a
fixed modification time (1980-01-01), fixed Unix permissions (``0644`` files, ``0755``
directories), ``deflate`` at a fixed level and no extra fields, so the same input gives the same
zip bytes. The root inside the zip is ``mutants/problems/``, so ``unzip data/mutants.zip -d data/``
lands exactly on the path ``generate`` writes (``data/mutants/problems/<id>/``): whoever generated
and whoever only received the package read the mutants from the same place.

Only the ``Mutant_<n>.cpp`` of COMPLETE problems go in. A problem excluded for not reaching 100 has
no folder in the zip, and ``generation.json``, ``.lock`` and ``building/`` never do. The packaging
refuses to run over a half-finished generation or a damaged problem, because a package is only worth
versioning if it is exactly what a whole run produced.
"""

import os
import zipfile
from dataclasses import dataclass
from pathlib import Path

from dataset.integrity.packaging import (
    COMPRESS_LEVEL,
    DIR_MODE,
    FILE_MODE,
    FIXED_DATE_TIME,
    SIZE_WARNING_BYTES,
)
from mutation import config, persistence

ZIP_ROOT = "mutants"


class PendingBuildError(Exception):
    """A problem is still half-written in ``data/mutants/building/``."""


class DamagedProblemError(Exception):
    """A closed problem lost or changed a file after it was closed."""


@dataclass(frozen=True)
class PackageResult:
    zip_path: Path
    size: int
    problem_count: int
    excluded_count: int
    over_size_warning: bool


def list_complete_problems(root: Path) -> list[str]:
    """Ids of the closed problems whose ``generation.json`` says ``complete``, sorted."""
    return [
        pid
        for pid in persistence.closed_problems(root)
        if persistence.read_generation(root, pid).status == "complete"
    ]


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


def _planned_entries(root: Path, problem_ids: list[str]) -> list[tuple[str, Path | None]]:
    """`(zip_path, source_file_or_None)`, `None` for directories; sorted by `zip_path`."""
    entries: list[tuple[str, Path | None]] = [
        (f"{ZIP_ROOT}/", None),
        (f"{ZIP_ROOT}/problems/", None),
    ]
    for pid in problem_ids:
        prefix = f"{ZIP_ROOT}/problems/{pid}"
        entries.append((f"{prefix}/", None))
        folder = persistence.problem_path(root, pid)
        for path in folder.glob(f"{config.MUTANT_FILE_PREFIX}*{config.MUTANT_FILE_SUFFIX}"):
            entries.append((f"{prefix}/{path.name}", path))
    entries.sort(key=lambda entry: entry[0])
    return entries


def build_mutants_zip(root: Path, zip_path: Path) -> PackageResult:
    """Build the zip atomically (temp file + ``os.replace``) from every complete problem."""
    root, zip_path = Path(root), Path(zip_path)
    pending = persistence.pending_building(root)
    if pending:
        raise PendingBuildError(
            f"{len(pending)} problem(s) half-written in {config.BUILDING_DIR} "
            f"({', '.join(pending)}); run `generate` again to finish them"
        )
    damaged = {
        pid: findings
        for pid in persistence.closed_problems(root)
        if (findings := persistence.check_closed(root, pid))
    }
    if damaged:
        listing = "; ".join(f"{pid}: {', '.join(found)}" for pid, found in sorted(damaged.items()))
        raise DamagedProblemError(f"damaged problem(s), delete and regenerate them: {listing}")
    problem_ids = list_complete_problems(root)
    excluded = len(persistence.closed_problems(root)) - len(problem_ids)
    tmp_path = zip_path.with_name(f".{zip_path.name}.tmp")
    try:
        with zipfile.ZipFile(tmp_path, "w") as archive:
            for entry_path, source in _planned_entries(root, problem_ids):
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
    return PackageResult(zip_path, size, len(problem_ids), excluded, size > SIZE_WARNING_BYTES)
