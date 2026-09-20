"""Tests for the private work directory (T012, part 2; spec decision D15).

The ``./data`` bind mount inherits the host permission (typically 0755), which a child process
with a dedicated uid could read. ``data/work/`` therefore is created with mode 0700.
"""

import os
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from dataset.persistence import store

SUBDIRS = ["staging", "staging/raw", "staging/shards", "building", "problems", "reports"]


def mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def test_work_dir_is_created_with_0700_even_under_a_permissive_umask(tmp_path):
    old = os.umask(0)
    try:
        work = store.ensure_work_dir(tmp_path)
    finally:
        os.umask(old)
    assert work == tmp_path / "data" / "work"
    assert mode(work) == 0o700


def test_an_existing_0755_work_dir_is_tightened_to_0700(tmp_path):
    work = tmp_path / "data" / "work"
    work.mkdir(parents=True)
    os.chmod(work, 0o755)
    store.ensure_work_dir(tmp_path)
    assert mode(work) == 0o700


def test_every_subdirectory_is_private(tmp_path):
    old = os.umask(0)
    try:
        work = store.ensure_work_dir(tmp_path)
    finally:
        os.umask(old)
    for sub in SUBDIRS:
        assert (work / sub).is_dir(), sub
        assert mode(work / sub) == 0o700, sub


def test_make_private_dir_is_0700_and_idempotent(tmp_path):
    target = tmp_path / "x"
    old = os.umask(0)
    try:
        store.make_private_dir(target)
        store.make_private_dir(target)
    finally:
        os.umask(old)
    assert mode(target) == 0o700


def test_ensure_work_dir_is_idempotent(tmp_path):
    first = store.ensure_work_dir(tmp_path)
    (first / "problems" / "keep.txt").write_text("x")
    second = store.ensure_work_dir(tmp_path)
    assert first == second
    assert (second / "problems" / "keep.txt").read_text() == "x"
    assert mode(second) == 0o700


def test_chown_to_host_uses_host_ids_when_root(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    monkeypatch.setattr(os, "chown", lambda p, u, g: calls.append((Path(p), u, g)))
    monkeypatch.setenv("HOST_UID", "1234")
    monkeypatch.setenv("HOST_GID", "5678")
    store.chown_to_host(tmp_path)
    assert calls == [(tmp_path, 1234, 5678)]


def test_chown_to_host_is_a_noop_when_unset_or_not_root(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(os, "chown", lambda p, u, g: calls.append((p, u, g)))
    monkeypatch.delenv("HOST_UID", raising=False)
    monkeypatch.delenv("HOST_GID", raising=False)
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    store.chown_to_host(tmp_path)
    monkeypatch.setenv("HOST_UID", "1234")
    monkeypatch.setenv("HOST_GID", "5678")
    monkeypatch.setattr(os, "geteuid", lambda: 1000)
    store.chown_to_host(tmp_path)
    assert calls == []


@pytest.mark.integration
@pytest.mark.skipif(os.geteuid() != 0, reason="needs root to switch to another uid")
def test_a_child_with_a_dedicated_uid_cannot_touch_the_work_dir():
    """The child must not list, read or write data/work/, but public files stay readable."""
    root = Path(tempfile.mkdtemp(prefix="perm-test-", dir="/tmp"))
    os.chmod(root, 0o755)
    try:
        work = store.ensure_work_dir(root)
        secret = work / "problems" / "secret.txt"
        secret.write_text("secret")
        os.chmod(root / "data", 0o755)
        public = root / "data" / "dataset.zip"
        public.write_text("public")
        os.chmod(public, 0o644)

        def as_child(code: str) -> subprocess.CompletedProcess:
            def drop():
                os.setgroups([])
                os.setgid(10001)
                os.setuid(10001)

            return subprocess.run(
                [sys.executable, "-c", code],
                preexec_fn=drop,
                capture_output=True,
                text=True,
                check=False,
            )

        listing = as_child(f"import os; os.listdir({str(work)!r})")
        reading = as_child(f"open({str(secret)!r}).read()")
        writing = as_child(f"open({str(work / 'problems' / 'x')!r}, 'w').write('x')")
        public_read = as_child(f"print(open({str(public)!r}).read())")

        assert "PermissionError" in listing.stderr
        assert "PermissionError" in reading.stderr
        assert "PermissionError" in writing.stderr
        assert public_read.returncode == 0 and public_read.stdout.strip() == "public"
    finally:
        subprocess.run(["rm", "-rf", str(root)], check=False)
