"""The attempt policy: one explicit table of phase, seed, temperature and template per attempt."""

import pytest

from ai_clients import config

EXPECTED = [
    (1, 1, 42, 0.7, "solution"),
    (2, 1, 43, 0.7, "solution"),
    (3, 1, 44, 0.7, "solution"),
    (4, 1, 45, 0.7, "solution"),
    (5, 1, 46, 0.7, "solution"),
    (6, 1, 47, 0.7, "solution"),
    (7, 2, 48, 0.7, "solution"),
    (8, 2, 48, 0.6, "solution"),
    (9, 2, 48, 0.5, "solution"),
    (10, 2, 48, 0.4, "solution"),
    (11, 2, 48, 0.3, "solution"),
    (12, 2, 48, 0.2, "solution"),
    (13, 4, 49, 0.7, "prediction"),
    (14, 4, 50, 0.7, "prediction"),
    (15, 4, 51, 0.7, "prediction"),
]


def rows(policy):
    return [(s.attempt, s.phase, s.seed, s.temperature, s.template) for s in policy]


def test_the_table_is_exactly_the_policy_of_the_experiment():
    assert rows(config.ATTEMPT_POLICY) == EXPECTED
    assert (config.SOLUTION_ATTEMPTS, config.MAX_ATTEMPTS) == (12, 15)


def test_no_seed_and_temperature_pair_repeats():
    pairs = [(s.seed, s.temperature) for s in config.ATTEMPT_POLICY]
    assert len(pairs) == len(set(pairs))


def test_attempt_spec_gives_the_row_of_an_attempt():
    assert config.attempt_spec(9) == config.ATTEMPT_POLICY[8]
    for attempt in (0, 16):
        with pytest.raises(ValueError):
            config.attempt_spec(attempt)


@pytest.mark.parametrize(
    "change",
    [
        lambda rows: rows[:-1] + [rows[-1]._replace(attempt=16)],  # a gap
        lambda rows: rows[:7] + [rows[7]._replace(temperature=0.7)] + rows[8:],  # a repeated pair
        lambda rows: rows[:2] + [rows[2]._replace(temperature=0)] + rows[3:],  # greedy decoding
        lambda rows: rows[:12] + [rows[12]._replace(template="solution")] + rows[13:],
        lambda rows: rows[:6] + [rows[6]._replace(phase=3)] + rows[7:],  # phase 3 makes no call
        lambda rows: [rows[0]._replace(phase=2)] + rows[1:],  # phases out of order
    ],
    ids=[
        "gap",
        "repeated_pair",
        "zero_temperature",
        "wrong_template",
        "phase_without_calls",
        "phases_out_of_order",
    ],
)
def test_an_inconsistent_table_is_refused(change):
    with pytest.raises(ValueError):
        config.check_policy(tuple(change(list(config.ATTEMPT_POLICY))))
