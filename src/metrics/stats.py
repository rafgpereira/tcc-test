"""Statistical layer (FR-011; proposal D; research R3).

Paired by problem. Families: ``scenarios`` (the 3 scenarios of each set: Friedman, then Wilcoxon
pairs with Holm if significant), ``models`` (the 4 models in each scenario: idem) and ``attempt1``
(``slm-attempt1`` against each model, Wilcoxon with Holm). The TFP is binary: only pairs, with the
exact McNemar test (two-sided binomial on the discordant pairs) and Holm. Effect size: A12 of
Vargha-Delaney and Cliff's delta (2·A12 − 1) on every pairwise row.
"""

from itertools import combinations

import numpy as np
import pandas as pd
from scipy import stats as sp

from metrics import config
from metrics.primary import per_problem_values

COLUMNS = (
    "family",
    "metric",
    "scope",
    "group_a",
    "group_b",
    "test",
    "statistic",
    "p_value",
    "p_adjusted",
    "significant",
    "a12",
    "cliff_delta",
    "n_pairs",
)
CONTINUOUS = ("TDF", "MS", "TDF_star", "MS_star")


def a12(x, y) -> float:
    """P(X > Y) + 0.5·P(X = Y) over all pairs (Vargha-Delaney)."""
    x, y = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    ranks = sp.rankdata(np.concatenate([x, y]))
    m, n = len(x), len(y)
    return float((ranks[:m].sum() / m - (m + 1) / 2) / n)


def holm(p_values) -> list[float]:
    """Holm-Bonferroni adjusted p-values, in the original order."""
    p = np.asarray(p_values, dtype=float)
    order = np.argsort(p, kind="stable")
    k = len(p)
    adjusted = np.empty(k)
    running = 0.0
    for rank, index in enumerate(order):
        running = max(running, min(1.0, (k - rank) * p[index]))
        adjusted[index] = running
    return adjusted.tolist()


def mcnemar_exact(a, b) -> tuple[float, float]:
    """(min of the discordant counts, two-sided exact p) for paired binary samples."""
    a, b = np.asarray(a, dtype=int), np.asarray(b, dtype=int)
    only_a, only_b = int(((a == 1) & (b == 0)).sum()), int(((a == 0) & (b == 1)).sum())
    n = only_a + only_b
    if n == 0:
        return 0.0, 1.0
    return float(min(only_a, only_b)), float(sp.binomtest(only_a, n, 0.5).pvalue)


def wilcoxon(a, b) -> tuple[float, float]:
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    if np.allclose(a, b):
        return 0.0, 1.0
    result = sp.wilcoxon(a, b, zero_method="wilcox", alternative="two-sided")
    return float(result.statistic), float(result.pvalue)


def friedman(samples) -> tuple[float, float]:
    matrix = np.column_stack(samples)
    if np.all(matrix == matrix[:, [0]]):
        return 0.0, 1.0
    result = sp.friedmanchisquare(*samples)
    if np.isnan(result.pvalue):
        return 0.0, 1.0
    return float(result.statistic), float(result.pvalue)


def _aligned(values: pd.DataFrame, metric: str, groups: list[tuple[str, str]]) -> list[np.ndarray]:
    """One vector per (set, scenario) group, aligned by problem."""
    vectors = []
    for set_name, scenario in groups:
        rows = values[(values["set"] == set_name) & (values["scenario"] == scenario)]
        vectors.append(rows.set_index("problem")[metric])
    common = sorted(set.intersection(*(set(v.index) for v in vectors)))
    return [v.loc[common].to_numpy() for v in vectors]


def _pairs(family, metric, scope, labels, vectors, pairs) -> list[dict]:
    rows = []
    for i, j in pairs:
        if metric == "TFP":
            test, (statistic, p) = "mcnemar_exact", mcnemar_exact(vectors[i], vectors[j])
        else:
            test, (statistic, p) = "wilcoxon", wilcoxon(vectors[i], vectors[j])
        effect = a12(vectors[i], vectors[j])
        rows.append(
            {
                "family": family,
                "metric": metric,
                "scope": scope,
                "group_a": labels[i],
                "group_b": labels[j],
                "test": test,
                "statistic": statistic,
                "p_value": p,
                "a12": effect,
                "cliff_delta": 2 * effect - 1,
                "n_pairs": len(vectors[i]),
            }
        )
    for row, adjusted in zip(rows, holm([r["p_value"] for r in rows]), strict=True):
        row["p_adjusted"] = adjusted
        row["significant"] = adjusted < config.ALPHA
    return rows


def _family(family, metric, scope, labels, groups, values, global_test: bool) -> list[dict]:
    vectors = _aligned(values, metric, groups)
    if any(len(v) == 0 for v in vectors):
        return []
    all_pairs = list(combinations(range(len(labels)), 2))
    if metric == "TFP" or not global_test:
        return _pairs(family, metric, scope, labels, vectors, all_pairs)
    statistic, p = friedman(vectors)
    rows = [
        {
            "family": family,
            "metric": metric,
            "scope": scope,
            "group_a": "*",
            "group_b": "*",
            "test": "friedman",
            "statistic": statistic,
            "p_value": p,
            "p_adjusted": p,
            "significant": p < config.ALPHA,
            "a12": float("nan"),
            "cliff_delta": float("nan"),
            "n_pairs": len(vectors[0]),
        }
    ]
    if p < config.ALPHA:
        rows += _pairs(family, metric, scope, labels, vectors, all_pairs)
    return rows


def table(per_problem: pd.DataFrame) -> pd.DataFrame:
    values = per_problem_values(per_problem)
    present = set(zip(values["set"], values["scenario"], strict=True))
    rows = []
    for metric in (*CONTINUOUS, "TFP"):
        for set_name in config.SETS:
            groups = [(set_name, s) for s in config.SCENARIOS if (set_name, s) in present]
            if len(groups) >= 2:
                labels = [g[1] for g in groups]
                rows += _family("scenarios", metric, set_name, labels, groups, values, True)
        for scenario in config.SCENARIOS:
            groups = [(m, scenario) for m in config.MODELS if (m, scenario) in present]
            if len(groups) >= 2:
                labels = [g[0] for g in groups]
                rows += _family("models", metric, scenario, labels, groups, values, True)
            if ("slm-attempt1", scenario) in present and groups:
                pair_groups = [("slm-attempt1", scenario), *groups]
                vectors = _aligned(values, metric, pair_groups)
                labels = ["slm-attempt1", *(g[0] for g in groups)]
                rows += _pairs(
                    "attempt1",
                    metric,
                    scenario,
                    labels,
                    vectors,
                    [(0, j) for j in range(1, len(labels))],
                )
    frame = pd.DataFrame(rows, columns=list(COLUMNS))
    for column in ("statistic", "p_value", "p_adjusted", "a12", "cliff_delta"):
        frame[column] = frame[column].astype(float).round(6)
    return frame
