"""The statement nodes as text: flattened (as the dataset has it) and marked (research R4).

| node | flattened | marked |
|---|---|---|
| sup ``5`` | ``5`` | ``^{5}`` |
| sub ``i`` | ``i`` | ``_{i}`` |
| formula ``1 \\le n \\le 10^5`` | ``1 ≤ n ≤ 10^5`` | the same |
| image | (nothing) | ``[image]`` |
| table | the cells, one row per line | a Markdown table |

Formulas use the equivalences measured in the pilot of 2026-10-18 (``EQUIVALENCES``); a LaTeX
command outside it is kept as written and the span is flagged ``unknown``, so a difference there
shows up as a ``formula`` difference instead of being hidden. Every piece of the marked text keeps
the index of the node it came from (``spans``), which is how a difference gets its kind.
"""

import re
from dataclasses import dataclass, field

from dataset.statements.extract import Node

# What the dataset wrote for these commands, measured: the first three in the pilot (2026-10-18,
# 1000_B); the others in the first report of the 200 problems (2026-10-18), each a one-symbol
# replacement seen consistently in the formula differences (research R9). Structural changes
# (\frac{a}{b} written as (a)/(b), for instance) stay out: they show up as formula differences.
EQUIVALENCES: dict[str, str] = {
    r"\le": "≤",
    r"\lt": "<",
    r"\dots": "...",
    r"\leq": "≤",
    r"\ldots": "…",
    r"\rightarrow": "→",
    r"\cdot": "⋅",
    r"\lfloor": "⌊",
    r"\rfloor": "⌋",
    r"\rceil": "⌉",
    r"\ne": "≠",
    r"\ge": "≥",
    r"\gt": ">",
    r"\sum": "∑",
    r"\,": " ",
    r"\neq": "≠",
    r"\times": "×",
    r"\lceil": "⌈",
    r"\bmod": "mod",
}
_COMMAND = re.compile(r"\\[A-Za-z]+")
_SPACE = re.compile(r"\s+")


@dataclass(frozen=True)
class Span:
    start: int  # in the marked text
    end: int
    node: int  # index in the node list
    kind: str  # the node kind (text, sup, sub, formula, image, table, break)
    unknown: bool = False  # a formula with a command outside EQUIVALENCES
    mark: tuple[int, int] | None = None  # sup/sub: where the content is, inside start..end


@dataclass
class Rendered:
    flat: str = ""
    marked: str = ""
    spans: list[Span] = field(default_factory=list)
    formats: set[str] = field(default_factory=set)  # "marked" (sup/sub) and/or "latex"


def convert_formula(latex: str) -> tuple[str, bool]:
    """The formula as the dataset wrote it, and whether a command was left unconverted."""
    text = latex
    for command in sorted(EQUIVALENCES, key=len, reverse=True):
        text = re.sub(re.escape(command) + r"(?![A-Za-z])", EQUIVALENCES[command], text)
    return text, bool(_COMMAND.search(text))


def markdown_table(rows: tuple[tuple[str, ...], ...]) -> str:
    if not rows:
        return ""
    width = max(len(r) for r in rows)
    padded = [list(r) + [""] * (width - len(r)) for r in rows]
    lines = ["| " + " | ".join(padded[0]) + " |", "|" + "---|" * width]
    lines += ["| " + " | ".join(r) + " |" for r in padded[1:]]
    return "\n".join(lines)


def render(nodes: list[Node]) -> Rendered:
    out = Rendered()
    for index, node in enumerate(nodes):
        start = len(out.marked)
        mark = None
        unknown = False
        if node.kind == "text":
            flat = marked = node.text
        elif node.kind in ("sup", "sub"):
            out.formats.add("marked")
            opener = "^{" if node.kind == "sup" else "_{"
            flat, marked = node.text, f"{opener}{node.text}}}"
            mark = (start + 2, start + 2 + len(node.text))
        elif node.kind == "formula":
            out.formats.add("latex")
            flat, unknown = convert_formula(node.text)
            marked = flat
        elif node.kind == "image":
            flat, marked = "", "[image]"
        elif node.kind == "table":
            flat = "\n".join(" ".join(r) for r in node.rows)
            marked = markdown_table(node.rows)
        else:  # break
            flat = marked = "\n\n"
        out.flat += flat
        out.marked += marked
        if marked:
            out.spans.append(Span(start, len(out.marked), index, node.kind, unknown, mark))
    return out


def normalize_space(text: str) -> str:
    """Every run of spaces (thin space and no-break space included) and line breaks → one space."""
    return _SPACE.sub(" ", text.replace(" ", " ").replace("\xa0", " ")).strip()


def normalize_with_map(text: str) -> tuple[str, list[int]]:
    """``normalize_space(text)`` and, for each of its characters, the index in ``text``."""
    out, where, pending = [], [], False
    for i, ch in enumerate(text):
        if ch.isspace() or ch in " \xa0":
            pending = bool(out)
            continue
        if pending:
            out.append(" ")
            where.append(i - 1)
            pending = False
        out.append(ch)
        where.append(i)
    return "".join(out), where
