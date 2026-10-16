"""The package of the final run of one commercial model: ``data/<model>_suites.zip`` (FR-026).

The core of the SLM package (``ai_clients.packaging``: deterministic zip, hashes, ``verify``),
with this model's paths. One package per model (A7): it is refused while any problem x scenario
of THIS model has no ``suite.json`` (the other model never blocks it) or if anything is damaged.
``run.json``, the barred answers and the template changes (with what they moved aside) go in; the
locks and the leftovers of an interrupted atomic write never do.
"""

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from ai_clients import packaging as core
from ai_clients.llm import config, store
from ai_clients.llm.schemas import LlmSuitesManifest
from ai_clients.llm.template_change import files_left
from ai_clients.problem import list_problem_ids
from ai_clients.report import DamagedTreeError
from dataset.integrity.packaging import SIZE_WARNING_BYTES
from dataset.persistence import store as files
from dataset.schemas.manifest import FileHash
from mutation.integrity import VerifyResult
from mutation.manifest import sha256_of_file

UnfinishedRunError = core.UnfinishedRunError


@dataclass(frozen=True)
class PackageResult:
    zip_path: Path
    size: int
    combinations: int
    statuses: dict[str, int]
    over_size_warning: bool


def check_finished(root: Path, model: str) -> dict[str, int]:
    """Suite status -> combinations of a finished run of ``model``; refuses an unfinished one."""
    root = Path(root)
    run = store.read_run(root, model)
    problems = list_problem_ids(root)
    unfinished, awaiting, damaged = [], [], []
    statuses: Counter = Counter()
    for problem_id in problems:
        for scenario in config.SCENARIOS:
            try:
                state = store.combination_state(root, model, problem_id, scenario, run)
            except store.DamagedCombination as exc:
                damaged.append(exc)
                continue
            if state.kind == "awaiting_manual":
                awaiting.append(f"{problem_id} {scenario}")
            if state.kind != "terminal":
                unfinished.append(f"{problem_id} {scenario}")
            else:
                statuses[store.read_suite(root, model, problem_id, scenario).status.value] += 1
    if damaged:
        raise DamagedTreeError(damaged)
    total = len(problems) * len(config.SCENARIOS)
    if unfinished:
        shown = ", ".join(unfinished[:5]) + (", ..." if len(unfinished) > 5 else "")
        message = (
            f"{len(unfinished)} of {total} combinations of {model} have no suite.json ({shown}); "
            f"finish the run (generate --model {model} --resume) before packaging"
        )
        if awaiting:
            message += (
                f"; {len(awaiting)} await manual handling ({', '.join(awaiting)}): close each "
                f"with python -m ai_clients close --model {model} --problem ID --scenario S "
                '--reason "..."'
            )
        raise UnfinishedRunError(message)
    base = store.base_dir(root, model) / "problems"
    extra = []
    for folder in sorted(base.iterdir()):
        if folder.name.startswith("."):
            continue
        if folder.name not in problems or not folder.is_dir():
            extra.append(folder.name)
            continue
        for entry in sorted(folder.iterdir()):
            if not entry.name.startswith(".") and entry.name not in config.SCENARIOS:
                extra.append(f"{folder.name}/{entry.name}")
    if extra:
        raise UnfinishedRunError(
            f"{config.suites_dir(model).as_posix()}/problems has entries that are not a problem x "
            f"scenario of the dataset: {', '.join(extra[:5])}"
        )
    for change in store.template_changes(root, model):
        if files_left(root, model, change):
            raise UnfinishedRunError(
                f"template change {change.number} was interrupted; run change-template again"
            )
    return {
        "accepted_predicted": statuses["accepted_predicted"],
        "discarded_manual": statuses["discarded_manual"],
    }


def build_zip(root: Path, model: str) -> PackageResult:
    root = Path(root)
    statuses = check_finished(root, model)
    zip_path = root / config.zip_path(model)
    size = core.zip_tree(store.base_dir(root, model), config.zip_root(model), zip_path)
    return PackageResult(
        zip_path, size, sum(statuses.values()), statuses, size > SIZE_WARNING_BYTES
    )


def build_manifest(model: str, zip_path: Path) -> LlmSuitesManifest:
    """Every hash recomputed from the zip; never trusts a previous manifest."""
    zip_path = Path(zip_path)
    return LlmSuitesManifest(
        model_key=model,
        suites_zip=FileHash(
            path=config.zip_path(model).as_posix(),
            size=zip_path.stat().st_size,
            sha256=sha256_of_file(zip_path),
        ),
        files=core.manifest_entries(zip_path),
    )


def write_manifest(root: Path, model: str, manifest: LlmSuitesManifest) -> Path:
    path = Path(root) / config.manifest_path(model)
    path.parent.mkdir(parents=True, exist_ok=True)
    files.atomic_write_json(path, manifest)
    return path


def verify(root: Path, model: str, extracted: Path | None = None) -> VerifyResult:
    """Compare the zip of ``model`` (and, if given, the extracted tree) with its manifest."""
    data = json.loads((Path(root) / config.manifest_path(model)).read_text(encoding="utf-8"))
    manifest = LlmSuitesManifest.model_validate(data)
    result = VerifyResult()
    core.check_zip(Path(root) / config.zip_path(model), manifest.suites_zip, manifest.files, result)
    if extracted is not None:
        core.check_extracted(Path(extracted), manifest.files, config.zip_root(model), result)
    return result
