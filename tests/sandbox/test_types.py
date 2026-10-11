"""Tests for the shared engine types (T011)."""

import dataclasses

import pytest

from sandbox.limits import STACK_LIMIT_BYTES
from sandbox.types import ExecutionLimits, InfraError, Verdict


def test_verdict_has_exactly_the_six_verdicts():
    assert [v.name for v in Verdict] == ["AC", "WA", "TLE", "MLE", "RE", "CE"]


def test_infra_is_not_a_verdict():
    """Infrastructure failure is an exception, never a verdict (FR-010)."""
    assert "INFRA" not in Verdict.__members__
    assert not issubclass(InfraError, Verdict)
    assert issubclass(InfraError, Exception)


def test_infra_error_is_not_a_subclass_of_any_verdict_type():
    for base in Verdict.__mro__:
        if base is object:
            continue
        assert not issubclass(InfraError, base) or base is Exception


def test_time_and_memory_limits_have_no_default():
    """Problem limits must always come from the problem metadata (Principle V)."""
    with pytest.raises(TypeError):
        ExecutionLimits()
    with pytest.raises(TypeError):
        ExecutionLimits(time_limit_seconds=1.0)
    with pytest.raises(TypeError):
        ExecutionLimits(memory_limit_bytes=256_000_000)


def test_stack_limit_defaults_to_256_mib_in_bytes():
    limits = ExecutionLimits(time_limit_seconds=1.0, memory_limit_bytes=256_000_000)
    assert limits.stack_limit_bytes == 268_435_456 == STACK_LIMIT_BYTES


@pytest.mark.parametrize("time_s, memory", [(0, 1), (-1.0, 1), (1.0, 0), (1.0, -5)])
def test_limits_must_be_positive(time_s, memory):
    with pytest.raises(ValueError):
        ExecutionLimits(time_limit_seconds=time_s, memory_limit_bytes=memory)


def test_a_stack_limit_that_looks_like_kib_is_rejected():
    """262144 is the KiB value for 256 MiB: passing it as bytes would apply only 256 KiB."""
    with pytest.raises(ValueError):
        ExecutionLimits(
            time_limit_seconds=1.0, memory_limit_bytes=1_000_000, stack_limit_bytes=262_144
        )


def test_limits_are_immutable():
    limits = ExecutionLimits(time_limit_seconds=1.0, memory_limit_bytes=256_000_000)
    with pytest.raises(dataclasses.FrozenInstanceError):
        limits.time_limit_seconds = 2.0
