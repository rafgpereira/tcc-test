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
    parts = (
        (SiteKind.OPERATOR, operator, (category,), None),
        (SiteKind.OPERAND_LEFT, left, operand_operators, operator.type),
        (SiteKind.OPERAND_RIGHT, right, operand_operators, operator.type),
    )
    return [
        Site(
            kind=kind,
            node_type="binary_expression",
            start_byte=part.start_byte,
            end_byte=part.end_byte,
            discovery_index=next_index + offset,
            eligible_operators=operators,
            parent_operator=parent,
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
