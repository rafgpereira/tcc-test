"""The original statement aligned with ``enunciado.md``; every difference classified (research R3).

There is no list of patterns. The marked text of the original and our text (without the examples)
are compared character by character after both have their spaces normalized; each stretch that is
not equal becomes a difference, and its kind is the kind of the element of the original under it:
a ``sup`` → ``lost_exponent`` (when its content is in our text without the mark), a ``sub`` →
``lost_index``, a formula → ``formula``, an image → ``image``, a table → ``table``, anything else
(or text only on our side) → ``other``.
"""

import difflib
import re
from pathlib import Path

from dataset.schemas.statements import (
    KINDS,
    Difference,
    FidelityReport,
    FidelityTotals,
    OriginalsManifest,
    ProblemFidelity,
)
from dataset.statements import render as rendering
from dataset.statements.extract import Node, NoStatementBlock, extract_statement

_EXAMPLES = re.compile(r"^Examples?\s*$")
_NOTE = re.compile(r"^Note\s*$")
_CONTEXT = 15


def cut_examples(text: str) -> tuple[str, list[int]]:
    """``text`` without the block of examples (from the line ``Examples`` up to the line ``Note``
    or the end), and for each kept character its index in ``text``."""
    lines = text.splitlines(keepends=True)
    offsets, at = [], 0
    for line in lines:
        offsets.append(at)
        at += len(line)
    start = next((i for i, line in enumerate(lines) if _EXAMPLES.match(line)), None)
    if start is None:
        return text, list(range(len(text)))
    end = next((i for i in range(start + 1, len(lines)) if _NOTE.match(lines[i])), len(lines))
    cut_from = offsets[start]
    cut_to = offsets[end] if end < len(lines) else len(text)
    kept = text[:cut_from] + text[cut_to:]
    where = list(range(cut_from)) + list(range(cut_to, len(text)))
    return kept, where


def _format(rendered: rendering.Rendered) -> str:
    if rendered.formats == {"marked", "latex"}:
        return "mixed"
    return "latex" if rendered.formats == {"latex"} else "marked"


def _span_at(spans: list[rendering.Span], position: int) -> rendering.Span | None:
    for span in spans:
        if span.start <= position < span.end:
            return span
    return None


_KIND_OF = {"sup": "lost_exponent", "sub": "lost_index", "formula": "formula", "image": "image"}
_PRIORITY = ("image", "table", "formula", "sup", "sub")


def compare(nodes: list[Node], enunciado: str, problem_id: str) -> ProblemFidelity:
    rendered = rendering.render(nodes)
    m_norm, m_map = rendering.normalize_with_map(rendered.marked)
    kept, kept_idx = cut_examples(enunciado)
    o_norm, o_map = rendering.normalize_with_map(kept)

    def ours_offset(j: int) -> int:
        return kept_idx[o_map[j]] if j < len(o_map) else len(enunciado)

    def context(j: int) -> str:
        return o_norm[max(0, j - _CONTEXT) : j + _CONTEXT]

    matcher = difflib.SequenceMatcher(None, m_norm, o_norm, autojunk=False)
    opcodes = matcher.get_opcodes()
    m_to_o: dict[int, int] = {}
    for tag, i1, i2, j1, _ in opcodes:
        if tag == "equal":
            for k in range(i2 - i1):
                m_to_o[i1 + k] = j1 + k
    # The marked position of every normalized character of the original.
    span_of = [_span_at(rendered.spans, m_map[i]) for i in range(len(m_norm))]

    groups: dict[object, dict] = {}
    for tag, i1, i2, j1, j2 in opcodes:
        if tag == "equal":
            continue
        touched = [s for s in span_of[i1:i2] if s is not None]
        kinds = {s.kind for s in touched}
        chosen = next((k for k in _PRIORITY if k in kinds), None)
        if chosen is not None:
            span = next(s for s in touched if s.kind == chosen)
            key = ("node", span.node)
        else:
            span, key = None, ("op", i1, j1)
        group = groups.setdefault(key, {"span": span, "kind": chosen, "ops": []})
        group["ops"].append((i1, i2, j1, j2))

    differences = []
    for group in groups.values():
        span, kind = group["span"], group["kind"]
        i1 = min(o[0] for o in group["ops"])
        j1 = min(o[2] for o in group["ops"])
        j2 = max(o[3] for o in group["ops"])
        if kind in ("sup", "sub"):
            # A lost mark: the content is in our text, only the mark is missing.
            content = [i for i in range(len(m_norm)) if span.mark[0] <= m_map[i] < span.mark[1]]
            if content and all(i in m_to_o for i in content):
                first, last = m_to_o[content[0]], m_to_o[content[-1]]
                start, end = max(0, span.start - 8), span.end
                differences.append(
                    Difference(
                        kind=_KIND_OF[kind],
                        original=rendering.normalize_space(rendered.marked[start:end]),
                        ours=o_norm[max(0, first - 8) : last + 1],
                        context=context(first),
                        ours_offset=ours_offset(first),
                        ours_length=ours_offset(last) + 1 - ours_offset(first),
                    )
                )
                continue
            kind = None  # the content itself differs: not just a lost mark
        final = {"image": "image", "table": "table", "formula": "formula"}.get(kind, "other")
        i2 = max(o[1] for o in group["ops"])
        if span is None:
            original = m_norm[i1:i2]
        elif final == "table":  # the Markdown table, line breaks kept: the correction uses it
            original = rendered.marked[span.start : span.end]
        else:
            original = rendering.normalize_space(rendered.marked[span.start : span.end])
        differences.append(
            Difference(
                kind=final,
                original=original,
                ours=o_norm[j1:j2],
                context=context(j1),
                ours_offset=ours_offset(j1),
                ours_length=(ours_offset(j2 - 1) + 1 - ours_offset(j1)) if j2 > j1 else 0,
            )
        )
    differences.sort(key=lambda d: (d.ours_offset, d.kind))
    return ProblemFidelity(
        problem_id=problem_id,
        format=_format(rendered),
        status="losses" if differences else "faithful",
        differences=differences,
    )


def check_problem(problem_id: str, block: str | None, enunciado: str, reason: str | None):
    """The fidelity of one problem; ``unchecked`` with the reason when there is nothing to compare."""
    if block is None:
        return ProblemFidelity(
            problem_id=problem_id, format=None, status="unchecked", unchecked_reason=reason
        )
    try:
        nodes = extract_statement(block)
    except NoStatementBlock:
        return ProblemFidelity(
            problem_id=problem_id,
            format=None,
            status="unchecked",
            unchecked_reason="no_statement_block",
        )
    return compare(nodes, enunciado, problem_id)


def totals(problems: list[ProblemFidelity]) -> FidelityTotals:
    by_kind = {k: 0 for k in KINDS}
    problems_by_kind = {k: 0 for k in KINDS}
    for p in problems:
        seen = set()
        for d in p.differences:
            by_kind[d.kind] += 1
            seen.add(d.kind)
        for k in seen:
            problems_by_kind[k] += 1
    return FidelityTotals(
        problems=len(problems),
        faithful=sum(p.status == "faithful" for p in problems),
        with_losses=sum(p.status == "losses" for p in problems),
        unchecked=sum(p.status == "unchecked" for p in problems),
        by_kind=by_kind,
        problems_by_kind=problems_by_kind,
    )


def build_report(
    root: Path,
    problem_ids: list[str],
    blocks: dict[str, str],
    manifest: OriginalsManifest,
    *,
    dataset_manifest_sha256: str,
    originals_manifest_sha256: str,
) -> FidelityReport:
    from dataset import config  # late: config is light, but keep this module importable alone

    problems = []
    for pid in problem_ids:
        entry = manifest.entry(pid)
        reason = "no_copy" if entry is None else (entry.error or "no_copy")
        enunciado = (Path(root) / config.EXTRACTED_PROBLEMS_DIR / pid / "enunciado.md").read_text(
            encoding="utf-8"
        )
        problems.append(check_problem(pid, blocks.get(pid), enunciado, reason))
    return FidelityReport(
        dataset_manifest_sha256=dataset_manifest_sha256,
        originals_manifest_sha256=originals_manifest_sha256,
        equivalences=dict(rendering.EQUIVALENCES),
        problems=problems,
        totals=totals(problems),
    )
