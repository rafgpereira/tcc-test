"""The package of the final run: ``data/slm_suites.zip``, its manifest, and their verification.

Same conventions as the zips of the dataset and of the mutants (``dataset.integrity.packaging``):
entries sorted by path, a fixed modification time, fixed Unix permissions, ``deflate`` at a fixed
level, so the same tree gives the same zip bytes. The root inside the zip is ``suites/slm/``, so
``unzip data/slm_suites.zip -d data/`` lands exactly on ``data/suites/slm/``, where the commands
read. Every file of every combination goes in, and ``run.json`` (the provenance of the run), with
the template changes and the attempts they moved aside (``template_changes/`` and ``superseded/``,
research R27); the locks and the leftovers of an interrupted atomic write never do.

A package is only worth versioning if it is exactly what a whole run produced, so it is refused
while any problem × scenario of the dataset has no ``suite.json``, or if anything is damaged.
"""

import json
import os
import zipfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from ai_clients import config, store, template_change
from ai_clients.problem import list_problem_ids
from ai_clients.report import DamagedTreeError
from ai_clients.schemas.common import SuiteStatus
from ai_clients.schemas.manifest import FileHash, SlmSuitesManifest
from ai_clients.schemas.provenance import CombinationOrigin, SlmProvenance
from dataset.integrity.packaging import (
    COMPRESS_LEVEL,
    DIR_MODE,
    FILE_MODE,
    FIXED_DATE_TIME,
    SIZE_WARNING_BYTES,
)
from dataset.persistence import store as files
from mutation.integrity import VerifyResult
from mutation.manifest import sha256_of_bytes, sha256_of_file

# The statuses of the SLM: accepted_barred belongs to the commercial models only.
SLM_STATUSES = tuple(s for s in SuiteStatus if s is not SuiteStatus.ACCEPTED_BARRED)


class UnfinishedRunError(Exception):
    """Some combinations of the dataset have no ``suite.json`` yet, or the tree has extra entries."""


@dataclass(frozen=True)
class PackageResult:
    zip_path: Path
    size: int
    combinations: int
    statuses: dict[str, int]  # suite status -> combinations, every status present
    over_size_warning: bool


def _ignored(name: str) -> bool:
    """``.lock`` and the temporary files of atomic writes: local, never part of a run."""
    return name.startswith(".")


def check_finished(root: Path) -> dict[str, int]:
    """Suite status -> combinations of a finished run; refuses an unfinished or damaged one."""
    root = Path(root)
    run = store.read_run(root)
    problems = list_problem_ids(root)
    unfinished, awaiting, damaged = [], [], []
    statuses: Counter = Counter()
    for problem_id in problems:
        for scenario in config.SCENARIOS:
            try:
                state = store.combination_state(root, problem_id, scenario, run)
            except store.DamagedCombination as exc:
                damaged.append(exc)
                continue
            if state.kind == "awaiting_manual":
                awaiting.append(f"{problem_id} {scenario}")
            if state.kind != "terminal":
                unfinished.append(f"{problem_id} {scenario}")
            else:
                statuses[store.read_suite(root, problem_id, scenario).status.value] += 1
    if damaged:
        raise DamagedTreeError(damaged)
    total = len(problems) * len(config.SCENARIOS)
    if unfinished:
        shown = ", ".join(unfinished[:5]) + (", ..." if len(unfinished) > 5 else "")
        message = (
            f"{len(unfinished)} of {total} combinations have no suite.json ({shown}); finish the "
            "run (generate --resume and execute) before packaging"
        )
        if awaiting:
            message += (
                f"; {len(awaiting)} await manual handling ({', '.join(awaiting)}): close each "
                'with python -m ai_clients close --problem ID --scenario S --reason "..."'
            )
        raise UnfinishedRunError(message)
    extra = []
    for folder in sorted((root / config.PROBLEMS_DIR).iterdir()):
        if _ignored(folder.name):
            continue
        if folder.name not in problems or not folder.is_dir():
            extra.append(folder.name)
            continue
        for entry in sorted(folder.iterdir()):
            if not _ignored(entry.name) and entry.name not in config.SCENARIOS:
                extra.append(f"{folder.name}/{entry.name}")
    if extra:
        raise UnfinishedRunError(
            f"data/suites/slm/problems has entries that are not a problem × scenario of the "
            f"dataset: {', '.join(extra[:5])}"
        )
    superseded = template_change.superseded_problems(root, store.template_changes(root))
    if superseded:
        raise UnfinishedRunError(
            f"the template changes and data/suites/slm/{config.SUPERSEDED_DIR} disagree: "
            + "; ".join(superseded[:5])
        )
    return {status.value: statuses[status.value] for status in SLM_STATUSES}


def _dir_info(path: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(path, FIXED_DATE_TIME)
    info.external_attr = (0o40000 | DIR_MODE) << 16 | 0x10  # S_IFDIR + mode, MS-DOS dir bit
    info.compress_type = zipfile.ZIP_STORED
    return info


def _file_info(path: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(path, FIXED_DATE_TIME)
    info.external_attr = (0o100000 | FILE_MODE) << 16  # S_IFREG + mode
    info.compress_type = zipfile.ZIP_DEFLATED
    return info


def _tree(base: Path) -> list[Path]:
    """Every directory and file under ``base``, without the ignored names, sorted by path."""
    found = []
    for path in sorted(base.rglob("*")):
        if any(_ignored(part) for part in path.relative_to(base).parts):
            continue
        found.append(path)
    return found


def zip_tree(base: Path, zip_root: str, zip_path: Path) -> int:
    """Zip every entry of ``base`` under ``zip_root/``, deterministically and atomically (temporary
    file + ``os.replace``); the size of the zip. The core of every suites package (SLM and the
    commercial models)."""
    base, zip_path = Path(base), Path(zip_path)
    entries: list[tuple[str, Path | None]] = [(f"{zip_root}/", None)]
    for path in _tree(base):
        name = f"{zip_root}/{path.relative_to(base).as_posix()}"
        entries.append((f"{name}/", None) if path.is_dir() else (name, path))
    entries.sort(key=lambda entry: entry[0])
    tmp_path = zip_path.with_name(f".{zip_path.name}.tmp")
    try:
        with zipfile.ZipFile(tmp_path, "w") as archive:
            for entry_path, source in entries:
                if source is None:
                    archive.writestr(_dir_info(entry_path), b"")
                else:
                    archive.writestr(
                        _file_info(entry_path), source.read_bytes(), compresslevel=COMPRESS_LEVEL
                    )
        os.replace(tmp_path, zip_path)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise
    return zip_path.stat().st_size


def build_zip(root: Path, zip_path: Path) -> PackageResult:
    """Build the zip atomically (temporary file + ``os.replace``) from a finished run."""
    root, zip_path = Path(root), Path(zip_path)
    statuses = check_finished(root)
    size = zip_tree(root / config.SUITES_DIR, config.ZIP_ROOT, zip_path)
    return PackageResult(
        zip_path, size, sum(statuses.values()), statuses, size > SIZE_WARNING_BYTES
    )


def manifest_entries(zip_path: Path) -> list[FileHash]:
    """The hash and size of every file member of ``zip_path``, sorted by path."""
    entries = []
    with zipfile.ZipFile(zip_path) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            data = archive.read(info.filename)
            entries.append(
                FileHash(path=info.filename, size=len(data), sha256=sha256_of_bytes(data))
            )
    entries.sort(key=lambda item: item.path)
    return entries


def build_manifest(zip_path: Path) -> SlmSuitesManifest:
    """Recompute every hash straight from ``zip_path``; never trusts a previous manifest."""
    zip_path = Path(zip_path)
    entries = manifest_entries(zip_path)
    return SlmSuitesManifest(
        slm_suites_zip=FileHash(
            path=config.ZIP_PATH.as_posix(),
            size=zip_path.stat().st_size,
            sha256=sha256_of_file(zip_path),
        ),
        files=entries,
    )


def write_manifest(root: Path, manifest: SlmSuitesManifest) -> Path:
    path = Path(root) / config.MANIFEST_PATH
    path.parent.mkdir(parents=True, exist_ok=True)  # `manifests/` is versioned, ordinary mode
    files.atomic_write_json(path, manifest)
    return path


def _check_zip(zip_path: Path, manifest: SlmSuitesManifest, result: VerifyResult) -> None:
    check_zip(zip_path, manifest.slm_suites_zip, manifest.files, result)


def check_zip(zip_path: Path, entry: FileHash, files: list[FileHash], result: VerifyResult) -> None:
    """Compare the zip with its manifest entry and every member with the manifest files."""
    if not zip_path.is_file():
        result.missing.append(entry.path)
        return
    if zip_path.stat().st_size != entry.size or sha256_of_file(zip_path) != entry.sha256:
        result.changed.append(entry.path)
        return
    # The zip is the one the manifest describes; its members are checked too, so a manifest that
    # was edited (not the zip) is caught as well.
    with zipfile.ZipFile(zip_path) as archive:
        inside = {i.filename: i for i in archive.infolist() if not i.is_dir()}
        for item in files:
            member = inside.get(item.path)
            if member is None:
                result.missing.append(item.path)
            elif (
                member.file_size != item.size
                or sha256_of_bytes(archive.read(member)) != item.sha256
            ):
                result.changed.append(item.path)
        result.extra.extend(sorted(set(inside) - {item.path for item in files}))


def _check_extracted(extracted: Path, manifest: SlmSuitesManifest, result: VerifyResult) -> None:
    check_extracted(extracted, manifest.files, config.ZIP_ROOT, result)


def check_extracted(
    extracted: Path, files: list[FileHash], zip_root: str, result: VerifyResult
) -> None:
    """Compare the extracted tree (``data/suites/<x>``) with the manifest files, file by file."""
    prefix = f"{zip_root}/"
    expected = {item.path.removeprefix(prefix): item for item in files}
    for rel, item in expected.items():
        path = extracted / rel
        if not path.is_file():
            result.missing.append(item.path)
        elif path.stat().st_size != item.size or sha256_of_file(path) != item.sha256:
            result.changed.append(item.path)
    if extracted.is_dir():
        for path in _tree(extracted):
            rel = path.relative_to(extracted).as_posix()
            if path.is_file() and rel not in expected:
                result.extra.append(f"{prefix}{rel}")


def verify(zip_path: Path, manifest_path: Path, extracted: Path | None = None) -> VerifyResult:
    """Compare the zip (and, if given, the extracted tree) with the manifest, file by file."""
    data = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    manifest = SlmSuitesManifest.model_validate(data)
    result = VerifyResult()
    _check_zip(Path(zip_path), manifest, result)
    if extracted is not None:
        _check_extracted(Path(extracted), manifest, result)
    return result


# ------------------------------------------------- merged package (revision 2 of the dataset)

PROVENANCE_FILE = "provenance.json"
REVISED_SCENARIOS = ("black_box", "hybrid")  # the scenarios that show the statement


def _dataset_revision_of(root: Path, manifest_sha256: str) -> int:
    """1 or 2: the revision whose manifest has this hash (the current one or the kept one)."""
    from dataset import config as dataset_config
    from dataset.schemas.manifest import RevisedManifest, parse_manifest

    current = Path(root) / dataset_config.MANIFEST_PATH
    kept = Path(root) / dataset_config.REVISION1_MANIFEST
    for path in (current, kept):
        if path.is_file() and sha256_of_file(path) == manifest_sha256:
            manifest = parse_manifest(path.read_bytes())
            return manifest.revision if isinstance(manifest, RevisedManifest) else 1
    raise UnfinishedRunError(
        f"the run was made with a dataset manifest ({manifest_sha256[:12]}…) that is neither the "
        "current one nor the kept revision 1"
    )


def affected_combinations(root: Path) -> set[tuple[str, str]]:
    """The black_box and hybrid of every problem whose statement revision 2 changed."""
    from dataset import config as dataset_config
    from dataset.schemas.revision import DatasetRevision

    path = Path(root) / dataset_config.REVISION_RECORD
    if not path.is_file():
        raise UnfinishedRunError(
            f"{dataset_config.REVISION_RECORD.as_posix()} does not exist: there is no dataset "
            "revision to merge for (run python -m dataset revise first)"
        )
    record = DatasetRevision.model_validate_json(path.read_bytes())
    return {(c.problem_id, s) for c in record.changed for s in REVISED_SCENARIOS}


def check_merge(root: Path, previous: Path) -> tuple[SlmProvenance, dict[str, int]]:
    """The provenance of the merged package; refuses a missing, extra or damaged combination.

    The new run (data/suites/slm, the current revision) must have a suite for every affected
    combination and nothing else; the previous run (``previous``, checked with the same rules of
    the store, without asking its run.json to be of the current dataset) must have a suite for
    every combination.
    """
    root, previous = Path(root), Path(previous)
    affected = affected_combinations(root)
    problems = list_problem_ids(root)
    run, old_run = store.read_run(root), store.read_run(root, previous)
    new_revision = _dataset_revision_of(root, run.dataset_manifest_sha256)
    old_revision = _dataset_revision_of(root, old_run.dataset_manifest_sha256)
    damaged, missing, extra = [], [], []
    statuses: Counter = Counter()
    combinations = []
    new_tree, old_tree = config.ZIP_ROOT, f"suites/{previous.name}"
    for problem_id in problems:
        for scenario in config.SCENARIOS:
            redone = (problem_id, scenario) in affected
            try:
                old_state = store.combination_state(
                    root, problem_id, scenario, old_run, tree=previous
                )
                new_dir = store.combination_dir(root, problem_id, scenario)
                new_state = (
                    store.combination_state(root, problem_id, scenario, run)
                    if new_dir.is_dir()
                    else None
                )
            except store.DamagedCombination as exc:
                damaged.append(exc)
                continue
            if old_state.kind != "terminal":
                missing.append(f"{previous.as_posix()} {problem_id} {scenario}")
            if redone and (new_state is None or new_state.kind != "terminal"):
                missing.append(f"data/suites/slm {problem_id} {scenario}")
            if not redone and new_state is not None:
                extra.append(f"{problem_id} {scenario}")
            tree = new_tree if redone else old_tree
            in_force_root = None if redone else previous
            suite = store.read_suite(root, problem_id, scenario, in_force_root)
            if suite is not None:
                statuses[suite.status.value] += 1
            combinations.append(
                CombinationOrigin(
                    problem_id=problem_id,
                    scenario=scenario,
                    tree=tree,
                    dataset_manifest_sha256=(run if redone else old_run).dataset_manifest_sha256,
                    dataset_revision=new_revision if redone else old_revision,
                )
            )
            if redone:
                combinations.append(
                    CombinationOrigin(
                        problem_id=problem_id,
                        scenario=scenario,
                        tree=old_tree,
                        dataset_manifest_sha256=old_run.dataset_manifest_sha256,
                        dataset_revision=old_revision,
                        superseded_in=new_tree,
                    )
                )
    if damaged:
        raise DamagedTreeError(damaged)
    if missing or extra:
        parts = []
        if missing:
            parts.append(f"{len(missing)} without suite.json ({', '.join(missing[:5])})")
        if extra:
            parts.append(
                f"{len(extra)} in the new run that revision 2 did not affect ({', '.join(extra[:5])})"
            )
        raise UnfinishedRunError("cannot merge: " + "; ".join(parts))
    provenance = SlmProvenance(combinations=combinations)
    return provenance, {status.value: statuses[status.value] for status in SLM_STATUSES}


def zip_trees(trees: list[tuple[Path, str]], zip_path: Path) -> int:
    """``zip_tree`` over several trees, each under its own root inside one zip."""
    zip_path = Path(zip_path)
    entries: list[tuple[str, Path | None]] = []
    for base, zip_root in trees:
        entries.append((f"{zip_root}/", None))
        for path in _tree(Path(base)):
            name = f"{zip_root}/{path.relative_to(base).as_posix()}"
            entries.append((f"{name}/", None) if path.is_dir() else (name, path))
    entries.sort(key=lambda entry: entry[0])
    tmp_path = zip_path.with_name(f".{zip_path.name}.tmp")
    try:
        with zipfile.ZipFile(tmp_path, "w") as archive:
            for entry_path, source in entries:
                if source is None:
                    archive.writestr(_dir_info(entry_path), b"")
                else:
                    archive.writestr(
                        _file_info(entry_path), source.read_bytes(), compresslevel=COMPRESS_LEVEL
                    )
        os.replace(tmp_path, zip_path)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise
    return zip_path.stat().st_size


def build_merged_zip(root: Path, previous: Path, zip_path: Path) -> PackageResult:
    """The package of revision 2: the new run, the previous run and ``provenance.json``."""
    root, previous = Path(root), Path(previous)
    provenance, statuses = check_merge(root, previous)
    files.atomic_write_json(root / config.SUITES_DIR / PROVENANCE_FILE, provenance)
    size = zip_trees(
        [(root / config.SUITES_DIR, config.ZIP_ROOT), (root / previous, f"suites/{previous.name}")],
        zip_path,
    )
    in_force = len(provenance.in_force())
    return PackageResult(zip_path, size, in_force, statuses, size > SIZE_WARNING_BYTES)
