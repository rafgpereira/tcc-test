"""The on-disk state of one commercial model under ``data/suites/<model>/`` (data-model.md, 1 and 4).

The rules of the SLM tree, reused: every fact is ONE immutable file written atomically; the state
of a problem x scenario is derived only from its files; ``suite.json`` is a pure function of them;
anything else is damage, listed and never repaired. The locks are the SLM ones, over this model's
own folder, so the two models (and the SLM) never block each other.

The answers barred for reporting no reasoning (FR-018a) live in ``barred/``, out of the attempts:
they never change the state of a combination.
"""

import fcntl
import re
import threading
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from ai_clients import store as slm_store
from ai_clients.llm import config
from ai_clients.llm.schemas import (
    BarredResponse,
    LlmAttempt,
    LlmAttemptSummary,
    LlmRunConfig,
    LlmSuite,
    LlmTemplateChange,
)
from ai_clients.schemas.common import SuiteStatus
from ai_clients.schemas.manual_close import ManualClose
from ai_clients.schemas.suite import ManualCloseInfo
from dataset.persistence import store

AlreadyRunningError = slm_store.AlreadyRunningError
DamagedCombination = slm_store.DamagedCombination
IncompatibleRunError = slm_store.IncompatibleRunError
DamagedRunError = slm_store.DamagedRunError


def _scenario(scenario) -> str:
    return str(getattr(scenario, "value", scenario))


def base_dir(root: Path, model: str, tree: Path | None = None) -> Path:
    """``data/suites/<model>``, or ``tree`` (an archived run of the model, read only)."""
    return Path(root) / (config.suites_dir(model) if tree is None else Path(tree))


def ensure_suites_dir(root: Path, model: str) -> Path:
    """Create ``data/suites/<model>/problems/``, one level at a time (never owned by root)."""
    return slm_store.ensure_tree(root, config.suites_dir(model))


def combination_dir(root: Path, model: str, problem_id: str, scenario, tree=None) -> Path:
    return base_dir(root, model, tree) / "problems" / problem_id / _scenario(scenario)


# Folders are created by several threads (two scenarios of one problem at the same time): one at
# a time, or the chmod/chown of ``make_private_dir`` of two threads would interleave (EPERM for
# root without CAP_FOWNER in the sandbox service).
_FOLDERS = threading.Lock()


def _ensure_combination_dir(root: Path, model: str, problem_id: str, scenario) -> Path:
    with _FOLDERS:
        ensure_suites_dir(root, model)
        store.make_private_dir(base_dir(root, model) / "problems" / problem_id)
        return store.make_private_dir(combination_dir(root, model, problem_id, scenario))


# -------------------------------------------------------------------------------------- locks


@contextmanager
def exclusive_run(root: Path, model: str) -> Iterator[None]:
    """No other command over this model's tree: starting a run, ``close``, ``change-template``,
    ``package``."""
    with slm_store.lock_tree(root, config.suites_dir(model), fcntl.LOCK_EX):
        yield


@contextmanager
def shared_run(root: Path, model: str) -> Iterator[None]:
    """Several ``generate --resume`` of the same model together (each combination claimed)."""
    with slm_store.lock_tree(root, config.suites_dir(model), fcntl.LOCK_SH):
        yield


@contextmanager
def claim(root: Path, model: str, problem_id: str, scenario) -> Iterator[bool]:
    """Take one combination for this thread: ``True``, or ``False`` if another one has it."""
    with _FOLDERS:  # created once, before the threads race for it
        store.make_private_dir(
            ensure_suites_dir(root, model) / slm_store.config.COMBINATION_LOCKS_DIR
        )
    with slm_store.claim_in(root, config.suites_dir(model), problem_id, _scenario(scenario)) as ok:
        yield ok


# ------------------------------------------------------------------------------------ writing


def write_attempt(root: Path, model: str, record: LlmAttempt) -> Path:
    folder = _ensure_combination_dir(root, model, record.problem_id, record.scenario)
    return slm_store.write_once(folder / config.attempt_file_name(record.attempt), record)


def barred_dir(root: Path, model: str, problem_id: str, scenario, tree=None) -> Path:
    return base_dir(root, model, tree) / config.BARRED_DIR / problem_id / _scenario(scenario)


_BARRED_FILE = re.compile(r"^(\d+)\.json$")


def barred_files(root: Path, model: str, problem_id: str, scenario, tree=None) -> list[Path]:
    folder = barred_dir(root, model, problem_id, scenario, tree)
    if not folder.is_dir():
        return []
    found = [p for p in folder.iterdir() if _BARRED_FILE.match(p.name)]
    return sorted(found, key=lambda p: int(_BARRED_FILE.match(p.name)[1]))


def write_barred(root: Path, model: str, record: BarredResponse) -> Path:
    """``barred/<id>/<scenario>/<n>.json``, ``n`` the next number (the combination is claimed)."""
    with _FOLDERS:
        ensure_suites_dir(root, model)
        folder = base_dir(root, model)
        for part in (config.BARRED_DIR, record.problem_id, record.scenario.value):
            folder = store.make_private_dir(folder / part)
    existing = barred_files(root, model, record.problem_id, record.scenario)
    number = int(_BARRED_FILE.match(existing[-1].name)[1]) + 1 if existing else 1
    return slm_store.write_once(folder / f"{number}.json", record)


def read_barred(root: Path, model: str) -> list[BarredResponse]:
    """Every barred answer of the tree (for the report and the cost of a run)."""
    found = []
    folder = base_dir(root, model) / config.BARRED_DIR
    if not folder.is_dir():
        return found
    for path in sorted(folder.glob("*/*/*.json")):
        if _BARRED_FILE.match(path.name):
            found.append(BarredResponse.model_validate_json(path.read_bytes()))
    return found


def write_manual_close(root: Path, model: str, record: ManualClose) -> Path:
    folder = _ensure_combination_dir(root, model, record.problem_id, record.scenario)
    return slm_store.write_once(folder / config.MANUAL_CLOSE_FILE, record)


def read_attempt(root: Path, model: str, problem_id: str, scenario, attempt: int, tree=None):
    folder = combination_dir(root, model, problem_id, scenario, tree)
    path = folder / config.attempt_file_name(attempt)
    if not path.is_file():
        return None
    return LlmAttempt.model_validate_json(path.read_bytes())


# ---------------------------------------------------------------------------------- run.json


def run_path(root: Path, model: str, tree: Path | None = None) -> Path:
    return base_dir(root, model, tree) / config.RUN_FILE


def run_exists(root: Path, model: str, tree: Path | None = None) -> bool:
    return run_path(root, model, tree).is_file()


def write_run(root: Path, model: str, run: LlmRunConfig) -> Path:
    ensure_suites_dir(root, model)
    return slm_store.write_once(run_path(root, model), run)


def incompatible(model: str) -> str:
    tree = config.suites_dir(model).as_posix()
    return (
        f"{tree} holds a run of another version of python -m ai_clients (it cannot be resumed "
        f"nor read); move it away first: mv {tree} {tree}-<name>"
    )


def read_run(root: Path, model: str, tree: Path | None = None) -> LlmRunConfig:
    """The run as it stands: ``run.json`` with its template changes applied in order."""
    raw = run_path(root, model, tree).read_bytes()
    try:
        run = LlmRunConfig.model_validate_json(raw)
    except ValueError as exc:
        raise IncompatibleRunError(incompatible(model)) from exc
    if run.model_key != model:
        raise IncompatibleRunError(incompatible(model))
    try:
        return run.with_changes(template_changes(root, model, tree))
    except ValueError as exc:
        tree = config.suites_dir(model).as_posix()
        raise DamagedRunError(f"{tree}/{config.TEMPLATE_CHANGES_DIR}: {exc}") from exc


# --------------------------------------------------------------------------- template changes


def template_changes_dir(root: Path, model: str, tree: Path | None = None) -> Path:
    return base_dir(root, model, tree) / config.TEMPLATE_CHANGES_DIR


def superseded_dir(root: Path, model: str, number: int, problem_id: str, scenario) -> Path:
    return (
        base_dir(root, model)
        / config.SUPERSEDED_DIR
        / f"{number:03d}"
        / problem_id
        / _scenario(scenario)
    )


def template_changes(root: Path, model: str, tree: Path | None = None) -> list[LlmTemplateChange]:
    folder = template_changes_dir(root, model, tree)
    if not folder.is_dir():
        return []
    names = sorted(p.name for p in folder.iterdir() if not p.name.startswith("."))
    changes = []
    for number, name in enumerate(names, start=1):
        if name != f"{number:03d}.json":
            raise ValueError(f"{name}: the changes are 001.json, 002.json, ... without a gap")
        try:
            change = LlmTemplateChange.model_validate_json((folder / name).read_bytes())
        except ValueError as exc:
            raise ValueError(f"{name}: {slm_store._reason(exc)}") from exc
        if change.number != number:
            raise ValueError(f"{name}: it says it is change {change.number}")
        changes.append(change)
    return changes


def write_template_change(root: Path, model: str, change: LlmTemplateChange) -> Path:
    folder = store.make_private_dir(ensure_suites_dir(root, model) / config.TEMPLATE_CHANGES_DIR)
    return slm_store.write_once(folder / f"{change.number:03d}.json", change)


# ------------------------------------------------------------------------------ state machine


@dataclass(frozen=True)
class State:
    """Where a problem x scenario stands; ``attempt`` is the one the next step is about."""

    kind: Literal["terminal", "pending", "finalizable", "awaiting_manual"]
    attempt: int


@dataclass(frozen=True)
class AttemptFiles:
    attempts: list[LlmAttempt]  # 1, 2, ... without a gap
    suite: Path | None
    manual_close: ManualClose | None = None


_ATTEMPT_FILE = re.compile(r"^attempt_(\d+)\.json$")


def _read_named(path: Path, schema, named_as: tuple, problems: list[str]):
    try:
        record = schema.model_validate_json(path.read_bytes())
    except ValueError as exc:
        problems.append(f"inconsistent: {path.name}: {slm_store._reason(exc)}")
        return None
    attempt = getattr(record, "attempt", None)
    named = (record.problem_id, record.scenario.value, *(() if attempt is None else (attempt,)))
    if named != named_as:
        problems.append(f"inconsistent: {path.name}: it is about {' '.join(map(str, named))}")
        return None
    return record


def _load(root: Path, model: str, problem_id: str, scenario, run: LlmRunConfig | None, tree=None):
    scenario = _scenario(scenario)
    folder = combination_dir(root, model, problem_id, scenario, tree)
    problems: list[str] = []
    found: dict[int, LlmAttempt] = {}
    suite = manual_close = None
    for path in sorted(folder.iterdir()) if folder.is_dir() else []:
        name = path.name
        if slm_store._is_leftover(name):
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
        attempt = int(match[1])
        if not 1 <= attempt <= config.MAX_ATTEMPTS:
            problems.append(f"inconsistent: {name}: there are only {config.MAX_ATTEMPTS} attempts")
            continue
        record = _read_named(path, LlmAttempt, (problem_id, scenario, attempt), problems)
        if record is not None:
            found[attempt] = record
    last = max(found, default=0)
    for n in range(1, last + 1):
        if n not in found:
            problems.append(f"missing: {config.attempt_file_name(n)}")
    for n, record in sorted(found.items()):
        name = config.attempt_file_name(n)
        if run is not None:
            if record.model_requested != run.model_requested:
                problems.append(
                    f"inconsistent: {name}: model {record.model_requested} differs from run.json "
                    f"({run.model_requested})"
                )
            if record.request_parameters != run.request_parameters:
                problems.append(f"inconsistent: {name}: request parameters differ from run.json")
            if record.template_sha256 != run.template_sha256:
                problems.append(
                    f"inconsistent: {name}: template_sha256 {record.template_sha256} is not the "
                    f"template of the run ({run.template_sha256}); it belongs in "
                    f"{config.SUPERSEDED_DIR}/ (run the same change-template again)"
                )
        if n < last and record.parse.ok:
            problems.append(
                f"inconsistent: {config.attempt_file_name(n + 1)}: attempt {n} was accepted"
            )
    if not problems and manual_close is not None:
        final = found.get(config.MAX_ATTEMPTS)
        if final is None or final.parse.ok:
            problems.append(
                f"inconsistent: {config.MANUAL_CLOSE_FILE}: the combination does not await "
                "manual handling"
            )
    if problems:
        raise DamagedCombination(problem_id, scenario, problems)
    return AttemptFiles([found[n] for n in range(1, last + 1)], suite, manual_close)


def _state_of_attempts(files: AttemptFiles) -> State:
    if not files.attempts:
        return State("pending", 1)
    last = files.attempts[-1]
    if last.parse.ok:
        return State("finalizable", last.attempt)  # accepted_predicted
    if last.attempt < config.MAX_ATTEMPTS:
        return State("pending", last.attempt + 1)
    return State("finalizable" if files.manual_close else "awaiting_manual", last.attempt)


def _detail(record: LlmAttempt) -> str:
    parse = record.parse
    if not parse.ok:
        return parse.detail
    dropped = parse.empty_tests + parse.abbreviated_tests + parse.duplicate_inputs
    return f"{len(parse.tests)} kept, {dropped} dropped"


def _build_suite(files: AttemptFiles, problem_id: str, scenario: str, run: LlmRunConfig):
    attempts = [
        LlmAttemptSummary(
            attempt=a.attempt,
            failure=None if a.parse.ok else a.parse.failure,
            detail=_detail(a),
            model_returned=a.model_returned,
            cost_usd=a.cost_usd,
        )
        for a in files.attempts
    ]
    last = files.attempts[-1]
    common = {
        "problem_id": problem_id,
        "scenario": scenario,
        "model": run.model_requested,
        "attempts": attempts,
        "accepted_phase": None,
        "discarded_inputs": [],
    }
    if last.parse.ok:
        return LlmSuite(
            **common,
            model_digest=last.model_returned,
            status=SuiteStatus.ACCEPTED_PREDICTED,
            accepted_attempt=last.attempt,
            tests=last.parse.tests,
            suite_size=len(last.parse.tests),
            duplicate_inputs=last.parse.duplicate_inputs,
        )
    close = files.manual_close
    return LlmSuite(
        **common,
        model_digest=None,
        status=SuiteStatus.DISCARDED_MANUAL,
        accepted_attempt=None,
        tests=[],
        suite_size=0,
        duplicate_inputs=0,
        manual_close=ManualCloseInfo(reason=close.reason, closed_at=close.closed_at),
    )


def attempt_files(
    root: Path, model: str, problem_id: str, scenario, run=None, tree=None
) -> AttemptFiles:
    return _load(root, model, problem_id, scenario, run, tree)


def combination_state(
    root: Path,
    model: str,
    problem_id: str,
    scenario,
    run: LlmRunConfig | None = None,
    tree: Path | None = None,
) -> State:
    """The state of a problem x scenario from its files; ``DamagedCombination`` if they diverge."""
    scenario = _scenario(scenario)
    files = _load(root, model, problem_id, scenario, run, tree)
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


def expected_suite(root: Path, model: str, problem_id: str, scenario, run: LlmRunConfig):
    files = _load(root, model, problem_id, scenario, run)
    if _state_of_attempts(files).kind != "finalizable":
        return None
    return _build_suite(files, problem_id, _scenario(scenario), run)


def finalize(root: Path, model: str, problem_id: str, scenario, run: LlmRunConfig):
    """Write ``suite.json`` if the combination is finalizable (the only writer of it)."""
    files = _load(root, model, problem_id, scenario, run)
    if files.suite is not None or _state_of_attempts(files).kind != "finalizable":
        return None
    suite = _build_suite(files, problem_id, _scenario(scenario), run)
    folder = combination_dir(root, model, problem_id, scenario)
    slm_store.write_once(folder / config.SUITE_FILE, suite)
    return suite


def read_suite(root: Path, model: str, problem_id: str, scenario) -> LlmSuite | None:
    path = combination_dir(root, model, problem_id, scenario) / config.SUITE_FILE
    if not path.is_file():
        return None
    return LlmSuite.model_validate_json(path.read_bytes())


def awaiting_manual(
    root: Path, model: str, combinations: Iterable[tuple[str, str]], run=None
) -> list[tuple[str, str]]:
    found = []
    for problem_id, scenario in combinations:
        try:
            if combination_state(root, model, problem_id, scenario, run).kind == "awaiting_manual":
                found.append((problem_id, scenario))
        except DamagedCombination:
            pass
    return found
