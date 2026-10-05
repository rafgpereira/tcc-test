"""Discovery of mutation sites over the syntax tree of a C++ file (research R1 to R3; FR-001).

The file is parsed with ``tree-sitter-cpp``, a tolerant parser that needs neither the headers nor
type information. Sites are read only from three kinds of node (``binary_expression``,
``unary_expression`` and ``update_expression``), so a string, a character literal or a comment can
never be touched: they are nodes of their own kind and never children of those three. The parser
also tells apart the ``>>`` that closes two nested templates (``vector<vector<int>>``, no expression
node at all) from the ``>>`` that is an operator.

Order is part of the result (FR-011). The walk is pre-order; a ``binary_expression`` yields its
operator site, then its left operand, then its right operand, and only then are its children
visited. ``discovery_index`` is the position in that list, and every later choice of the module
(which candidates come first, which combinations are tried) follows it, so no seed is needed.
"""

import re

import tree_sitter_cpp
from tree_sitter import Language, Node, Parser

from mutation.operators import (
    ARITHMETIC_TOKENS,
    LOGICAL_TOKENS,
    RELATIONAL_TOKENS,
    SWAPPABLE_UNARY_TOKENS,
)
from mutation.types import MutationOperator, Site, SiteKind

_PARSER = Parser(Language(tree_sitter_cpp.language()))

_PREPROCESSOR_WITH_CONDITION = ("preproc_if", "preproc_elif")

# Stream I/O (`cin >> a >> b`, `cout << x << endl`) is not a mutation target: swapping its operator,
# or putting `abs`/`-`/`++` in front of the stream or of the variable being read, never compiles
# (measured: research R16). The value written by `cout <<` is a normal operand and stays a site.
_STREAM_ROOTS = frozenset({"cin", "cout", "cerr", "clog"})
_SHIFTS = ("<<", ">>")
# Operands that are not numbers whatever the types are: text and stream manipulators.
_NON_NUMERIC_OPERAND_TYPES = frozenset(
    {"string_literal", "raw_string_literal", "concatenated_string"}
)
_STREAM_MANIPULATORS = frozenset({"endl", "flush", "ends"})
# Sizes are unsigned: `abs` of one is ambiguous to the compiler, and where it compiles it changes
# nothing (an equivalent mutant), so ABS is not offered for them.
_UNSIGNED_OPERAND = re.compile(r"(?:(?:\.|->)(?:size|length)\s*\(\s*\)|^sizeof\b.*)$", re.DOTALL)

_OPERATOR_OF_TOKEN: dict[str, MutationOperator] = {
    **dict.fromkeys(RELATIONAL_TOKENS, MutationOperator.ROR),
    **dict.fromkeys(ARITHMETIC_TOKENS, MutationOperator.AOR),
    **dict.fromkeys(LOGICAL_TOKENS, MutationOperator.LCR),
}
# ABS and UOI both act on the operands of a relational or arithmetic expression (numbers by
# construction, so no type inference is needed); a logical connector only takes UOI (research R2).
_ABS_PARENTS = frozenset({MutationOperator.ROR, MutationOperator.AOR})


def _token(node: Node | None) -> str | None:
    return node.type if node is not None else None


def _text(node: Node) -> str:
    return node.text.decode("utf-8") if node.text is not None else ""


def _is_stream_expression(node: Node) -> bool:
    """``cin >> a >> b`` and ``cout << x << endl``: a chain of shifts that starts at a std stream."""
    while (
        node.type == "binary_expression" and _token(node.child_by_field_name("operator")) in _SHIFTS
    ):
        left = node.child_by_field_name("left")
        if left is None:
            return False
        node = left
    return _text(node).removeprefix("std::") in _STREAM_ROOTS and node.type in (
        "identifier",
        "qualified_identifier",
    )


def _is_numeric_candidate(operand: Node) -> bool:
    """Can ABS or UOI possibly apply to this operand, judging only by its syntax?"""
    if operand.type in _NON_NUMERIC_OPERAND_TYPES:
        return False
    if operand.type in ("identifier", "qualified_identifier") and (
        _text(operand).removeprefix("std::") in _STREAM_MANIPULATORS
    ):
        return False
    return not (operand.type == "binary_expression" and _is_stream_expression(operand))


def _without_abs(
    operand: Node, operators: tuple[MutationOperator, ...]
) -> tuple[MutationOperator, ...]:
    if _UNSIGNED_OPERAND.search(_text(operand)):
        return tuple(op for op in operators if op is not MutationOperator.ABS)
    return operators


def _binary_sites(node: Node, next_index: int) -> list[Site]:
    operator = node.child_by_field_name("operator")
    left, right = node.child_by_field_name("left"), node.child_by_field_name("right")
    category = _OPERATOR_OF_TOKEN.get(_token(operator) or "")
    if operator is None or left is None or right is None or category is None:
        return []  # bitwise, comma, spaceship...: not a mutation site of this experiment
    operand_operators = (
        (MutationOperator.ABS, MutationOperator.UOI)
        if category in _ABS_PARENTS
        else (MutationOperator.UOI,)
    )
    parts = [(SiteKind.OPERATOR, operator, (category,), None)]
    if not _is_stream_expression(node):
        parts.append((SiteKind.OPERAND_LEFT, left, operand_operators, operator.type))
        parts.append((SiteKind.OPERAND_RIGHT, right, operand_operators, operator.type))
    elif operator.type == "<<":  # what `cout` prints is a value; what `cin` reads is not
        parts = [(SiteKind.OPERAND_RIGHT, right, operand_operators, operator.type)]
    else:
        parts = []
    parts = [p for p in parts if p[0] is SiteKind.OPERATOR or _is_numeric_candidate(p[1])]
    parts = [
        (
            kind,
            part,
            _without_abs(part, operators) if kind is not SiteKind.OPERATOR else operators,
            parent,
        )
        for kind, part, operators, parent in parts
    ]
    return [
        Site(
            kind=kind,
            node_type="binary_expression",
            start_byte=part.start_byte,
            end_byte=part.end_byte,
            discovery_index=next_index + offset,
            eligible_operators=operators,
            parent_operator=parent,
            operand_type=None if kind is SiteKind.OPERATOR else part.type,
        )
        for offset, (kind, part, operators, parent) in enumerate(parts)
    ]


def _unary_sites(node: Node, next_index: int) -> list[Site]:
    operator = node.child_by_field_name("operator")
    if operator is None:
        return []
    if node.type == "unary_expression" and operator.type not in SWAPPABLE_UNARY_TOKENS:
        return []  # `~` and unary `+` are not part of the operator set
    return [
        Site(
            kind=SiteKind.OPERATOR,
            node_type=node.type,
            start_byte=operator.start_byte,
            end_byte=operator.end_byte,
            discovery_index=next_index,
            eligible_operators=(MutationOperator.UOI,),
        )
    ]


def find_sites(source: str) -> list[Site]:
    """Every mutation site of ``source``, in pre-order of the syntax tree (research R3)."""
    tree = _PARSER.parse(source.encode("utf-8"))
    sites: list[Site] = []
    stack = [tree.root_node]
    while stack:  # explicit stack: a long chain `a + b + c + ...` must not hit the recursion limit
        node = stack.pop()
        if node.type == "binary_expression":
            sites.extend(_binary_sites(node, len(sites)))
        elif node.type in ("unary_expression", "update_expression"):
            sites.extend(_unary_sites(node, len(sites)))
        children = node.children
        if node.type in _PREPROCESSOR_WITH_CONDITION:
            condition = node.child_by_field_name("condition")  # `#if N > 3` is not program logic
            children = [c for c in children if c != condition]
        stack.extend(reversed(children))
    return sites
