"""The execution phase: judge each attempt pending execution, then record the terminal suite."""

import pytest

from ai_clients import config, execution, store
from sandbox.types import RunStatus
from tests.ai_clients.fakes import (
    ECHO_PY,
    FakePythonRunner,
    echo_runner,
    record_generation,
    run_result,
    start_run,
)

WRONG_PY = "print(0)\n"  # fails the public tests of the echo problems


@pytest.fixture()
def run(repo):
    return start_run(repo)


def execute(root, run, combos, runner=None, limit=None):
    lines = []
    result = execution.execute(
        root, combos, run=run, runner=runner or echo_runner(), echo=lines.append, limit=limit
    )
    return result, lines


def wrong_runner():
    """Echo for the echo solution; the wrong solution prints 0 for everything."""
    return FakePythonRunner(
        default=lambda code, stdin: run_result(b"0\n" if code == WRONG_PY else stdin)
    )


def names(root, pid="1_A", scenario="black_box"):
    return sorted(p.name for p in store.combination_dir(root, pid, scenario).iterdir())


def test_an_accepted_attempt_records_the_execution_and_the_suite(repo, run):
    record_generation(repo, inputs=["5\n", "6\n", "5\n"])
    result, lines = execute(repo, run, [("1_A", "black_box")])
    assert names(repo) == [
        "attempt_1.execution.json",
        "attempt_1.generation.json",
        "suite.json",
    ]
    suite = store.read_suite(repo, "1_A", "black_box")
    assert suite.status == "accepted" and suite.accepted_attempt == 1
    assert [t.model_dump() for t in suite.tests] == [
        {"input": "5\n", "output": "5\n"},
        {"input": "6\n", "output": "6\n"},
        {"input": "5\n", "output": "5\n"},
    ]
    assert suite.suite_size == 3 and suite.discarded_inputs == []
    assert (suite.model, suite.model_digest) == (run.model, run.model_digest)
    assert [(a.attempt, a.seed, a.hardware_label, a.failure) for a in suite.attempts] == [
        (1, 42, "RTX 3060 12GB", None)
    ]
    assert lines == ["1_A black_box attempt 1: accepted (3 kept, 0 discarded)"]
    assert (result.executed, result.accepted, result.failed) == (1, 1, 0)
    assert sum(result.suites.values()) == 0  # the accepted suites are not in this counter


def test_the_suite_lists_the_discarded_inputs_of_the_accepted_attempt(repo, run):
    record_generation(repo, inputs=["5\n", "6\n"])
    runner = FakePythonRunner(
        table={(ECHO_PY, b"6\n"): run_result(status=RunStatus.TIMEOUT, cpu_time_s=11.0)},
        default=lambda code, stdin: run_result(stdin),
    )
    _, lines = execute(repo, run, [("1_A", "black_box")], runner)
    suite = store.read_suite(repo, "1_A", "black_box")
    assert [t.input for t in suite.tests] == ["5\n"]
    assert [d.model_dump(mode="json") for d in suite.discarded_inputs] == [
        {"index": 1, "discard": "timeout", "verdict": "TLE"}
    ]
    assert lines == ["1_A black_box attempt 1: accepted (1 kept, 1 discarded)"]


def test_a_failed_attempt_asks_for_a_new_generation(repo, run):
    record_generation(repo, code=WRONG_PY)
    result, lines = execute(repo, run, [("1_A", "black_box")], wrong_runner())
    assert names(repo) == ["attempt_1.execution.json", "attempt_1.generation.json"]
    assert store.combination_state(repo, "1_A", "black_box") == store.State("pending_generation", 2)
    # a WA: the generated inputs also ran, so this attempt can still be a fallback
    assert lines == [
        "1_A black_box attempt 1: public_test_failed (test 0: WA; 2 kept, 0 discarded)"
    ]
    assert (result.failed, result.need_generation, result.pending_generation) == (1, 1, 1)


def test_all_inputs_failed_is_reported_with_its_reasons(repo, run):
    record_generation(repo, inputs=["5\n", "6\n", "7\n"])
    runner = FakePythonRunner(
        table={
            (ECHO_PY, b"5\n"): run_result(status=RunStatus.TIMEOUT, cpu_time_s=11.0),
            (ECHO_PY, b"6\n"): run_result(status=RunStatus.NONZERO_EXIT, exit_code=1),
            (ECHO_PY, b"7\n"): run_result(status=RunStatus.TIMEOUT, cpu_time_s=11.0),
        },
        default=lambda code, stdin: run_result(stdin),
    )
    _, lines = execute(repo, run, [("1_A", "black_box")], runner)
    assert lines == ["1_A black_box attempt 1: all_inputs_failed (2 timeout, 1 runtime_error)"]


def crash_runner():
    """Echo for the echo solution; the wrong solution crashes on everything (RE, never WA)."""
    return FakePythonRunner(
        default=lambda code, stdin: (
            run_result(status=RunStatus.NONZERO_EXIT, exit_code=1)
            if code == WRONG_PY
            else run_result(stdin)
        )
    )


def test_after_re_on_a_public_test_no_input_runs(repo, run):
    record_generation(repo, code=WRONG_PY, inputs=["5\n", "6\n"])
    runner = crash_runner()
    _, lines = execute(repo, run, [("1_A", "black_box")], runner)
    assert [stdin for _, stdin, _, _ in runner.calls] == [b"1\n"]  # the first public test only
    assert store.read_execution(repo, "1_A", "black_box", 1).inputs == []
    assert lines == ["1_A black_box attempt 1: public_test_failed (test 0: RE)"]


def test_twelve_failures_without_a_fallback_go_straight_to_the_prediction(repo, run):
    """Phases 1 and 2 over, no WA among them: phase 3 has nothing, so phase 4 (attempt 13)."""
    for n in range(1, config.SOLUTION_ATTEMPTS + 1):
        parsed = n % 2 == 0  # odd ones unparseable, even ones crash on a public test (RE)
        record_generation(repo, attempt=n, parsed=parsed, code=WRONG_PY)
        if parsed:
            result, _ = execute(repo, run, [("1_A", "black_box")], crash_runner())
    assert store.read_suite(repo, "1_A", "black_box") is None
    state = store.combination_state(repo, "1_A", "black_box", run)
    assert (state.kind, state.attempt) == ("pending_generation", 13)
    assert (result.failed, result.need_generation, sum(result.suites.values())) == (1, 1, 0)


def test_a_finalizable_combination_only_gets_its_suite(repo, run, monkeypatch):
    record_generation(repo)
    execute(repo, run, [("1_A", "black_box")])
    (store.combination_dir(repo, "1_A", "black_box") / config.SUITE_FILE).unlink()
    runner = FakePythonRunner()  # any run would fail the test
    result, _ = execute(repo, run, [("1_A", "black_box")], runner)
    assert runner.calls == [] and result.executed == 0
    assert store.read_suite(repo, "1_A", "black_box").status == "accepted"


def test_finalize_gives_the_same_bytes_for_the_same_files(repo, run):
    record_generation(repo)
    execute(repo, run, [("1_A", "black_box")])
    path = store.combination_dir(repo, "1_A", "black_box") / config.SUITE_FILE
    first = path.read_bytes()
    path.unlink()
    store.finalize(repo, "1_A", "black_box", run)
    assert path.read_bytes() == first


def test_only_combinations_pending_execution_run(repo, run):
    record_generation(repo, "1_A", "black_box")
    record_generation(repo, "1_A", "white_box", parsed=False)  # pending a generation
    record_generation(repo, "2_B", "hybrid")
    combos = [(pid, s) for pid in ("1_A", "2_B") for s in config.SCENARIOS]
    result, lines = execute(repo, run, combos)
    assert [line.split(":")[0] for line in lines] == [
        "1_A black_box attempt 1",
        "2_B hybrid attempt 1",
    ]
    # 1_A white_box (attempt 2) and the 3 never generated still need generate
    assert result.pending_generation == 4


def test_limit_counts_the_pending_combinations_in_the_order_given(repo, run):
    for pid in ("1_A", "2_B"):
        record_generation(repo, pid, "black_box")
    result, lines = execute(repo, run, [("1_A", "black_box"), ("2_B", "black_box")], limit=1)
    assert result.executed == 1 and lines[0].startswith("1_A black_box")
    assert store.combination_state(repo, "2_B", "black_box").kind == "pending_execution"


def test_a_terminal_combination_is_never_touched(repo, run):
    record_generation(repo)
    execute(repo, run, [("1_A", "black_box")])
    before = {
        p.name: p.read_bytes() for p in store.combination_dir(repo, "1_A", "black_box").iterdir()
    }
    runner = FakePythonRunner()
    execute(repo, run, [("1_A", "black_box")], runner)
    after = {
        p.name: p.read_bytes() for p in store.combination_dir(repo, "1_A", "black_box").iterdir()
    }
    assert runner.calls == [] and before == after


def test_execute_never_reads_the_reference_cpp(repo, run):
    record_generation(repo)
    (repo / "data" / "dataset" / "problems" / "1_A" / "AC_ref.cpp").unlink()
    result, _ = execute(repo, run, [("1_A", "black_box")])
    assert result.accepted == 1


def test_an_infrastructure_failure_records_nothing(repo, run):
    from sandbox.types import InfraError

    record_generation(repo)
    runner = FakePythonRunner(default=lambda code, stdin: InfraError("tmpfs full"))
    with pytest.raises(InfraError):
        execute(repo, run, [("1_A", "black_box")], runner)
    assert names(repo) == ["attempt_1.generation.json"]


# ------------------------------------------------------------------------------- fallback suites


def fallback_runner(passes_first=()):
    """Echo for the echo solution. A wrong solution ``print(<k>)`` prints k for everything, except
    for the solutions listed in ``passes_first``, which echo the first public test (``1\n``)."""

    def answer(code, stdin):
        if code == ECHO_PY or (code in passes_first and stdin == b"1\n"):
            return run_result(stdin)
        return run_result(code.removeprefix("print(").removesuffix(")\n").encode() + b"\n")

    return FakePythonRunner(default=answer)


def wrong(k):
    return f"print({k})\n"


def fail_attempts(repo, run, numbers, *, runner, code=WRONG_PY, inputs=("1\n", "2\n")):
    for n in numbers:
        record_generation(repo, attempt=n, code=code(n) if callable(code) else code, inputs=inputs)
        execute(repo, run, [("1_A", "black_box")], runner)


def test_twelve_failures_with_a_wa_accept_the_best_attempt_as_a_fallback(repo, run):
    # attempts 1-12 all fail; 3 and 6 pass the first public test (test 1: WA), the others fail
    # test 0; 6 kept more inputs than 3, so 6 is the fallback; 7 is unparseable
    best = {3: wrong(30), 6: wrong(60)}
    runner = fallback_runner(passes_first=set(best.values()))
    for n in range(1, config.SOLUTION_ATTEMPTS):
        if n == 7:
            record_generation(repo, attempt=n, parsed=False)
            continue
        inputs = ("4\n", "5\n", "6\n") if n == 6 else ("4\n", "5\n")
        record_generation(repo, attempt=n, code=best.get(n, wrong(100 + n)), inputs=inputs)
        execute(repo, run, [("1_A", "black_box")], runner)
    record_generation(repo, attempt=12, code=wrong(112), inputs=("4\n",))
    result, lines = execute(repo, run, [("1_A", "black_box")], runner)
    suite = store.read_suite(repo, "1_A", "black_box")
    assert suite.status == "accepted_fallback" and suite.accepted_attempt == 6
    assert suite.accepted_phase == 3
    assert len(suite.attempts) == 12 and all(a.failure is not None for a in suite.attempts)
    eligible = [a.attempt for a in suite.attempts if a.fallback_eligible]
    assert eligible == [n for n in range(1, 13) if n != 7]
    assert suite.attempts[5].detail == "test 1: WA; 3 kept, 0 discarded"
    # the expected outputs are what the wrong solution printed
    assert [t.model_dump() for t in suite.tests] == [
        {"input": i, "output": "60\n"} for i in ("4\n", "5\n", "6\n")
    ]
    assert lines[-1] == "1_A black_box: suite recorded (accepted_fallback)"
    assert (result.suites["accepted_fallback"], result.need_generation) == (1, 0)


def test_between_equal_fallbacks_the_earliest_wins(repo, run):
    fail_attempts(repo, run, range(1, 13), runner=wrong_runner())
    suite = store.read_suite(repo, "1_A", "black_box")
    assert suite.status == "accepted_fallback" and suite.accepted_attempt == 1


@pytest.mark.parametrize("failed", [6, 9, 11])
def test_a_wa_before_the_12th_attempt_still_asks_for_a_new_generation(repo, run, failed):
    """The fallback is only chosen once phases 1 and 2 are over (after the 6th: phase 2)."""
    fail_attempts(repo, run, range(1, failed + 1), runner=wrong_runner())
    state = store.combination_state(repo, "1_A", "black_box")
    assert state == store.State("pending_generation", failed + 1)
    assert store.read_suite(repo, "1_A", "black_box") is None


def test_a_wa_whose_inputs_all_failed_is_not_a_fallback(repo, run):
    runner = FakePythonRunner(
        default=lambda code, stdin: (
            run_result(stdin)
            if code == ECHO_PY
            else (
                run_result(b"0\n")
                if stdin in (b"1\n", b"2\n")  # the public tests: a WA
                else run_result(status=RunStatus.NONZERO_EXIT, exit_code=1)
            )
        )
    )
    fail_attempts(repo, run, range(1, 13), runner=runner, inputs=("5\n",))
    assert store.read_suite(repo, "1_A", "black_box") is None
    state = store.combination_state(repo, "1_A", "black_box")
    assert state == store.State("pending_generation", 13)


def test_a_full_pass_in_phase_2_is_an_ordinary_accepted_suite(repo, run):
    fail_attempts(repo, run, range(1, 9), runner=crash_runner())
    record_generation(repo, attempt=9)
    execute(repo, run, [("1_A", "black_box")])
    suite = store.read_suite(repo, "1_A", "black_box")
    assert suite.status == "accepted" and suite.accepted_attempt == 9
    assert suite.accepted_phase == 2 and suite.attempts[-1].temperature == 0.5


def test_a_full_pass_in_phase_1_stops_there(repo, run):
    fail_attempts(repo, run, range(1, 3), runner=crash_runner())
    record_generation(repo, attempt=3)
    execute(repo, run, [("1_A", "black_box")])
    suite = store.read_suite(repo, "1_A", "black_box")
    assert (suite.status, suite.accepted_attempt, suite.accepted_phase) == ("accepted", 3, 1)
