"""Cost, tokens, time and cost per detection per set × scenario (FR-009; research R5).

Commercial models: cost and tokens of ``manifests/<model>_generation_report.json`` (``cost_usd``
``by_group``, which includes repeated requests, plus the barred answers of the scenario); time = sum of ``latency_s`` of the
attempts and barred answers of the scenario. Local model: tokens and time of every attempt of the
tree in force (only attempt 1 for ``slm-attempt1``), never converted to US$.
"""

import json
import math
from pathlib import Path

import pandas as pd

from metrics import config

COLUMNS = (
    "set",
    "scenario",
    "cost_usd",
    "input_tokens",
    "output_tokens",
    "duration_s",
    "cpd_wa_declared",
    "cpd_wa_corrected",
    "cpd_mutants_declared",
    "cpd_mutants_corrected",
)


def _json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _slm_tree(root: Path) -> dict[tuple[str, str], str]:
    path = Path(root) / "data/suites/slm/provenance.json"
    if not path.is_file():
        return {}
    return {
        (e["problem_id"], e["scenario"]): e["tree"]
        for e in _json(path)["combinations"]
        if not e.get("superseded_in")
    }


def _slm_usage(root: Path, scenario: str, problems, only_first: bool) -> tuple[int, int, float]:
    trees = _slm_tree(root)
    tokens_in = tokens_out = 0
    duration_ns = 0
    for problem in problems:
        tree = trees.get((problem, scenario), "suites/slm")
        folder = Path(root) / "data" / tree / "problems" / problem / scenario
        pattern = "attempt_1.generation.json" if only_first else "attempt_*.generation.json"
        for path in sorted(folder.glob(pattern)):
            ollama = _json(path).get("ollama") or {}
            tokens_in += int(ollama.get("prompt_eval_count", 0))
            tokens_out += int(ollama.get("eval_count", 0))
            duration_ns += int(ollama.get("total_duration_ns", 0))
    return tokens_in, tokens_out, duration_ns / 1e9


def _commercial_extra(root: Path, model: str, scenario: str, problems) -> tuple[float, float]:
    """(latency of attempts and barred answers, cost of the barred answers) of the scenario.

    ``cost_usd.by_group`` of the generation report leaves the barred answers out (they are
    ``barred_cost_usd``); they are added here, per scenario, so the costs sum to the report total.
    """
    latency = barred_cost = 0.0
    base = Path(root) / "data/suites" / model
    for problem in problems:
        for path in sorted((base / "problems" / problem / scenario).glob("attempt_*.json")):
            latency += float(_json(path).get("latency_s") or 0.0)
        for path in sorted((base / "barred" / problem / scenario).glob("*.json")):
            record = _json(path)
            latency += float(record.get("latency_s") or 0.0)
            barred_cost += float(record.get("cost_usd") or 0.0)
    return latency, barred_cost


def _cpd(cost, detected) -> float:
    return float(cost / detected) if not math.isnan(cost) and detected else float("nan")


def table(root: Path, per_problem: pd.DataFrame) -> pd.DataFrame:
    root = Path(root)
    rows = []
    for set_name in config.SETS:
        model = config.SET_MODEL[set_name]
        report_path = root / config.generation_report(model)
        report = _json(report_path) if report_path.is_file() else {}
        for scenario in config.SCENARIOS:
            group = per_problem[
                (per_problem["set"] == set_name) & (per_problem["scenario"] == scenario)
            ]
            if group.empty:
                continue
            problems = sorted(group["problem"])
            if model in config.COMMERCIAL:
                cost = float(
                    report.get("cost_usd", {}).get("by_group", {}).get(scenario, float("nan"))
                )
                tokens = report.get("tokens", {}).get(scenario, {})
                tokens_in = int(tokens.get("input", 0)) + int(tokens.get("cached_input", 0))
                tokens_out = int(tokens.get("output", 0))
                duration, barred_cost = _commercial_extra(root, model, scenario, problems)
                cost += barred_cost
            else:
                cost = float("nan")  # the local model is never converted to US$
                tokens_in, tokens_out, duration = _slm_usage(
                    root, scenario, problems, only_first=set_name == "slm-attempt1"
                )
            rows.append(
                {
                    "set": set_name,
                    "scenario": scenario,
                    "cost_usd": cost,
                    "input_tokens": tokens_in,
                    "output_tokens": tokens_out,
                    "duration_s": duration,
                    "cpd_wa_declared": _cpd(cost, group["wa_declared"].sum()),
                    "cpd_wa_corrected": _cpd(cost, group["wa_corrected"].sum()),
                    "cpd_mutants_declared": _cpd(cost, group["mutants_declared"].sum()),
                    "cpd_mutants_corrected": _cpd(cost, group["mutants_corrected"].sum()),
                }
            )
    frame = pd.DataFrame(rows, columns=list(COLUMNS))
    frame["duration_s"] = frame["duration_s"].astype(float).round(3)
    for column in ("cost_usd", "cpd_wa_declared", "cpd_wa_corrected"):
        frame[column] = frame[column].astype(float).round(8)
    for column in ("cpd_mutants_declared", "cpd_mutants_corrected"):
        frame[column] = frame[column].astype(float).round(8)
    return frame
