"""The public copy of the dashboard (Streamlit Community Cloud): the data it reads.

The cloud clones the repository, where ``data/`` holds only the versioned packages (zips). Before
the first page opens, ``prepare`` unzips each package whose folder is still missing into ``data/``,
in the same layout as the ``unzip ... -d data/`` of the module READMEs. Each package goes first to a
temporary folder and is moved in place only when complete, so an interrupted start never leaves a
half-unzipped folder behind. Nothing else is written, and nothing is sent anywhere.
"""

import shutil
import tempfile
import zipfile
from pathlib import Path

from dashboard import config


def _top_folders(archive: zipfile.ZipFile) -> set[str]:
    return {Path(name).parts[0] for name in archive.namelist()}


def _target(archive: zipfile.ZipFile) -> Path:
    """The folder a package fills (``evaluation/gpt``, ``suites/gpt``, ``dataset``...)."""
    names = [Path(n) for n in archive.namelist()]
    top = _top_folders(archive)
    if len(top) != 1:
        raise ValueError(f"a package must have one top folder, found {sorted(top)}")
    (root,) = top
    if root in ("evaluation", "suites"):
        second = {n.parts[1] for n in names if len(n.parts) > 1}
        return Path(root) / min(second)
    return Path(root)


def prepare(root: Path) -> list[str]:
    """Unzip into ``root/data`` every public package whose folder is missing; what was unzipped."""
    data = root / "data"
    done = []
    for package in config.PUBLIC_PACKAGES:
        with zipfile.ZipFile(root / package) as archive:
            target = _target(archive)
            if (data / target).is_dir():
                continue
            with tempfile.TemporaryDirectory(dir=data) as scratch:
                archive.extractall(scratch)
                for folder in sorted(Path(scratch).iterdir()):
                    _merge(folder, data / folder.name)
        done.append(package)
    return done


def _merge(source: Path, destination: Path) -> None:
    """Move ``source`` to ``destination``; folders already there gain only the missing entries."""
    if not destination.exists():
        shutil.move(str(source), str(destination))
        return
    if source.is_dir():
        for item in sorted(source.iterdir()):
            _merge(item, destination / item.name)
