"""Deterministic packaging of the validated dataset into `data/dataset.zip` (FR-026, FR-029).

Only `complete` problems are packaged (`pending_triage` and `discarded` are excluded, D4/D17).
Entries are sorted by path, with a fixed modification time (the earliest one the zip format
allows, 1980-01-01), fixed Unix permissions (`0644` files, `0755` directories), `deflate` at a
fixed level, no extra fields and no comment (research R14), so the same input gives the same zip
bytes in the same environment (SC-008). The root inside the zip is `dataset/`, so
`unzip data/dataset.zip -d data/` produces `data/dataset/problems/<problem_id>/`.
"""

import os
import zipfile
from dataclasses import dataclass
from pathlib import Path

from dataset import config
from dataset.persistence import store

ZIP_ROOT = "dataset"
FIXED_DATE_TIME = (1980, 1, 1, 0, 0, 0)  # the earliest date the zip format can represent
FILE_MODE = 0o644
DIR_MODE = 0o755
COMPRESS_LEVEL = 6
SIZE_WARNING_BYTES = 95 * 1024 * 1024  # research R15: GitHub warns above 50 MB, refuses above 100


@dataclass(frozen=True)
class PackageResult:
    zip_path: Path
    size: int
    problem_count: int
    over_size_warning: bool


def list_complete_problems(root: Path) -> list[str]:
    """Problem ids under `data/work/problems/` whose `validacao.json.status == "complete"`."""
    problems_dir = Path(root) / config.PROBLEMS_DIR
    if not problems_dir.is_dir():
        return []
    return sorted(
        p.name
        for p in problems_dir.iterdir()
        if p.is_dir() and store.problem_status(root, p.name) == "complete"
    )


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
        folder = Path(root) / config.PROBLEMS_DIR / pid
        for file_path in sorted(folder.iterdir()):
            if file_path.is_file():
                entries.append((f"{prefix}/{file_path.name}", file_path))
    entries.sort(key=lambda entry: entry[0])
    return entries


def build_dataset_zip(root: Path, zip_path: Path) -> PackageResult:
    """Build the zip atomically (temp file + `os.replace`) from every `complete` problem."""
    root, zip_path = Path(root), Path(zip_path)
    problem_ids = list_complete_problems(root)
    tmp_path = zip_path.with_name(f".{zip_path.name}.tmp")
    try:
        with zipfile.ZipFile(tmp_path, "w") as zf:
            for entry_path, source in _planned_entries(root, problem_ids):
                if source is None:
                    zf.writestr(_dir_info(entry_path), b"")
                else:
                    zf.writestr(
                        _file_info(entry_path), source.read_bytes(), compresslevel=COMPRESS_LEVEL
                    )
        os.replace(tmp_path, zip_path)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise
    size = zip_path.stat().st_size
    return PackageResult(zip_path, size, len(problem_ids), size > SIZE_WARNING_BYTES)
