"""Closing by hand a problem × scenario that awaits manual handling (``python -m ai_clients close``).

A combination gets there only when the 3 prediction attempts were not parsed (``config.py``). The
authors decide what to do with it and record the decision: ``manual_close.json`` (the reason and the
date), then ``suite.json`` with the status ``discarded_manual``, which copies them. It is the only
way a combination ends without a suite; it still counts in the N of the experiment.
"""

from collections.abc import Callable
from pathlib import Path

from ai_clients import store
from ai_clients.schemas.manual_close import ManualClose
from ai_clients.schemas.run import RunConfig
from ai_clients.schemas.suite import SlmSuite


class NotAwaitingManual(Exception):
    """The combination is in another state: nothing to close (exit code 2)."""


def manual_close_record(
    problem_id: str, scenario: str, reason: str, *, now: Callable[[], str]
) -> ManualClose:
    """The ``manual_close.json`` of the decision; ``ValueError`` if the reason is blank."""
    return ManualClose(
        problem_id=problem_id, scenario=scenario, reason=reason.strip(), closed_at=now()
    )


def check_awaiting(root: Path, problem_id: str, scenario: str, run: RunConfig) -> None:
    """``NotAwaitingManual`` unless the combination awaits manual handling (damage propagates)."""
    state = store.combination_state(root, problem_id, scenario, run)
    if state.kind != "awaiting_manual":
        raise NotAwaitingManual(
            f"{problem_id} {scenario} is {state.kind}, not awaiting manual handling; "
            "nothing was recorded"
        )


def close(
    root: Path,
    problem_id: str,
    scenario: str,
    reason: str,
    *,
    run: RunConfig,
    now: Callable[[], str],
) -> SlmSuite:
    """Record the decision of the authors and the ``discarded_manual`` suite it gives."""
    record = manual_close_record(problem_id, scenario, reason, now=now)
    check_awaiting(root, problem_id, scenario, run)
    store.write_manual_close(root, record)
    return store.finalize(root, problem_id, scenario, run)
