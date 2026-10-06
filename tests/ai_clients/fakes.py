"""Test doubles of the ai_clients tests: a fake Ollama client, a fake Python runner, a fake clock.

Nothing here talks to a network or starts a process. The fake client answers from a table keyed by
``(problem_id, scenario, seed)``: the problem is found by its id inside the prompt (the synthetic
problems of ``conftest.py`` carry it both in the statement and in a comment of ``AC_ref.cpp``) and
the scenario by the sub-labels of ``<context_data>``.
"""

import dataclasses
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

import pytest

from sandbox.types import RunResult, RunStatus

STATEMENT_TAG = "<problem_statement>"
CODE_TAG = "<reference_solution_cpp>"


def scenario_of(prompt: str) -> str:
    """The scenario of a prompt, from the sub-labels present in ``<context_data>``."""
    statement, code = STATEMENT_TAG in prompt, CODE_TAG in prompt
    if statement and code:
        return "hybrid"
    if statement:
        return "black_box"
    if code:
        return "white_box"
    raise AssertionError("the prompt has no context sub-label")


def completion(
    content: str,
    *,
    done_reason: str = "stop",
    prompt_eval_count: int = 1000,
    eval_count: int = 500,
    model: str = "qwen2.5-coder:7b",
):
    """A ``Completion`` as the real client would return it."""
    from ai_clients.ollama import Completion  # imported late: the client comes after the fakes

    return Completion(
        content=content,
        model=model,
        created_at="2026-10-01T12:00:00.000Z",
        done_reason=done_reason,
        prompt_eval_count=prompt_eval_count,
        eval_count=eval_count,
        total_duration_ns=2_000_000_000,
        load_duration_ns=10_000_000,
        prompt_eval_duration_ns=500_000_000,
        eval_duration_ns=1_400_000_000,
    )


def well_formed_response(
    inputs: Iterable[str],
    code: str = "import sys\nprint(sys.stdin.read().strip())\n",
    analysis: str = "Edge cases: smallest and largest n.",
) -> str:
    """A response with the three blocks in order, as the prompt asks for."""
    blocks = "".join(f"<input>\n{text}</input>\n" for text in inputs)
    return (
        f"<edge_cases_analysis>\n{analysis}\n</edge_cases_analysis>\n"
        f"<reference_py>\n{code}</reference_py>\n"
        f"<inputs>\n{blocks}</inputs>\n"
    )


def predicted_response(
    tests: Iterable[tuple[str, str]],
    analysis: str = "Edge cases: smallest and largest n.",
) -> str:
    """A prediction answer (attempts 21 to 23): the two blocks in order, as the template asks."""
    blocks = "".join(
        f"<test>\n<input>\n{given}</input>\n<output>\n{expected}</output>\n</test>\n"
        for given, expected in tests
    )
    return (
        f"<edge_cases_analysis>\n{analysis}\n</edge_cases_analysis>\n"
        f"<tests>\n{blocks}</tests>\n"
    )


@dataclass
class FakeModelInfo:
    digest: str = "sha256:" + "a" * 64
    quantization_level: str = "Q4_K_M"
    ollama_version: str = "0.12.0"


@dataclass
class FakeSLMClient:
    """Answers ``complete`` from ``table[(problem_id, scenario, seed)]``.

    A value is a completion, an exception instance (raised), or a list of those consumed one per
    call (the last one repeats). Every call is recorded in ``requests``; an unexpected key fails
    the test with that key.
    """

    table: dict
    problem_ids: Iterable[str]
    info: FakeModelInfo = field(default_factory=FakeModelInfo)
    requests: list[dict] = field(default_factory=list)

    def model_info(self, model: str):
        return self.info

    def _problem_of(self, prompt: str) -> str:
        found = [pid for pid in self.problem_ids if pid in prompt]
        if len(found) != 1:
            pytest.fail(f"cannot tell the problem of the prompt (found {found})")
        return found[0]

    def complete(self, model: str, prompt: str, options):
        key = (self._problem_of(prompt), scenario_of(prompt), options.seed)
        self.requests.append(
            {"key": key, "model": model, "prompt": prompt, "options": dataclasses.asdict(options)}
        )
        if key not in self.table:
            pytest.fail(f"unexpected call to the model: {key}")
        answer = self.table[key]
        if isinstance(answer, list):
            answer = answer.pop(0) if len(answer) > 1 else answer[0]
        if isinstance(answer, BaseException):
            raise answer
        return answer


def run_result(
    stdout: bytes = b"",
    *,
    status: RunStatus = RunStatus.OK,
    exit_code: int | None = 0,
    signal: int | None = None,
    cpu_time_s: float = 0.01,
    peak_rss_bytes: int = 8 * 1024 * 1024,
    stderr_tail: bytes = b"",
) -> RunResult:
    """A ``RunResult`` of the engine, OK by default."""
    return RunResult(
        status=status,
        exit_code=exit_code,
        signal=signal,
        stdout=stdout,
        stderr_tail=stderr_tail,
        cpu_time_s=cpu_time_s,
        wall_time_s=cpu_time_s,
        peak_rss_bytes=peak_rss_bytes,
    )


@dataclass
class FakePythonRunner:
    """Answers ``(code, stdin, limits, slot)`` from ``table[(code, stdin)]`` or from a function.

    ``default`` (a function of ``(code, stdin)``) answers what the table does not have; without it,
    an unexpected call fails the test. Every call is recorded in ``calls``.
    """

    table: dict = field(default_factory=dict)
    default: Callable[[str, bytes], RunResult] | None = None
    calls: list[tuple] = field(default_factory=list)

    def __call__(self, code: str, stdin: bytes, limits, slot: int) -> RunResult:
        self.calls.append((code, stdin, limits, slot))
        key = (code, stdin)
        if key in self.table:
            answer = self.table[key]
        elif self.default is not None:
            answer = self.default(code, stdin)
        else:
            pytest.fail(f"unexpected Python run: stdin={stdin!r}")
        if isinstance(answer, BaseException):
            raise answer
        return answer


def echo_runner() -> FakePythonRunner:
    """A runner whose program prints its input back (the synthetic problems are echo problems)."""
    return FakePythonRunner(default=lambda code, stdin: run_result(stdin))


ECHO_PY = "import sys\nsys.stdout.write(sys.stdin.read())\n"


def start_run(root):
    """Write the ``run.json`` a first ``generate`` with the fake client would write; return it."""
    from ai_clients import generation, store
    from ai_clients.prompt import load_template

    run = generation.current_run_config(
        FakeSLMClient({}, problem_ids=[]),
        load_template(),
        root,
        now=lambda: "2026-10-01T12:00:00Z",
        clock=FakeClock(),
        max_infra_retries=1,
        echo=print,
    )
    store.write_run(root, run)
    return run


def record_generation(
    root,
    problem_id: str = "1_A",
    scenario: str = "black_box",
    attempt: int = 1,
    *,
    inputs: Iterable[str] = ("1\n", "2\n"),
    code: str = ECHO_PY,
    parsed: bool = True,
    hardware_label: str = "RTX 3060 12GB",
):
    """Write ``attempt_<n>.generation.json`` as ``generate`` would (no model involved); return it."""
    from ai_clients import store
    from ai_clients.schemas.generation import GenerationRecord
    from tests.ai_clients.test_schemas import generation
    from tests.ai_clients.test_schemas import parsed as parsed_block

    inputs = list(inputs)
    parse = (
        parsed_block(inputs=inputs, reference_py=code, duplicate_inputs=0)
        if parsed
        else {"ok": False, "error": "missing_block:reference_py"}
    )
    run = store.read_run(root)
    record = GenerationRecord(
        **generation(
            problem_id=problem_id,
            scenario=scenario,
            attempt=attempt,
            seed=42 + attempt,
            model_digest=run.model_digest,
            hardware_label=hardware_label,
            parse=parse,
        )
    )
    store.write_generation(root, record)
    return record


@dataclass
class FakeClock:
    """``now()`` and ``sleep(seconds)`` without waiting; every sleep is recorded."""

    current: float = 0.0
    sleeps: list[float] = field(default_factory=list)

    def now(self) -> float:
        return self.current

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.current += seconds
