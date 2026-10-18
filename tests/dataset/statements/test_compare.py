"""The original aligned with enunciado.md; each difference classified by the original (R3)."""

from collections import Counter

from dataset.statements.compare import check_problem, cut_examples
from dataset.statements.extract import statement_block
from tests.dataset.statements.fixtures import (
    BIG_POWER_HTML,
    BIG_POWER_OURS,
    NEW_LEGEND_HTML,
    NEW_LEGEND_OURS,
    OLD_LEGEND_HTML,
    OLD_LEGEND_OURS,
    enunciado,
    page,
)


def check(legend_html, legend_ours, **kw):
    ours = enunciado(legend_ours, **kw)
    return check_problem("1_A", statement_block(page(legend_html, **kw)), ours, None), ours


def kinds(result):
    return Counter(d.kind for d in result.differences)


def test_the_examples_block_is_cut_until_the_note():
    text = enunciado("L.")
    kept, where = cut_examples(text)
    assert "Examples" not in kept and "Note\n\nIt works." in kept
    assert all(text[where[i]] == kept[i] for i in range(len(kept)))
    kept, _ = cut_examples(enunciado("L.", note=None))
    assert kept.rstrip().endswith("One number.")


def test_lost_exponent_and_index_with_where_they_are_in_our_text():
    result, ours = check(OLD_LEGEND_HTML, OLD_LEGEND_OURS)
    assert result.status == "losses" and result.format == "marked"
    assert kinds(result) == {"lost_exponent": 1, "lost_index": 1}
    exponent = next(d for d in result.differences if d.kind == "lost_exponent")
    assert exponent.original.endswith("10^{5}") and exponent.ours.endswith("105")
    assert ours[exponent.ours_offset : exponent.ours_offset + exponent.ours_length] == "5"
    index = next(d for d in result.differences if d.kind == "lost_index")
    assert ours[index.ours_offset : index.ours_offset + index.ours_length] == "i"


def test_a_long_exponent():
    result, ours = check(BIG_POWER_HTML, BIG_POWER_OURS)
    (d,) = result.differences
    assert d.kind == "lost_exponent" and d.original.endswith("10^{100000}")
    assert ours[d.ours_offset : d.ours_offset + d.ours_length] == "100000"


def test_the_new_format_without_loss_is_faithful():
    result, _ = check(NEW_LEGEND_HTML, NEW_LEGEND_OURS)
    assert result.status == "faithful" and result.format == "latex" and result.differences == []


def test_only_spaces_and_the_header_do_not_count():
    result, _ = check("1&thinsp;≤&thinsp;<i>n</i>", "1 ≤ n")
    assert result.status == "faithful"


def test_an_unknown_formula_an_image_a_table_and_a_changed_word():
    assert kinds(check(r"$$$\frac{x}{y}$$$", "(x)/(y)")[0]) == {"formula": 1}
    assert kinds(check(r"$$$2 \cdot 10^5$$$", "2 ⋅ 10^5")[0]) == {}  # a measured equivalence
    assert kinds(check('See <img src="a.png"/> here.', "See here.")[0]) == {"image": 1}
    table = "<table><tr><td>1</td><td>2</td></tr></table>"
    assert kinds(check(table, "1 2")[0]) == {"table": 1}
    result, _ = check("The cat sleeps.", "The dog sleeps.")
    (d,) = result.differences
    assert d.kind == "other" and "cat" in d.original and "dog" in d.ours


def test_without_a_block_or_a_copy_it_is_unchecked():
    unchecked = check_problem("1_A", None, enunciado("L."), "http_404")
    assert (unchecked.status, unchecked.unchecked_reason) == ("unchecked", "http_404")
    broken = check_problem("1_A", '<div class="problem-statement"><p>x</p></div>', "x", None)
    assert broken.unchecked_reason == "no_statement_block"
