"""Small tables with known values, and a repository with real `results.csv` files.

``per_problem_rows`` builds a per-problem table by hand (the numbers of each test are explicit);
``repo`` reuses the evaluated tree of the dashboard tests (fake engine) and writes the
``results.csv`` of every set with the evaluation's own ``report``.
"""

import json

import pandas as pd
import pytest

from evaluation import config as evaluation_config
from evaluation import report as evaluation_report
from metrics import sources
from tests.dashboard.conftest import build_evaluated


def row(set_name="gpt", scenario="black_box", problem="1_A", **values):
    base = {
        "set": set_name,
        "scenario": scenario,
        "problem": problem,
        "macrocategoria": "matematica",
        "status": "accepted",
        "has_suite": True,
        "suite_size": 10,
        "ac_rejected": False,
        "ac_wrong_output_tests": 0,
        "ac_runtime_error_tests": 0,
        "n_wa": 100,
        "n_mutants": 100,
        "wa_declared": 0,
        "wa_corrected": 0,
        "mutants_declared": 0,
        "mutants_corrected": 0,
    }
    base.update(values)
    return base


def per_problem_rows(rows) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=list(sources.PER_PROBLEM_COLUMNS))


def write_generation_reports(root):
    for model, cost in (("gpt", 3.0), ("gemini", 1.5), ("claude", 0.3)):
        report = {
            "cost_usd": {
                "by_group": {s: cost / 3 for s in evaluation_config.SCENARIOS} | {"total": cost},
                "total": cost,
            },
            "tokens": {
                s: {"input": 100, "cached_input": 10, "output": 50, "reasoning": 40}
                for s in evaluation_config.SCENARIOS
            },
        }
        path = root / f"manifests/{model}_generation_report.json"
        path.write_text(json.dumps(report))
    (root / "manifests/slm_generation_report.json").write_text("{}")


@pytest.fixture
def repo(tmp_path, monkeypatch):
    base = build_evaluated(tmp_path)
    for set_name in evaluation_config.SETS:
        evaluation_report.write_outputs(tmp_path, base, set_name)
    write_generation_reports(tmp_path)
    monkeypatch.chdir(tmp_path)
    return tmp_path
