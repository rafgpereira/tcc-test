"""One problem: compile once, AC first, targets one at a time, no-suite combinations (T014, T019)."""

import random

import pytest

from evaluation import problem_task, runtime, sources
from sandbox.types import InfraError
from tests.evaluation.conftest import FakeEngine, double, make_tree, ok, tle

KEYS = [("gpt", "black_box"), ("gpt", "hybrid"), ("claude", "black_box")]


def task_for(root, keys=KEYS, problem="1_A"):
    suites = tuple((key, sources.suite_for(root, key[0], problem, key[1])) for key in keys)
    return problem_task.ProblemTask(sources.problem_targets(root, problem), suites)


def test_each_program_is_compiled_once_for_every_suite(tmp_path):
    make_tree(tmp_path, was=2, mutants=2)
    fake = FakeEngine()
    results = problem_task.evaluate_problem(task_for(tmp_path), fake.engine(), 0)
    assert fake.compiled == ["AC", "WA_1", "WA_2", "Mutant_1", "Mutant_2"]
    assert set(results) == set(KEYS)
    for result in results.values():
        assert [t.target for t in result.targets] == ["WA_1", "WA_2", "Mutant_1", "Mutant_2"]
        assert result.ac.approved and result.has_suite


def test_ac_runs_every_suite_before_any_target(tmp_path):
    make_tree(tmp_path)
    fake = FakeEngine()
    problem_task.evaluate_problem(task_for(tmp_path), fake.engine(), 0)
    programs = [name for name, _ in fake.runs]
    last_ac = max(i for i, name in enumerate(programs) if name == "AC")
    assert all(name == "AC" for name in programs[: last_ac + 1])


def test_a_target_that_does_not_compile_is_never_detected(tmp_path):
    make_tree(tmp_path)
    (tmp_path / "data/mutants/problems/1_A/Mutant_2.cpp").write_text("prog:CE")
    results = problem_task.evaluate_problem(task_for(tmp_path), FakeEngine().engine(), 0)
    for result in results.values():
        bad = result.targets[-1]
        assert (bad.target, bad.compiled, bad.declared.detected) == ("Mutant_2", False, False)


def test_ac_that_does_not_compile_is_an_infrastructure_failure(tmp_path):
    make_tree(tmp_path)
    (tmp_path / "data/dataset/problems/1_A/AC_ref.cpp").write_text("prog:CE")
    with pytest.raises(InfraError):
        problem_task.evaluate_problem(task_for(tmp_path), FakeEngine().engine(), 0)


def test_a_combination_without_a_suite_runs_nothing(tmp_path):
    closed = {"status": "discarded_manual", "tests": []}
    make_tree(tmp_path, suites={("claude", "1_A", "black_box"): closed})
    fake = FakeEngine()
    results = problem_task.evaluate_problem(
        task_for(tmp_path, [("claude", "black_box")]), fake.engine(), 0
    )
    result = results[("claude", "black_box")]
    assert (result.has_suite, result.no_suite_reason, result.ac) == (
        False,
        "discarded_manual",
        None,
    )
    assert fake.compiled == [] and fake.runs == []


def test_detection_and_corrected_counts(tmp_path):
    wrong = {
        "status": "accepted_predicted",
        "tests": [{"input": "1\n", "output": "3\n"}, {"input": "2\n", "output": "4\n"}],
    }
    make_tree(tmp_path, suites={("gpt", "1_A", "black_box"): wrong})
    fake = FakeEngine({"WA_2": lambda t, n: ok("0\n") if t == "2\n" else double(t)})
    result = problem_task.evaluate_problem(
        task_for(tmp_path, [("gpt", "black_box")]), fake.engine(), 0
    )[("gpt", "black_box")]
    assert not result.ac.approved
    assert result.detected.declared_wa == ["WA_1", "WA_2"]  # test 0 declares 3: everyone fails
    assert result.detected.corrected_wa == ["WA_2"]
    assert result.detected.declared_mutants == ["Mutant_1", "Mutant_2"]
    assert result.detected.corrected_mutants == []
    assert (result.corrected_oracle_tests, result.corrected_oracle_excluded) == (2, 0)


def test_the_order_of_the_suites_does_not_change_the_result(tmp_path):
    make_tree(tmp_path)
    programs = {"WA_1": lambda t, n: tle() if t == "3\n" else double(t)}
    a = problem_task.evaluate_problem(task_for(tmp_path, KEYS), FakeEngine(programs).engine(), 0)
    b = problem_task.evaluate_problem(
        task_for(tmp_path, KEYS[::-1]), FakeEngine(programs).engine(), 0
    )
    strip = {"elapsed_s": True}
    assert {k: v.model_dump(exclude=strip) for k, v in a.items()} == {
        k: v.model_dump(exclude=strip) for k, v in b.items()
    }


def test_inline_and_threads_give_the_same_results(tmp_path):
    """FR-016: the result does not depend on the number of workers nor on the completion order."""
    problems = ("1_A", "2_B", "3_C", "4_D")
    make_tree(tmp_path, problems)
    programs = {"WA_1": lambda t, n: ok("0\n") if t == "3\n" else double(t)}
    tasks = [task_for(tmp_path, KEYS, p) for p in problems]

    def collect(rt, order):
        futures = {p: rt.submit(tasks[problems.index(p)]) for p in order}
        out = {
            p: {k: v.model_dump(exclude={"elapsed_s": True}) for k, v in f.result().items()}
            for p, f in futures.items()
        }
        rt.close()
        return out

    inline = collect(runtime.InlineRuntime(FakeEngine(programs).engine()), problems)
    shuffled = list(problems)
    random.Random(7).shuffle(shuffled)
    threads = collect(runtime.ThreadRuntime(FakeEngine(programs).engine(), 3), shuffled)
    assert inline == threads
