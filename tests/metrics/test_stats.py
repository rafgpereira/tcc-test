"""The statistical layer against known values (T015–T016)."""

import numpy as np
import pytest
from scipy import stats as sp

from metrics import stats
from tests.metrics.conftest import per_problem_rows, row


def test_a12_and_cliff_by_hand():
    assert stats.a12([3, 4, 5], [1, 2, 3]) == pytest.approx((8 + 0.5) / 9)  # 8 wins, 1 tie
    assert stats.a12([1, 1], [1, 1]) == 0.5


def test_holm_textbook_example():
    assert stats.holm([0.01, 0.04, 0.03]) == [0.03, 0.06, 0.06]
    assert stats.holm([0.5, 0.9]) == [1.0, 1.0]


def test_mcnemar_exact_is_the_binomial_on_discordant_pairs():
    a = [1, 1, 1, 1, 1, 0, 0, 1]
    b = [0, 0, 0, 0, 1, 0, 1, 1]
    statistic, p = stats.mcnemar_exact(a, b)
    assert statistic == 1 and p == sp.binomtest(4, 5, 0.5).pvalue
    assert stats.mcnemar_exact([1, 0], [1, 0]) == (0.0, 1.0)


def test_wilcoxon_and_friedman_match_scipy_and_handle_no_variation():
    rng = np.random.default_rng(1)
    a, b = rng.normal(size=30), rng.normal(size=30) + 1
    assert stats.wilcoxon(a, b)[1] == sp.wilcoxon(a, b).pvalue
    c = rng.normal(size=30)
    assert stats.friedman([a, b, c])[1] == sp.friedmanchisquare(a, b, c).pvalue
    same = np.ones(10)
    assert stats.wilcoxon(same, same) == (0.0, 1.0)
    assert stats.friedman([same, same, same]) == (0.0, 1.0)


def _table(gap):
    rows = []
    for i in range(30):
        p = f"{i + 1}_A"
        base = 20 + (i % 7)
        rows.append(row("gpt", "black_box", p, wa_declared=base))
        rows.append(row("gpt", "white_box", p, wa_declared=base + gap))
        rows.append(row("gpt", "hybrid", p, wa_declared=base + 2 * gap, ac_rejected=i < 12))
    return stats.table(per_problem_rows(rows))


def test_a_built_difference_is_significant_with_effect_size():
    t = _table(gap=10)
    tdf = t[(t["family"] == "scenarios") & (t["metric"] == "TDF")]
    assert tdf.iloc[0]["test"] == "friedman" and tdf.iloc[0]["significant"]
    pairs = tdf[tdf["test"] == "wilcoxon"]
    assert len(pairs) == 3 and pairs["significant"].all()
    hybrid_vs_black = pairs[
        (pairs["group_a"] == "black_box") & (pairs["group_b"] == "hybrid")
    ].iloc[0]
    assert hybrid_vs_black["a12"] < 0.5 and hybrid_vs_black["cliff_delta"] < 0
    tfp = t[(t["family"] == "scenarios") & (t["metric"] == "TFP")]
    assert set(tfp["test"]) == {"mcnemar_exact"}  # binary: no global test


def test_no_difference_gives_no_post_hoc():
    t = _table(gap=0)
    tdf = t[(t["family"] == "scenarios") & (t["metric"] == "TDF")]
    assert len(tdf) == 1 and tdf.iloc[0]["p_value"] == 1.0 and not tdf.iloc[0]["significant"]
