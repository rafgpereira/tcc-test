"""The on-disk state of the SLM suites under ``data/suites/slm/`` (data-model.md, sections 3 and 4).

Every fact is ONE immutable file, written once and atomically (temporary file in the same
directory, ``fsync``, ``os.replace``; ``dataset.persistence.store``), so an interruption never
leaves a half-written file and a file that exists is never rewritten. The state of a problem ×
scenario is derived only from which files exist (``combination_state``), and ``suite.json`` is a
pure function of the attempt files (``finalize``), so an interruption between the last attempt file
and ``suite.json`` only means computing ``suite.json`` again.
"""

import fcntl
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from ai_clients import config
from ai_clients.schemas.execution import ExecutionRecord
from ai_clients.schemas.generation import GenerationRecord
from ai_clients.schemas.run import RunConfig
from ai_clients.schemas.suite import AttemptSummary, DiscardedInput, SlmSuite
from dataset.persistence import store
from dataset.schemas.testes import TestCase

__all__ = [
    "AlreadyRunningError",
    "ExecutionRecord",
    "GenerationRecord",
    "State",
    "combination_dir",
    "combination_state",
    "ensure_suites_dir",
    "exclusive_run",
    "finalize",
    "read_execution",
    "read_generation",
    "read_run",
    "read_suite",
    "run_exists",
    "write_execution",
    "write_generation",
    "write_run",
]


def ensure_suites_dir(root: Path) -> Path:
    """Create ``data/suites/``, ``data/suites/slm/`` and ``data/suites/slm/problems/``.

    Each level on its own (not ``mkdir -p``) so that, when the ``sandbox`` service runs as root,
    none of them stays owned by root in the bind-mounted ``data/``.
    """
    root = Path(root)
    store.make_private_dir(root / config.SUITES_DIR.parent)
    base = store.make_private_dir(root / config.SUITES_DIR)
    store.make_private_dir(root / config.PROBLEMS_DIR)
    return base


def combination_dir(root: Path, problem_id: str, scenario: str) -> Path:
    return Path(root) / config.PROBLEMS_DIR / problem_id / str(getattr(scenario, "value", scenario))


def _ensure_combination_dir(root: Path, problem_id: str, scenario: str) -> Path:
    ensure_suites_dir(root)
    store.make_private_dir(Path(root) / config.PROBLEMS_DIR / problem_id)
    return store.make_private_dir(combination_dir(root, problem_id, scenario))


class AlreadyRunningError(Exception):
    """Another ``python -m ai_clients`` command holds the lock of ``data/suites/slm/``."""


@contextmanager
def exclusive_run(root: Path) -> Iterator[None]:
    """One command at a time over ``data/suites/slm/`` (also across the two services).

    An ``flock`` on ``data/suites/slm/.lock``: the operating system releases it when the process
    ends, however it ends (Ctrl+C, ``kill -9``, a power cut), so it never goes stale.
    """
    ensure_suites_dir(root)
    with (Path(root) / config.SUITES_DIR / config.LOCK_FILE).open("a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise AlreadyRunningError(
                "another python -m ai_clients command is already running over data/suites/slm/"
            ) from exc
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def _write_once(path: Path, record) -> Path:
    if path.exists():
        raise FileExistsError(f"{path} already exists; records are never rewritten")
    store.atomic_write_json(path, record)
    return path


def write_generation(root: Path, record: GenerationRecord) -> Path:
    folder = _ensure_combination_dir(root, record.problem_id, record.scenario)
    return _write_once(folder / config.generation_file_name(record.attempt), record)


def write_execution(root: Path, record: ExecutionRecord) -> Path:
    folder = _ensure_combination_dir(root, record.problem_id, record.scenario)
    return _write_once(folder / config.execution_file_name(record.attempt), record)


def read_generation(
    root: Path, problem_id: str, scenario: str, attempt: int
) -> GenerationRecord | None:
    path = combination_dir(root, problem_id, scenario) / config.generation_file_name(attempt)
    if not path.is_file():
        return None
    return GenerationRecord.model_validate_json(path.read_text(encoding="utf-8"))


def read_execution(
    root: Path, problem_id: str, scenario: str, attempt: int
) -> ExecutionRecord | None:
    path = combination_dir(root, problem_id, scenario) / config.execution_file_name(attempt)
    if not path.is_file():
        return None
    return ExecutionRecord.model_validate_json(path.read_text(encoding="utf-8"))


# ----------------------------------------------------------------------------------- run.json


def run_path(root: Path) -> Path:
    return Path(root) / config.SUITES_DIR / config.RUN_FILE


def run_exists(root: Path) -> bool:
    return run_path(root).is_file()


def write_run(root: Path, run: RunConfig) -> Path:
    ensure_suites_dir(root)
    return _write_once(run_path(root), run)


def read_run(root: Path) -> RunConfig:
    return RunConfig.model_validate_json(run_path(root).read_text(encoding="utf-8"))


# ------------------------------------------------------------------------------ state machine


@dataclass(frozen=True)
class State:
    """Where a problem × scenario stands; ``attempt`` is the one the next step is about."""

    kind: Literal["terminal", "pending_generation", "pending_execution", "finalizable"]
    attempt: int


def read_suite(root: Path, problem_id: str, scenario: str) -> SlmSuite | None:
    path = combination_dir(root, problem_id, scenario) / config.SUITE_FILE
    if not path.is_file():
        return None
    return SlmSuite.model_validate_json(path.read_text(encoding="utf-8"))


def _generations(root: Path, problem_id: str, scenario: str) -> list[GenerationRecord]:
    """The generation records 1, 2, ... that exist without a gap."""
    records = []
    for attempt in range(1, config.MAX_ATTEMPTS + 1):
        record = read_generation(root, problem_id, scenario, attempt)
        if record is None:
            break
        records.append(record)
    return records


def combination_state(root: Path, problem_id: str, scenario: str) -> State:
    """The state of a problem × scenario, from the files present only (data-model.md, 4)."""
    folder = combination_dir(root, problem_id, scenario)
    if (folder / config.SUITE_FILE).is_file():
        return State("terminal", 0)
    generations = _generations(root, problem_id, scenario)
    if not generations:
        return State("pending_generation", 1)
    last = generations[-1]
    n = last.attempt
    if not last.parse.ok:
        failed = True
    else:
        execution = read_execution(root, problem_id, scenario, n)
        if execution is None:
            return State("pending_execution", n)
        if execution.outcome == "accepted":
            return State("finalizable", n)
        failed = True
    if failed and n < config.MAX_ATTEMPTS:
        return State("pending_generation", n + 1)
    return State("finalizable", n)


def _summary(generation: GenerationRecord, execution: ExecutionRecord | None) -> AttemptSummary:
    if not generation.parse.ok:
        failure, detail = "unparseable_response", generation.parse.error
    elif execution.outcome == "public_test_failed":
        tests = execution.public_tests
        failure = "public_test_failed"
        detail = f"test {tests.failed_index}: {tests.failed_verdict.value}"
    else:
        reasons = Counter(item.discard.value for item in execution.inputs if not item.kept)
        if execution.outcome == "all_inputs_failed":
            failure = "all_inputs_failed"
            detail = ", ".join(f"{count} {reason}" for reason, count in sorted(reasons.items()))
        else:
            failure = None
            kept = sum(item.kept for item in execution.inputs)
            detail = f"{kept} kept, {len(execution.inputs) - kept} discarded"
    return AttemptSummary(
        attempt=generation.attempt,
        seed=generation.seed,
        hardware_label=generation.hardware_label,
        failure=failure,
        detail=detail,
    )


def finalize(root: Path, problem_id: str, scenario: str, run: RunConfig) -> SlmSuite | None:
    """Write ``suite.json`` if the combination is finalizable; the same files give the same bytes.

    This is the only place that writes ``suite.json``. Returns ``None`` if the combination is not
    finalizable (already terminal, or still pending).
    """
    if combination_state(root, problem_id, scenario).kind != "finalizable":
        return None
    generations = _generations(root, problem_id, scenario)
    executions = [read_execution(root, problem_id, scenario, g.attempt) for g in generations]
    attempts = [_summary(g, e) for g, e in zip(generations, executions, strict=True)]
    last_generation, last_execution = generations[-1], executions[-1]
    accepted = attempts[-1].failure is None
    tests, discarded = [], []
    if accepted:
        inputs = last_generation.parse.inputs
        for item in last_execution.inputs:
            if item.kept:
                tests.append(TestCase(input=inputs[item.index], output=item.output))
            else:
                discarded.append(
                    DiscardedInput(index=item.index, discard=item.discard, verdict=item.verdict)
                )
    suite = SlmSuite(
        problem_id=problem_id,
        scenario=scenario,
        model=run.model,
        model_digest=run.model_digest,
        status="accepted" if accepted else "discarded",
        attempts=attempts,
        accepted_attempt=last_generation.attempt if accepted else None,
        tests=tests,
        suite_size=len(tests),
        discarded_inputs=discarded,
        duplicate_inputs=last_generation.parse.duplicate_inputs if accepted else 0,
    )
    _write_once(combination_dir(root, problem_id, scenario) / config.SUITE_FILE, suite)
    return suite
