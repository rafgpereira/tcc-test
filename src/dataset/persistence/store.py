"""Deterministic serialization, atomic writes and the private work directory.

JSON files are written with sorted keys and a final newline, so the same object always gives the
same bytes (Constitution, Principle II). Every write is atomic (temporary file in the same
directory, then ``os.replace``), so an interruption never leaves a truncated file (Principle VII).
"""

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from dataset import config


def normalize_text(data: str | bytes, encoding: str = "utf-8") -> str:
    """Normalize source or statement text: UTF-8 without BOM and ``\\r\\n`` turned into ``\\n``.

    Nothing else changes; the content is never edited semantically. Invalid bytes are replaced
    (U+FFFD) instead of raising, which keeps the result deterministic.
    """
    text = data if isinstance(data, str) else data.decode(encoding, errors="replace")
    text = text.removeprefix("﻿")
    return text.replace("\r\n", "\n")


def dumps_json(obj: Any) -> str:
    """Serialize to the project JSON format: sorted keys, 2-space indent, UTF-8, final newline."""
    if isinstance(obj, BaseModel):
        obj = obj.model_dump(mode="json")
    return json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    path = Path(path)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp_name, 0o644)
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise


def atomic_write_json(path: Path, obj: Any) -> None:
    """Write ``obj`` as JSON atomically. Serialization happens first, so a failure touches nothing."""
    _atomic_write_bytes(path, dumps_json(obj).encode("utf-8"))


def atomic_write_text(path: Path, text: str) -> None:
    """Write text atomically, normalized (UTF-8, ``\\n``)."""
    _atomic_write_bytes(path, normalize_text(text).encode("utf-8"))


def chown_to_host(path: Path) -> None:
    """Give a file to the host user, so files written by root in a bind mount are not root-owned.

    A no-op unless running as root with ``HOST_UID`` and ``HOST_GID`` set.
    """
    if os.geteuid() != 0:
        return
    uid, gid = os.environ.get("HOST_UID"), os.environ.get("HOST_GID")
    if uid is None or gid is None:
        return
    os.chown(path, int(uid), int(gid))


def make_private_dir(path: Path) -> Path:
    """Create a directory with mode 0700, tightening it if it exists (``umask`` cannot loosen it)."""
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    os.chmod(path, 0o700)
    chown_to_host(path)
    return path


def ensure_work_dir(root: Path = Path(".")) -> Path:
    """Create ``<root>/data/work`` and its subdirectories, all with mode 0700.

    The ``./data`` bind mount inherits the host permission (typically 0755), which a child process
    with a dedicated uid could read. ``data/work/`` holds the raw dataset, the problems under
    construction and the finished ones, so it must be private (spec decision D15).
    """
    work = make_private_dir(Path(root) / config.WORK_DIR)
    for sub in config.WORK_SUBDIRS:
        make_private_dir(work / sub)
    return work
