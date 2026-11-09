"""From the evaluation's ``results.csv`` to the two base tables (research R1, R2; data-model.md).

``per_problem``: one row per set × scenario × problem with the counts every metric needs.
``detected_wa``: one row per WA detected, per oracle (the sets the IIC operates on). A combination
without a suite has zero detections and ``n_wa = n_mutants = 100``, so it counts 0% in TDF and MS
(rule B.1 of the methodology).
"""

import json
from pathlib import Path

import pandas as pd

from metrics import config

PER_PROBLEM_COLUMNS = (
    "set",
    "scenario",
    "problem",
    "macrocategoria",
    "status",
    "has_suite",
    "suite_size",
    "ac_rejected",
    "ac_wrong_output_tests",
    "ac_runtime_error_tests",
    "n_wa",
    "n_mutants",
    "wa_declared",
    "wa_corrected",
    "mutants_declared",
    "mutants_corrected",
)
DETECTED_COLUMNS = ("set", "scenario", "problem", "target", "oracle")


def _macrocategorias(root: Path, problems) -> dict[str, str]:
    out = {}
    for problem in problems:
        path = Path(root) / config.DATASET_PROBLEMS_DIR / problem / "metadata.json"
        try:
            out[problem] = json.loads(path.read_text(encoding="utf-8")).get("macrocategoria", "")
        except (OSError, ValueError):
            out[problem] = ""
    return out


def _true(series: pd.Series) -> pd.Series:
    return series.astype(str).str.lower() == "true"


def _int(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series.replace("", "0"), errors="coerce").fillna(0).astype(int)


def _read_set(path: Path, set_name: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    raw = pd.read_csv(path, dtype=str, keep_default_na=False)
    raw["has_suite"] = _true(raw["has_suite"])
    raw["is_wa"] = raw["kind"] == "wa"
    raw["is_mutant"] = raw["kind"] == "mutant"
    raw["dec"] = _true(raw["declared_detected"])
    raw["cor"] = _true(raw["corrected_detected"])
    keys = ["problem_id", "scenario"]
    first = raw.groupby(keys, sort=True).first()
    raw["wa_declared"] = raw["dec"] & raw["is_wa"]
    raw["wa_corrected"] = raw["cor"] & raw["is_wa"]
    raw["mutants_declared"] = raw["dec"] & raw["is_mutant"]
    raw["mutants_corrected"] = raw["cor"] & raw["is_mutant"]
    counted = ["wa_declared", "wa_corrected", "mutants_declared", "mutants_corrected"]
    counts = (
        raw.groupby(keys, sort=True)[["is_wa", "is_mutant", *counted]]
        .sum()
        .rename(columns={"is_wa": "n_wa", "is_mutant": "n_mutants"})
        .astype(int)
    )
    per = pd.DataFrame(
        {
            "set": set_name,
            "status": first["suite_status"],
            "has_suite": first["has_suite"],
            "suite_size": _int(first["suite_size"]),
            "ac_rejected": first["has_suite"] & (first["ac_approved"].str.lower() == "false"),
            "ac_wrong_output_tests": _int(first["ac_wrong_output_tests"]),
            "ac_runtime_error_tests": _int(first["ac_runtime_error_tests"]),
        }
    ).join(counts)
    without = ~per["has_suite"]
    per.loc[without, "n_wa"] = config.WA_PER_PROBLEM
    per.loc[without, "n_mutants"] = config.MUTANTS_PER_PROBLEM
    per = per.reset_index().rename(columns={"problem_id": "problem"})
    detected = []
    for oracle, column in (("declared", "dec"), ("corrected", "cor")):
        rows = raw[raw["is_wa"] & raw[column]]
        detected.append(
            pd.DataFrame(
                {
                    "set": set_name,
                    "scenario": rows["scenario"],
                    "problem": rows["problem_id"],
                    "target": rows["target"],
                    "oracle": oracle,
                }
            )
        )
    return per, pd.concat(detected, ignore_index=True)


def _order(frame: pd.DataFrame) -> pd.DataFrame:
    rank_set = {s: i for i, s in enumerate(config.SETS)}
    rank_sc = {s: i for i, s in enumerate(config.SCENARIOS)}
    keys = frame.assign(_s=frame["set"].map(rank_set), _c=frame["scenario"].map(rank_sc))
    extra = [c for c in ("problem", "target", "oracle") if c in frame.columns]
    return keys.sort_values(["_s", "_c", *extra]).drop(columns=["_s", "_c"]).reset_index(drop=True)


def load(
    root: Path = Path("."), evaluation_dir: Path = config.EVALUATION_DIR, sets=config.SETS
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """``(per_problem, detected_wa)`` from ``<evaluation_dir>/<set>/results.csv``."""
    root = Path(root)
    pers, detected = [], []
    for set_name in sets:
        path = root / evaluation_dir / set_name / "results.csv"
        per, det = _read_set(path, set_name)
        pers.append(per)
        detected.append(det)
    per_problem = pd.concat(pers, ignore_index=True)
    macro = _macrocategorias(root, sorted(set(per_problem["problem"])))
    per_problem["macrocategoria"] = per_problem["problem"].map(macro)
    for column in ("n_wa", "n_mutants"):
        per_problem[column] = per_problem[column].astype(int)
    per_problem = _order(per_problem[list(PER_PROBLEM_COLUMNS)])
    detected_wa = _order(pd.concat(detected, ignore_index=True)[list(DETECTED_COLUMNS)])
    return per_problem, detected_wa
