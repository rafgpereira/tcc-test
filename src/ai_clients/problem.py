"""One problem of the dataset, as this module needs it.

There is no single reader of a whole problem in the ``dataset`` package, so this composes the
readers that exist there (``Metadata.from_folder``, ``Testes.from_folder``, which validate the schema
and that ``problem_id`` equals the folder name) with a plain read of the two text files. Nothing of
the ``dataset`` package changes.
"""

from dataclasses import dataclass
from pathlib import Path

from ai_clients import config
from dataset.schemas.metadata import Metadata
from dataset.schemas.testes import Testes


@dataclass(frozen=True)
class ProblemInput:
    problem_id: str
    statement: str  # enunciado.md
    ac_ref: str  # AC_ref.cpp: goes into the prompt only, never runs and never judges anything
    metadata: Metadata  # the time and memory limits
    testes: Testes  # the public tests: the few-shot example and the only judge of the solution


@dataclass(frozen=True)
class JudgeInput:
    """What judging a Python solution needs: the limits and the public tests, and nothing else.

    ``execute`` reads only this, so ``AC_ref.cpp`` is not even read in the execution phase.
    """

    problem_id: str
    metadata: Metadata
    testes: Testes


def problem_folder(root: Path, problem_id: str) -> Path:
    return Path(root) / config.DATASET_PROBLEMS_DIR / problem_id


def _testes(folder: Path, problem_id: str) -> Testes:
    testes = Testes.from_folder(folder)
    if not testes.public_tests:
        raise ValueError(
            f"{problem_id}: testes.json has no public test (needed for the example of the prompt "
            "and to judge the Python solution)"
        )
    return testes


def load_judge_input(root: Path, problem_id: str) -> JudgeInput:
    """Read ``metadata.json`` and ``testes.json`` of the problem; ``ValueError`` without public test."""
    folder = problem_folder(root, problem_id)
    return JudgeInput(problem_id, Metadata.from_folder(folder), _testes(folder, problem_id))


def load_problem(root: Path, problem_id: str) -> ProblemInput:
    """Read ``data/dataset/problems/<id>/``; ``ValueError`` if it has no public test."""
    folder = problem_folder(root, problem_id)
    testes = _testes(folder, problem_id)
    return ProblemInput(
        problem_id=problem_id,
        statement=(folder / "enunciado.md").read_text(encoding="utf-8"),
        ac_ref=(folder / "AC_ref.cpp").read_text(encoding="utf-8"),
        metadata=Metadata.from_folder(folder),
        testes=testes,
    )


def list_problem_ids(root: Path) -> list[str]:
    """The problem folders of the extracted dataset, in alphabetical order."""
    base = Path(root) / config.DATASET_PROBLEMS_DIR
    if not base.is_dir():
        return []
    return sorted(p.name for p in base.iterdir() if p.is_dir())
