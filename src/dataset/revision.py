"""Revision 2 of the dataset: the statements with the exponents and indices of the original
(constitution 1.8.0; specs/007-dataset-revision, research R2 to R5).

Only versioned inputs are used: the extracted revision 1 (checked against its manifest), the
fidelity report of ``check-statements`` (made from that same dataset), the package of the original
statements and one decision per statement under review (``manifests/statement_decisions/<id>.json``,
written by the authors). The automatic corrections are rebuilt here, in memory, and must pass the
three checks again; a decision may only change what the report found different. Nothing is
written unless everything passes and, file by file, revision 2 differs from revision 1 only in the
``enunciado.md`` of the changed problems. Revision 1 is kept, byte for byte, as an audit copy.
"""

import difflib
import hashlib
import os
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from dataset import config
from dataset.integrity import manifest as manifest_module
from dataset.integrity import packaging
from dataset.integrity import verify as verify_module
from dataset.persistence import store
from dataset.schemas.manifest import Manifest, RevisedManifest, RevisionOf, parse_manifest
from dataset.schemas.revision import (
    ChangedStatement,
    DatasetRevision,
    KeptStatement,
    StatementDecision,
    SuggestedDifference,
)
from dataset.schemas.statements import FidelityReport, ProblemFidelity
from dataset.statements import fetch
from dataset.statements.correct import CORRECTABLE, checks, corrected_text

AUTOMATIC_KINDS = {"lost_exponent", "lost_index"}
_MARKUP_ONLY = set("^_{}")
_NEAR = 16  # unchanged characters between two reported differences that still join them
SCENARIOS_WITH_STATEMENT = ("black_box", "hybrid")


class RevisionRefused(Exception):
    """An input or a check does not allow revision 2: nothing was written (exit code 1)."""


def _sha(data: bytes | str) -> str:
    raw = data.encode("utf-8") if isinstance(data, str) else data
    return hashlib.sha256(raw).hexdigest()


def _enunciado_path(root: Path, problem_id: str) -> Path:
    return Path(root) / config.EXTRACTED_PROBLEMS_DIR / problem_id / "enunciado.md"


def _read_enunciado(root: Path, problem_id: str) -> str:
    return _enunciado_path(root, problem_id).read_text(encoding="utf-8")


def decision_path(root: Path, problem_id: str) -> Path:
    return Path(root) / config.STATEMENT_DECISIONS_DIR / f"{problem_id}.json"


# ------------------------------------------------------------------------------------- inputs


@dataclass
class Inputs:
    manifest: Manifest
    manifest_sha256: str
    report: FidelityReport
    report_sha256: str
    originals_sha256: str
    blocks: dict[str, str]


def load_inputs(root: Path) -> Inputs:
    """Revision 1 extracted and intact, and the report and originals made from it (R2)."""
    root = Path(root)
    if (root / config.REVISION1_ZIP).exists() or (root / config.REVISION1_MANIFEST).exists():
        raise RevisionRefused("revision 2 already exists (data/dataset.rev1.zip is there)")
    manifest_file = root / config.MANIFEST_PATH
    raw = manifest_file.read_bytes()
    manifest = parse_manifest(raw)
    if isinstance(manifest, RevisedManifest):
        raise RevisionRefused("the dataset is already a revision; revision 2 already exists")
    result = verify_module.verify(
        root / config.DATASET_ZIP, manifest_file, extracted_dir=root / config.DATA_DIR / "dataset"
    )
    if not result.ok:
        raise RevisionRefused(
            "data/dataset does not match manifests/dataset.manifest.json; restore it with: "
            "rm -rf data/dataset && unzip data/dataset.zip -d data/"
        )
    report_file = root / config.STATEMENT_FIDELITY_REPORT
    if not report_file.is_file():
        raise RevisionRefused("no manifests/statement_fidelity_report.json: run check-statements")
    report_raw = report_file.read_bytes()
    report = FidelityReport.model_validate_json(report_raw)
    if report.dataset_manifest_sha256 != _sha(raw):
        raise RevisionRefused(
            "the fidelity report was made from another dataset; run check-statements"
        )
    originals = fetch.read_manifest(root)
    if originals is None:
        raise RevisionRefused("no manifests/statement_originals.manifest.json")
    originals_raw = fetch.manifest_path(root).read_bytes()
    if report.originals_manifest_sha256 != _sha(originals_raw):
        raise RevisionRefused(
            "the fidelity report was made from other originals; run check-statements"
        )
    try:
        fetch.verify_originals(root, originals)
    except fetch.OriginalMismatch as exc:
        raise RevisionRefused(str(exc)) from None
    return Inputs(
        manifest=manifest,
        manifest_sha256=_sha(raw),
        report=report,
        report_sha256=_sha(report_raw),
        originals_sha256=_sha(originals_raw),
        blocks=fetch.read_statement_blocks(root, originals),
    )


def automatic_problems(report: FidelityReport) -> list[ProblemFidelity]:
    """Problems with losses that ``correct-statements`` corrects alone (marks or tables only)."""
    return [
        p
        for p in report.problems
        if p.status == "losses" and {d.kind for d in p.differences} <= CORRECTABLE
    ]


def review_problems(report: FidelityReport) -> list[ProblemFidelity]:
    """Problems the authors decide by hand: any other difference, or unchecked."""
    auto = {p.problem_id for p in automatic_problems(report)}
    return [p for p in report.problems if p.status != "faithful" and p.problem_id not in auto]


# ---------------------------------------------------------------------------------- decisions


def _lost_only(fidelity: ProblemFidelity) -> ProblemFidelity:
    kept = [d for d in fidelity.differences if d.kind in AUTOMATIC_KINDS]
    return fidelity.model_copy(update={"differences": kept})


def draft_decisions(root: Path, report: FidelityReport) -> list[Path]:
    """A draft for each problem under review without a decision file; never overwrites one."""
    written = []
    folder = Path(root) / config.STATEMENT_DECISIONS_DIR
    for fidelity in review_problems(report):
        path = decision_path(root, fidelity.problem_id)
        if path.exists():
            continue
        enunciado = _read_enunciado(root, fidelity.problem_id)
        lost = _lost_only(fidelity)
        suggested = corrected_text(enunciado, lost)[0] if lost.differences else None
        draft = StatementDecision(
            problem_id=fidelity.problem_id,
            decision=None,
            enunciado=None,
            reason="",
            reviewed_by="",
            reviewed_at="",
            sha256_before=_sha(enunciado),
            differences=[
                SuggestedDifference(
                    kind=d.kind, original=d.original, ours=d.ours, context=d.context
                )
                for d in fidelity.differences
            ],
            suggested_enunciado=suggested,
        )
        folder.mkdir(parents=True, exist_ok=True)
        store.atomic_write_json(path, draft)
        written.append(path)
    return written


def check_decision(enunciado: str, decision: StatementDecision, fidelity: ProblemFidelity) -> None:
    """``RevisionRefused`` unless the decision is about this text and changes only what the
    report found different (or only inserts marks)."""
    pid = decision.problem_id
    if decision.sha256_before != _sha(enunciado):
        raise RevisionRefused(f"{pid}: sha256_before is not the enunciado.md of revision 1")
    if decision.decision == "keep":
        return
    # Differences at most _NEAR characters apart are one stretch: a rewritten sentence is reported
    # as many small differences around letters that match by chance, and a decision aligned on its
    # own may change those letters too (670_D2).
    spans: list[tuple[int, int]] = []
    for s, e in sorted(
        (d.ours_offset, d.ours_offset + d.ours_length) for d in fidelity.differences
    ):
        if spans and s - spans[-1][1] <= _NEAR:
            spans[-1] = (spans[-1][0], max(e, spans[-1][1]))
        else:
            spans.append((s, e))

    def covered(i1: int, i2: int) -> bool:
        """Whether the stretch [i1, i2) of the current text touches a reported difference."""
        for s, e in spans:
            if i1 < e and s < i2:  # the stretches overlap
                return True
            if (i1 == i2 and s <= i1 <= e) or (s == e and i1 <= s <= i2):  # an insertion point
                return True
        return False

    matcher = difflib.SequenceMatcher(None, enunciado, decision.enunciado, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        if tag == "insert" and set(decision.enunciado[j1:j2]) <= _MARKUP_ONLY:
            continue
        if not covered(i1, i2):
            snippet = enunciado[max(0, i1 - 15) : i2 + 15].replace("\n", " ")
            raise RevisionRefused(
                f"{pid}: the decision changes text the report did not find different: "
                f"{snippet!r} -> {decision.enunciado[max(0, j1 - 15) : j2 + 15]!r}"
            )


def load_decisions(root: Path, report: FidelityReport) -> dict[str, StatementDecision]:
    """The decision of every problem under review, each checked; ``RevisionRefused`` otherwise."""
    review = {p.problem_id: p for p in review_problems(report)}
    folder = Path(root) / config.STATEMENT_DECISIONS_DIR
    found = {p.stem: p for p in folder.glob("*.json")} if folder.is_dir() else {}
    stray = sorted(set(found) - set(review))
    if stray:
        raise RevisionRefused(f"decisions for problems not under review: {', '.join(stray)}")
    decisions, missing = {}, []
    for pid, fidelity in review.items():
        if pid not in found:
            missing.append(pid)
            continue
        decision = StatementDecision.model_validate_json(found[pid].read_bytes())
        if decision.problem_id != pid:
            raise RevisionRefused(f"{found[pid].name}: it is about {decision.problem_id}")
        if decision.is_draft:
            missing.append(pid)
            continue
        check_decision(_read_enunciado(root, pid), decision, fidelity)
        decisions[pid] = decision
    if missing:
        raise RevisionRefused(
            f"no decision yet for {len(missing)} problem(s) under review: {', '.join(missing)} "
            "(run revise --draft-decisions and fill them in)"
        )
    return decisions


# ----------------------------------------------------------------------------------- revision


@dataclass
class RevisionResult:
    record: DatasetRevision
    manifest: RevisedManifest
    changed_ids: list[str]
    written: bool


def _new_statements(root: Path, inputs: Inputs, decisions: dict[str, StatementDecision]):
    """``problem_id -> (new text, ChangedStatement)`` and the kept ones (R5)."""
    changed, kept = {}, []
    for fidelity in automatic_problems(inputs.report):
        pid = fidelity.problem_id
        enunciado = _read_enunciado(root, pid)
        text, _ = corrected_text(enunciado, fidelity)
        result = checks(inputs.blocks[pid], enunciado, text, fidelity)
        if not result.passed:
            failed = [n for n, ok in result.model_dump().items() if not ok]
            raise RevisionRefused(f"{pid}: the automatic correction fails {', '.join(failed)}")
        markups: dict[str, int] = {}
        for d in fidelity.differences:
            markups[d.kind] = markups.get(d.kind, 0) + 1
        changed[pid] = (
            text,
            ChangedStatement(
                problem_id=pid,
                origin="automatic",
                markups=markups,
                sha256_before=_sha(enunciado),
                sha256_after=_sha(text),
            ),
        )
    for pid, decision in sorted(decisions.items()):
        if decision.decision == "keep":
            kept.append(KeptStatement(problem_id=pid, reason=decision.reason))
            continue
        changed[pid] = (
            decision.enunciado,
            ChangedStatement(
                problem_id=pid,
                origin="manual",
                reason=decision.reason,
                sha256_before=decision.sha256_before,
                sha256_after=_sha(decision.enunciado),
            ),
        )
    return changed, kept


def build_revision(root: Path, *, dry_run: bool = False, now: str | None = None) -> RevisionResult:
    root = Path(root)
    inputs = load_inputs(root)
    decisions = load_decisions(root, inputs.report)
    changed, kept = _new_statements(root, inputs, decisions)
    work = root / config.REVISION_WORK_DIR
    if work.exists():
        shutil.rmtree(work)
    for level in (root / config.WORK_DIR, work):
        store.make_private_dir(level)
    problems = work / "problems"
    shutil.copytree(root / config.EXTRACTED_PROBLEMS_DIR, problems)
    for pid, (text, _) in changed.items():
        (problems / pid / "enunciado.md").write_bytes(text.encode("utf-8"))
    try:
        new_zip = work / "dataset.zip"
        packaging.build_dataset_zip(root, new_zip, problems.relative_to(root))
        built = manifest_module.build_manifest(root, new_zip, provenance=inputs.manifest.provenance)
        # FR-002: file by file, only the enunciado.md of the changed problems differ.
        before = {f.path: f.sha256 for f in inputs.manifest.files}
        after = {f.path: f.sha256 for f in built.files}
        expected = {f"dataset/problems/{pid}/enunciado.md" for pid in changed}
        differing = {p for p in before.keys() | after.keys() if before.get(p) != after.get(p)}
        if differing != expected:
            extra = sorted(differing - expected)[:5]
            missing = sorted(expected - differing)[:5]
            raise RevisionRefused(
                f"revision 2 would differ from revision 1 in other files {extra} or not in {missing}"
            )
        record = DatasetRevision(
            revision=2,
            previous_manifest_sha256=inputs.manifest_sha256,
            changed=[changed[pid][1] for pid in sorted(changed)],
            kept=kept,
        )
        record_text = store.dumps_json(record)
        manifest = RevisedManifest(
            **built.model_dump(exclude={"schema_version"}),
            revision=2,
            revision_of=RevisionOf(
                previous_manifest_sha256=inputs.manifest_sha256,
                fidelity_report_sha256=inputs.report_sha256,
                originals_manifest_sha256=inputs.originals_sha256,
                revision_record_sha256=_sha(record_text),
                created_at=now or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            ),
        )
        if not dry_run:
            # Revision 1 kept byte for byte, then revision 2 in place.
            os.replace(root / config.DATASET_ZIP, root / config.REVISION1_ZIP)
            os.replace(root / config.MANIFEST_PATH, root / config.REVISION1_MANIFEST)
            os.replace(new_zip, root / config.DATASET_ZIP)
            store.atomic_write_json(root / config.MANIFEST_PATH, manifest)
            store.atomic_write_text(root / config.REVISION_RECORD, record_text)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return RevisionResult(record, manifest, sorted(changed), not dry_run)
