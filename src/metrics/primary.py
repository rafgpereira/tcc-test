"""TDF, MS, TFP, TC and the complementary C.1, C.2, C.4 per set × scenario (FR-003 to FR-010).

All values are percentages. TDF and MS are means over the problems of the cut; since every problem
has 100 WAs and 100 mutants, the mean of the ratios equals the ratio of the sums (proposal B.3).
"""

import numpy as np
import pandas as pd

from metrics import config

COLUMNS = (
    "set",
    "scenario",
    "problems",
    "TC",
    "TDF",
    "MS",
    "TFP",
    "TFP_with_suite",
    "without_suite",
    "TDF_star",
    "MS_star",
    "delta_TDF",
    "delta_MS",
    "TFP_test",
    "FP_tests_oracle",
    "FP_tests_invalid_input",
    "total_tests",
    "mean_suite_size",
    "density_TDF",
)


def per_problem_values(per_problem: pd.DataFrame) -> pd.DataFrame:
    """The per-problem percentages the means and the paired tests use."""
    out = per_problem[["set", "scenario", "problem", "has_suite"]].copy()
    out["TDF"] = 100 * per_problem["wa_declared"] / per_problem["n_wa"]
    out["MS"] = 100 * per_problem["mutants_declared"] / per_problem["n_mutants"]
    out["TDF_star"] = 100 * per_problem["wa_corrected"] / per_problem["n_wa"]
    out["MS_star"] = 100 * per_problem["mutants_corrected"] / per_problem["n_mutants"]
    out["TFP"] = per_problem["ac_rejected"].astype(int)  # binary per problem
    return out


def _ratio(numerator: float, denominator: float) -> float:
    return float(100 * numerator / denominator) if denominator else float("nan")


def _row(group: pd.DataFrame, values: pd.DataFrame) -> dict:
    problems = len(group)
    with_suite = group["has_suite"]
    n_with = int(with_suite.sum())
    rejected = int(group["ac_rejected"].sum())
    oracle = int(group["ac_wrong_output_tests"].sum())
    invalid = int(group["ac_runtime_error_tests"].sum())
    total = int(group["suite_size"].sum())
    mean_size = float(group.loc[with_suite, "suite_size"].mean()) if n_with else float("nan")
    tdf, ms = float(values["TDF"].mean()), float(values["MS"].mean())
    tdf_s, ms_s = float(values["TDF_star"].mean()), float(values["MS_star"].mean())
    return {
        "problems": problems,
        "TC": _ratio(n_with, problems),
        "TDF": tdf,
        "MS": ms,
        "TFP": _ratio(rejected, problems),
        "TFP_with_suite": _ratio(rejected, n_with),
        "without_suite": problems - n_with,
        "TDF_star": tdf_s,
        "MS_star": ms_s,
        "delta_TDF": tdf - tdf_s,
        "delta_MS": ms - ms_s,
        "TFP_test": _ratio(oracle + invalid, total),
        "FP_tests_oracle": oracle,
        "FP_tests_invalid_input": invalid,
        "total_tests": total,
        "mean_suite_size": mean_size,
        "density_TDF": tdf / mean_size if n_with and mean_size else float("nan"),
    }


def table(per_problem: pd.DataFrame) -> pd.DataFrame:
    """One row per set × scenario present in the (possibly cut) per-problem table."""
    values = per_problem_values(per_problem)
    rows = []
    for set_name in config.SETS:
        for scenario in config.SCENARIOS:
            mask = (per_problem["set"] == set_name) & (per_problem["scenario"] == scenario)
            if not mask.any():
                continue
            rows.append(
                {"set": set_name, "scenario": scenario, **_row(per_problem[mask], values[mask])}
            )
    frame = pd.DataFrame(rows, columns=list(COLUMNS))
    numeric = frame.select_dtypes(include=[np.number]).columns
    frame[numeric] = frame[numeric].round(config.DECIMALS)
    return frame
