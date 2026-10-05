"""The real Python runner: known programs run as the slot uid, without network, in a fresh workdir.

They start real processes under the isolation of the engine, so they only run in the ``sandbox``
service (root with the capabilities of the slot switch, no network, ``/sandbox`` tmpfs).
"""

import shutil

import pytest

from ai_clients import oracle, problem
from ai_clients.schemas.generation import GenerationRecord
from sandbox import isolation, judge
from sandbox.types import ExecutionLimits, RunStatus, Verdict
from tests.ai_clients.fakes import ECHO_PY
from tests.ai_clients.test_schemas import generation, parsed

pytestmark = pytest.mark.integration

SLOT = 0
MIB = 1024 * 1024
LIMITS = ExecutionLimits(time_limit_seconds=2.0, memory_limit_bytes=256 * MIB)


@pytest.fixture(autouse=True)
def clean_slot():
    yield
    isolation.kill_slot_processes(SLOT)
    shutil.rmtree(isolation.slot_workdir(SLOT), ignore_errors=True)


def run(code, stdin=b"", limits=LIMITS):
    return oracle.run_python(code, stdin, limits, SLOT)


def test_a_correct_program_runs_and_its_stdout_is_returned():
    result = run(ECHO_PY, b"42\n")
    assert result.status is RunStatus.OK and result.stdout == b"42\n"
    assert judge.judge_test(result, "42\n", LIMITS) is Verdict.AC


def test_a_syntax_error_is_a_runtime_error():
    result = run("def f(:\n")
    assert judge.judge_test(result, "", LIMITS) is Verdict.RE
    assert b"SyntaxError" in result.stderr_tail


def test_an_infinite_loop_is_a_tle():
    result = run("while True:\n    pass\n", limits=ExecutionLimits(1.0, 256 * MIB))
    assert judge.judge_test(result, "", ExecutionLimits(1.0, 256 * MIB)) is Verdict.TLE


def test_allocating_beyond_the_memory_limit_fails():
    result = run("x = bytearray(512 * 1024 * 1024)\nprint(len(x))\n")
    assert judge.judge_test(result, "", LIMITS) in (Verdict.RE, Verdict.MLE)
    assert result.stdout == b""


def test_a_non_utf8_output_is_returned_as_is():
    result = run("import sys\nsys.stdout.buffer.write(b'\\xff\\xfe\\n')\n")
    assert result.status is RunStatus.OK and result.stdout == b"\xff\xfe\n"


def test_only_the_standard_library_is_available():
    result = run("import pydantic\n")
    assert result.status is RunStatus.NONZERO_EXIT and b"ModuleNotFoundError" in result.stderr_tail
    assert run("import json, math, collections, heapq\nprint('ok')\n").stdout == b"ok\n"


def test_exit_and_quit_exist_as_in_a_normal_python():
    # the 3rd pilot: solutions calling exit() failed with NameError while `site` was skipped (-S)
    result = run("print('a')\nexit()\nprint('b')\n")
    assert result.status is RunStatus.OK and result.stdout == b"a\n"
    assert run("quit(0)\n").status is RunStatus.OK


def test_the_interpreter_is_isolated_and_utf8():
    code = "import sys\nprint(sys.flags.isolated, sys.flags.no_site, sys.prefix == sys.base_prefix)\nprint('é')\n"
    assert run(code).stdout == "1 0 True\né\n".encode()  # isolated, `site` loaded, no venv


def test_there_is_no_network():
    code = (
        "import socket\n"
        "try:\n"
        "    socket.create_connection(('1.1.1.1', 53), timeout=2)\n"
        "    print('connected')\n"
        "except OSError:\n"
        "    print('no network')\n"
    )
    assert run(code).stdout == b"no network\n"


def test_a_file_written_in_one_run_does_not_exist_in_the_next():
    write = "open('state.txt', 'w').write('x')\nprint('written')\n"
    read = "import os\nprint(os.path.exists('state.txt'))\n"
    assert run(write).stdout == b"written\n"
    assert run(read).stdout == b"False\n"


def test_it_runs_as_the_slot_uid_not_root():
    result = run("import os\nprint(os.getuid(), os.geteuid())\n")
    uid = isolation.slot_uid(SLOT)
    assert result.stdout == f"{uid} {uid}\n".encode()


def test_a_solution_that_fails_only_one_input_loses_only_that_input(repo):
    code = (
        "import sys\n"
        "n = int(sys.stdin.read())\n"
        "if n == 13:\n"
        "    raise ValueError('unlucky')\n"
        "print(n)\n"
    )
    record = GenerationRecord(
        **generation(parse=parsed(inputs=["5\n", "13\n", "7\n"], reference_py=code))
    )
    result = oracle.evaluate_attempt(record, problem.load_judge_input(repo, "1_A"), slot=SLOT)
    assert result.outcome == "accepted"
    assert [(i.kept, i.output, i.discard) for i in result.inputs] == [
        (True, "5\n", None),
        (False, None, "runtime_error"),
        (True, "7\n", None),
    ]
    assert "unlucky" in result.inputs[1].stderr_tail
