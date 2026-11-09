"""Integration test: a tiny problem judged by the real engine (service `sandbox`; T015, T024).

Nothing here is faked: AC, WA and mutant go through GCC 13.2, the isolation and the limits. The
suite declares a wrong output on one test, so the AC is rejected there, a WA that behaves like the
AC on that test is detected only by the declared oracle, and a WA with a real bug is detected by
both.
"""

import pytest

from evaluation import problem_task
from evaluation.schemas.result import SuiteSource
from evaluation.sources import ProblemTargets, SuiteToEvaluate, Target
from sandbox import isolation
from sandbox.types import ExecutionLimits, Test

pytestmark = pytest.mark.integration

SLOT = 0
LIMITS = ExecutionLimits(time_limit_seconds=2.0, memory_limit_bytes=256 * 1024 * 1024)


def program(body: str) -> str:
    return "#include <iostream>\nint main() { long long n; std::cin >> n; " + body + " }\n"


AC = program('std::cout << 2 * n << "\\n"; return 0;')
WA_LIKE_AC = AC  # a "WA" equal to the AC: only a wrong declared output can "detect" it
WA_BUG = program('std::cout << (n == 3 ? 7 : 2 * n) << "\\n"; return 0;')
MUTANT_LOOP = program('if (n == 4) { while (true) {} } std::cout << 2 * n << "\\n"; return 0;')

SUITE = (Test("1\n", "2\n"), Test("2\n", "5\n"), Test("3\n", "6\n"), Test("4\n", "8\n"))


@pytest.fixture(scope="module")
def results():
    isolation.prepare_slot_workdir(SLOT)
    problem = ProblemTargets(
        problem_id="1_A",
        ac_source=AC,
        targets=(
            Target("WA_1", "wa", WA_LIKE_AC),
            Target("WA_2", "wa", WA_BUG),
            Target("Mutant_1", "mutant", MUTANT_LOOP),
        ),
        limits=LIMITS,
    )
    suite = SuiteToEvaluate(
        SUITE, SuiteSource(status="accepted_predicted", tree="suites/gpt"), None
    )
    task = problem_task.ProblemTask(problem, ((("gpt", "black_box"), suite),))
    return problem_task.evaluate_problem(task, problem_task.real_engine(), SLOT)[
        ("gpt", "black_box")
    ]


def test_the_ac_is_rejected_on_the_wrong_declared_output_and_runs_every_test(results):
    assert [t.verdict for t in results.ac.tests] == ["passed", "wrong_output", "passed", "passed"]
    assert results.ac.tests[1].actual_output.strip() == "4"
    assert not results.ac.approved


def test_a_target_equal_to_the_ac_is_detected_only_by_the_declared_oracle(results):
    wa = results.targets[0]
    assert wa.declared.detected and wa.declared.test_index == 1
    assert not wa.corrected.detected


def test_a_real_bug_is_detected_by_both_oracles(results):
    wa = results.targets[1]
    assert wa.declared.test_index == 1  # the declared 5 already differs from 4
    assert wa.corrected.test_index == 2 and wa.corrected.verdict == "wrong_output"


def test_a_loop_is_a_tle_confirmed_in_three_runs(results):
    mutant = results.targets[2]
    assert mutant.corrected.verdict == "TLE" and mutant.corrected.test_index == 3
    assert results.detected.corrected_mutants == ["Mutant_1"]
