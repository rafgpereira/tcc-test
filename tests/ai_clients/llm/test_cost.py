"""The cost of a call and the estimate of the dry run (research R9)."""

from datetime import date

import pytest

from ai_clients.llm import config, cost
from ai_clients.llm.schemas import Usage


def usage(i=2000, c=0, o=1500):
    return Usage(input_tokens=i, cached_input_tokens=c, output_tokens=o, reasoning_tokens=1)


def test_the_formula():
    row = cost.price_row_for("gpt", date(2026, 10, 20))
    expected = ((2000 - 500) * 0.75 + 500 * 0.075 + 1500 * 4.50) / 1e6
    assert cost.call_cost(usage(2000, 500, 1500), row) == pytest.approx(expected)


def test_the_gemini_price_doubles_on_2027_01_01():
    before = cost.price_row_for("gemini", date(2026, 12, 31))
    after = cost.price_row_for("gemini", date(2027, 1, 1))
    assert (before.output_per_mtok, after.output_per_mtok) == (3.75, 7.50)
    assert cost.call_cost(usage(), after) == pytest.approx(2 * cost.call_cost(usage(), before))


def test_no_price_before_the_table():
    with pytest.raises(ValueError):
        cost.price_row_for("gpt", date(2026, 1, 1))


def test_the_estimate_uses_the_declared_ratio_and_the_ceiling():
    estimate = cost.Estimate()
    estimate.add("1_A", 3000)
    estimate.add("2_B", 6000)
    assert estimate.largest_prompt == (6000, "2_B")
    assert cost.estimated_input_tokens("gpt", estimate.prompt_chars) == round(9000 / 3.0)
    low, high = cost.cost_range("gpt", estimate, date(2026, 10, 20))
    one = (3000 * 0.75 + 2 * config.MAX_OUTPUT_TOKENS * 4.50) / 1e6
    assert low == pytest.approx(one) and high == pytest.approx(3 * one)


def test_the_claude_price_row():
    row = cost.price_row_for("claude", date(2026, 10, 20))
    assert (row.input_per_mtok, row.cached_input_per_mtok, row.output_per_mtok) == (
        0.10,
        0.01,
        0.50,
    )
    expected = ((2000 - 500) * 0.10 + 500 * 0.01 + 1500 * 0.50) / 1e6
    assert cost.call_cost(usage(2000, 500, 1500), row) == pytest.approx(expected)
    with pytest.raises(ValueError):
        cost.price_row_for("claude", date(2026, 10, 19))  # no price before it was checked
