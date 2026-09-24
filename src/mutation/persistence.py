"""Write the mutants of a problem so that an interruption never leaves a half-written one.

Same life cycle as a problem of the dataset (research R5; Constitution, Principle VII): the folder
is built in ``data/mutants/building/<id>/`` and closed with ONE atomic rename to
``data/mutants/problems/<id>/``. A folder still in ``building/`` is partial by definition and is
rebuilt from scratch on the next run; a closed problem is never touched again.

A closed folder holds ``Mutant_1.cpp`` ... ``Mutant_100.cpp`` and ``generation.json`` (how they were
reached, see ``schemas.generation``). A problem that could not reach 100 mutants (spec FR-009) is
closed too, with ``generation.json`` only, so it is not retried on every run and ``report`` can
list it.
"""

import os
import shutil
from collections import Counter
from pathlib import Path

from dataset.persistence import store
from mutation import config
from mutation.schemas.generation import (
    DiscardCount,
    Exclusion,
    Generation,
    MutantRecord,
    OperatorUse,
)
from mutation.types import Selection


def ensure_mutants_dir(root: Path) -> Path:
    """Create ``data/mutants/`` and its two subdirectories, each one given to the host user.

    Every level is created on its own (not with ``mkdir -p``) so that, when the ``sandbox``
    service runs as root, none of them stays owned by root in the bind-mounted ``data/``.
    """
    base = store.make_private_dir(Path(root) / config.MUTANTS_DIR)
    store.make_private_dir(Path(root) / config.BUILDING_DIR)
    store.make_private_dir(Path(root) / config.PROBLEMS_DIR)
    return base


def building_path(root: Path, problem_id: str) -> Path:
    return Path(root) / config.BUILDING_DIR / problem_id


def problem_path(root: Path, problem_id: str) -> Path:
    return Path(root) / config.PROBLEMS_DIR / problem_id


def is_closed(root: Path, problem_id: str) -> bool:
    """A problem is closed once its folder in ``problems/`` has the generation record."""
    return (problem_path(root, problem_id) / config.GENERATION_FILE).is_file()


def closed_problems(root: Path) -> list[str]:
    folder = Path(root) / config.PROBLEMS_DIR
    if not folder.is_dir():
        return []
    return sorted(p.name for p in folder.iterdir() if is_closed(root, p.name))


def pending_building(root: Path) -> list[str]:
    """Problems left half-written in ``building/`` (refuses ``package``; rebuilt by ``generate``)."""
    folder = Path(root) / config.BUILDING_DIR
    if not folder.is_dir():
        return []
    return sorted(p.name for p in folder.iterdir())


def reset_building(root: Path) -> int:
    """Remove every partial problem; return how many were removed."""
    removed = 0
    for name in pending_building(root):
        path = building_path(root, name)
        shutil.rmtree(path) if path.is_dir() else path.unlink()
        removed += 1
    return removed


def _generation(problem_id: str, selection: Selection) -> Generation:
    counts = Counter((d.order, d.reason) for d in selection.discards)
    discards = [
        DiscardCount(order=order, reason=reason, count=count)
        for (order, reason), count in sorted(
            counts.items(), key=lambda item: (item[0][0], item[0][1].value)
        )
    ]
    if selection.alert is not None:
        return Generation(
            problem_id=problem_id,
            status="excluded",
            mutants=[],
            discards=discards,
            exclusion=Exclusion(
                mutants_reached=selection.alert.mutants_reached,
                highest_order_attempted=selection.alert.highest_order_attempted,
            ),
        )
    return Generation(
        problem_id=problem_id,
        status="complete",
        mutants=[
            MutantRecord(
                file=config.mutant_file_name(m.index),
                order=m.order,
                operators=[OperatorUse(operator=op, variant=v) for op, v in m.operators],
                sha256=m.source_sha256,
            )
            for m in selection.mutants
        ],
        discards=discards,
    )


def write_selection(root: Path, problem_id: str, selection: Selection) -> Path:
    """Persist the outcome of a problem and close it; return its folder in ``problems/``.

    ``FileExistsError`` if the problem is already closed (never overwritten). ``ValueError`` if the
    selection is neither 100 numbered mutants nor an exclusion; nothing is written then.
    """
    # The record is built (and validated) first, so a bad selection touches nothing on disk.
    record = _generation(problem_id, selection)
    if problem_path(root, problem_id).exists():
        raise FileExistsError(f"{problem_path(root, problem_id)} is already closed")
    ensure_mutants_dir(root)
    folder = building_path(root, problem_id)
    if folder.exists():
        shutil.rmtree(folder)  # stale leftovers of an interrupted run
    store.make_private_dir(folder)
    if record.status == "complete":
        for mutant in selection.mutants:
            store.write_problem_text(folder, config.mutant_file_name(mutant.index), mutant.source)
    store.write_problem_json(folder, config.GENERATION_FILE, record)
    target = problem_path(root, problem_id)
    os.rename(folder, target)  # the single atomic step that closes the problem
    return target


def read_generation(root: Path, problem_id: str) -> Generation:
    path = problem_path(root, problem_id) / config.GENERATION_FILE
    return Generation.model_validate(store.read_json(path))
