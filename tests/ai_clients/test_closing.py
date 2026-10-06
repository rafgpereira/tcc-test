"""Closing by hand a combination that awaits manual handling: the only way to end without a suite."""

import pytest

from ai_clients import closing, config, store
from ai_clients.schemas.manual_close import ManualClose
from tests.ai_clients.fakes import record_generation, start_run

NOW = "2026-10-07T12:00:00Z"


@pytest.fixture()
def run(repo):
    return start_run(repo)


def awaiting(repo, pid="1_A", scenario="hybrid"):
    for n in range(1, config.MAX_ATTEMPTS + 1):
        record_generation(repo, pid, scenario, n, parsed=False)
    assert store.combination_state(repo, pid, scenario).kind == "awaiting_manual"


def test_close_records_the_decision_and_the_discarded_manual_suite(repo, run):
    awaiting(repo)
    suite = closing.close(repo, "1_A", "hybrid", "  never parsed  ", run=run, now=lambda: NOW)
    folder = store.combination_dir(repo, "1_A", "hybrid")
    record = ManualClose.model_validate_json((folder / config.MANUAL_CLOSE_FILE).read_text())
    assert (record.reason, record.closed_at) == ("never parsed", NOW)
    assert suite.status == "discarded_manual" and suite.tests == []
    assert suite.manual_close.model_dump() == {"reason": "never parsed", "closed_at": NOW}
    assert len(suite.attempts) == config.MAX_ATTEMPTS
    assert store.read_suite(repo, "1_A", "hybrid") == suite
    assert store.combination_state(repo, "1_A", "hybrid", run).kind == "terminal"


@pytest.mark.parametrize("attempts", [0, 3, 14])
def test_close_refuses_a_combination_that_does_not_await_manual_handling(repo, run, attempts):
    for n in range(1, attempts + 1):
        record_generation(repo, "1_A", "hybrid", n, parsed=False)
    with pytest.raises(closing.NotAwaitingManual, match="not awaiting manual handling"):
        closing.close(repo, "1_A", "hybrid", "why", run=run, now=lambda: NOW)
    assert not (store.combination_dir(repo, "1_A", "hybrid") / config.MANUAL_CLOSE_FILE).exists()


def test_a_blank_reason_is_refused_before_anything_is_written(repo, run):
    awaiting(repo)
    with pytest.raises(ValueError):
        closing.close(repo, "1_A", "hybrid", " \n", run=run, now=lambda: NOW)
    assert store.combination_state(repo, "1_A", "hybrid").kind == "awaiting_manual"


def test_an_interruption_between_the_decision_and_the_suite_only_needs_the_suite(repo, run):
    awaiting(repo)
    store.write_manual_close(
        repo, closing.manual_close_record("1_A", "hybrid", "never parsed", now=lambda: NOW)
    )
    assert store.combination_state(repo, "1_A", "hybrid", run).kind == "finalizable"
    assert store.finalize(repo, "1_A", "hybrid", run).status == "discarded_manual"


def test_a_manual_close_outside_that_state_is_damage(repo, run):
    record_generation(repo, "1_A", "hybrid", 1, parsed=False)
    store.write_manual_close(
        repo, closing.manual_close_record("1_A", "hybrid", "too early", now=lambda: NOW)
    )
    with pytest.raises(store.DamagedCombination, match="does not await manual handling"):
        store.combination_state(repo, "1_A", "hybrid", run)
