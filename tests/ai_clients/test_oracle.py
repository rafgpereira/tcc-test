"""The Python reference solution of an attempt, judged by the public tests and run on each input."""

import pytest

from ai_clients import oracle, problem
from ai_clients.schemas.generation import GenerationRecord
from sandbox import judge
from sandbox.types import ExecutionLimits, InfraError, RunStatus, Verdict
from tests.ai_clients.conftest import MEMORY_LIMIT_BYTES, TIME_LIMIT_S
from tests.ai_clients.fakes import ECHO_PY, FakePythonRunner, run_result
from tests.ai_clients.test_schemas import generation, parsed

LIMITS = ExecutionLimits(time_limit_seconds=10.0, memory_limit_bytes=4 * MEMORY_LIMIT_BYTES)


def attempt(inputs=("10\n", "20\n", "30\n"), code=ECHO_PY):
    return GenerationRecord(**generation(parse=parsed(inputs=list(inputs), reference_py=code)))


@pytest.fixture()
def judged(repo):
    return problem.load_judge_input(repo, "1_A")


def no_cpp(code, stdin):
    """The default answer of the fake runner: an echo, and never a C++ program."""
    assert "#include" not in code, "AC_ref.cpp must never run"
    return run_result(stdin)


def runner(table=None):
    return FakePythonRunner(table=table or {}, default=no_cpp)


def test_the_limits_are_the_problem_limits_times_the_factors(judged):
    limits = oracle.python_limits(judged.metadata)
    assert limits == ExecutionLimits(
        time_limit_seconds=TIME_LIMIT_S * 10, memory_limit_bytes=MEMORY_LIMIT_BYTES * 4
    )


def test_the_limits_follow_the_metadata_never_a_constant(judged):
    other = judged.metadata.model_copy(
        update={"time_limit_seconds": 2.5, "memory_limit_bytes": 64 * 1024 * 1024}
    )
    limits = oracle.python_limits(other)
    assert (limits.time_limit_seconds, limits.memory_limit_bytes) == (25.0, 256 * 1024 * 1024)


def test_the_interpreter_is_the_base_cpython_outside_the_venv():
    path = oracle.interpreter_path()
    assert path.name.startswith("python3.") and "venv" not in str(path)


def test_all_public_tests_pass_and_every_input_keeps_its_real_stdout(judged):
    fake = runner({(ECHO_PY, b"20\n"): run_result(b"  20  \n\n")})  # never normalized
    record = oracle.evaluate_attempt(attempt(), judged, runner=fake)
    assert record.outcome == "accepted"
    assert record.public_tests.model_dump() == {
        "total": 2,
        "passed": 2,
        "failed_index": None,
        "failed_verdict": None,
        "failed_output_head": None,
        "failed_stderr_tail": None,
        "failed_cpu_time_s": None,
        "failed_peak_rss_bytes": None,
    }
    assert [i.output for i in record.inputs] == ["10\n", "  20  \n\n", "30\n"]
    assert all(i.kept and i.discard is None and i.stderr_tail == "" for i in record.inputs)
    # the 2 public tests first, in order, then the 3 inputs, in order
    assert [stdin for _, stdin, _, _ in fake.calls] == [b"1\n", b"2\n", b"10\n", b"20\n", b"30\n"]
    assert all(limits == LIMITS for _, _, limits, _ in fake.calls)


def test_the_record_keeps_the_effective_and_the_problem_limits(judged):
    record = oracle.evaluate_attempt(attempt(), judged, runner=runner())
    assert record.limits.model_dump() == {
        "time_limit_seconds": 10.0,
        "memory_limit_bytes": 4 * MEMORY_LIMIT_BYTES,
        "problem_time_limit_seconds": TIME_LIMIT_S,
        "problem_memory_limit_bytes": MEMORY_LIMIT_BYTES,
    }
    assert str(oracle.interpreter_path()) in record.interpreter


@pytest.mark.parametrize(
    ("answer", "verdict"),
    [
        (run_result(status=RunStatus.TIMEOUT, cpu_time_s=31.0), Verdict.TLE),
        (run_result(peak_rss_bytes=4 * MEMORY_LIMIT_BYTES), Verdict.MLE),
        (run_result(status=RunStatus.NONZERO_EXIT, exit_code=1), Verdict.RE),
    ],
)
def test_a_failing_public_test_other_than_wa_stops_everything(judged, answer, verdict):
    """RE, TLE or MLE: the attempt can be neither accepted nor the fallback; no input runs."""
    fake = runner({(ECHO_PY, b"2\n"): answer})
    record = oracle.evaluate_attempt(attempt(), judged, runner=fake)
    assert record.outcome == "public_test_failed"
    assert (record.public_tests.failed_index, record.public_tests.failed_verdict) == (1, verdict)
    assert record.public_tests.passed == 1
    assert record.inputs == []
    assert [stdin for _, stdin, _, _ in fake.calls] == [b"1\n", b"2\n"]  # no input ran


def test_a_wa_on_a_public_test_still_runs_every_generated_input(judged):
    """The attempt fails, but can still become a fallback suite: its inputs need outputs."""
    fake = runner({(ECHO_PY, b"2\n"): run_result(b"7\n")})
    generation = attempt()
    record = oracle.evaluate_attempt(generation, judged, runner=fake)
    assert record.outcome == "public_test_failed"
    assert (record.public_tests.failed_index, record.public_tests.failed_verdict) == (1, Verdict.WA)
    assert len(record.inputs) == len(generation.parse.inputs)
    assert [stdin for _, stdin, _, _ in fake.calls][:2] == [b"1\n", b"2\n"]
    assert len(fake.calls) == 2 + len(generation.parse.inputs)


def test_a_failing_public_test_keeps_what_the_solution_printed(judged):
    crash = run_result(
        b"partial\n",
        status=RunStatus.NONZERO_EXIT,
        exit_code=1,
        cpu_time_s=0.5,
        peak_rss_bytes=12345,
        stderr_tail=b"ValueError: invalid literal for int() with base 10: '23C55'\n",
    )
    record = oracle.evaluate_attempt(attempt(), judged, runner=runner({(ECHO_PY, b"1\n"): crash}))
    tests = record.public_tests
    assert (tests.failed_index, tests.failed_verdict) == (0, Verdict.RE)
    assert tests.failed_output_head == "partial\n"
    assert tests.failed_stderr_tail.startswith("ValueError: invalid literal")
    assert (tests.failed_cpu_time_s, tests.failed_peak_rss_bytes) == (0.5, 12345)


def test_only_the_start_of_a_long_wrong_output_is_kept(judged):
    long = b"9" * (oracle.FAILED_OUTPUT_HEAD_BYTES + 1000)
    fake = runner({(ECHO_PY, b"2\n"): run_result(long)})
    record = oracle.evaluate_attempt(attempt(), judged, runner=fake)
    assert record.public_tests.failed_verdict is Verdict.WA
    assert record.public_tests.failed_output_head == "9" * oracle.FAILED_OUTPUT_HEAD_BYTES
    assert record.public_tests.failed_stderr_tail == ""


@pytest.mark.parametrize(
    ("answer", "discard", "verdict"),
    [
        (run_result(status=RunStatus.TIMEOUT, cpu_time_s=12.0), "timeout", Verdict.TLE),
        (run_result(cpu_time_s=10.5), "timeout", Verdict.TLE),
        (
            run_result(status=RunStatus.NONZERO_EXIT, exit_code=1, stderr_tail=b"Traceback"),
            "runtime_error",
            Verdict.RE,
        ),
        (run_result(peak_rss_bytes=4 * MEMORY_LIMIT_BYTES), "runtime_error", Verdict.MLE),
        (run_result(b"\xff\xfe\n"), "non_utf8_output", None),
    ],
)
def test_an_input_that_fails_alone_is_discarded_and_the_others_stay(
    judged, answer, discard, verdict
):
    fake = runner({(ECHO_PY, b"20\n"): answer})
    record = oracle.evaluate_attempt(attempt(), judged, runner=fake)
    assert record.outcome == "accepted"
    first, second, third = record.inputs
    assert first.kept and third.kept
    assert (second.index, second.kept, second.output) == (1, False, None)
    assert (second.discard, second.verdict) == (discard, verdict)


def test_the_stderr_tail_is_kept_only_for_a_discarded_input(judged):
    fake = runner(
        {
            (ECHO_PY, b"10\n"): run_result(b"10\n", stderr_tail=b"warning"),
            (ECHO_PY, b"20\n"): run_result(
                status=RunStatus.SIGNALED, exit_code=None, signal=9, stderr_tail=b"Killed"
            ),
        }
    )
    record = oracle.evaluate_attempt(attempt(), judged, runner=fake)
    assert [i.stderr_tail for i in record.inputs] == ["", "Killed", ""]
    assert record.inputs[1].cpu_time_s == 0.01 and record.inputs[1].peak_rss_bytes > 0


def test_every_input_failing_is_all_inputs_failed_never_an_empty_suite(judged):
    fake = runner(
        {
            (ECHO_PY, b"10\n"): run_result(status=RunStatus.TIMEOUT, cpu_time_s=12.0),
            (ECHO_PY, b"20\n"): run_result(status=RunStatus.NONZERO_EXIT, exit_code=1),
            (ECHO_PY, b"30\n"): run_result(status=RunStatus.TIMEOUT, cpu_time_s=12.0),
        }
    )
    record = oracle.evaluate_attempt(attempt(), judged, runner=fake)
    assert record.outcome == "all_inputs_failed"
    assert [i.discard for i in record.inputs] == ["timeout", "runtime_error", "timeout"]


def test_every_verdict_comes_from_the_engine_judge_with_the_multiplied_limits(judged, monkeypatch):
    seen = []
    real = judge.judge_test

    def spy(run, expected, limits):
        seen.append(limits)
        return real(run, expected, limits)

    monkeypatch.setattr(oracle, "judge_test", spy)
    oracle.evaluate_attempt(attempt(), judged, runner=runner())
    assert len(seen) == 5 and set(seen) == {LIMITS}


def test_an_infrastructure_failure_propagates_and_is_never_a_verdict(judged):
    fake = runner({(ECHO_PY, b"20\n"): InfraError("cannot fork")})
    with pytest.raises(InfraError, match="cannot fork"):
        oracle.evaluate_attempt(attempt(), judged, runner=fake)


def test_an_unparsed_attempt_has_nothing_to_execute(judged):
    record = GenerationRecord(**generation(parse={"ok": False, "error": "wrong_order"}))
    with pytest.raises(ValueError, match="parsed"):
        oracle.evaluate_attempt(record, judged, runner=runner())


def test_the_judge_input_does_not_read_the_reference_cpp(repo):
    (repo / "data" / "dataset" / "problems" / "1_A" / "AC_ref.cpp").unlink()
    judged = problem.load_judge_input(repo, "1_A")
    assert judged.problem_id == "1_A" and len(judged.testes.public_tests) == 2
    assert not hasattr(judged, "ac_ref")
