"""Isolation of third-party code: dedicated uid per slot, private workdir, resource limits.

Each worker owns a numbered ``slot``. Everything a slot executes runs as the uid ``10000 + slot``
with no capabilities, no supplementary groups, no network (the ``sandbox`` service has none) and
the limits below. The orchestrator is root with only CHOWN, DAC_OVERRIDE, SETUID, SETGID and KILL
(docker-compose.yml). Design and verification: research R8 and decision D13 (rule 7).
"""

import os
import resource
import shutil
from collections.abc import Callable
from pathlib import Path

from sandbox.limits import (
    RUN_FSIZE_BYTES,
    RUN_NPROC,
    cpu_reserve_seconds,
    validate_stack_limit_bytes,
)
from sandbox.types import ExecutionLimits, InfraError

SLOT_UID_BASE = 10000
MAX_SLOTS = 1000

# (resource, soft, hard)
RlimitSpec = tuple[int, int, int]


def sandbox_root() -> Path:
    """The tmpfs where slot workdirs live (``/sandbox`` in the service; overridable for tests)."""
    return Path(os.environ.get("SANDBOX_ROOT", "/sandbox"))


def slot_uid(slot: int) -> int:
    if not 0 <= slot < MAX_SLOTS:
        raise ValueError(f"slot must be in [0, {MAX_SLOTS}), got {slot}")
    return SLOT_UID_BASE + slot


def slot_workdir(slot: int, root: Path | None = None) -> Path:
    slot_uid(slot)  # validates the slot
    return (root or sandbox_root()) / f"slot{slot}"


def prepare_slot_workdir(slot: int, root: Path | None = None) -> Path:
    """Create an EMPTY workdir owned by the slot uid, mode 0700 (no other slot can read it).

    Order matters: root has no CAP_FOWNER, so the mode is set while root still owns the directory
    and ``chown`` (CAP_CHOWN) comes last.
    """
    path = slot_workdir(slot, root)
    uid = slot_uid(slot)
    try:
        if path.exists():
            shutil.rmtree(path)
        path.mkdir(parents=True, mode=0o700)
        os.chmod(path, 0o700)
        os.chown(path, uid, uid)
    except OSError as exc:
        raise InfraError(f"cannot prepare the workdir {path}: {exc}") from exc
    return path


def give_to_slot(path: Path, slot: int) -> None:
    """Hand a file created by the orchestrator (for example the source) to the slot uid."""
    uid = slot_uid(slot)
    try:
        os.chown(path, uid, uid)
    except OSError as exc:
        raise InfraError(f"cannot give {path} to slot {slot}: {exc}") from exc


def run_rlimits(limits: ExecutionLimits) -> list[RlimitSpec]:
    """Kernel limits of a program under evaluation. Time and memory come from the problem."""
    stack = validate_stack_limit_bytes(limits.stack_limit_bytes)  # BYTES, never KiB
    cpu = cpu_reserve_seconds(limits.time_limit_seconds)
    memory = limits.memory_limit_bytes
    return [
        (resource.RLIMIT_STACK, stack, stack),
        (resource.RLIMIT_AS, memory, memory),
        (resource.RLIMIT_CPU, cpu, cpu + 1),  # SIGXCPU at the soft limit, SIGKILL at the hard one
        (resource.RLIMIT_NPROC, RUN_NPROC, RUN_NPROC),
        (resource.RLIMIT_CORE, 0, 0),
        (resource.RLIMIT_FSIZE, RUN_FSIZE_BYTES, RUN_FSIZE_BYTES),
        (resource.RLIMIT_MSGQUEUE, 0, 0),  # /dev/mqueue is world-writable: no POSIX queues
    ]


def make_preexec(slot: int, rlimits: list[RlimitSpec]) -> Callable[[], None]:
    """The function run in the child between ``fork`` and ``exec``, in this exact order.

    New session (the whole tree can be killed by group) -> no supplementary groups -> gid -> uid
    (drops every capability) -> resource limits. ``setuid`` MUST come before ``RLIMIT_NPROC``: the
    kernel can refuse the ``execve`` if the process count of the new uid already exceeds it.
    No shell is involved anywhere.
    """
    uid = slot_uid(slot)

    def preexec() -> None:
        os.setsid()
        os.setgroups([])
        os.setgid(uid)
        os.setuid(uid)
        for res, soft, hard in rlimits:
            resource.setrlimit(res, (soft, hard))

    return preexec


def kill_slot_processes(slot: int) -> int:
    """SIGKILL every process of the slot uid (children that left the session); returns how many."""
    uid = slot_uid(slot)
    killed = 0
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            for line in (entry / "status").read_text().splitlines():
                if line.startswith("Uid:"):
                    if int(line.split()[1]) == uid:
                        os.kill(int(entry.name), 9)
                        killed += 1
                    break
        except (OSError, ValueError):
            continue
    return killed
