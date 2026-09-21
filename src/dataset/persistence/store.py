"""Deterministic serialization, atomic writes and the private work directory.

JSON files are written with sorted keys and a final newline, so the same object always gives the
same bytes (Constitution, Principle II). Every write is atomic (temporary file in the same
directory, then ``os.replace``), so an interruption never leaves a truncated file (Principle VII).
"""

import gzip
import io
import json
import os
import stat
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


def atomic_write_json_gz(path: Path, obj: Any) -> None:
    """Write ``obj`` as gzip-compressed JSON atomically.

    The gzip header carries no timestamp and no file name, so the same object always gives the same
    bytes.
    """
    payload = dumps_json(obj).encode("utf-8")
    buffer = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=buffer, mtime=0, compresslevel=6) as gz:
        gz.write(payload)
    _atomic_write_bytes(path, buffer.getvalue())


def read_json(path: Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def read_json_gz(path: Path) -> Any:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        return json.load(handle)


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


def _set_mode(path: Path, mode: int) -> None:
    """``chmod`` that also works for root WITHOUT ``CAP_FOWNER`` on a directory of another owner.

    The ``sandbox`` service is root but keeps only CHOWN, DAC_OVERRIDE, SETUID, SETGID and KILL.
    ``DAC_OVERRIDE`` lets it read and write anywhere, but changing the mode of a file it does not
    own needs ``CAP_FOWNER``. After ``chown_to_host`` the directories belong to the host user, so a
    second call (for example when a run is resumed) would fail with EPERM. The mode is left alone
    when it is already right; otherwise root takes ownership (``CAP_CHOWN``), changes the mode as
    the owner and gives the directory back.
    """
    if stat.S_IMODE(path.stat().st_mode) == mode:
        return
    try:
        os.chmod(path, mode)
    except PermissionError:
        if os.geteuid() != 0:
            raise
        before = path.stat()
        os.chown(path, os.geteuid(), before.st_gid)
        try:
            os.chmod(path, mode)
        finally:
            os.chown(path, before.st_uid, before.st_gid)


def make_private_dir(path: Path) -> Path:
    """Create a directory with mode 0700, tightening it if it exists (``umask`` cannot loosen it)."""
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    _set_mode(path, 0o700)
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
