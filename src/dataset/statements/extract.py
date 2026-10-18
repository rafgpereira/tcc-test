"""The statement block of a Codeforces problem page, as a sequence of nodes (research R2).

The page is parsed with ``html.parser`` into a small tree. Inside ``<div class="problem-statement">``
the header (title, limits) and the examples (``div.sample-tests``) are left out; the description,
the input and output specifications, the note and any other section with a ``div.section-title``
are kept, in order. Two formats exist (pilot of 2026-10-18): the old one marks exponents and
indices with ``<sup class="upper-index">`` and ``<sub class="lower-index">``; the new one writes
formulas in LaTeX between ``$$$``. Style tags (``<i>``, ``<b>``, ``<span>``) leave nothing behind.
"""

from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Literal

NodeKind = Literal["text", "sup", "sub", "formula", "image", "table", "break"]

VOID = {"img", "br", "hr", "meta", "link", "input", "source", "wbr", "col", "area", "base"}
BLOCK = {"p", "div", "li", "ul", "ol", "center", "pre", "br", "tr", "h1", "h2", "h3", "blockquote"}
SKIPPED_PARTS = {"header", "sample-tests"}


class NoStatementBlock(ValueError):
    """The page has no ``div.problem-statement`` (or none with the expected parts)."""


@dataclass
class Element:
    tag: str
    attrs: dict[str, str]
    children: list = field(default_factory=list)  # Element or str

    @property
    def classes(self) -> set[str]:
        return set(self.attrs.get("class", "").split())

    def text(self) -> str:
        return "".join(c if isinstance(c, str) else c.text() for c in self.children)


@dataclass(frozen=True)
class Node:
    kind: NodeKind
    text: str = ""
    rows: tuple[tuple[str, ...], ...] = ()  # tables only


class _TreeBuilder(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Element("#root", {})
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        element = Element(tag, {k: v or "" for k, v in attrs})
        self.stack[-1].children.append(element)
        if tag not in VOID:
            self.stack.append(element)

    def handle_startendtag(self, tag, attrs):
        self.stack[-1].children.append(Element(tag, {k: v or "" for k, v in attrs}))

    def handle_endtag(self, tag):
        for depth in range(len(self.stack) - 1, 0, -1):  # tolerate unclosed tags
            if self.stack[depth].tag == tag:
                del self.stack[depth:]
                return

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def parse(html: str) -> Element:
    builder = _TreeBuilder()
    builder.feed(html)
    builder.close()
    return builder.root


def _find(element: Element, css_class: str) -> Element | None:
    for child in element.children:
        if isinstance(child, Element):
            if child.tag == "div" and css_class in child.classes:
                return child
            found = _find(child, css_class)
            if found is not None:
                return found
    return None


def statement_block(html: str) -> str | None:
    """The HTML text of ``<div class="problem-statement">...</div>`` (what the package keeps)."""
    start = html.find('<div class="problem-statement">')
    if start < 0:
        return None
    depth, at = 0, start
    while True:
        opening, closing = html.find("<div", at), html.find("</div>", at)
        if closing < 0:
            return None
        if 0 <= opening < closing:
            depth, at = depth + 1, opening + 4
        else:
            depth, at = depth - 1, closing + 6
            if depth == 0:
                return html[start:at]


def _split_formulas(text: str, out: list[Node]) -> None:
    for i, piece in enumerate(text.split("$$$")):
        if piece:
            out.append(Node("formula" if i % 2 else "text", piece))


def _table(element: Element) -> Node:
    rows = []

    def walk(e: Element) -> None:
        for child in e.children:
            if isinstance(child, Element):
                if child.tag == "tr":
                    cells = [
                        " ".join(c.text().split())
                        for c in child.children
                        if isinstance(c, Element) and c.tag in ("td", "th")
                    ]
                    rows.append(tuple(cells))
                else:
                    walk(child)

    walk(element)
    return Node("table", rows=tuple(rows))


def _nodes(element: Element, out: list[Node]) -> None:
    for child in element.children:
        if isinstance(child, str):
            _split_formulas(child, out)
            continue
        if child.tag in ("script", "style"):
            continue
        if child.tag == "sup":
            out.append(Node("sup", child.text()))
        elif child.tag == "sub":
            out.append(Node("sub", child.text()))
        elif child.tag == "img":
            out.append(Node("image", child.attrs.get("src", "")))
        elif child.tag == "table":
            out.append(Node("break"))
            out.append(_table(child))
            out.append(Node("break"))
        elif child.tag in ("ul", "ol"):
            # The dataset wrote lists in Markdown: "* " for an item, "1. ", "2. " when numbered
            # (measured in the first report of the 200 problems, 2026-10-18).
            out.append(Node("break"))
            number = 0
            for item in child.children:
                if isinstance(item, Element) and item.tag == "li":
                    number += 1
                    out.append(Node("break"))
                    out.append(Node("text", "* " if child.tag == "ul" else f"{number}. "))
                    _nodes(item, out)
                    out.append(Node("break"))
            out.append(Node("break"))
        elif child.tag in BLOCK:
            out.append(Node("break"))
            _nodes(child, out)
            out.append(Node("break"))
        else:
            _nodes(child, out)


def extract_statement(html: str) -> list[Node]:
    """The nodes of the statement: description, input, output, note and other titled sections."""
    block = _find(parse(html), "problem-statement")
    if block is None:
        raise NoStatementBlock("no problem-statement block")
    parts = [c for c in block.children if isinstance(c, Element) and c.tag == "div"]
    kept = [p for p in parts if not (p.classes & SKIPPED_PARTS)]
    has_header = any("header" in p.classes for p in parts)
    if not has_header or not kept:
        raise NoStatementBlock("the problem-statement block has not the expected parts")
    out: list[Node] = []
    for part in kept:
        out.append(Node("break"))
        _nodes(part, out)
        out.append(Node("break"))
    return out
