"""The on-disk state of the SLM suites under ``data/suites/slm/`` (data-model.md, sections 3 and 4).

Every fact is ONE immutable file, written once and atomically (temporary file in the same
directory, ``fsync``, ``os.replace``; ``dataset.persistence.store``), so an interruption never
leaves a half-written file and a file that exists is never rewritten. The state of a problem ×
scenario is derived only from which files exist; the state machine and ``suite.json`` come with
the stories that need them.
"""

import fcntl
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from ai_clients import config
from ai_clients.schemas.execution import ExecutionRecord
from ai_clients.schemas.generation import GenerationRecord
from dataset.persistence import store

__all__ = [
    "AlreadyRunningError",
    "ExecutionRecord",
    "GenerationRecord",
    "combination_dir",
    "ensure_suites_dir",
    "exclusive_run",
    "read_execution",
    "read_generation",
    "write_execution",
    "write_generation",
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
