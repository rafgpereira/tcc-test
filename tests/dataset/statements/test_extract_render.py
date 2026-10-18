"""The statement block as nodes (R2) and as flattened and marked text (R4)."""

import pytest

from dataset.statements.extract import NoStatementBlock, extract_statement, statement_block
from dataset.statements.render import (
    convert_formula,
    markdown_table,
    normalize_space,
    normalize_with_map,
    render,
)
from tests.dataset.statements.fixtures import NEW_LEGEND_HTML, OLD_LEGEND_HTML, page


def kinds(nodes):
    return [n.kind for n in nodes if n.kind != "break"]


def test_the_header_and_the_examples_are_left_out():
    text = render(extract_statement(page("Hello."))).flat
    assert "time limit" not in text and "A. Test" not in text
    assert "Examples" not in text and "<pre>" not in text
    assert normalize_space(text) == "Hello. Input One line. Output One number. Note It works."


def test_an_extra_titled_section_is_kept():
    extra = '<div class="interaction"><div class="section-title">Interaction</div><p>Ask.</p></div>'
    text = normalize_space(render(extract_statement(page("Hi.", extra=extra))).flat)
    assert "Interaction Ask." in text


def test_old_format_sup_and_sub_become_nodes_and_style_tags_leave_no_space():
    nodes = extract_statement(page(OLD_LEGEND_HTML))
    assert "sup" in kinds(nodes) and "sub" in kinds(nodes)
    rendered = render(nodes)
    assert "(1 ≤ n ≤ 105) and the numbers ai." in normalize_space(rendered.flat)
    assert "(1 ≤ n ≤ 10^{5}) and the numbers a_{i}." in normalize_space(rendered.marked)
    assert rendered.formats == {"marked"}


def test_new_format_formulas_use_the_measured_equivalences():
    rendered = render(extract_statement(page(NEW_LEGEND_HTML)))
    assert "Read n (1 ≤ n ≤ 10^5) and the numbers a_i." in normalize_space(rendered.flat)
    assert rendered.flat == rendered.marked
    assert rendered.formats == {"latex"}


def test_an_unknown_command_is_flagged():
    assert convert_formula(r"1 \le n") == ("1 ≤ n", False)
    assert convert_formula(r"0 \lt a \lt \dots") == ("0 < a < ...", False)
    assert convert_formula(r"\frac{x}{y}")[1] is True
    span = next(
        s
        for s in render(extract_statement(page(r"$$$\frac{x}{y}$$$"))).spans
        if s.kind == "formula"
    )
    assert span.unknown


def test_image_and_table():
    legend = 'See <img src="a.png"/> and <table><tr><th>a</th><th>b</th></tr><tr><td>1</td><td>2</td></tr></table>'
    rendered = render(extract_statement(page(legend)))
    assert "[image]" in rendered.marked and "[image]" not in rendered.flat
    assert "| a | b |\n|---|---|\n| 1 | 2 |" in rendered.marked
    assert "a b\n1 2" in rendered.flat
    assert markdown_table((("x",),)) == "| x |\n|---|"


def test_the_map_points_each_piece_to_its_node():
    rendered = render(extract_statement(page(OLD_LEGEND_HTML)))
    sup = next(s for s in rendered.spans if s.kind == "sup")
    assert rendered.marked[sup.start : sup.end] == "^{5}"
    assert rendered.marked[sup.mark[0] : sup.mark[1]] == "5"


def test_normalize_with_map():
    text, where = normalize_with_map("a  b\n\nc")
    assert text == "a b c" and [where[0], where[2], where[4]] == [0, 3, 6]


def test_a_page_without_the_block_is_refused():
    with pytest.raises(NoStatementBlock):
        extract_statement("<html><body>nothing</body></html>")
    with pytest.raises(NoStatementBlock):
        extract_statement('<div class="problem-statement"><p>no parts</p></div>')
    assert statement_block("<p>none</p>") is None
    block = statement_block(page("Hi."))
    assert block.startswith('<div class="problem-statement">') and block.endswith("</div>")
    assert "menu" not in block and "<script>" not in block


def test_lists_are_written_as_the_dataset_wrote_them():
    legend = "Do:</p><ul><li>one</li><li>two</li></ul><ol><li>first</li><li>second</li></ol><p>end."
    text = normalize_space(render(extract_statement(page(legend))).flat)
    assert "Do: * one * two 1. first 2. second end." in text


def test_the_equivalences_measured_in_the_200_problems():
    assert convert_formula(r"1 \leq n \leq 2 \cdot 10^5") == ("1 ≤ n ≤ 2 ⋅ 10^5", False)
    assert convert_formula(r"a_1, \ldots, a_n") == ("a_1, …, a_n", False)
    assert convert_formula(r"\lfloor x \rfloor \ne \lceil y \rceil")[0] == "⌊ x ⌋ ≠ ⌈ y ⌉"
    assert convert_formula(r"100\,000")[0] == "100 000"
    assert convert_formula(r"\frac{a}{b}")[1] is True  # a structural change stays a difference
