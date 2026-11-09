"""Evaluate every requested suite of ONE problem (contracts/evaluation-api.md, ``evaluate_problem``).

Each program is compiled once for all the suites of the problem (research R1): first the AC, which
runs every suite before anything else (its outputs are the corrected oracle of the targets), then
one target at a time, ``WA_1..WA_n`` and ``Mutant_1..Mutant_m``, against every suite. A compilation
starts in a fresh, empty workdir of the slot, so only the binary of the program being judged
exists at any time (research R4). The outcome depends only on the files of the problem and on the
verdicts of the engine, never on the order of the suites or on how many workers there are.
"""

import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from evaluation import config, judging
from evaluation.schemas.result import AcResult, CombinationResult, TargetResult, detected_sets
from evaluation.sources import ProblemTargets, SuiteToEvaluate
from sandbox.types import CompileResult, ExecutionLimits, InfraError, RunResult

Key = tuple[str, str]  # (set, scenario)


@dataclass(frozen=True)
class Engine:
    """The engine as the evaluation sees it; the tests inject a fake one (no C++, no root)."""

    gcc_version: str
    compile: Callable[[str, int], CompileResult]
    run: Callable[[Path, bytes, ExecutionLimits, int], RunResult]


def real_engine() -> Engine:
    """The engine of the project, unchanged: compile in a fresh workdir of the slot, run isolated."""
    from dataset.validation.engine import gcc_version
    from sandbox import isolation
    from sandbox.compiler import compile_cpp
    from sandbox.runner import run_binary

    def compile_(source: str, slot: int) -> CompileResult:
        return compile_cpp(source, isolation.prepare_slot_workdir(slot), slot)

    return Engine(gcc_version=gcc_version(), compile=compile_, run=run_binary)


@dataclass(frozen=True)
class ProblemTask:
    """Everything one worker needs for one problem (small, immutable, picklable)."""

    problem: ProblemTargets
    suites: tuple[tuple[Key, SuiteToEvaluate], ...]  # in a fixed order (set, scenario)


def _no_suite(key: Key, problem_id: str, suite: SuiteToEvaluate) -> CombinationResult:
    set_name, scenario = key
    return CombinationResult(
        set=set_name,
        model=config.SET_MODEL[set_name],
        problem_id=problem_id,
        scenario=scenario,
        suite_source=suite.source,
        has_suite=False,
        no_suite_reason=suite.no_suite_reason,
        suite_size=0,
        ac=None,
        corrected_oracle_tests=0,
        corrected_oracle_excluded=0,
        targets=[],
        detected=detected_sets([]),
        elapsed_s=0.0,
    )


def evaluate_problem(task: ProblemTask, engine: Engine, slot: int) -> dict[Key, CombinationResult]:
    """One ``CombinationResult`` per requested (set, scenario) of the problem."""
    problem = task.problem
    limits = problem.limits
    suites = dict(task.suites)
    with_tests = [key for key, suite in task.suites if suite.tests]
    elapsed = {key: 0.0 for key in with_tests}
    results: dict[Key, CombinationResult] = {
        key: _no_suite(key, problem.problem_id, suite)
        for key, suite in task.suites
        if not suite.tests
    }
    if not with_tests:
        return results

    compiled = engine.compile(problem.ac_source, slot)
    if not compiled.ok or compiled.binary is None:
        # The AC passed the whole official suite in this engine (dataset validation): failing to
        # compile it now is a broken environment, never a verdict.
        raise InfraError(f"{problem.problem_id}: AC_ref.cpp did not compile in any standard")
    ac: dict[Key, AcResult] = {}
    for key in with_tests:
        start = time.perf_counter()
        ac[key] = judging.judge_ac(
            compiled.binary,
            suites[key].tests,
            limits,
            slot,
            run=engine.run,
            standard_used=compiled.standard_used or "unknown",
        )
        elapsed[key] += time.perf_counter() - start

    targets: dict[Key, list[TargetResult]] = {key: [] for key in with_tests}
    for target in problem.targets:
        built = engine.compile(target.source, slot)
        for key in with_tests:
            if not built.ok or built.binary is None:
                targets[key].append(judging.not_compiled(target.name, target.kind))
                continue
            start = time.perf_counter()
            targets[key].append(
                judging.judge_target(
                    built.binary,
                    suites[key].tests,
                    ac[key],
                    limits,
                    slot,
                    run=engine.run,
                    target=target.name,
                    kind=target.kind,
                )
            )
            elapsed[key] += time.perf_counter() - start

    for key in with_tests:
        set_name, scenario = key
        suite = suites[key]
        valid = sum(t.verdict != "runtime_error" for t in ac[key].tests)
        results[key] = CombinationResult(
            set=set_name,
            model=config.SET_MODEL[set_name],
            problem_id=problem.problem_id,
            scenario=scenario,
            suite_source=suite.source,
            has_suite=True,
            no_suite_reason=None,
            suite_size=len(suite.tests),
            ac=ac[key],
            corrected_oracle_tests=valid,
            corrected_oracle_excluded=len(suite.tests) - valid,
            targets=targets[key],
            detected=detected_sets(targets[key]),
            elapsed_s=round(elapsed[key], 3),
        )
    return results


def group_by_set(
    results: Mapping[Key, CombinationResult],
) -> dict[str, dict[str, CombinationResult]]:
    grouped: dict[str, dict[str, CombinationResult]] = {}
    for (set_name, scenario), result in results.items():
        grouped.setdefault(set_name, {})[scenario] = result
    return grouped
