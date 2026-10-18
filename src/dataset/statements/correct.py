"""The corrected statements: the current ``enunciado.md`` with the marks of the original inserted
(research R5, decision S2), accepted only after three checks (FR-008).

For each ``lost_exponent``/``lost_index`` difference, ``^{``/``_{`` and ``}`` go around the content
at the position the comparison found; a table difference has the flattened stretch replaced by
the Markdown table. Anything else (an image, an unknown formula, an ``other`` difference) sends the
problem to manual review. The three checks:

(a) ``text_equal``: without the inserted marks, the corrected text is the current one, and the
    current one (without the examples) is the original flattened, spaces aside;
(b) ``all_marks_present``: comparing the corrected text with the original again leaves no lost
    exponent or index;
(c) ``only_markup_diff``: every change from the current text is an inserted mark (or a table).

The dataset is never written: the corrected files go to the folder asked for.
"""

import difflib
import hashlib
import re
import shutil
from pathlib import Path

from dataset import config
from dataset.persistence import store
from dataset.schemas.statements import (
    CorrectedStatement,
    CorrectionChecks,
    CorrectionSummary,
    FidelityReport,
    ProblemFidelity,
    ReviewEntry,
)
from dataset.statements import UsageError
from dataset.statements import render as rendering
from dataset.statements.compare import compare, cut_examples
from dataset.statements.extract import extract_statement

CORRECTABLE = {"lost_exponent", "lost_index", "table"}
FORBIDDEN = (Path("data/dataset"), Path("data/suites"), Path("manifests"))
_MARKUP_ONLY = re.compile(r"^[\^_{}]+$")


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def corrected_text(enunciado: str, fidelity: ProblemFidelity) -> tuple[str, list[tuple[int, int]]]:
    """The text with the marks inserted, and the inserted stretches (start, end) in it."""
    edits = []  # (offset, length, replacement)
    for d in fidelity.differences:
        if d.kind in ("lost_exponent", "lost_index"):
            opener = "^{" if d.kind == "lost_exponent" else "_{"
            content = enunciado[d.ours_offset : d.ours_offset + d.ours_length]
            edits.append((d.ours_offset, d.ours_length, f"{opener}{content}}}"))
        elif d.kind == "table":
            edits.append((d.ours_offset, d.ours_length, d.original))
    text, inserted, shift = enunciado, [], 0
    for offset, length, replacement in sorted(edits):
        start = offset + shift
        text = text[:start] + replacement + text[start + length :]
        inserted.append((start, start + len(replacement)))
        shift += len(replacement) - length
    return text, inserted


def checks(
    block: str, enunciado: str, corrected: str, fidelity: ProblemFidelity
) -> CorrectionChecks:
    nodes = extract_statement(block)
    rendered = rendering.render(nodes)
    has_table = any(d.kind == "table" for d in fidelity.differences)
    # (a) the current text is the original flattened, and the correction only adds marks to it
    kept, _ = cut_examples(enunciado)
    flat_equal = rendering.normalize_space(kept) == rendering.normalize_space(rendered.flat)
    unmarked = re.sub(r"[\^_]\{([^{}]*)\}", r"\1", corrected) if not has_table else None
    original_unmarked = re.sub(r"[\^_]\{([^{}]*)\}", r"\1", enunciado)
    text_equal = flat_equal and (has_table or unmarked == original_unmarked)
    # (b) nothing is lost any more
    again = compare(nodes, corrected, fidelity.problem_id)
    all_marks = not any(d.kind in ("lost_exponent", "lost_index") for d in again.differences)
    # (c) only marks (and tables) changed
    only_markup = True
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(
        None, enunciado, corrected, autojunk=False
    ).get_opcodes():
        if tag == "equal":
            continue
        if tag == "insert" and _MARKUP_ONLY.match(corrected[j1:j2]):
            continue
        if has_table:
            continue  # a table rewrites a stretch: checked by (a) on the flattened text
        only_markup = False
    return CorrectionChecks(
        text_equal=text_equal, all_marks_present=all_marks, only_markup_diff=only_markup
    )


def check_destination(root: Path, out_dir: Path, *, force: bool) -> None:
    target = (Path(root) / out_dir).resolve()
    for folder in FORBIDDEN:
        base = (Path(root) / folder).resolve()
        if target == base or base in target.parents or target in base.parents:
            raise UsageError(
                f"{Path(out_dir).as_posix()} is inside (or contains) {folder.as_posix()}/"
            )
    if target.exists() and not target.is_dir():
        raise UsageError(f"{Path(out_dir).as_posix()} is a file, not a folder")
    if target.is_dir() and any(target.iterdir()) and not force:
        raise UsageError(
            f"{Path(out_dir).as_posix()} already has files; use --force to replace them"
        )


def correct_all(
    root: Path,
    report: FidelityReport,
    report_sha256: str,
    blocks: dict[str, str],
    out_dir: Path,
    *,
    force: bool,
) -> CorrectionSummary:
    check_destination(root, out_dir, force=force)
    target = Path(root) / out_dir
    if target.is_dir():
        shutil.rmtree(target)
    store.make_private_dir(target)
    corrected, unchanged, review = [], [], []
    for fidelity in report.problems:
        pid = fidelity.problem_id
        if fidelity.status == "faithful":
            unchanged.append(pid)
            continue
        if fidelity.status == "unchecked":
            review.append(
                ReviewEntry(problem_id=pid, reasons=[f"unchecked: {fidelity.unchecked_reason}"])
            )
            continue
        blocked = sorted({d.kind for d in fidelity.differences} - CORRECTABLE)
        if blocked:
            review.append(ReviewEntry(problem_id=pid, reasons=blocked))
            continue
        path = Path(root) / config.EXTRACTED_PROBLEMS_DIR / pid / "enunciado.md"
        enunciado = path.read_text(encoding="utf-8")
        text, _ = corrected_text(enunciado, fidelity)
        result = checks(blocks[pid], enunciado, text, fidelity)
        if not result.passed:
            failed = [n for n, ok in result.model_dump().items() if not ok]
            review.append(
                ReviewEntry(problem_id=pid, reasons=[f"check failed: {f}" for f in failed])
            )
            continue
        store.atomic_write_text(target / f"{pid}.md", text)
        counts: dict[str, int] = {}
        for d in fidelity.differences:
            counts[d.kind] = counts.get(d.kind, 0) + 1
        corrected.append(
            CorrectedStatement(
                problem_id=pid,
                file=f"{pid}.md",
                markups_inserted=counts,
                checks=result,
                sha256_before=_sha(enunciado),
                sha256_after=_sha(text),
            )
        )
    summary = CorrectionSummary(
        report_sha256=report_sha256, corrected=corrected, unchanged=unchanged, review=review
    )
    store.atomic_write_json(target / "summary.json", summary)
    return summary
