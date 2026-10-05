"""Tests for the five operators of Offutt et al. as pure functions over text (data-model.md)."""

import pytest

from mutation import operators
from mutation.operators import apply, variant_count
from mutation.sites import find_sites
from mutation.types import MutationOperator, Site, SiteKind

ROR, AOR, LCR = MutationOperator.ROR, MutationOperator.AOR, MutationOperator.LCR
ABS, UOI = MutationOperator.ABS, MutationOperator.UOI

PRELUDE = "int a, b, c; bool p, q;\n"


def program(expression: str) -> str:
    return f"{PRELUDE}int main() {{ auto r = {expression}; }}\n"


def site_of(source: str, kind: SiteKind, text: str | None = None) -> Site:
    """The first site of ``kind`` (and, when given, covering exactly ``text``)."""
    raw = source.encode("utf-8")
    for site in find_sites(source):
        if site.kind is kind and (
            text is None or raw[site.start_byte : site.end_byte] == text.encode()
        ):
            return site
    raise AssertionError(f"no {kind.name} site {text!r} in {source!r}")


def variants(source: str, site: Site, operator: MutationOperator) -> list[str]:
    """Every applicable mutation of the site, in variant order, as the resulting expression."""
    mutated = []
    for variant in range(variant_count(operator)):
        text = apply(source, site, operator, variant)
        if text is not None:
            mutated.append(text.split("auto r = ")[1].split(";")[0])
    return mutated


# ------------------------------------------------------------------ ROR


def test_ror_on_less_than_gives_the_five_other_relational_operators():
    source = program("a < b")
    assert variants(source, site_of(source, SiteKind.OPERATOR, "<"), ROR) == [
        "a <= b",
        "a > b",
        "a >= b",
        "a == b",
        "a != b",
    ]


@pytest.mark.parametrize("token", ["<", "<=", ">", ">=", "==", "!="])
def test_ror_never_gives_the_original_operator_back_and_always_gives_five(token):
    source = program(f"a {token} b")
    outcomes = variants(source, site_of(source, SiteKind.OPERATOR, token), ROR)
    assert len(outcomes) == 5
    assert f"a {token} b" not in outcomes


# ------------------------------------------------------------------ AOR


def test_aor_on_plus_gives_the_other_four_arithmetic_operators():
    source = program("a + b")
    assert variants(source, site_of(source, SiteKind.OPERATOR, "+"), AOR) == [
        "a - b",
        "a * b",
        "a / b",
        "a % b",
    ]


def test_aor_on_a_shift_only_swaps_it_with_the_other_shift():
    source = program("a >> 1")
    assert variants(source, site_of(source, SiteKind.OPERATOR, ">>"), AOR) == ["a << 1"]


# ------------------------------------------------------------------ LCR


def test_lcr_on_and_gives_only_or():
    source = program("p && q")
    assert variants(source, site_of(source, SiteKind.OPERATOR, "&&"), LCR) == ["p || q"]


def test_lcr_on_or_gives_only_and():
    source = program("p || q")
    assert variants(source, site_of(source, SiteKind.OPERATOR, "||"), LCR) == ["p && q"]


# ------------------------------------------------------------------ ABS


def test_abs_on_an_operand_gives_exactly_three_variants_zero_positive_negative():
    source = program("a + b")
    assert variants(source, site_of(source, SiteKind.OPERAND_LEFT, "a"), ABS) == [
        "0 + b",
        "(+abs(a)) + b",
        "(-abs(a)) + b",
    ]


def test_abs_wraps_a_compound_operand_inside_the_call_only():
    source = program("(a + b) * c")
    site = site_of(source, SiteKind.OPERAND_LEFT, "(a + b)")
    assert variants(source, site, ABS)[1] == "(+abs((a + b))) * c"


# ------------------------------------------------------------------ UOI


def test_uoi_on_an_operand_of_a_relational_expression_can_insert_not():
    source = program("a < b")
    assert variants(source, site_of(source, SiteKind.OPERAND_LEFT, "a"), UOI) == [
        "-a < b",
        "!a < b",
        "++a < b",
        "--a < b",
    ]


def test_uoi_on_an_operand_of_a_logical_connector_inserts_only_not():
    source = program("p && q")
    assert variants(source, site_of(source, SiteKind.OPERAND_RIGHT, "q"), UOI) == ["p && !q"]


def test_uoi_on_an_operand_of_an_arithmetic_expression_never_inserts_not():
    source = program("a + b")
    site = site_of(source, SiteKind.OPERAND_LEFT, "a")
    assert apply(source, site, UOI, operators.UOI_TOKENS.index("!")) is None  # not an error
    assert variants(source, site, UOI) == ["-a + b", "++a + b", "--a + b"]


def test_uoi_keeps_the_precedence_of_a_compound_operand():
    source = program("a * b < c")
    site = site_of(source, SiteKind.OPERAND_LEFT, "a * b")
    assert variants(source, site, UOI)[1] == "!(a * b) < c"


def test_uoi_swaps_an_existing_unary_minus_and_not():
    minus = f"{PRELUDE}int main() {{ auto r = -a; }}\n"
    assert variants(minus, site_of(minus, SiteKind.OPERATOR, "-"), UOI) == ["!a"]
    negation = f"{PRELUDE}int main() {{ auto r = !p; }}\n"
    assert variants(negation, site_of(negation, SiteKind.OPERATOR, "!"), UOI) == ["-p"]


@pytest.mark.parametrize(("expression", "swapped"), [("a++", "a--"), ("--a", "++a")])
def test_uoi_swaps_increment_and_decrement(expression, swapped):
    source = program(expression)
    (site,) = [s for s in find_sites(source) if s.node_type == "update_expression"]
    assert variants(source, site, UOI) == [swapped]


# ------------------------------------------------------------------ what every operator preserves


def all_applications(source: str):
    for site in find_sites(source):
        for operator in site.eligible_operators:
            for variant in range(variant_count(operator)):
                mutated = apply(source, site, operator, variant)
                if mutated is not None:
                    yield site, operator, variant, mutated


SAMPLE = (
    f'{PRELUDE}int main() {{ // a < b\n  const char* s = "x + y";\n'
    "  for (int i = 0; i < a && !p; i++) b += i * 2 - (a % 3);\n  return a >> 1 == 0; }\n"
)


def test_every_operator_preserves_every_byte_outside_the_site():
    raw = SAMPLE.encode("utf-8")
    seen = 0
    for site, _operator, _variant, mutated in all_applications(SAMPLE):
        result = mutated.encode("utf-8")
        assert result.startswith(raw[: site.start_byte])
        assert result.endswith(raw[site.end_byte :])
        assert result != raw
        seen += 1
    assert seen > 40


def test_every_variant_of_a_site_gives_a_different_text():
    for site in find_sites(SAMPLE):
        for operator in site.eligible_operators:
            texts = [apply(SAMPLE, site, operator, v) for v in range(variant_count(operator))]
            texts = [t for t in texts if t is not None]
            assert len(texts) == len(set(texts)), (site, operator)


def test_an_operator_that_does_not_apply_to_the_site_returns_none():
    source = program("a < b")
    less_than = site_of(source, SiteKind.OPERATOR, "<")
    operand = site_of(source, SiteKind.OPERAND_LEFT, "a")
    assert apply(source, less_than, AOR, 0) is None
    assert apply(source, less_than, LCR, 0) is None
    assert apply(source, operand, ROR, 0) is None
    assert apply(source, less_than, ABS, 0) is None
    assert apply(source, less_than, ROR, 99) is None


def test_non_ascii_text_before_the_site_does_not_shift_the_replacement():
    source = f'{PRELUDE}int main() {{ const char* s = "ação"; auto r = a < b; }}\n'
    site = site_of(source, SiteKind.OPERATOR, "<")
    assert apply(source, site, ROR, 4) == source.replace("a < b", "a == b")


def test_a_second_call_gives_the_same_text():
    source = program("a < b")
    site = site_of(source, SiteKind.OPERATOR, "<")
    assert apply(source, site, ROR, 1) == apply(source, site, ROR, 1)


def test_abs_zero_on_the_literal_zero_is_not_a_mutation():
    source = program("a + 0")
    site = site_of(source, SiteKind.OPERAND_RIGHT, "0")
    assert apply(source, site, ABS, 0) is None  # the text would not change
    assert variants(source, site, ABS) == ["a + (+abs(0))", "a + (-abs(0))"]


def test_increment_and_decrement_are_only_inserted_in_front_of_something_assignable():
    source = f"{PRELUDE}int v[3];\nint main() {{ auto r = v[1] + a; }}\n"
    element = site_of(source, SiteKind.OPERAND_LEFT, "v[1]")
    assert variants(source, element, UOI) == [
        "-v[1] + a",
        "++v[1] + a",
        "--v[1] + a",
    ]
    literal = program("a + 2")
    site = site_of(literal, SiteKind.OPERAND_RIGHT, "2")
    assert variants(literal, site, UOI) == ["a + -2"]  # `++2` and `--2` would never compile
    total = program("(a + b) * c")
    inner = site_of(total, SiteKind.OPERAND_LEFT, "(a + b)")
    assert variants(total, inner, UOI)[0].startswith("-(a + b)")
