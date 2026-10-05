"""Unit tests of the isolation helpers that do not need root (T042; D13 rule 7).

The behaviour of the real child (uid, capabilities, limits, filesystem) is covered by the
integration tests in test_runner_isolation.py, which run in the `sandbox` service.
"""

import os
import resource
from pathlib import Path

import pytest

from sandbox import isolation
from sandbox.limits import RUN_FSIZE_BYTES, RUN_NPROC, STACK_LIMIT_BYTES, cpu_reserve_seconds
from sandbox.types import ExecutionLimits

LIMITS = ExecutionLimits(time_limit_seconds=1.5, memory_limit_bytes=128 * 1024 * 1024)


def test_the_uid_of_a_slot_is_10000_plus_the_slot():
    assert isolation.slot_uid(0) == 10000
    assert isolation.slot_uid(7) == 10007


@pytest.mark.parametrize("slot", [-1, 1000, 10**6])
def test_an_out_of_range_slot_is_rejected(slot):
    with pytest.raises(ValueError):
        isolation.slot_uid(slot)


def test_the_workdir_of_a_slot_is_under_the_sandbox_root():
    assert isolation.slot_workdir(3, Path("/sandbox")) == Path("/sandbox/slot3")


def test_the_run_rlimits_come_from_the_problem_and_the_engine_constants():
    specs = {res: (soft, hard) for res, soft, hard in isolation.run_rlimits(LIMITS)}
    assert specs[resource.RLIMIT_STACK] == (STACK_LIMIT_BYTES, STACK_LIMIT_BYTES)
    assert specs[resource.RLIMIT_AS] == (128 * 1024 * 1024, 128 * 1024 * 1024)
    cpu = cpu_reserve_seconds(1.5)
    assert specs[resource.RLIMIT_CPU][0] == cpu
    assert specs[resource.RLIMIT_CPU][1] >= cpu
    assert specs[resource.RLIMIT_NPROC] == (RUN_NPROC, RUN_NPROC)
    assert specs[resource.RLIMIT_CORE] == (0, 0)
    assert specs[resource.RLIMIT_FSIZE] == (RUN_FSIZE_BYTES, RUN_FSIZE_BYTES)
    assert specs[resource.RLIMIT_MSGQUEUE] == (0, 0)


def test_the_stack_limit_is_in_bytes_and_never_kib():
    stack = {res: soft for res, soft, _ in isolation.run_rlimits(LIMITS)}[resource.RLIMIT_STACK]
    assert stack == 268435456
    assert stack != 262144


def test_the_preexec_order_is_session_groups_gid_uid_and_only_then_rlimits(monkeypatch):
    calls = []
    monkeypatch.setattr(os, "setsid", lambda: calls.append("setsid"))
    monkeypatch.setattr(os, "setgroups", lambda groups: calls.append(("setgroups", list(groups))))
    monkeypatch.setattr(os, "setgid", lambda gid: calls.append(("setgid", gid)))
    monkeypatch.setattr(os, "setuid", lambda uid: calls.append(("setuid", uid)))
    monkeypatch.setattr(
        resource, "setrlimit", lambda res, lim: calls.append(("setrlimit", res, lim))
    )
    rlimits = isolation.run_rlimits(LIMITS)
    isolation.make_preexec(2, rlimits)()
    assert calls[:4] == ["setsid", ("setgroups", []), ("setgid", 10002), ("setuid", 10002)]
    assert [c[0] for c in calls[4:]] == ["setrlimit"] * len(rlimits)
    # RLIMIT_NPROC only after setuid: the kernel can refuse the execve otherwise (research R8).
    assert calls.index(("setuid", 10002)) < min(
        i for i, c in enumerate(calls) if c[0] == "setrlimit"
    )


def test_a_failure_while_dropping_privileges_is_not_swallowed(monkeypatch):
    def boom(uid):
        raise PermissionError("no CAP_SETUID")

    monkeypatch.setattr(os, "setsid", lambda: None)
    monkeypatch.setattr(os, "setgroups", lambda groups: None)
    monkeypatch.setattr(os, "setgid", lambda gid: None)
    monkeypatch.setattr(os, "setuid", boom)
    with pytest.raises(PermissionError):
        isolation.make_preexec(0, isolation.run_rlimits(LIMITS))()
