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
from ai_clients.schemas.manual_close import ManualClose
from ai_clients.schemas.run import RunConfig
from ai_clients.schemas.suite import AttemptSummary, DiscardedInput, ManualCloseInfo, SlmSuite
from ai_clients.schemas.template_change import TemplateChange
from dataset.persistence import store
from dataset.schemas.testes import TestCase
from sandbox.types import Verdict

__all__ = [
    "AlreadyRunningError",
    "DamagedCombination",
    "DamagedRunError",
    "ExecutionRecord",
    "GenerationRecord",
    "IncompatibleRunError",
    "State",
    "attempt_files",
    "awaiting_manual",
    "busy_message",
    "claim",
    "claim_in",
    "combination_dir",
    "combination_state",
    "count_in_state",
    "ensure_suites_dir",
    "ensure_tree",
    "exclusive_run",
    "expected_suite",
    "finalize",
    "lock_tree",
    "read_execution",
    "read_generation",
    "read_run",
    "read_suite",
    "run_exists",
    "shared_run",
    "single_execute",
    "superseded_dir",
    "template_changes",
    "write_execution",
    "write_generation",
    "write_manual_close",
    "write_once",
    "write_run",
    "write_template_change",
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


def suites_tree(tree: Path | None = None) -> Path:
    """The tree of suites read: ``data/suites/slm``, or ``tree`` (an archived run, read only)."""
    return config.SUITES_DIR if tree is None else Path(tree)


def combination_dir(root: Path, problem_id: str, scenario: str, tree: Path | None = None) -> Path:
    scenario = str(getattr(scenario, "value", scenario))
    return Path(root) / suites_tree(tree) / "problems" / problem_id / scenario


def _ensure_combination_dir(root: Path, problem_id: str, scenario: str) -> Path:
    ensure_suites_dir(root)
    store.make_private_dir(Path(root) / config.PROBLEMS_DIR / problem_id)
    return store.make_private_dir(combination_dir(root, problem_id, scenario))


class AlreadyRunningError(Exception):
    """Another ``python -m ai_clients`` command holds the lock of ``data/suites/slm/``."""


ALREADY_RUNNING = "another python -m ai_clients command is already running over data/suites/slm/"


def _open_lock(path: Path):
    """Open (creating it if needed) a lock file that every service can open afterwards.

    ``execute`` runs as root in the ``sandbox`` service: a lock file it creates is given to the
    host user, like every file and folder it writes, or ``generate`` (the host user, in ``app``)
    could not open it again (``PermissionError``, found on 2026-10-08).
    """
    handle = path.open("a")
    store.chown_to_host(path)
    return handle


@contextmanager
def _flock(path: Path, mode: int, busy: str) -> Iterator[None]:
    """Hold an ``flock`` on ``path``, never waiting: ``AlreadyRunningError(busy)`` if it is taken.

    The operating system releases it when the process ends, however it ends (Ctrl+C, ``kill -9``,
    a power cut), so it never goes stale.
    """
    with _open_lock(path) as handle:
        try:
            fcntl.flock(handle, mode | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise AlreadyRunningError(busy) from exc
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


@contextmanager
def exclusive_run(root: Path) -> Iterator[None]:
    """No other command over ``data/suites/slm/`` (also across the two services).

    ``generate`` starting a run, ``close`` and ``package`` (research R24).
    """
    ensure_suites_dir(root)
    with _flock(Path(root) / config.SUITES_DIR / config.LOCK_FILE, fcntl.LOCK_EX, ALREADY_RUNNING):
        yield


@contextmanager
def shared_run(root: Path) -> Iterator[None]:
    """Several ``generate --resume`` and an ``execute`` together, none with an exclusive one.

    Each combination is then taken by one of them at a time (``claim``).
    """
    ensure_suites_dir(root)
    with _flock(Path(root) / config.SUITES_DIR / config.LOCK_FILE, fcntl.LOCK_SH, ALREADY_RUNNING):
        yield


@contextmanager
def single_execute(root: Path) -> Iterator[None]:
    """One ``execute`` at a time: they all use the same engine slot, cleaned at start and end."""
    ensure_suites_dir(root)
    path = Path(root) / config.SUITES_DIR / config.EXECUTE_LOCK_FILE
    with _flock(path, fcntl.LOCK_EX, "another python -m ai_clients execute is already running"):
        yield


@contextmanager
def claim(root: Path, problem_id: str, scenario: str) -> Iterator[bool]:
    """Take one combination for this process: ``True``, or ``False`` if another process has it.

    The state of a combination is read only while it is claimed, so two processes never make the
    same attempt; a combination in use is skipped, never waited for (research R24).
    """
    locks = store.make_private_dir(ensure_suites_dir(root) / config.COMBINATION_LOCKS_DIR)
    name = f"{problem_id}__{getattr(scenario, 'value', scenario)}.lock"
    with _open_lock(locks / name) as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        try:
            yield True
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def busy_message(tree: Path) -> str:
    """The refusal when another command holds the lock of ``tree`` (``data/suites/<model>``)."""
    return f"another python -m ai_clients command is already running over {Path(tree).as_posix()}/"


def ensure_tree(root: Path, tree: Path) -> Path:
    """Create ``tree`` (relative to ``root``) and its ``problems/``, one level at a time."""
    current = Path(root)
    for part in Path(tree).parts:
        current = store.make_private_dir(current / part)
    store.make_private_dir(current / "problems")
    return current


@contextmanager
def lock_tree(root: Path, tree: Path, mode: int) -> Iterator[None]:
    """``exclusive_run``/``shared_run`` over another tree of suites (the commercial models)."""
    base = ensure_tree(root, tree)
    with _flock(base / config.LOCK_FILE, mode, busy_message(tree)):
        yield


@contextmanager
def claim_in(root: Path, tree: Path, problem_id: str, scenario: str) -> Iterator[bool]:
    """``claim`` over another tree of suites. ``flock`` locks an open file, so two threads of one
    process that each open the lock file also exclude each other."""
    locks = store.make_private_dir(ensure_tree(root, tree) / config.COMBINATION_LOCKS_DIR)
    name = f"{problem_id}__{getattr(scenario, 'value', scenario)}.lock"
    with _open_lock(locks / name) as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        try:
            yield True
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def _write_once(path: Path, record) -> Path:
    if path.exists():
        raise FileExistsError(f"{path} already exists; records are never rewritten")
    store.atomic_write_json(path, record)
    return path


write_once = _write_once  # public for ai_clients.llm: a record is written once, atomically


def write_generation(root: Path, record: GenerationRecord) -> Path:
    folder = _ensure_combination_dir(root, record.problem_id, record.scenario)
    return _write_once(folder / config.generation_file_name(record.attempt), record)


def write_execution(root: Path, record: ExecutionRecord) -> Path:
    folder = _ensure_combination_dir(root, record.problem_id, record.scenario)
    return _write_once(folder / config.execution_file_name(record.attempt), record)


def write_manual_close(root: Path, record: ManualClose) -> Path:
    folder = _ensure_combination_dir(root, record.problem_id, record.scenario)
    return _write_once(folder / config.MANUAL_CLOSE_FILE, record)


def read_generation(
    root: Path, problem_id: str, scenario: str, attempt: int, tree: Path | None = None
) -> GenerationRecord | None:
    folder = combination_dir(root, problem_id, scenario, tree)
    path = folder / config.generation_file_name(attempt)
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


def run_path(root: Path, tree: Path | None = None) -> Path:
    return Path(root) / suites_tree(tree) / config.RUN_FILE


def run_exists(root: Path, tree: Path | None = None) -> bool:
    return run_path(root, tree).is_file()


def write_run(root: Path, run: RunConfig) -> Path:
    ensure_suites_dir(root)
    return _write_once(run_path(root), run)


class IncompatibleRunError(Exception):
    """``run.json`` was written by an older version of the module (another attempt policy)."""


INCOMPATIBLE_RUN = (
    "data/suites/slm holds a run of an older version of python -m ai_clients (it cannot be "
    "resumed nor read); move it away first: mv data/suites/slm data/suites/slm-<name>"
)


class DamagedRunError(Exception):
    """The template changes of the run are not what ``change-template`` writes; never repaired."""


def read_run(root: Path, tree: Path | None = None) -> RunConfig:
    """The run as it stands: ``run.json`` with its template changes applied in order (R27).

    ``IncompatibleRunError`` if ``run.json`` is not a run of this version (schema 2);
    ``DamagedRunError`` if a template change is unreadable, misnumbered or out of the chain.
    """
    raw = run_path(root, tree).read_bytes()
    try:
        run = RunConfig.model_validate_json(raw)
    except ValueError as exc:  # also invalid JSON: never read a run half-way
        raise IncompatibleRunError(INCOMPATIBLE_RUN) from exc
    try:
        return run.with_changes(template_changes(root, tree))
    except ValueError as exc:
        raise DamagedRunError(f"data/suites/slm/{config.TEMPLATE_CHANGES_DIR}: {exc}") from exc


# ---------------------------------------------------------------------------- template changes


def template_changes_dir(root: Path, tree: Path | None = None) -> Path:
    return Path(root) / suites_tree(tree) / config.TEMPLATE_CHANGES_DIR


def superseded_dir(root: Path, number: int, problem_id: str, scenario: str) -> Path:
    """Where change ``number`` keeps the files it moved out of ``problems/<id>/<scenario>/``."""
    name = config.template_change_file_name(number).removesuffix(".json")
    scenario = str(getattr(scenario, "value", scenario))
    return Path(root) / config.SUITES_DIR / config.SUPERSEDED_DIR / name / problem_id / scenario


def template_changes(root: Path, tree: Path | None = None) -> list[TemplateChange]:
    """Every template change of the run, in order; ``ValueError`` if one is not well formed."""
    folder = template_changes_dir(root, tree)
    if not folder.is_dir():
        return []
    names = sorted(p.name for p in folder.iterdir() if not p.name.startswith("."))
    changes = []
    for number, name in enumerate(names, start=1):
        if name != config.template_change_file_name(number):
            raise ValueError(f"{name}: the changes are 001.json, 002.json, ... without a gap")
        try:
            change = TemplateChange.model_validate_json((folder / name).read_bytes())
        except ValueError as exc:  # also invalid JSON
            raise ValueError(f"{name}: {_reason(exc)}") from exc
        if change.number != number:
            raise ValueError(f"{name}: it says it is change {change.number}")
        changes.append(change)
    return changes


def write_template_change(root: Path, change: TemplateChange) -> Path:
    folder = store.make_private_dir(ensure_suites_dir(root) / config.TEMPLATE_CHANGES_DIR)
    return _write_once(folder / config.template_change_file_name(change.number), change)


# ------------------------------------------------------------------------------ state machine


@dataclass(frozen=True)
class State:
    """Where a problem × scenario stands; ``attempt`` is the one the next step is about."""

    kind: Literal[
        "terminal", "pending_generation", "pending_execution", "finalizable", "awaiting_manual"
    ]
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
    manual_close: ManualClose | None = None


def _read_named(path: Path, schema, named_as: tuple, problems: list[str]):
    """The record of ``path`` if it is valid and about ``named_as``; else a problem and ``None``."""
    try:
        record = schema.model_validate_json(path.read_bytes())
    except ValueError as exc:  # also invalid JSON and invalid UTF-8
        problems.append(f"inconsistent: {path.name}: {_reason(exc)}")
        return None
    attempt = getattr(record, "attempt", None)  # manual_close.json is about no attempt
    named = (record.problem_id, record.scenario.value, *(() if attempt is None else (attempt,)))
    if named != named_as:
        problems.append(f"inconsistent: {path.name}: it is about {' '.join(map(str, named))}")
        return None
    return record


def _load(
    root: Path, problem_id: str, scenario: str, run: RunConfig | None, tree: Path | None = None
) -> AttemptFiles:
    """Read and cross-check every file of the combination; ``DamagedCombination`` if any diverges."""
    scenario = str(getattr(scenario, "value", scenario))
    folder = combination_dir(root, problem_id, scenario, tree)
    problems: list[str] = []
    found: dict[str, dict] = {"generation": {}, "execution": {}}
    suite = manual_close = None
    for path in sorted(folder.iterdir()) if folder.is_dir() else []:
        name = path.name
        if _is_leftover(name):
            continue
        if name == config.SUITE_FILE and path.is_file():
            suite = path
            continue
        if name == config.MANUAL_CLOSE_FILE and path.is_file():
            manual_close = _read_named(path, ManualClose, (problem_id, scenario), problems)
            continue
        match = _ATTEMPT_FILE.match(name)
        if match is None or not path.is_file():
            problems.append(f"inconsistent: {name}: not a file written by python -m ai_clients")
            continue
        attempt, kind = int(match[1]), match[2]
        if not 1 <= attempt <= config.MAX_ATTEMPTS:
            problems.append(f"inconsistent: {name}: there are only {config.MAX_ATTEMPTS} attempts")
            continue
        if kind == "execution" and attempt > config.SOLUTION_ATTEMPTS:
            problems.append(f"inconsistent: {name}: a prediction attempt is never executed")
            continue
        schema = GenerationRecord if kind == "generation" else ExecutionRecord
        record = _read_named(path, schema, (problem_id, scenario, attempt), problems)
        if record is not None:
            found[kind][attempt] = record
    generations, executions = found["generation"], found["execution"]
    last = max([*generations, *executions], default=0)
    for n in range(1, last + 1):
        if n not in generations:
            problems.append(f"missing: {config.generation_file_name(n)}")
    for n, record in sorted(generations.items()):
        # The row of the attempt: run.json's when there is one, else the policy of the code.
        spec = run.spec(n) if run is not None and n <= len(run.attempt_policy) else None
        expected = (
            (spec.phase, spec.seed, spec.temperature, spec.template.value)
            if spec is not None
            else tuple(config.attempt_spec(n))[1:]
        )
        recorded = (record.phase, record.seed, record.temperature, record.template.value)
        if recorded != expected:
            problems.append(
                f"inconsistent: {config.generation_file_name(n)}: phase, seed, temperature and "
                f"template {recorded}, but attempt {n} is {expected} in the attempt policy"
            )
        if run is not None and record.model_digest != run.model_digest:
            problems.append(
                f"inconsistent: {config.generation_file_name(n)}: model_digest "
                f"{record.model_digest} differs from run.json ({run.model_digest})"
            )
        if run is not None:
            problems += _template_problems(record, run)
        execution = executions.get(n)
        if not record.parse.ok:
            if execution is not None:
                problems.append(
                    f"inconsistent: {config.execution_file_name(n)}: attempt {n} was not parsed"
                )
        elif (
            execution is not None
            and (execution.inputs or execution.public_tests.failed_index is None)  # none after RE
            and len(execution.inputs) != len(record.parse.inputs)
        ):
            problems.append(
                f"inconsistent: {config.execution_file_name(n)}: {len(execution.inputs)} "
                f"inputs, the generation has {len(record.parse.inputs)}"
            )
        if n < last and record.parse.ok:  # a later attempt exists: this one must have failed
            if record.template.value == "prediction" or (
                execution is not None and execution.outcome == "accepted"
            ):
                problems.append(
                    f"inconsistent: {config.generation_file_name(n + 1)}: attempt {n} was accepted"
                )
            elif execution is None:
                problems.append(f"missing: {config.execution_file_name(n)}")
    if not problems:
        problems += _early_suite(generations, executions, last)
    if not problems and manual_close is not None:
        final = generations.get(config.MAX_ATTEMPTS)
        if final is None or final.parse.ok:
            problems.append(
                f"inconsistent: {config.MANUAL_CLOSE_FILE}: the combination does not await "
                "manual handling"
            )
    if problems:
        raise DamagedCombination(problem_id, scenario, problems)
    generations = [generations[n] for n in range(1, last + 1)]
    return AttemptFiles(generations, executions, suite, manual_close)


def _template_problems(record: GenerationRecord, run: RunConfig) -> list[str]:
    """An attempt made with another template than the run's current one of its kind (R27)."""
    kind, name = record.template.value, config.generation_file_name(record.attempt)
    again = f"it belongs in {config.SUPERSEDED_DIR}/ (run the same change-template again)"
    if record.template_sha256 is None:
        if run.template_was_changed(kind):
            return [f"inconsistent: {name}: made before the {kind} template was changed; {again}"]
        return []
    current = run.template_sha256(kind)
    if record.template_sha256 != current:
        wrong = f"template_sha256 {record.template_sha256}"
        return [
            f"inconsistent: {name}: {wrong} is not the {kind} template of the run ({current}); {again}"
        ]
    return []


def _early_suite(generations: dict, executions: dict, last: int) -> list[str]:
    """A prediction made although one of the 12 solutions could be the fallback (config.py)."""
    if last <= config.SOLUTION_ATTEMPTS:
        return []
    for n in range(1, config.SOLUTION_ATTEMPTS + 1):
        if n in executions and _can_be_fallback(generations[n], executions[n]):
            name = config.generation_file_name(last)
            return [f"inconsistent: {name}: attempt {n} could already be the fallback suite"]
    return []


def _can_be_fallback(generation: GenerationRecord, execution: ExecutionRecord | None) -> bool:
    """A parsed attempt whose solution failed a public test by WA and kept some generated input."""
    return (
        generation.parse.ok
        and execution is not None
        and execution.public_tests.failed_verdict is Verdict.WA
        and any(item.kept for item in execution.inputs)
    )


def _fallback(files: AttemptFiles) -> int | None:
    """The attempt a fallback suite comes from, once the 12 solutions failed; else ``None``.

    The one that passed the most public tests, then kept the most generated inputs, then the
    earliest.
    """
    if len(files.generations) != config.SOLUTION_ATTEMPTS:
        return None
    candidates = [
        (g.attempt, files.executions[g.attempt])
        for g in files.generations
        if _can_be_fallback(g, files.executions.get(g.attempt))
    ]
    if not candidates:
        return None
    best = min(
        candidates,
        key=lambda c: (-c[1].public_tests.passed, -sum(i.kept for i in c[1].inputs), c[0]),
    )
    return best[0]


def _state_of_attempts(files: AttemptFiles) -> State:
    if not files.generations:
        return State("pending_generation", 1)
    last = files.generations[-1]
    n = last.attempt
    if last.template.value == "prediction":
        if last.parse.ok:
            return State("finalizable", n)  # accepted_predicted (phase 4)
        if n < config.MAX_ATTEMPTS:
            return State("pending_generation", n + 1)
        return State("finalizable" if files.manual_close else "awaiting_manual", n)
    if last.parse.ok:
        execution = files.executions.get(n)
        if execution is None:
            return State("pending_execution", n)
        if execution.outcome == "accepted":
            return State("finalizable", n)  # accepted (phase 1 or 2)
    if _fallback(files) is not None:
        return State("finalizable", n)  # accepted_fallback (phase 3)
    return State("pending_generation", n + 1)  # the next row; after the 12th, the prediction


def combination_state(
    root: Path,
    problem_id: str,
    scenario: str,
    run: RunConfig | None = None,
    tree: Path | None = None,
) -> State:
    """The state of a problem × scenario, from the files present only (data-model.md, 4).

    Every file is read and cross-checked first; ``DamagedCombination`` if anything diverges. With
    ``run``, also the ``model_digest`` of every attempt and, for a terminal combination, that
    ``suite.json`` is byte for byte what ``finalize`` writes from the attempt files.
    """
    files = _load(root, problem_id, scenario, run, tree)
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
    elif generation.template.value == "prediction":
        failure, detail = None, f"{len(generation.parse.tests)} tests predicted"
    elif execution.outcome == "public_test_failed":
        tests = execution.public_tests
        failure = "public_test_failed"
        detail = f"test {tests.failed_index}: {tests.failed_verdict.value}"
        if execution.inputs:  # a WA: the generated inputs also ran
            kept = sum(item.kept for item in execution.inputs)
            detail += f"; {kept} kept, {len(execution.inputs) - kept} discarded"
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
        phase=generation.phase,
        seed=generation.seed,
        temperature=generation.temperature,
        template=generation.template,
        hardware_label=generation.hardware_label,
        failure=failure,
        detail=detail,
        fallback_eligible=_can_be_fallback(generation, execution),
    )


def _build_suite(files: AttemptFiles, problem_id: str, scenario: str, run: RunConfig) -> SlmSuite:
    """``suite.json`` as a pure function of the files of the combination and of ``run.json``."""
    generations = files.generations
    executions = [files.executions.get(g.attempt) for g in generations]
    attempts = [_summary(g, e) for g, e in zip(generations, executions, strict=True)]
    last = generations[-1]
    phase = None
    if attempts[-1].failure is None:
        chosen = last.attempt
        if last.template.value == "solution":
            status, phase = "accepted", last.phase
        else:
            status, phase = "accepted_predicted", last.phase
    elif (chosen := _fallback(files)) is not None:
        status, phase = "accepted_fallback", config.FALLBACK_PHASE
    else:  # the 15th was not parsed and the authors closed it (manual_close.json)
        status = "discarded_manual"
    tests, discarded, duplicates = [], [], 0
    if chosen is not None:
        parse = generations[chosen - 1].parse
        duplicates = parse.duplicate_inputs
        if status == "accepted_predicted":
            tests = list(parse.tests)
        else:
            for item in executions[chosen - 1].inputs:
                if item.kept:
                    tests.append(TestCase(input=parse.inputs[item.index], output=item.output))
                else:
                    discarded.append(
                        DiscardedInput(index=item.index, discard=item.discard, verdict=item.verdict)
                    )
    closed = files.manual_close if status == "discarded_manual" else None
    return SlmSuite(
        problem_id=problem_id,
        scenario=scenario,
        model=run.model,
        model_digest=run.model_digest,
        status=status,
        accepted_phase=phase,
        attempts=attempts,
        accepted_attempt=chosen,
        tests=tests,
        suite_size=len(tests),
        discarded_inputs=discarded,
        duplicate_inputs=duplicates,
        manual_close=(
            None
            if closed is None
            else ManualCloseInfo(reason=closed.reason, closed_at=closed.closed_at)
        ),
    )


def attempt_files(
    root: Path,
    problem_id: str,
    scenario: str,
    run: RunConfig | None = None,
    tree: Path | None = None,
) -> AttemptFiles:
    """The attempt records of a combination, cross-checked; ``DamagedCombination`` if damaged."""
    return _load(root, problem_id, scenario, run, tree)


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


def awaiting_manual(
    root: Path, combinations: Iterable[tuple[str, str]], run: RunConfig | None = None
) -> list[tuple[str, str]]:
    """The combinations of ``combinations`` that await manual handling (``close``), in order."""
    found = []
    for problem_id, scenario in combinations:
        try:
            if combination_state(root, problem_id, scenario, run).kind == "awaiting_manual":
                found.append((problem_id, scenario))
        except DamagedCombination:
            pass
    return found
