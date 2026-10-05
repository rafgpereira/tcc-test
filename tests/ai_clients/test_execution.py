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
        (1, 43, "RTX 3060 12GB", None)
    ]
    assert lines == ["1_A black_box attempt 1: accepted (3 kept, 0 discarded)"]
    assert (result.executed, result.accepted, result.failed, result.discarded) == (1, 1, 0, 0)


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


def test_a_failure_before_the_6th_attempt_asks_for_a_new_generation(repo, run):
    record_generation(repo, code=WRONG_PY)
    result, lines = execute(repo, run, [("1_A", "black_box")], wrong_runner())
    assert names(repo) == ["attempt_1.execution.json", "attempt_1.generation.json"]
    assert store.combination_state(repo, "1_A", "black_box") == store.State("pending_generation", 2)
    assert lines == ["1_A black_box attempt 1: public_test_failed (test 0: WA)"]
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


def test_the_6th_failure_discards_the_suite_with_every_individual_reason(repo, run):
    # attempts 1, 3, 5 unparseable; 2 and 4 failed a public test; 6 is waiting for execution
    for n in range(1, 6):
        record_generation(repo, attempt=n, parsed=n % 2 == 0, code=WRONG_PY)
        if n % 2 == 0:
            execute(repo, run, [("1_A", "black_box")], wrong_runner())
    record_generation(repo, attempt=6, inputs=["5\n"])
    runner = FakePythonRunner(
        table={(ECHO_PY, b"5\n"): run_result(status=RunStatus.NONZERO_EXIT, exit_code=1)},
        default=lambda code, stdin: run_result(stdin),
    )
    result, _ = execute(repo, run, [("1_A", "black_box")], runner)
    suite = store.read_suite(repo, "1_A", "black_box")
    assert suite.status == "discarded" and suite.tests == [] and suite.accepted_attempt is None
    assert [(a.attempt, a.seed, a.failure) for a in suite.attempts] == [
        (1, 43, "unparseable_response"),
        (2, 44, "public_test_failed"),
        (3, 45, "unparseable_response"),
        (4, 46, "public_test_failed"),
        (5, 47, "unparseable_response"),
        (6, 48, "all_inputs_failed"),
    ]
    assert (result.failed, result.need_generation, result.discarded) == (1, 0, 1)


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
