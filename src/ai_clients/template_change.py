"""Changing a template in the middle of a run (``python -m ai_clients change-template``, R27).

A run keeps ONE version of each template. After the authors edit a template file, this records the
change (``template_changes/<NNN>.json``: the template, the old and new hashes, the date, the reason
and the files it moves) and then moves out of ``problems/`` every attempt made with the old version,
from the first of them in each combination on, with ``suite.json`` and ``manual_close.json``, to
``superseded/<NNN>/<id>/<scenario>/``. The combination is pending again at that attempt, and
``generate --resume`` makes it again with the new template and the same seeds.

The record is written before anything moves, so from then on the run's current template is the new
one and an attempt still in ``problems/`` with the old one makes its combination damaged: an
interruption can never leave old and new attempts mixed silently. Running the command again finishes
moving what the last change lists, without recording another one.
"""

import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ai_clients import config, store
from ai_clients.problem import list_problem_ids
from ai_clients.prompt import PromptTemplate
from ai_clients.report import DamagedTreeError
from ai_clients.schemas.run import RunConfig
from ai_clients.schemas.template_change import SupersededCombination, TemplateChange
from dataset.persistence import store as files


class NothingToChange(Exception):
    """The template file is the run's current template, and no change is left half-way (code 2)."""


class BrokenChangeError(Exception):
    """A file a change lists is both in ``problems/`` and in ``superseded/``, or in neither."""


@dataclass(frozen=True)
class ChangeResult:
    change: TemplateChange
    finished_earlier: bool  # True: an interrupted change was finished; no new one was recorded
    moved: int  # files moved by this command


def _names_to_move(attempts: store.AttemptFiles, kind: str) -> list[str]:
    """From the first attempt made with ``kind`` on: suite and manual close, then the attempts
    from the last to that one (so the files left are always a prefix of the attempts)."""
    first = next((g.attempt for g in attempts.generations if g.template.value == kind), None)
    if first is None:
        return []
    names = []
    if attempts.suite is not None:
        names.append(config.SUITE_FILE)
    if attempts.manual_close is not None:
        names.append(config.MANUAL_CLOSE_FILE)
    for generation in reversed(attempts.generations):
        if generation.attempt < first:
            break
        if generation.attempt in attempts.executions:
            names.append(config.execution_file_name(generation.attempt))
        names.append(config.generation_file_name(generation.attempt))
    return names


def plan_change(
    root: Path,
    kind: str,
    template: PromptTemplate,
    reason: str,
    *,
    run: RunConfig,
    number: int,
    now: Callable[[], str],
) -> TemplateChange:
    """The change to record, from the files as they are; nothing is written.

    ``NothingToChange`` if ``template`` is the current one; ``DamagedTreeError`` if any combination
    of the dataset is damaged (a change never starts on a tree it cannot read); ``ValueError`` if
    the reason is blank.
    """
    current = run.template_sha256(kind)
    if template.sha256 == current:
        raise NothingToChange(
            f"the {kind} template file is the current {kind} template of the run ({current}); "
            "edit the file first"
        )
    superseded, damaged = [], []
    for problem_id in list_problem_ids(root):
        for scenario in config.SCENARIOS:
            try:
                attempts = store.attempt_files(root, problem_id, scenario, run)
            except store.DamagedCombination as exc:
                damaged.append(exc)
                continue
            names = _names_to_move(attempts, kind)
            if names:
                superseded.append(
                    SupersededCombination(problem_id=problem_id, scenario=scenario, files=names)
                )
    if damaged:
        raise DamagedTreeError(damaged)
    return TemplateChange(
        number=number,
        template=kind,
        from_sha256=current,
        to_sha256=template.sha256,
        changed_at=now(),
        reason=reason.strip(),
        superseded=superseded,
    )


def files_left(root: Path, change: TemplateChange) -> int:
    """How many files the change lists are not in ``superseded/<NNN>/`` yet (0: it is complete).

    Never judged by ``problems/``: once the combination is made again, files with the same names
    (a new ``suite.json``, a new ``attempt_13``) are there, and they belong to the new template.
    """
    return sum(
        not (
            store.superseded_dir(root, change.number, item.problem_id, item.scenario) / name
        ).exists()
        for item in change.superseded
        for name in item.files
    )


def superseded_problems(root: Path, changes: list[TemplateChange]) -> list[str]:
    """What diverges between the changes and ``superseded/``: a listed file not moved yet (or
    missing), or anything there that no change lists. Empty when they agree."""
    root = Path(root)
    problems, listed = [], set()
    for change in changes:
        for item in change.superseded:
            target = store.superseded_dir(root, change.number, item.problem_id, item.scenario)
            for name in item.files:
                listed.add(target / name)
                if (target / name).is_file():
                    continue
                what = f"change {change.number}: {item.problem_id} {item.scenario.value} {name}"
                if (store.combination_dir(root, item.problem_id, item.scenario) / name).exists():
                    problems.append(f"{what} is not moved yet (run the same change-template again)")
                else:
                    problems.append(f"{what} is missing from {config.SUPERSEDED_DIR}/")
    base = Path(root) / config.SUITES_DIR / config.SUPERSEDED_DIR
    if base.is_dir():
        for path in sorted(base.rglob("*")):
            if path.is_file() and not path.name.startswith(".") and path not in listed:
                problems.append(f"{path.relative_to(base).as_posix()}: no template change lists it")
    return problems


def apply_change(root: Path, change: TemplateChange) -> int:
    """Move what ``change`` lists to ``superseded/<NNN>/``, skipping what already moved; the count.

    Each move is one ``rename`` in the same file system: a file is always whole, in one place.
    """
    moved = 0
    for item in change.superseded:
        source = store.combination_dir(root, item.problem_id, item.scenario)
        target = store.superseded_dir(root, change.number, item.problem_id, item.scenario)
        # superseded/, then <NNN>/, <id>/ and <scenario>/, each level on its own (store.py)
        for level in reversed([target, *list(target.parents)[:3]]):
            files.make_private_dir(level)
        for name in item.files:
            here, there = source / name, target / name
            if there.exists():  # moved already (a file of the same name in problems/ is new)
                continue
            if not here.exists():
                raise BrokenChangeError(
                    f"{item.problem_id} {item.scenario.value} {name}: change {change.number} lists "
                    f"it, and it is neither in problems/ nor in {config.SUPERSEDED_DIR}/"
                )
            os.rename(here, there)
            moved += 1
    return moved


def change_template(
    root: Path, kind: str, template: PromptTemplate, reason: str, *, now: Callable[[], str]
) -> ChangeResult:
    """Record and apply a change of the ``kind`` template to ``template`` (or finish the last one).

    Run under the exclusive lock of the run: nothing else may read or write while files move.
    """
    root = Path(root)
    changes = store.template_changes(root)
    if changes and files_left(root, changes[-1]):
        return ChangeResult(changes[-1], True, apply_change(root, changes[-1]))
    run = store.read_run(root)
    change = plan_change(root, kind, template, reason, run=run, number=len(changes) + 1, now=now)
    store.write_template_change(root, change)
    return ChangeResult(change, False, apply_change(root, change))
