"""The execution phase: judge every attempt pending execution and record the terminal suites.

For each problem × scenario whose last attempt was parsed and not executed yet: run its Python
solution in the sandbox (``oracle.evaluate_attempt``), record ``attempt_<n>.execution.json``, and
then ``suite.json`` if the attempt was accepted or a failed one already gives the suite
(``config.ATTEMPT_POLICY``: the 12th with a fallback among the 12). Otherwise the combination waits
for ``generate --resume`` (the next attempt, a prediction after the 12th). A combination found with
every attempt file but no ``suite.json`` (an interruption between the two) only gets its
``suite.json``. Nothing is recorded before the whole evaluation of an attempt ends. Each combination
is claimed first (``store.claim``): one in use by a ``generate`` running at the same time is
skipped.
"""

from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from ai_clients import oracle, store
from ai_clients.problem import JudgeInput, load_judge_input
from ai_clients.schemas.execution import ExecutionRecord
from ai_clients.schemas.run import RunConfig


@dataclass
class ExecuteResult:
    executed: int = 0
    accepted: int = 0
    failed: int = 0
    need_generation: int = 0  # failed attempts that leave the combination for `generate --resume`
    # suites this run recorded after a failed attempt, by status (accepted_fallback,
    # accepted_predicted only after an interrupted generate)
    suites: Counter = field(default_factory=Counter)
    pending_generation: int = 0  # combinations of the selection waiting for `generate` at the end
    awaiting_manual: list[tuple[str, str]] = field(default_factory=list)  # selection, at the end
    damaged: list[store.DamagedCombination] = field(default_factory=list)  # reported, not repaired
    skipped: int = 0  # combinations in use by another command, left for it (research R24)


def describe(record: ExecutionRecord) -> str:
    """The outcome of one attempt, as printed by ``execute``."""
    if record.outcome == "accepted":
        kept = sum(item.kept for item in record.inputs)
        return f"accepted ({kept} kept, {len(record.inputs) - kept} discarded)"
    if record.outcome == "public_test_failed":
        tests = record.public_tests
        text = f"public_test_failed (test {tests.failed_index}: {tests.failed_verdict.value}"
        if record.inputs:  # a WA: the generated inputs also ran
            kept = sum(item.kept for item in record.inputs)
            text += f"; {kept} kept, {len(record.inputs) - kept} discarded"
        return text + ")"
    reasons = Counter(item.discard.value for item in record.inputs)
    counts = [f"{reasons['timeout']} timeout", f"{reasons['runtime_error']} runtime_error"]
    if reasons["non_utf8_output"]:
        counts.append(f"{reasons['non_utf8_output']} non_utf8_output")
    return f"all_inputs_failed ({', '.join(counts)})"


def execute(
    root: Path,
    combinations: Sequence[tuple[str, str]],
    *,
    run: RunConfig,
    runner: oracle.PythonRunner = oracle.run_python,
    echo: Callable[[str], None],
    limit: int | None = None,
    slot: int = 0,
) -> ExecuteResult:
    """Execute every combination pending execution (or finalizable), in the order given."""
    result = ExecuteResult()
    problems: dict[str, JudgeInput] = {}
    handled = 0
    for problem_id, scenario in combinations:
        try:
            state = store.combination_state(root, problem_id, scenario, run)
        except store.DamagedCombination as exc:
            result.damaged.append(exc)
            continue
        if state.kind not in ("finalizable", "pending_execution"):
            continue
        if state.kind == "pending_execution" and limit is not None and handled >= limit:
            break
        with store.claim(root, problem_id, scenario) as mine:
            if not mine:  # a generate is on it: left for it, never waited for
                echo(f"{problem_id} {scenario}: skipped (in use by another command)")
                result.skipped += 1
                continue
            try:  # read again: the other command may have moved it on before letting it go
                state = store.combination_state(root, problem_id, scenario, run)
            except store.DamagedCombination as exc:
                result.damaged.append(exc)
                continue
            what = f"{problem_id} {scenario} attempt {state.attempt}"
            if state.kind == "finalizable":  # interrupted before its suite.json: nothing to run
                suite = store.finalize(root, problem_id, scenario, run)
                echo(f"{what}: suite recorded ({suite.status.value})")
                result.suites[suite.status.value] += 1
                continue
            if state.kind != "pending_execution":
                continue
            handled += 1
            if problem_id not in problems:
                problems[problem_id] = load_judge_input(root, problem_id)
            generation = store.read_generation(root, problem_id, scenario, state.attempt)
            record = oracle.evaluate_attempt(
                generation, problems[problem_id], slot=slot, runner=runner
            )
            store.write_execution(root, record)
            result.executed += 1
            echo(f"{what}: {describe(record)}")
            if record.outcome == "accepted":
                result.accepted += 1
                store.finalize(root, problem_id, scenario, run)
                continue
            result.failed += 1
            if store.combination_state(root, problem_id, scenario, run).kind == "finalizable":
                suite = store.finalize(root, problem_id, scenario, run)
                echo(f"{problem_id} {scenario}: suite recorded ({suite.status.value})")
                result.suites[suite.status.value] += 1
            else:
                result.need_generation += 1
    result.pending_generation = store.count_in_state(root, combinations, "pending_generation", run)
    result.awaiting_manual = store.awaiting_manual(root, combinations, run)
    return result
