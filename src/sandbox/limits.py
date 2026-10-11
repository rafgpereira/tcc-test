"""Engine limit constants and unit conversions.

The stack limit is the classic unit trap. ``268435456`` is 256 MiB in BYTES. ``resource.setrlimit``
takes BYTES, while the shell ``ulimit -s`` takes KiB (``262144``). Passing ``262144`` to
``setrlimit`` would silently apply 256 KiB instead of 256 MiB, so the value lives in ONE constant,
the KiB equivalent is derived by ONE function, and values that look like KiB are rejected.

Only slack factors of the engine live here. The time and memory limits of a problem never do:
they always come from the problem metadata (Constitution, Principle V).
"""

import math
import resource

# The Codeforces judge runs on Windows and links with -Wl,--stack=268435456, an option the Linux
# linker does not know. The same effect is obtained by limiting the stack at run time.
STACK_LIMIT_BYTES = 268_435_456

# Anything below this is almost certainly a KiB value passed where bytes are expected.
MIN_STACK_LIMIT_BYTES = 1024 * 1024

# Engine slack, not problem limits: the kernel CPU limit is ceil(limit) + CPU_EXTRA_S and the wall
# clock reserve (only to detect blocked programs) is limit * WALL_FACTOR + WALL_EXTRA_S.
CPU_EXTRA_S = 1
WALL_FACTOR = 3
WALL_EXTRA_S = 1

MAX_OUTPUT_BYTES = 64 * 1024 * 1024
RUN_NPROC = 32
RUN_FSIZE_BYTES = 1024 * 1024
STDERR_TAIL_BYTES = 4096
LAUNCHER_PATH = "/usr/local/bin/sandbox-launch"

# The compiler is third-party-controlled input too (a source can be a template bomb), so it runs
# isolated with its own limits. These are engine constants, not problem limits. The address space
# is generous because cc1plus reserves a lot of virtual memory.
COMPILE_CPU_S = 60
COMPILE_WALL_S = 120
COMPILE_AS_BYTES = 4 * 1024 * 1024 * 1024
COMPILE_NPROC = 64
COMPILE_FSIZE_BYTES = 64 * 1024 * 1024
DIAGNOSTIC_BYTES = 64 * 1024


def stack_limit_bytes_to_kib(n: int) -> int:
    """Convert a stack limit in bytes to the KiB value the shell ``ulimit -s`` expects."""
    if n <= 0 or n % 1024 != 0:
        raise ValueError(f"stack limit must be a positive multiple of 1024 bytes, got {n}")
    return n // 1024


def kib_to_stack_limit_bytes(kib: int) -> int:
    """Convert KiB (the ``ulimit -s`` unit) to bytes (the ``setrlimit`` unit)."""
    if kib <= 0:
        raise ValueError(f"stack limit in KiB must be positive, got {kib}")
    return kib * 1024


def validate_stack_limit_bytes(n: int) -> int:
    """Return ``n`` if it is a plausible stack limit in bytes, otherwise raise ``ValueError``."""
    if n < MIN_STACK_LIMIT_BYTES:
        raise ValueError(
            f"stack limit {n} is below {MIN_STACK_LIMIT_BYTES} bytes: is it a KiB value? "
            f"setrlimit takes bytes ({STACK_LIMIT_BYTES} = 256 MiB); ulimit -s takes KiB"
        )
    return n


def apply_stack_limit(stack_limit_bytes: int = STACK_LIMIT_BYTES) -> None:
    """Apply the stack limit to the current process (soft == hard, so it cannot be raised)."""
    validate_stack_limit_bytes(stack_limit_bytes)
    resource.setrlimit(resource.RLIMIT_STACK, (stack_limit_bytes, stack_limit_bytes))


def cpu_reserve_seconds(time_limit_seconds: float) -> int:
    """Kernel CPU limit (RLIMIT_CPU): ceil(limit) + 1 second."""
    return math.ceil(time_limit_seconds) + CPU_EXTRA_S


def wall_reserve_seconds(time_limit_seconds: float) -> float:
    """Wall clock reserve, used only to kill blocked programs: limit * 3 + 1 second."""
    return time_limit_seconds * WALL_FACTOR + WALL_EXTRA_S
