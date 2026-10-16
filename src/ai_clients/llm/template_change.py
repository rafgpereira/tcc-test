"""``change-template --model gpt|gemini --template llm``: the text-base changed during a run (FR-009).

The same rule as the SLM (``ai_clients.template_change``, research R27 of the SLM): a run keeps
ONE version of its text-base. ``run.json`` is never rewritten; the change is recorded in
``template_changes/<NNN>.json`` and every file made with the old text-base (the attempts, from the
first one, with ``suite.json`` and ``manual_close.json``) is moved to ``superseded/<NNN>/``, so
those combinations are made again with the new one. The record is written before anything moves,
so an interrupted change is finished by running the command again. ``barred/`` never moves.
"""

import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ai_clients.llm import config, store
from ai_clients.llm.schemas import LlmTemplateChange
from ai_clients.prompt import PromptTemplate
from ai_clients.report import DamagedTreeError
from ai_clients.schemas.template_change import SupersededCombination
from ai_clients.template_change import NothingToChange
from dataset.persistence import store as files


class BrokenChangeError(Exception):
    """A file listed by a change is neither in ``problems/`` nor in ``superseded/``."""


@dataclass(frozen=True)
class ChangeResult:
    change: LlmTemplateChange
    moved: int
    finished_earlier: bool


def _names_to_move(attempts: store.AttemptFiles) -> list[str]:
    names = []
    if attempts.suite is not None:
        names.append(config.SUITE_FILE)
    if attempts.manual_close is not None:
        names.append(config.MANUAL_CLOSE_FILE)
    names += [config.attempt_file_name(a.attempt) for a in reversed(attempts.attempts)]
    return names


def plan_change(root: Path, model: str, template: PromptTemplate, reason: str, *, run, number, now):
    """The change that would be recorded (nothing written); ``NothingToChange`` if the file is the
    current text-base; ``DamagedTreeError`` if any combination is damaged."""
    if template.sha256 == run.template_sha256:
        raise NothingToChange(
            f"the llm template file is the current template of the run ({template.sha256[:12]}); "
            "edit the file first"
        )
    problems_dir = store.base_dir(root, model) / "problems"
    superseded, damaged = [], []
    for problem in (
        sorted(p for p in problems_dir.iterdir() if p.is_dir()) if problems_dir.is_dir() else []
    ):
        for scenario in config.SCENARIOS:
            if not (problem / scenario).is_dir():
                continue
            try:
                attempts = store.attempt_files(root, model, problem.name, scenario, run)
            except store.DamagedCombination as exc:
                damaged.append(exc)
                continue
            names = _names_to_move(attempts)
            if names:
                superseded.append(
                    SupersededCombination(problem_id=problem.name, scenario=scenario, files=names)
                )
    if damaged:
        raise DamagedTreeError(damaged)
    return LlmTemplateChange(
        number=number,
        from_sha256=run.template_sha256,
        to_sha256=template.sha256,
        changed_at=now(),
        reason=reason.strip(),
        superseded=superseded,
    )


def _source(root, model, item, name) -> Path:
    return store.combination_dir(root, model, item.problem_id, item.scenario) / name


def files_left(root: Path, model: str, change: LlmTemplateChange) -> int:
    return sum(
        _source(root, model, item, name).is_file()
        for item in change.superseded
        for name in item.files
    )


def apply_change(root: Path, model: str, change: LlmTemplateChange) -> int:
    """Move what ``change`` lists out of ``problems/``; the number of files moved."""
    moved = 0
    for item in change.superseded:
        target = store.superseded_dir(root, model, change.number, item.problem_id, item.scenario)
        for name in item.files:
            source = _source(root, model, item, name)
            if not source.is_file():
                if not (target / name).is_file():
                    raise BrokenChangeError(
                        f"{item.problem_id} {item.scenario.value} {name}: change {change.number} "
                        "lists it, and it is neither in problems/ nor in superseded/"
                    )
                continue
            folder = store.base_dir(root, model)
            for part in (
                config.SUPERSEDED_DIR,
                f"{change.number:03d}",
                item.problem_id,
                item.scenario.value,
            ):
                folder = files.make_private_dir(folder / part)
            os.replace(source, target / name)
            moved += 1
    return moved


def change_template(
    root: Path, model: str, template: PromptTemplate, reason: str, *, now: Callable[[], str]
) -> ChangeResult:
    changes = store.template_changes(root, model)
    if changes and files_left(root, model, changes[-1]):
        last = changes[-1]
        return ChangeResult(last, apply_change(root, model, last), finished_earlier=True)
    run = store.read_run(root, model)
    change = plan_change(root, model, template, reason, run=run, number=len(changes) + 1, now=now)
    store.write_template_change(root, model, change)
    return ChangeResult(change, apply_change(root, model, change), finished_earlier=False)
