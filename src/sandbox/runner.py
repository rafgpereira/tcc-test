"""Run one process under isolation and measure it (contract: engine-api.md, ``run_binary``).

A program under evaluation runs through ``sandbox-launch`` (src/sandbox/launcher/launcher.cpp),
which reports how it ended and its memory peak from a tiny process; measuring it from this large
Python process would inflate ``ru_maxrss`` with the resident set of the forked parent.

One selector loop feeds ``stdin`` and drains ``stdout``/``stderr`` without threads, enforces the
wall clock reserve and the output cap, and kills the whole process group when the leader ends.
CPU time comes from ``wait4`` (``ru_utime + ru_stime``), never from the wall clock. Any failure to
start the process is an ``InfraError``: a broken environment is never a verdict (FR-010).
"""

import os
import selectors
import signal
import subprocess
import time
from collections.abc import Mapping, Sequence
from pathlib import Path

from sandbox import isolation
from sandbox.limits import (
    LAUNCHER_PATH,
    MAX_OUTPUT_BYTES,
    STDERR_TAIL_BYTES,
    wall_reserve_seconds,
)
from sandbox.types import ExecutionLimits, InfraError, RunResult, RunStatus

_CHUNK = 64 * 1024
# After the leader exits, pipes held by stray children should close right after the group kill.
_DRAIN_GRACE_S = 1.0


def _kill_group(pgid: int) -> bool:
    """SIGKILL the process group; True if it still had members."""
    try:
        os.killpg(pgid, signal.SIGKILL)
    except ProcessLookupError:
        return False
    except PermissionError as exc:
        raise InfraError(f"cannot kill process group {pgid}: {exc}") from exc
    return True


def launcher_path() -> str:
    return os.environ.get("SANDBOX_LAUNCHER", LAUNCHER_PATH)


def parse_report(text: str) -> tuple[int, int, float, int] | None:
    """Parse the launcher report into (exec errno, wait status, cpu seconds, maxrss KiB)."""
    parts = text.split()
    if len(parts) != 7:
        return None
    exec_errno, status, u_s, u_us, s_s, s_us, maxrss = (int(part) for part in parts)
    return exec_errno, status, u_s + u_us / 1e6 + s_s + s_us / 1e6, maxrss


def execute(
    argv: Sequence[str],
    *,
    stdin: bytes,
    slot: int,
    rlimits: list[isolation.RlimitSpec],
    cwd: Path,
    wall_limit_s: float,
    env: Mapping[str, str],
    max_stdout_bytes: int = MAX_OUTPUT_BYTES,
    stderr_bytes: int = STDERR_TAIL_BYTES,
    measured_by_launcher: bool = False,
) -> RunResult:
    """Run ``argv`` as the slot uid with ``rlimits`` and return what happened.

    With ``measured_by_launcher`` the program runs through ``sandbox-launch`` and its exit status,
    CPU time and memory peak come from the launcher's report.
    """
    report_r = report_w = -1
    command = list(argv)
    pass_fds: tuple[int, ...] = ()
    if measured_by_launcher:
        report_r, report_w = os.pipe()
        command = [launcher_path(), str(report_w), *argv]
        pass_fds = (report_w,)
    started = time.monotonic()
    try:
        proc = subprocess.Popen(  # argv is a list and there is no shell
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=cwd,
            env=dict(env),
            close_fds=True,
            pass_fds=pass_fds,
            preexec_fn=isolation.make_preexec(slot, rlimits),  # noqa: PLW1509
        )
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        for fd in (report_r, report_w):
            if fd >= 0:
                os.close(fd)
        raise InfraError(f"cannot start {argv[0]} in slot {slot}: {exc}") from exc
    if report_w >= 0:
        os.close(report_w)  # only the launcher keeps the write end

    deadline = started + wall_limit_s
    assert proc.stdin is not None and proc.stdout is not None and proc.stderr is not None
    selector = selectors.DefaultSelector()
    out = bytearray()
    err = bytearray()
    for stream, name in ((proc.stdout, "out"), (proc.stderr, "err")):
        os.set_blocking(stream.fileno(), False)
        selector.register(stream, selectors.EVENT_READ, name)
    written = 0
    if stdin:
        os.set_blocking(proc.stdin.fileno(), False)
        selector.register(proc.stdin, selectors.EVENT_WRITE, "in")
    else:
        proc.stdin.close()

    def close_stdin() -> None:
        selector.unregister(proc.stdin)
        proc.stdin.close()

    exited = False
    exit_at = 0.0
    status = 0
    rusage = None
    timed_out = False
    output_limit = False
    pgid = proc.pid  # the child called setsid, so it leads its own group
    try:
        while selector.get_map():
            now = time.monotonic()
            if now >= deadline:
                timed_out = True
                break
            if exited and now >= exit_at + _DRAIN_GRACE_S:
                break
            for key, _ in selector.select(timeout=min(deadline - now, 0.05 if exited else 0.2)):
                if key.data == "in":
                    try:
                        written += os.write(proc.stdin.fileno(), stdin[written : written + _CHUNK])
                    except BlockingIOError:
                        pass
                    except BrokenPipeError:
                        written = len(stdin)
                    if written >= len(stdin):
                        close_stdin()
                    continue
                data = os.read(key.fileobj.fileno(), _CHUNK)
                if not data:
                    selector.unregister(key.fileobj)
                    key.fileobj.close()
                elif key.data == "out":
                    out += data
                    if len(out) > max_stdout_bytes:
                        output_limit = True
                else:
                    err += data
                    if len(err) > stderr_bytes:
                        del err[: len(err) - stderr_bytes]
            if output_limit:
                break
            if not exited:
                reaped, status_, rusage_ = os.wait4(proc.pid, os.WNOHANG)
                if reaped:
                    exited, exit_at, status, rusage = True, time.monotonic(), status_, rusage_
                    _kill_group(pgid)  # stray children may still hold the pipes
        if not exited:
            _kill_group(pgid)
            _, status, rusage = os.wait4(proc.pid, 0)
        leftovers = _kill_group(pgid)
        if leftovers:
            isolation.kill_slot_processes(slot)
    except OSError as exc:
        _kill_group(pgid)
        raise InfraError(f"failure while running in slot {slot}: {exc}") from exc
    finally:
        selector.close()
        for stream in (proc.stdin, proc.stdout, proc.stderr):
            if stream is not None and not stream.closed:
                stream.close()

    proc.returncode = os.waitstatus_to_exitcode(status)
    wall = time.monotonic() - started
    cpu = rusage.ru_utime + rusage.ru_stime
    peak_kib = rusage.ru_maxrss
    if measured_by_launcher:
        try:
            text = os.read(report_r, 4096).decode("ascii", errors="replace")
        finally:
            os.close(report_r)
        report = parse_report(text)
        if report is not None:
            exec_errno, status, cpu, peak_kib = report
            if exec_errno:
                raise InfraError(f"cannot exec {argv[0]}: {os.strerror(exec_errno)}")
        else:  # the launcher was killed (wall clock reserve): only its own usage is known
            peak_kib = 0
    signaled = os.WIFSIGNALED(status)
    signum = os.WTERMSIG(status) if signaled else None
    exit_code = None if signaled else os.WEXITSTATUS(status)
    if timed_out:
        run_status = RunStatus.TIMEOUT
    elif output_limit:
        run_status = RunStatus.OUTPUT_LIMIT
    elif signaled:
        run_status = RunStatus.SIGNALED
    elif exit_code != 0:
        run_status = RunStatus.NONZERO_EXIT
    else:
        run_status = RunStatus.OK
    return RunResult(
        status=run_status,
        exit_code=exit_code,
        signal=signum,
        stdout=bytes(out[:max_stdout_bytes]),
        stderr_tail=bytes(err),
        cpu_time_s=cpu,
        wall_time_s=wall,
        peak_rss_bytes=peak_kib * 1024,  # Linux reports KiB
    )


def run_binary(binary: Path, stdin: bytes, limits: ExecutionLimits, slot: int) -> RunResult:
    """Run a compiled program on one test input under the limits of the problem."""
    return execute(
        [str(binary)],
        stdin=stdin,
        slot=slot,
        rlimits=isolation.run_rlimits(limits),
        cwd=Path(binary).parent,
        wall_limit_s=wall_reserve_seconds(limits.time_limit_seconds),
        env={},
        measured_by_launcher=True,
    )
