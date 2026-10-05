"""Tests for the discovery of mutation sites over the syntax tree (research R1 to R3; FR-001).

The fixtures are real C++ fragments, among them the case that motivates the choice of a parser over
a textual search: ``vector<pair<int, string>> mb;`` has a ``>>`` that is not an operator.
"""

import pytest

from mutation.sites import find_sites
from mutation.types import MutationOperator, Site, SiteKind

ROR, AOR, LCR = MutationOperator.ROR, MutationOperator.AOR, MutationOperator.LCR
ABS, UOI = MutationOperator.ABS, MutationOperator.UOI


def wrap(body: str, prelude: str = "") -> str:
    return f"{prelude}\nint main() {{\n{body}\n}}\n"


def text_of(source: str, site: Site) -> str:
    return source.encode("utf-8")[site.start_byte : site.end_byte].decode("utf-8")


def described(source: str, sites: list[Site]) -> list[tuple[str, str]]:
    """``(kind, text)`` of every site, in the order returned."""
    return [(site.kind.name, text_of(source, site)) for site in sites]


def operator_sites(source: str) -> list[Site]:
    return [s for s in find_sites(source) if s.kind is SiteKind.OPERATOR]


# ------------------------------------------------------------------ templates versus operators


def test_the_closing_of_nested_templates_is_not_an_operator_site():
    source = wrap("", prelude="vector<pair<int, string>> mb;")  # the real case of problem 175_B
    assert find_sites(source) == []


def test_a_right_shift_expression_is_a_site_even_in_a_file_that_has_nested_templates():
    source = wrap("int y = x >> 1;", prelude="vector<vector<int>> grid;\nint x;")
    ops = operator_sites(source)
    assert [text_of(source, s) for s in ops] == [">>"]
    assert ops[0].eligible_operators == (AOR,)  # arithmetic in this context (shifts, see research)


# ------------------------------------------------------------------ stream I/O is not a target


def test_stream_extraction_has_no_sites_at_all():
    source = wrap("cin >> n >> m;", prelude="int n, m;")
    assert find_sites(source) == []  # not the operator, not `cin`, not the variables read


def test_std_qualified_streams_are_streams_too():
    source = wrap("std::cin >> n; std::cout << std::endl;", prelude="int n;")
    assert find_sites(source) == []


def test_what_cout_prints_is_a_normal_operand_but_the_stream_is_not():
    source = wrap("cout << x << y;", prelude="int x, y;")
    sites = find_sites(source)
    assert described(source, sites) == [("OPERAND_RIGHT", "y"), ("OPERAND_RIGHT", "x")]  # pre-order
    assert all(s.parent_operator == "<<" for s in sites)


def test_stream_manipulators_and_text_are_not_operands():
    source = wrap('cout << "sum: " << x << endl << flush;', prelude="int x;")
    assert described(source, find_sites(source)) == [("OPERAND_RIGHT", "x")]


def test_an_expression_inside_a_stream_statement_keeps_its_own_sites():
    source = wrap("cout << (a + b) << endl;", prelude="int a, b;")
    texts = described(source, find_sites(source))
    assert ("OPERATOR", "+") in texts and ("OPERAND_RIGHT", "(a + b)") in texts
    assert ("OPERATOR", "<<") not in texts


def test_a_shift_that_does_not_start_at_a_stream_is_still_arithmetic():
    source = wrap("int r = (a << 2) >> 1;", prelude="int a;")
    assert [text_of(source, s) for s in operator_sites(source)] == [">>", "<<"]


def test_the_operand_type_is_recorded_for_operand_sites_only():
    source = wrap("auto r = v[0] + 1;", prelude="int v[2];")
    sites = find_sites(source)
    assert [(s.kind.name, s.operand_type) for s in sites] == [
        ("OPERATOR", None),
        ("OPERAND_LEFT", "subscript_expression"),
        ("OPERAND_RIGHT", "number_literal"),
    ]


def test_abs_is_not_offered_for_unsigned_sizes():
    source = wrap("auto r = v.size() + n + sizeof(int);", prelude="vector<int> v; int n;")
    operands = {
        text_of(source, s): s.eligible_operators
        for s in find_sites(source)
        if s.kind is not SiteKind.OPERATOR
    }
    assert operands["v.size()"] == (UOI,)
    assert operands["sizeof(int)"] == (UOI,)
    assert operands["v.size() + n"] == (ABS, UOI)  # a sum is not itself flagged
    assert operands["n"] == (ABS, UOI)


# ------------------------------------------------------------------ literals and comments


def test_nothing_inside_a_string_or_a_comment_is_a_site():
    body = "const char* s = \"a<b>>c && d\";\nchar c = '<';\n// x < y >> z && w\n/* p + q */\nint k = 1;"
    source = wrap(body)
    assert find_sites(source) == []
    trap = source.encode("utf-8")
    dead = [
        (trap.index(marker), trap.index(marker) + len(marker))
        for marker in (b'"a<b>>c && d"', b"'<'", b"// x < y >> z && w", b"/* p + q */")
    ]
    real = wrap(body + "\nint z = k < 2;")
    for site in find_sites(real):
        assert not any(lo <= site.start_byte < hi for lo, hi in dead)


def test_a_real_expression_next_to_a_string_with_operators_is_found_exactly_once():
    source = wrap('puts("a<b"); int r = m < n;', prelude="int m, n;")
    assert [text_of(source, s) for s in operator_sites(source)] == ["<"]


def test_preprocessor_conditions_are_not_sites():
    source = "#if N > 3\nint a;\n#endif\n" + wrap("")
    assert find_sites(source) == []


# ------------------------------------------------------------------ which operator tokens are sites


@pytest.mark.parametrize(
    ("expression", "token", "operator"),
    [
        ("a < b", "<", ROR),
        ("a <= b", "<=", ROR),
        ("a > b", ">", ROR),
        ("a >= b", ">=", ROR),
        ("a == b", "==", ROR),
        ("a != b", "!=", ROR),
        ("a + b", "+", AOR),
        ("a - b", "-", AOR),
        ("a * b", "*", AOR),
        ("a / b", "/", AOR),
        ("a % b", "%", AOR),
        ("a << b", "<<", AOR),
        ("a && b", "&&", LCR),
        ("a || b", "||", LCR),
    ],
)
def test_each_operator_token_is_a_site_of_its_category(expression, token, operator):
    source = wrap(f"auto r = {expression};", prelude="int a, b;")
    ops = operator_sites(source)
    assert [text_of(source, s) for s in ops] == [token]
    assert ops[0].eligible_operators == (operator,)
    assert ops[0].node_type == "binary_expression"


@pytest.mark.parametrize("expression", ["a & b", "a | b", "a ^ b", "(a, b)"])
def test_bitwise_and_comma_expressions_are_not_sites(expression):
    source = wrap(f"auto r = {expression};", prelude="int a, b;")
    assert find_sites(source) == []


# ------------------------------------------------------------------ operands (ABS and UOI)


def test_operands_of_a_relational_or_arithmetic_expression_accept_abs_and_uoi():
    for expression in ("a < b", "a + b"):
        source = wrap(f"auto r = {expression};", prelude="int a, b;")
        left, right = [s for s in find_sites(source) if s.kind is not SiteKind.OPERATOR]
        assert (left.kind, text_of(source, left)) == (SiteKind.OPERAND_LEFT, "a")
        assert (right.kind, text_of(source, right)) == (SiteKind.OPERAND_RIGHT, "b")
        assert left.eligible_operators == right.eligible_operators == (ABS, UOI)
        assert left.parent_operator == right.parent_operator == expression.split()[1]


def test_operands_of_a_logical_connector_accept_only_uoi():
    source = wrap("auto r = a && b;", prelude="bool a, b;")
    operands = [s for s in find_sites(source) if s.kind is not SiteKind.OPERATOR]
    assert [s.eligible_operators for s in operands] == [(UOI,), (UOI,)]
    assert {s.parent_operator for s in operands} == {"&&"}


def test_the_operand_of_an_operator_site_is_the_whole_subexpression():
    source = wrap("auto r = a + b * c;", prelude="int a, b, c;")
    operands = [text_of(source, s) for s in find_sites(source) if s.kind is SiteKind.OPERAND_RIGHT]
    assert operands == ["b * c", "c"]  # the `+` right operand, then the `*` right operand


# ------------------------------------------------------------------ unary and update expressions


@pytest.mark.parametrize(
    ("expression", "node_type", "token"),
    [
        ("-x", "unary_expression", "-"),
        ("!y", "unary_expression", "!"),
        ("++x", "update_expression", "++"),
        ("x--", "update_expression", "--"),
        ("x++", "update_expression", "++"),
        ("--x", "update_expression", "--"),
    ],
)
def test_existing_unary_and_update_operators_are_uoi_sites(expression, node_type, token):
    source = wrap(f"auto r = {expression};", prelude="int x; bool y;")
    ops = operator_sites(source)
    assert len(ops) == 1
    assert (ops[0].node_type, text_of(source, ops[0])) == (node_type, token)
    assert ops[0].eligible_operators == (UOI,)


def test_a_for_loop_header_yields_the_condition_and_the_increment():
    source = wrap("for (int i = 0; i < n; i++) {}", prelude="int n;")
    assert [(s.node_type, text_of(source, s)) for s in operator_sites(source)] == [
        ("binary_expression", "<"),
        ("update_expression", "++"),
    ]


# ------------------------------------------------------------------ deterministic order


def test_sites_come_in_pre_order_with_the_operator_before_the_operands():
    source = wrap("auto r = a + b * c;", prelude="int a, b, c;")
    assert described(source, find_sites(source)) == [
        ("OPERATOR", "+"),
        ("OPERAND_LEFT", "a"),
        ("OPERAND_RIGHT", "b * c"),
        ("OPERATOR", "*"),
        ("OPERAND_LEFT", "b"),
        ("OPERAND_RIGHT", "c"),
    ]


def test_discovery_index_is_the_position_in_the_returned_list():
    source = wrap("for (int i = 0; i < n && !f; i++) s += i * 2;", prelude="int n, s; bool f;")
    sites = find_sites(source)
    assert [s.discovery_index for s in sites] == list(range(len(sites)))
    assert len(sites) > 6


def test_two_calls_on_the_same_text_return_the_same_sites_in_the_same_order():
    source = wrap("for (int i = 0; i < n; i++) if (i % 2 == 0 || i > 7) s += i;", "int n, s;")
    first, second = find_sites(source), find_sites(source)
    assert first == second
    assert [s.eligible_operators for s in first] == [s.eligible_operators for s in second]


def test_no_two_sites_are_the_same_site():
    source = wrap("int r = (a + b) * (a + b) - a;", prelude="int a, b;")
    sites = find_sites(source)
    assert len(set(sites)) == len(sites)


# ------------------------------------------------------------------ bytes, not characters


def test_offsets_are_utf8_bytes_even_after_non_ascii_text():
    source = wrap('const char* s = "ação"; // ç\nint r = m < n;', prelude="int m, n;")
    ops = operator_sites(source)
    assert [text_of(source, s) for s in ops] == ["<"]  # sliced with byte offsets


def test_an_empty_or_expression_free_file_has_no_sites():
    assert find_sites("") == []
    assert find_sites("int main() { return 0; }\n") == []
