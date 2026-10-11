"""Fixtures of the engine integration tests (they run in the `sandbox` service, as root)."""

import shutil
from pathlib import Path

import pytest

from sandbox import isolation
from sandbox.compiler import compile_cpp
from sandbox.limits import STACK_LIMIT_BYTES
from sandbox.types import ExecutionLimits

SLOT = 0
MIB = 1024 * 1024
DEFAULT_LIMITS = ExecutionLimits(
    time_limit_seconds=2.0, memory_limit_bytes=256 * MIB, stack_limit_bytes=STACK_LIMIT_BYTES
)


@pytest.fixture()
def slot() -> int:
    return SLOT


@pytest.fixture()
def workdir(slot) -> Path:
    """A clean, private working directory of the slot, removed afterwards."""
    path = isolation.prepare_slot_workdir(slot)
    yield path
    shutil.rmtree(path, ignore_errors=True)


@pytest.fixture()
def build(slot, workdir):
    """Compile C++ source in the slot workdir and return the binary (fails the test on CE)."""

    def _build(source: str) -> Path:
        result = compile_cpp(source, workdir, slot)
        assert result.ok, [a.diagnostic for a in result.attempts]
        assert result.binary is not None
        return result.binary

    return _build
