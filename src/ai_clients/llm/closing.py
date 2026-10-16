"""Closing by hand a problem x scenario of a commercial model that awaits the authors (FR-016).

The same rule and messages as the SLM (``ai_clients.closing``): after 3 format failures only the
authors can close a combination, with a reason; ``manual_close.json`` and then ``suite.json``
(``discarded_manual``). It still counts in the N of the experiment.
"""

from collections.abc import Callable
from pathlib import Path

from ai_clients.closing import NotAwaitingManual, manual_close_record
from ai_clients.llm import store
from ai_clients.llm.schemas import LlmRunConfig, LlmSuite

__all__ = ["NotAwaitingManual", "check_awaiting", "close", "manual_close_record"]


def check_awaiting(root: Path, model: str, problem_id: str, scenario: str, run) -> None:
    state = store.combination_state(root, model, problem_id, scenario, run)
    if state.kind != "awaiting_manual":
        raise NotAwaitingManual(
            f"{problem_id} {scenario} is {state.kind}, not awaiting manual handling; "
            "nothing was recorded"
        )


def close(
    root: Path,
    model: str,
    problem_id: str,
    scenario: str,
    reason: str,
    *,
    run: LlmRunConfig,
    now: Callable[[], str],
) -> LlmSuite:
    record = manual_close_record(problem_id, scenario, reason, now=now)
    check_awaiting(root, model, problem_id, scenario, run)
    store.write_manual_close(root, model, record)
    return store.finalize(root, model, problem_id, scenario, run)
