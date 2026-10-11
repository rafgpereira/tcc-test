"""Tests for the limit constants and the bytes/KiB conversion (T013).

The stack limit is the classic unit trap: ``268435456`` is 256 MiB in BYTES, the shell
``ulimit -s`` takes KiB (``262144``), and ``resource.setrlimit`` takes BYTES. Applying
``262144`` to ``setrlimit`` would silently give 256 KiB instead of 256 MiB.
"""

import resource

import pytest

from sandbox import limits


def test_stack_limit_constant_is_256_mib_in_bytes():
    assert limits.STACK_LIMIT_BYTES == 268_435_456 == 256 * 1024 * 1024


def test_conversion_bytes_to_kib_is_correct():
    """conversão bytes→KiB do limite de stack está correta."""
    assert limits.stack_limit_bytes_to_kib(268_435_456) == 262_144
    assert limits.stack_limit_bytes_to_kib(limits.STACK_LIMIT_BYTES) == 262_144


def test_conversion_kib_to_bytes_is_the_inverse():
    assert limits.kib_to_stack_limit_bytes(262_144) == 268_435_456
    for n in (1024, 8 * 1024 * 1024, limits.STACK_LIMIT_BYTES):
        assert limits.kib_to_stack_limit_bytes(limits.stack_limit_bytes_to_kib(n)) == n


@pytest.mark.parametrize("bad", [1, 1023, 1025, 268_435_457, 0, -1024])
def test_conversion_rejects_non_multiples_of_1024(bad):
    with pytest.raises(ValueError):
        limits.stack_limit_bytes_to_kib(bad)


def test_setrlimit_receives_bytes_never_kib(monkeypatch):
    calls = []
    monkeypatch.setattr(resource, "setrlimit", lambda which, value: calls.append((which, value)))

    limits.apply_stack_limit()

    assert calls == [(resource.RLIMIT_STACK, (268_435_456, 268_435_456))]
    _, (soft, hard) = calls[0]
    assert soft not in (262_144, 268_435_456 * 1024)
    assert hard == soft, "soft == hard so the child cannot raise it again"


def test_apply_stack_limit_rejects_a_kib_looking_value(monkeypatch):
    """Defense in depth against the 256 KiB vs 256 MiB mix-up."""
    calls = []
    monkeypatch.setattr(resource, "setrlimit", lambda *a: calls.append(a))
    with pytest.raises(ValueError):
        limits.apply_stack_limit(262_144)
    assert calls == []


@pytest.mark.parametrize("limit, expected", [(2.0, 3), (2.5, 4), (0.1, 2), (1.0, 2)])
def test_cpu_reserve_is_ceil_of_limit_plus_one(limit, expected):
    assert limits.cpu_reserve_seconds(limit) == expected


@pytest.mark.parametrize("limit, expected", [(2.0, 7.0), (0.5, 2.5), (1.0, 4.0)])
def test_wall_reserve_is_three_times_limit_plus_one(limit, expected):
    assert limits.wall_reserve_seconds(limit) == pytest.approx(expected)


def test_engine_slack_constants_are_not_problem_limits():
    """Only slack factors live in code; time and memory of a problem never do (Principle V)."""
    assert limits.WALL_FACTOR == 3 and limits.WALL_EXTRA_S == 1
    assert not hasattr(limits, "DEFAULT_TIME_LIMIT_SECONDS")
    assert not hasattr(limits, "DEFAULT_MEMORY_LIMIT_BYTES")
