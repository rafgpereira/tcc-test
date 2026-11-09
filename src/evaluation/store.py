"""Write the evaluation of a set × problem so that an interruption never leaves a half-written one.

Same life cycle as the mutants (research R5; Constitution, Principle VII): the three scenario files
are built in ``<output>/<set>/building/<id>/`` and closed with ONE atomic rename to
``<output>/<set>/problems/<id>/``. A folder still in ``building/`` is partial and is rebuilt from
scratch; a closed one is never touched again (FR-015). One run at a time per output tree (``flock``
on ``<output>/.lock``, released by the operating system however the process ends).
"""

import fcntl
import hashlib
import json
import os
import shutil
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from dataset.persistence import store
from evaluation import config
from evaluation.schemas.result import CombinationResult
from evaluation.schemas.run import RunConfig


class AlreadyRunningError(Exception):
    """Another ``run`` holds the lock of the output tree."""


class RunMismatchError(Exception):
    """``run.json`` says this set was evaluated on other inputs."""


def set_dir(base: Path, set_name: str) -> Path:
    return Path(base) / set_name


def building_path(base: Path, set_name: str, problem_id: str) -> Path:
    return set_dir(base, set_name) / config.BUILDING / problem_id


def problem_path(base: Path, set_name: str, problem_id: str) -> Path:
    return set_dir(base, set_name) / config.PROBLEMS / problem_id


def ensure_set_dir(base: Path, set_name: str) -> Path:
    """Each level on its own, so none stays owned by root in the bind-mounted ``data/``."""
    store.make_private_dir(Path(base))
    folder = store.make_private_dir(set_dir(base, set_name))
    store.make_private_dir(folder / config.BUILDING)
    store.make_private_dir(folder / config.PROBLEMS)
    return folder


@contextmanager
def exclusive_run(base: Path) -> Iterator[None]:
    store.make_private_dir(Path(base))
    with (Path(base) / config.LOCK_FILE).open("a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise AlreadyRunningError(
                f"another `python -m evaluation run` is already running over {base}"
            ) from exc
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def is_closed(base: Path, set_name: str, problem_id: str) -> bool:
    return problem_path(base, set_name, problem_id).is_dir()


def closed_problems(base: Path, set_name: str) -> list[str]:
    folder = set_dir(base, set_name) / config.PROBLEMS
    return sorted(p.name for p in folder.iterdir() if p.is_dir()) if folder.is_dir() else []


def pending_building(base: Path, set_name: str) -> list[str]:
    folder = set_dir(base, set_name) / config.BUILDING
    return sorted(p.name for p in folder.iterdir()) if folder.is_dir() else []


def reset_building(base: Path, set_name: str) -> int:
    """Remove every partial problem of the set; return how many were removed."""
    removed = 0
    for name in pending_building(base, set_name):
        path = building_path(base, set_name, name)
        shutil.rmtree(path) if path.is_dir() else path.unlink()
        removed += 1
    return removed


def write_problem(
    base: Path, set_name: str, problem_id: str, results: Mapping[str, CombinationResult]
) -> Path:
    """Persist the scenarios of one set × problem and close it; ``FileExistsError`` if closed."""
    for scenario, result in results.items():
        if (result.set, result.problem_id, result.scenario) != (set_name, problem_id, scenario):
            raise ValueError(f"{set_name} {problem_id} {scenario}: the result is of another one")
    target = problem_path(base, set_name, problem_id)
    if target.exists():
        raise FileExistsError(f"{target} is already closed")
    ensure_set_dir(base, set_name)
    folder = building_path(base, set_name, problem_id)
    if folder.exists():
        shutil.rmtree(folder)  # stale leftovers of an interrupted run
    store.make_private_dir(folder)
    for scenario in sorted(results):
        store.atomic_write_json(folder / config.scenario_file(scenario), results[scenario])
    os.rename(folder, target)  # the single atomic step that closes the set × problem
    return target


def read_problem(base: Path, set_name: str, problem_id: str) -> dict[str, CombinationResult]:
    folder = problem_path(base, set_name, problem_id)
    results = {}
    for path in sorted(folder.glob("*.json")):
        result = CombinationResult.model_validate_json(path.read_bytes())
        if path.name != config.scenario_file(result.scenario) or result.problem_id != problem_id:
            raise ValueError(f"{path}: the file is not named after its scenario and problem")
        results[result.scenario] = result
    return results


# --------------------------------------------------------------------------------- run.json


def sha256_of_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def current_run(root: Path, set_name: str, gcc_version: str) -> RunConfig:
    """The ``RunConfig`` of the inputs on disk now (the manifests the gate has just checked)."""
    root = Path(root)
    dataset_manifest = root / config.DATASET_MANIFEST
    revision = json.loads(dataset_manifest.read_text(encoding="utf-8")).get("revision", 1)
    model = config.SET_MODEL[set_name]
    return RunConfig(
        set=set_name,
        model=model,
        attempt=config.SET_ATTEMPT.get(set_name),
        dataset_manifest_sha256=sha256_of_file(dataset_manifest),
        dataset_revision=revision,
        mutants_manifest_sha256=sha256_of_file(root / config.MUTANTS_MANIFEST),
        suites_manifest_sha256=sha256_of_file(root / config.suites_manifest(model)),
        gcc_version=gcc_version,
        created_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )


def read_run(base: Path, set_name: str) -> RunConfig | None:
    path = set_dir(base, set_name) / config.RUN_FILE
    if not path.is_file():
        return None
    return RunConfig.model_validate_json(path.read_bytes())


def open_run(base: Path, set_name: str, current: RunConfig) -> RunConfig:
    """Write ``run.json`` on the first run of the set; on a resumption, refuse other inputs."""
    recorded = read_run(base, set_name)
    if recorded is None:
        ensure_set_dir(base, set_name)
        store.atomic_write_json(set_dir(base, set_name) / config.RUN_FILE, current)
        return current
    different = recorded.differences(current)
    if different:
        raise RunMismatchError(
            f"{set_name}: run.json was recorded with other inputs ({', '.join(different)}); "
            "evaluate in another --output-dir, or remove the set to start it again"
        )
    return recorded
