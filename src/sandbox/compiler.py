"""Compile C++ with the flags of the original judge (FR-008; contract: engine-api.md).

The flags are the judge's, minus the Windows-only ``-Wl,--stack=268435456`` that the Linux linker
rejects: the 256 MiB stack is applied at run time instead (FR-009a). The standard falls back along
the cascade ``gnu++20 -> gnu++17 -> gnu++14 -> gnu++11``, stopping at the first success. The
compiler runs as the slot uid, without network, with its own time and memory limits.
"""

import os
import resource
from pathlib import Path

from sandbox import isolation
from sandbox.limits import (
    COMPILE_AS_BYTES,
    COMPILE_CPU_S,
    COMPILE_FSIZE_BYTES,
    COMPILE_NPROC,
    COMPILE_WALL_S,
    DIAGNOSTIC_BYTES,
)
from sandbox.runner import execute
from sandbox.types import CompileAttempt, CompileResult, InfraError, RunStatus

COMPILE_FLAGS = ("-Wall", "-Wextra", "-Wconversion", "-static", "-DONLINE_JUDGE", "-O2")
STANDARD_CASCADE = ("gnu++20", "gnu++17", "gnu++14", "gnu++11")
SOURCE_NAME = "main.cpp"
BINARY_NAME = "main"


def build_command(standard: str, source_name: str, output_name: str) -> list[str]:
    return ["g++", *COMPILE_FLAGS, f"-std={standard}", source_name, "-o", output_name]


def _compile_rlimits() -> list[isolation.RlimitSpec]:
    return [
        (resource.RLIMIT_CPU, COMPILE_CPU_S, COMPILE_CPU_S + 1),
        (resource.RLIMIT_AS, COMPILE_AS_BYTES, COMPILE_AS_BYTES),
        (resource.RLIMIT_NPROC, COMPILE_NPROC, COMPILE_NPROC),
        (resource.RLIMIT_CORE, 0, 0),
        (resource.RLIMIT_FSIZE, COMPILE_FSIZE_BYTES, COMPILE_FSIZE_BYTES),
    ]


def _text(data: bytes) -> str:
    return data[-DIAGNOSTIC_BYTES:].decode("utf-8", errors="replace")


def compile_cpp(source: str, workdir: Path, slot: int) -> CompileResult:
    """Compile ``source`` in ``workdir`` (owned by the slot) and return the binary or the diagnostics."""
    workdir = Path(workdir)
    source_path = workdir / SOURCE_NAME
    binary_path = workdir / BINARY_NAME
    try:
        binary_path.unlink(missing_ok=True)
        source_path.write_text(source, encoding="utf-8")
    except OSError as exc:
        raise InfraError(f"cannot write the source in {workdir}: {exc}") from exc
    isolation.give_to_slot(source_path, slot)

    env = {"PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"), "TMPDIR": str(workdir)}
    attempts: list[CompileAttempt] = []
    for standard in STANDARD_CASCADE:
        run = execute(
            build_command(standard, SOURCE_NAME, BINARY_NAME),
            stdin=b"",
            slot=slot,
            rlimits=_compile_rlimits(),
            cwd=workdir,
            wall_limit_s=COMPILE_WALL_S,
            env=env,
            stderr_bytes=DIAGNOSTIC_BYTES,
        )
        if run.status is RunStatus.OK:
            if not binary_path.is_file():
                raise InfraError(f"g++ exited 0 but {binary_path} does not exist")
            attempts.append(CompileAttempt(standard, True, ""))
            return CompileResult(True, binary_path, standard, tuple(attempts))
        if run.status is RunStatus.TIMEOUT:
            diagnostic = f"compilation exceeded {COMPILE_WALL_S} s"
        elif run.status is RunStatus.SIGNALED:
            diagnostic = f"compiler killed by signal {run.signal}\n{_text(run.stderr_tail)}"
        else:
            diagnostic = _text(run.stderr_tail) or f"g++ exited with code {run.exit_code}"
        attempts.append(CompileAttempt(standard, False, diagnostic))
    return CompileResult(False, None, None, tuple(attempts))
