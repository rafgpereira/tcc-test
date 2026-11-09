"""Índice de Influência do Contexto (FR-005; proposal B.3).

D(R), D(C), D(H): sets of (problem, WA) detected in black box, white box and hybrid. The pooled
IIC (over all problems of the cut) is the official one; the per-problem view excludes, and counts,
the problems whose base is empty. Computed for both oracles (research R4).
"""

import numpy as np
import pandas as pd

from metrics import config

COLUMNS = (
    "set",
    "oracle",
    "direction",
    "iic_pooled",
    "gains",
    "losses",
    "base_size",
    "per_problem_median",
    "per_problem_q1",
    "per_problem_q3",
    "positive",
    "negative",
    "zero",
    "excluded",
)
BASE = {
    "cod": "black_box",
    "req": "white_box",
}  # IIC_cod: hybrid over black box; IIC_req: over white


def _iic(hybrid: set, base: set) -> tuple[float, int, int]:
    gains, losses = len(hybrid - base), len(base - hybrid)
    value = 100 * (gains - losses) / len(base) if base else float("nan")
    return value, gains, losses


def _sets(detected: pd.DataFrame, scenario: str) -> set:
    rows = detected[detected["scenario"] == scenario]
    return set(zip(rows["problem"], rows["target"], strict=True))


def per_problem_values(
    detected_wa: pd.DataFrame, set_name: str, oracle: str, direction: str, problems
) -> tuple[list[float], int]:
    """IIC of each problem with a non-empty base, and how many problems were excluded."""
    mine = detected_wa[(detected_wa["set"] == set_name) & (detected_wa["oracle"] == oracle)]
    values, excluded = [], 0
    for problem in sorted(problems):
        one = mine[mine["problem"] == problem]
        value, _, _ = _iic(_sets(one, "hybrid"), _sets(one, BASE[direction]))
        if np.isnan(value):
            excluded += 1
        else:
            values.append(value)
    return values, excluded


def table(detected_wa: pd.DataFrame, per_problem: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for set_name in config.SETS:
        problems = set(per_problem.loc[per_problem["set"] == set_name, "problem"])
        if not problems:
            continue
        for oracle in ("declared", "corrected"):
            mine = detected_wa[
                (detected_wa["set"] == set_name)
                & (detected_wa["oracle"] == oracle)
                & detected_wa["problem"].isin(problems)
            ]
            for direction in ("cod", "req"):
                base = _sets(mine, BASE[direction])
                value, gains, losses = _iic(_sets(mine, "hybrid"), base)
                values, excluded = per_problem_values(
                    detected_wa, set_name, oracle, direction, problems
                )
                arr = np.array(values)
                rows.append(
                    {
                        "set": set_name,
                        "oracle": oracle,
                        "direction": direction,
                        "iic_pooled": value,
                        "gains": gains,
                        "losses": losses,
                        "base_size": len(base),
                        "per_problem_median": float(np.median(arr)) if len(arr) else float("nan"),
                        "per_problem_q1": (
                            float(np.percentile(arr, 25)) if len(arr) else float("nan")
                        ),
                        "per_problem_q3": (
                            float(np.percentile(arr, 75)) if len(arr) else float("nan")
                        ),
                        "positive": int((arr > 0).sum()),
                        "negative": int((arr < 0).sum()),
                        "zero": int((arr == 0).sum()),
                        "excluded": excluded,
                    }
                )
    frame = pd.DataFrame(rows, columns=list(COLUMNS))
    for column in ("iic_pooled", "per_problem_median", "per_problem_q1", "per_problem_q3"):
        frame[column] = frame[column].round(config.DECIMALS)
    return frame
