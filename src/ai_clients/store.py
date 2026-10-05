"""The on-disk state of the SLM suites under ``data/suites/slm/`` (data-model.md, sections 3 and 4).

Every fact is ONE immutable file, written once and atomically (temporary file in the same
directory, ``fsync``, ``os.replace``; ``dataset.persistence.store``), so an interruption never
leaves a half-written file and a file that exists is never rewritten. The state of a problem ×
scenario is derived only from which files exist (``combination_state``), and ``suite.json`` is a
pure function of the attempt files (``finalize``), so an interruption between the last attempt file
and ``suite.json`` only means computing ``suite.json`` again.
"""

import fcntl
import re
from collections import Counter
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import ValidationError

from ai_clients import config
from ai_clients.schemas.execution import ExecutionRecord
from ai_clients.schemas.generation import GenerationRecord
from ai_clients.schemas.run import RunConfig
from ai_clients.schemas.suite import AttemptSummary, DiscardedInput, SlmSuite
from dataset.persistence import store
from dataset.schemas.testes import TestCase

__all__ = [
    "AlreadyRunningError",
    "DamagedCombination",
    "ExecutionRecord",
    "GenerationRecord",
    "State",
    "attempt_files",
    "combination_dir",
    "combination_state",
    "count_in_state",
    "ensure_suites_dir",
    "exclusive_run",
    "expected_suite",
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


class DamagedCombination(Exception):
    """The files of a problem × scenario are not what the commands write; never repaired.

    ``problems`` lists what diverges, each line starting with ``missing:``, ``changed:`` or
    ``inconsistent:`` and the file it is about.
    """

    def __init__(self, problem_id: str, scenario: str, problems: list[str]) -> None:
        self.problem_id, self.scenario, self.problems = problem_id, scenario, problems
        super().__init__(f"{problem_id} {scenario}: {'; '.join(problems)}")


_ATTEMPT_FILE = re.compile(r"^attempt_(\d+)\.(generation|execution)\.json$")


def _is_leftover(name: str) -> bool:
    """A temporary file of an atomic write that a ``kill -9`` left behind: never read."""
    return name.startswith(".") and name.endswith(".tmp")


def _reason(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        error = exc.errors()[0]
        where = ".".join(str(part) for part in error["loc"])
        return f"{where}: {error['msg']}" if where else error["msg"]
    return str(exc)


@dataclass(frozen=True)
class AttemptFiles:
    generations: list[GenerationRecord]  # attempts 1, 2, ... without a gap
    executions: dict[int, ExecutionRecord]
    suite: Path | None


def _load(root: Path, problem_id: str, scenario: str, run: RunConfig | None) -> AttemptFiles:
    """Read and cross-check every file of the combination; ``DamagedCombination`` if any diverges."""
    scenario = str(getattr(scenario, "value", scenario))
    folder = combination_dir(root, problem_id, scenario)
    problems: list[str] = []
    found: dict[str, dict] = {"generation": {}, "execution": {}}
    suite = None
    for path in sorted(folder.iterdir()) if folder.is_dir() else []:
        name = path.name
        if _is_leftover(name):
            continue
        if name == config.SUITE_FILE and path.is_file():
            suite = path
            continue
        match = _ATTEMPT_FILE.match(name)
        if match is None or not path.is_file():
            problems.append(f"inconsistent: {name}: not a file written by python -m ai_clients")
            continue
        attempt, kind = int(match[1]), match[2]
        if not 1 <= attempt <= config.MAX_ATTEMPTS:
            problems.append(f"inconsistent: {name}: there are only {config.MAX_ATTEMPTS} attempts")
            continue
        schema = GenerationRecord if kind == "generation" else ExecutionRecord
        try:
            record = schema.model_validate_json(path.read_bytes())
        except ValueError as exc:  # also invalid JSON and invalid UTF-8
            problems.append(f"inconsistent: {name}: {_reason(exc)}")
            continue
        named = (record.problem_id, record.scenario.value, record.attempt)
        if named != (problem_id, scenario, attempt):
            problems.append(f"inconsistent: {name}: it is about {' '.join(map(str, named))}")
            continue
        found[kind][attempt] = record
    generations, executions = found["generation"], found["execution"]
    last = max([*generations, *executions], default=0)
    for n in range(1, last + 1):
        if n not in generations:
            problems.append(f"missing: {config.generation_file_name(n)}")
    for n, record in sorted(generations.items()):
        if run is not None and record.model_digest != run.model_digest:
            problems.append(
                f"inconsistent: {config.generation_file_name(n)}: model_digest "
                f"{record.model_digest} differs from run.json ({run.model_digest})"
            )
        execution = executions.get(n)
        if not record.parse.ok:
            if execution is not None:
                problems.append(
                    f"inconsistent: {config.execution_file_name(n)}: attempt {n} was not parsed"
                )
        elif (
            execution is not None
            and execution.public_tests.failed_index is None
            and len(execution.inputs) != len(record.parse.inputs)
        ):
            problems.append(
                f"inconsistent: {config.execution_file_name(n)}: {len(execution.inputs)} "
                f"inputs, the generation has {len(record.parse.inputs)}"
            )
        if n < last and record.parse.ok:  # a later attempt exists: this one must have failed
            if execution is None:
                problems.append(f"missing: {config.execution_file_name(n)}")
            elif execution.outcome == "accepted":
                problems.append(
                    f"inconsistent: {config.generation_file_name(n + 1)}: attempt {n} was accepted"
                )
    if problems:
        raise DamagedCombination(problem_id, scenario, problems)
    return AttemptFiles([generations[n] for n in range(1, last + 1)], executions, suite)


def _state_of_attempts(files: AttemptFiles) -> State:
    if not files.generations:
        return State("pending_generation", 1)
    last = files.generations[-1]
    n = last.attempt
    if last.parse.ok:
        execution = files.executions.get(n)
        if execution is None:
            return State("pending_execution", n)
        if execution.outcome == "accepted":
            return State("finalizable", n)
    if n < config.MAX_ATTEMPTS:
        return State("pending_generation", n + 1)
    return State("finalizable", n)


def combination_state(
    root: Path, problem_id: str, scenario: str, run: RunConfig | None = None
) -> State:
    """The state of a problem × scenario, from the files present only (data-model.md, 4).

    Every file is read and cross-checked first; ``DamagedCombination`` if anything diverges. With
    ``run``, also the ``model_digest`` of every attempt and, for a terminal combination, that
    ``suite.json`` is byte for byte what ``finalize`` writes from the attempt files.
    """
    files = _load(root, problem_id, scenario, run)
    state = _state_of_attempts(files)
    if files.suite is None:
        return state
    if state.kind != "finalizable":
        raise DamagedCombination(
            problem_id, scenario, ["inconsistent: suite.json: the attempts are not finished"]
        )
    if run is not None:
        expected = store.dumps_json(_build_suite(files, problem_id, scenario, run))
        if files.suite.read_bytes() != expected.encode("utf-8"):
            raise DamagedCombination(
                problem_id, scenario, ["changed: suite.json: not what the attempt files give"]
            )
    return State("terminal", 0)


def read_suite(root: Path, problem_id: str, scenario: str) -> SlmSuite | None:
    path = combination_dir(root, problem_id, scenario) / config.SUITE_FILE
    if not path.is_file():
        return None
    return SlmSuite.model_validate_json(path.read_text(encoding="utf-8"))


def _summary(generation: GenerationRecord, execution: ExecutionRecord | None) -> AttemptSummary:
    if generation.model_failure is not None:
        failure, detail = generation.model_failure.reason, generation.model_failure.detail
    elif not generation.parse.ok:
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


def _build_suite(files: AttemptFiles, problem_id: str, scenario: str, run: RunConfig) -> SlmSuite:
    """``suite.json`` as a pure function of the attempt files and of ``run.json``."""
    generations = files.generations
    executions = [files.executions.get(g.attempt) for g in generations]
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
    return SlmSuite(
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


def attempt_files(
    root: Path, problem_id: str, scenario: str, run: RunConfig | None = None
) -> AttemptFiles:
    """The attempt records of a combination, cross-checked; ``DamagedCombination`` if damaged."""
    return _load(root, problem_id, scenario, run)


def expected_suite(root: Path, problem_id: str, scenario: str, run: RunConfig) -> SlmSuite | None:
    """The suite the attempt files give (what ``finalize`` writes), or ``None`` while pending.

    For a terminal combination it is ``suite.json`` itself (``combination_state`` checks they are
    byte for byte equal); for a finalizable one, the ``suite.json`` still to be written.
    """
    files = _load(root, problem_id, scenario, run)
    if _state_of_attempts(files).kind != "finalizable":
        return None
    return _build_suite(files, problem_id, scenario, run)


def finalize(root: Path, problem_id: str, scenario: str, run: RunConfig) -> SlmSuite | None:
    """Write ``suite.json`` if the combination is finalizable; the same files give the same bytes.

    This is the only place that writes ``suite.json``. Returns ``None`` if the combination is not
    finalizable (already terminal, or still pending); ``DamagedCombination`` if it is damaged.
    """
    files = _load(root, problem_id, scenario, run)
    if files.suite is not None or _state_of_attempts(files).kind != "finalizable":
        return None
    suite = _build_suite(files, problem_id, scenario, run)
    _write_once(combination_dir(root, problem_id, scenario) / config.SUITE_FILE, suite)
    return suite


def count_in_state(
    root: Path, combinations: Iterable[tuple[str, str]], kind: str, run: RunConfig | None = None
) -> int:
    """How many of ``combinations`` are in the state ``kind`` (a damaged one is in none)."""
    total = 0
    for problem_id, scenario in combinations:
        try:
            total += combination_state(root, problem_id, scenario, run).kind == kind
        except DamagedCombination:
            pass
    return total
