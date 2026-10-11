"""The mutation operators of Offutt et al. (1996) as pure functions over text (data-model.md).

Every operator replaces ONE byte range of the original file (the range of a ``Site``) and leaves
every other byte untouched. A ``variant`` is an index into a fixed table of the operator; a variant
that does not make sense for the site (the operator itself, an unary operator that is illegal in
that position) returns ``None``: that is "not applicable", not an error. Whether the result
compiles is the business of the validation (a candidate that does not compile is discarded there).

Nothing here is random: variants are enumerated in table order, which is what makes the order of
the candidates of a whole run fixed (spec FR-011).
"""

import re

from mutation.types import MutationOperator, Site, SiteKind

RELATIONAL_TOKENS = ("<", "<=", ">", ">=", "==", "!=")
# Shifts are arithmetic in this experiment (`x >> 1`); they are only swapped with each other, never
# with `+ - * / %`, which would not type-check for the streams that dominate competitive code.
ARITHMETIC_TOKENS = ("+", "-", "*", "/", "%", "<<", ">>")
_ARITHMETIC_GROUPS = (("+", "-", "*", "/", "%"), ("<<", ">>"))
LOGICAL_TOKENS = ("&&", "||")
SWAPPABLE_UNARY_TOKENS = ("-", "!")

UOI_TOKENS = ("-", "!", "++", "--")
_UOI_ON_OPERAND = {  # which unary operators may be inserted, by operator of the parent expression
    "relational": ("-", "!", "++", "--"),
    "arithmetic": ("-", "++", "--"),  # `!` in front of an arithmetic operand: not legal here
    "logical": ("!",),
}
_UOI_SWAP = {"unary_expression": ("-", "!"), "update_expression": ("++", "--")}

# `++x` and `--x` need something that can be assigned to; anything else never compiles.
_LVALUE_TYPES = frozenset(
    {
        "identifier",
        "qualified_identifier",
        "subscript_expression",
        "field_expression",
        "pointer_expression",
        "parenthesized_expression",
    }
)

ABS_VARIANTS = 3  # zero, positive, negative

# An identifier with subscripts and member accesses, or a number: nothing an unary operator could bind
# to only partly (`-v[1]`, `!p->ok`).
_SIMPLE_OPERAND = re.compile(r"[A-Za-z_]\w*(?:\[[^\[\]]*\]|\.\w+|->\w+)*|\d[\w.']*")


def _text(source_bytes: bytes, site: Site) -> str:
    return source_bytes[site.start_byte : site.end_byte].decode("utf-8")


def _replace(source_bytes: bytes, site: Site, replacement: str) -> str:
    return (
        source_bytes[: site.start_byte]
        + replacement.encode("utf-8")
        + source_bytes[site.end_byte :]
    ).decode("utf-8")


def _is_parenthesized(text: str) -> bool:
    if not (text.startswith("(") and text.endswith(")")):
        return False
    depth = 0
    for position, char in enumerate(text):
        depth += (char == "(") - (char == ")")
        if depth == 0 and position < len(text) - 1:
            return False  # the first "(" closed before the end: `(a) + (b)`
    return True


def _operand(text: str) -> str:
    """The operand as a unit an unary operator can be put in front of without changing its parse."""
    if _SIMPLE_OPERAND.fullmatch(text) or _is_parenthesized(text):
        return text
    return f"({text})"


def _category(token: str | None) -> str | None:
    if token in RELATIONAL_TOKENS:
        return "relational"
    if token in ARITHMETIC_TOKENS:
        return "arithmetic"
    if token in LOGICAL_TOKENS:
        return "logical"
    return None


# ------------------------------------------------------------------------------ the five operators


def ror(source: str, site: Site, variant: int) -> str | None:
    """Relational operator replacement: variant ``i`` puts ``RELATIONAL_TOKENS[i]`` in the site."""
    raw = source.encode("utf-8")
    if site.kind is not SiteKind.OPERATOR or not 0 <= variant < len(RELATIONAL_TOKENS):
        return None
    current = _text(raw, site)
    if current not in RELATIONAL_TOKENS or RELATIONAL_TOKENS[variant] == current:
        return None
    return _replace(raw, site, RELATIONAL_TOKENS[variant])


def aor(source: str, site: Site, variant: int) -> str | None:
    """Arithmetic operator replacement, inside the group of the current operator (see above)."""
    raw = source.encode("utf-8")
    if site.kind is not SiteKind.OPERATOR or not 0 <= variant < len(ARITHMETIC_TOKENS):
        return None
    current, replacement = _text(raw, site), ARITHMETIC_TOKENS[variant]
    group = next((g for g in _ARITHMETIC_GROUPS if current in g), ())
    if replacement == current or replacement not in group:
        return None
    return _replace(raw, site, replacement)


def lcr(source: str, site: Site, variant: int) -> str | None:
    """Logical connector replacement: ``&&`` and ``||`` swap (a single variant, index 0)."""
    raw = source.encode("utf-8")
    if site.kind is not SiteKind.OPERATOR or variant != 0:
        return None
    current = _text(raw, site)
    if current not in LOGICAL_TOKENS:
        return None
    return _replace(raw, site, "||" if current == "&&" else "&&")


def abs_(source: str, site: Site, variant: int) -> str | None:
    """Absolute value insertion: the operand becomes zero, ``+abs(operand)`` or ``-abs(operand)``."""
    raw = source.encode("utf-8")
    if site.kind is SiteKind.OPERATOR or not 0 <= variant < ABS_VARIANTS:
        return None
    operand = _text(raw, site)
    replacement = ("0", f"(+abs({operand}))", f"(-abs({operand}))")[variant]
    return _replace(raw, site, replacement)


def uoi(source: str, site: Site, variant: int) -> str | None:
    """Unary operator insertion (operand sites) or replacement (existing ``-x``, ``!x``, ``x++``).

    Variant ``i`` uses ``UOI_TOKENS[i]``. In front of an operand only the operators that are legal
    for the parent expression apply; on an existing unary or update operator the token is swapped
    with its counterpart (``-`` with ``!``, ``++`` with ``--``).
    """
    raw = source.encode("utf-8")
    if not 0 <= variant < len(UOI_TOKENS):
        return None
    token = UOI_TOKENS[variant]
    if site.kind is SiteKind.OPERATOR:
        swap = _UOI_SWAP.get(site.node_type)
        current = _text(raw, site)
        if swap is None or current not in swap or token not in swap or token == current:
            return None
        return _replace(raw, site, token)
    if token not in _UOI_ON_OPERAND.get(_category(site.parent_operator) or "", ()):
        return None
    if token in ("++", "--") and site.operand_type not in _LVALUE_TYPES:
        return None
    return _replace(raw, site, token + _operand(_text(raw, site)))


_FUNCTIONS = {
    MutationOperator.ROR: ror,
    MutationOperator.AOR: aor,
    MutationOperator.LCR: lcr,
    MutationOperator.ABS: abs_,
    MutationOperator.UOI: uoi,
}
_VARIANT_COUNT = {
    MutationOperator.ROR: len(RELATIONAL_TOKENS),
    MutationOperator.AOR: len(ARITHMETIC_TOKENS),
    MutationOperator.LCR: 1,
    MutationOperator.ABS: ABS_VARIANTS,
    MutationOperator.UOI: len(UOI_TOKENS),
}


def variant_count(operator: MutationOperator) -> int:
    """How many entries the variant table of ``operator`` has (not all apply to every site)."""
    return _VARIANT_COUNT[operator]


def apply(source: str, site: Site, operator: MutationOperator, variant: int) -> str | None:
    """The text of ``source`` with ``site`` changed by ``operator``, or ``None`` if not applicable.

    A variant that would leave the text unchanged (zero in front of the literal ``0``) is not a
    mutation, so it is not applicable either.
    """
    mutated = _FUNCTIONS[operator](source, site, variant)
    return None if mutated == source else mutated
