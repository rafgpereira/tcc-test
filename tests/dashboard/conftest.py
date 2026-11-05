"""An evaluated tree built with the fake engine of the evaluation tests (no C++, no Streamlit).

Two problems; the Gemini black-box suite of ``1_A`` declares a wrong output (so the AC is rejected
and some WAs are caught only by the declared oracle); the Claude hybrid suite of ``2_B`` is
``discarded_manual``; the local model's black box of ``1_A`` comes from ``suites/slm-rev1``; every
first attempt of the local model has tests.
"""

import json

import pytest

from evaluation import config as evaluation_config
from evaluation import problem_task, sources, store
from tests.evaluation.conftest import FakeEngine, double, make_tree, ok, solution_attempt

PROBLEMS = ("1_A", "2_B")
WRONG = {
    "status": "accepted_predicted",
    "tests": [{"input": "1\n", "output": "2\n"}, {"input": "3\n", "output": "7\n"}],
}


def build_evaluated(root):
    attempts = {
        (p, s, 1): solution_attempt(["1\n", "3\n"], ["2\n", "6\n"])
        for p in PROBLEMS
        for s in evaluation_config.SCENARIOS
    }
    make_tree(
        root,
        PROBLEMS,
        slm_attempts=attempts,
        suites={
            ("gemini", "1_A", "black_box"): WRONG,
            ("claude", "2_B", "hybrid"): {"status": "discarded_manual", "tests": []},
        },
        provenance={  # every combination is listed, as in the real file
            (p, s): "suites/slm-rev1" if (p, s) == ("1_A", "black_box") else "suites/slm"
            for p in PROBLEMS
            for s in evaluation_config.SCENARIOS
        },
    )
    for problem, macro in zip(PROBLEMS, ("matematica", "logica_direta"), strict=True):
        path = root / "data/dataset/problems" / problem / "metadata.json"
        metadata = json.loads(path.read_text())
        metadata["macrocategoria"] = macro
        path.write_text(json.dumps(metadata))
    base = root / "data/evaluation"
    engine = FakeEngine({"WA_1": lambda t, n: ok("0\n") if t == "3\n" else double(t)}).engine()
    for problem in PROBLEMS:
        suites = tuple(
            ((s, sc), sources.suite_for(root, s, problem, sc))
            for s in evaluation_config.SETS
            for sc in evaluation_config.SCENARIOS
        )
        task = problem_task.ProblemTask(sources.problem_targets(root, problem), suites)
        grouped = problem_task.group_by_set(problem_task.evaluate_problem(task, engine, 0))
        for set_name, results in grouped.items():
            store.write_problem(base, set_name, problem, results)
    return base


@pytest.fixture
def evaluated(tmp_path, monkeypatch):
    base = build_evaluated(tmp_path)
    monkeypatch.chdir(tmp_path)
    return tmp_path, base
