"""The corrected statement: the current text with the marks of the original, three checks (R5)."""

from dataset.statements.compare import check_problem
from dataset.statements.correct import checks, corrected_text
from dataset.statements.extract import statement_block
from tests.dataset.statements.fixtures import (
    BIG_POWER_HTML,
    BIG_POWER_OURS,
    OLD_LEGEND_HTML,
    OLD_LEGEND_OURS,
    enunciado,
    page,
)


def setup(legend_html, legend_ours):
    block = statement_block(page(legend_html))
    ours = enunciado(legend_ours)
    fidelity = check_problem("1_A", block, ours, None)
    return block, ours, fidelity


def test_the_marks_are_inserted_and_nothing_else_changes():
    block, ours, fidelity = setup(OLD_LEGEND_HTML, OLD_LEGEND_OURS)
    text, inserted = corrected_text(ours, fidelity)
    assert text == ours.replace("≤ 105)", "≤ 10^{5})").replace("numbers ai.", "numbers a_{i}.")
    assert len(inserted) == 2
    result = checks(block, ours, text, fidelity)
    assert result.passed


def test_a_long_exponent_is_marked_whole():
    block, ours, fidelity = setup(BIG_POWER_HTML, BIG_POWER_OURS)
    text, _ = corrected_text(ours, fidelity)
    assert "0 ≤ n ≤ 10^{100000})" in text
    assert checks(block, ours, text, fidelity).passed


def test_each_check_fails_when_the_correction_is_tampered_with():
    block, ours, fidelity = setup(OLD_LEGEND_HTML, OLD_LEGEND_OURS)
    good, _ = corrected_text(ours, fidelity)
    letter = good.replace("Read n", "Reed n")
    assert not checks(block, ours, letter, fidelity).text_equal
    without_mark = good.replace("a_{i}", "ai")
    assert not checks(block, ours, without_mark, fidelity).all_marks_present
    extra_space = good.replace("One line.", "One  line.")
    assert not checks(block, ours, extra_space, fidelity).only_markup_diff


def test_a_table_becomes_a_markdown_table():
    table = "<table><tr><th>a</th><th>b</th></tr><tr><td>1</td><td>2</td></tr></table>"
    block, ours, fidelity = setup(table, "a b\n1 2")
    assert [d.kind for d in fidelity.differences] == ["table"]
    text, _ = corrected_text(ours, fidelity)
    assert "| a | b |\n|---|---|\n| 1 | 2 |" in text
    result = checks(block, ours, text, fidelity)
    assert result.text_equal and result.all_marks_present
