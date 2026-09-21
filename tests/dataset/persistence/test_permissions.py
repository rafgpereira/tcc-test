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


def test_chmod_is_skipped_when_the_mode_is_already_right(tmp_path, monkeypatch):
    """No chmod means no EPERM for root without CAP_FOWNER on a directory of the host user."""
    target = tmp_path / "x"
    store.make_private_dir(target)

    def refuse(path, mode):
        raise PermissionError(1, "Operation not permitted")

    monkeypatch.setattr(os, "chmod", refuse)
    store.make_private_dir(target)  # must not call chmod
    assert mode(target) == 0o700


def test_chmod_falls_back_to_taking_ownership_when_root_lacks_fowner(tmp_path, monkeypatch):
    """Regression: the sandbox service is root without CAP_FOWNER (found in the container run)."""
    target = tmp_path / "x"
    target.mkdir()
    os.chmod(target, 0o755)
    real_chmod, calls, chowns = os.chmod, [], []

    def flaky_chmod(path, new_mode):
        calls.append(new_mode)
        if len(calls) == 1:
            raise PermissionError(1, "Operation not permitted")
        real_chmod(path, new_mode)

    monkeypatch.setattr(os, "geteuid", lambda: 0)
    monkeypatch.setattr(os, "chmod", flaky_chmod)
    monkeypatch.setattr(os, "chown", lambda p, u, g: chowns.append((Path(p), u, g)))
    store._set_mode(target, 0o700)

    owner = target.stat()
    assert calls == [0o700, 0o700], "the second chmod happens after taking ownership"
    assert chowns[0] == (target, 0, owner.st_gid), "takes ownership as root first"
    assert chowns[-1] == (target, owner.st_uid, owner.st_gid), "gives the directory back"
    assert mode(target) == 0o700


def test_a_non_root_chmod_failure_is_not_swallowed(tmp_path, monkeypatch):
    target = tmp_path / "x"
    target.mkdir()
    os.chmod(target, 0o755)

    def refuse(path, new_mode):
        raise PermissionError(1, "Operation not permitted")

    monkeypatch.setattr(os, "geteuid", lambda: 1000)
    monkeypatch.setattr(os, "chmod", refuse)
    with pytest.raises(PermissionError):
        store._set_mode(target, 0o700)


@pytest.mark.integration
@pytest.mark.skipif(os.geteuid() != 0, reason="needs root to own files as another uid")
def test_a_work_dir_owned_by_the_host_user_can_be_reused_and_tightened(tmp_path, monkeypatch):
    """Regression for the resume case: ensure_work_dir runs again on directories given to the host."""
    monkeypatch.setenv("HOST_UID", "12345")
    monkeypatch.setenv("HOST_GID", "12345")
    work = store.ensure_work_dir(tmp_path)
    assert work.stat().st_uid == 12345

    store.ensure_work_dir(tmp_path)  # second call must not raise

    os.chown(work, 0, 0)  # loosen it the way a manual `mkdir` on the host would have
    os.chmod(work, 0o755)
    os.chown(work, 12345, 12345)
    store.ensure_work_dir(tmp_path)
    assert mode(work) == 0o700
    assert work.stat().st_uid == 12345, "ownership stays with the host user"


@pytest.mark.integration
@pytest.mark.skipif(os.geteuid() != 0, reason="needs root to switch to another uid")
def test_a_child_with_a_dedicated_uid_cannot_touch_the_work_dir():
    """The child must not list, read or write data/work/, but public files stay readable."""
    # /sandbox (0755) mirrors the production layout; /tmp is root-only (0700) in the sandbox service,
    # so a child could not even reach a public file placed there.
    root = Path(tempfile.mkdtemp(prefix="perm-test-", dir="/sandbox"))
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
