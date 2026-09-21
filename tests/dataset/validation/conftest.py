"""Fake engine and helpers for the validation tests (they need neither root nor a container).

Sources drive the fake: a `// MARK` comment on the first line says how the program behaves.

    // AC             passes every test
    // WA@n           wrong answer on test n (0-based, in suite order)
    // TLE@n, MLE@n, RE@n   time limit, memory limit or runtime error on test n
    // CE             does not compile
    // FLAKY          WA@0 on the first run and WA@1 on the second (unstable verdict)
    // FMT@n          prints the right tokens with different spacing on test n (a WA for the engine)
"""

import re
import threading
import time
from pathlib import Path

import pytest

from dataset.schemas.pool import IncorrectSolution, RawProblem, RawTestGroup
from dataset.validation.engine import Engine
from sandbox.types import (
    CompileAttempt,
    CompileResult,
    RunResult,
    RunStatus,
    SuiteVerdict,
    TestVerdict,
    Verdict,
)

MARK = re.compile(r"^// (AC|CE|FLAKY|WA|TLE|MLE|RE|FMT)(?:@(\d+))?")


def _run(**kw) -> RunResult:
    base = dict(
        status=RunStatus.OK,
        exit_code=0,
        signal=None,
        stdout=b"",
        stderr_tail=b"",
        cpu_time_s=0.01,
        wall_time_s=0.01,
        peak_rss_bytes=1_000_000,
    )
    return RunResult(**{**base, **kw})


class FakeEngine:
    """Behaves according to the mark on the first line of each source."""

    def __init__(self, delay=None):
        self.compiled: list[str] = []
        self.suite_runs: list[str] = []
        self.slots: list[int] = []
        self.flaky_calls: dict[str, int] = {}
        self.delay = delay or {}
        self.lock = threading.Lock()

    # -- Engine API ---------------------------------------------------------------------------
    def compile(self, source: str, slot: int) -> CompileResult:
        with self.lock:
            self.compiled.append(source)
            self.slots.append(slot)
        kind = MARK.match(source)
        if kind and kind.group(1) == "CE":
            attempts = tuple(
                CompileAttempt(s, False, f"{s}: error: expected ';'")
                for s in ("gnu++20", "gnu++17", "gnu++14", "gnu++11")
            )
            return CompileResult(False, None, None, attempts)
        std = "gnu++14" if "LEGACY" in source else "gnu++20"
        return CompileResult(
            True, Path(f"/fake/{abs(hash(source))}"), std, (CompileAttempt(std, True, ""),)
        )

    def run_suite(self, binary, tests, limits, slot) -> SuiteVerdict:
        raise AssertionError("use as_engine(): the fake needs the source")

    # -- helpers ------------------------------------------------------------------------------
    def judge(self, source, tests, limits, slot, std):
        with self.lock:
            self.suite_runs.append(source)
        time.sleep(self.delay.get(source, 0))
        kind = MARK.match(source)
        name, at = (kind.group(1), int(kind.group(2) or 0)) if kind else ("AC", 0)
        if name == "FLAKY":
            with self.lock:
                n = self.flaky_calls.get(source, 0)
                self.flaky_calls[source] = n + 1
            name, at = "WA", n % 2
        if name == "AC":
            return SuiteVerdict(Verdict.AC, std, None, len(tests), 0.05, 2_000_000, None)
        at = min(at, len(tests) - 1)
        verdict = Verdict.WA if name == "FMT" else Verdict[name]
        actual = {"WA": "WRONG\n", "FMT": "1  2\n"}.get(name, "")
        if name == "FMT":
            tests_out = tests[at].output
            actual = "  ".join(tests_out.split()) + "\n\n"
        failure = TestVerdict(verdict, _run(stdout=actual.encode()), tests[at].output, actual)
        return SuiteVerdict(verdict, std, at, at + 1, 0.05, 2_000_000, failure)

    def as_engine(self) -> Engine:
        engine = self
        last_std = {}

        def compile_(source, slot):
            result = engine.compile(source, slot)
            if result.binary is not None:
                last_std[result.binary] = (source, result.standard_used)
            return result

        def run_suite(binary, tests, limits, slot):
            source, std = last_std[binary]
            return engine.judge(source, tests, limits, slot, std)

        return Engine(gcc_version="13.2.0", compile=compile_, run_suite=run_suite)


@pytest.fixture()
def fake():
    return FakeEngine()


def _make_raw(
    problem_id="1101_A",
    *,
    ac=("// AC\nint main(){return 0;}",),
    wa=None,
    n_tests=(1, 1, 2),
    limit=2.0,
    memory=256_000_000,
    split="train",
) -> RawProblem:
    """A raw problem. `wa` is a list of sources (default: 120 distinct wrong candidates)."""
    if wa is None:
        wa = [f"// WA@{i % 3}\nint main(){{return {i};}}" for i in range(120)]
    groups = []
    for size in n_tests:
        groups.append(
            RawTestGroup(
                input=[f"{i}\n" for i in range(size)], output=[f"{i * 2}\n" for i in range(size)]
            )
        )
    contest, index = problem_id.split("_")
    return RawProblem(
        problem_id=problem_id,
        split=split,
        shard_index=0,
        source_row=0,
        name="Minimum Integer",
        description="Read n.\r\nPrint 2n.\r\n",
        cf_contest_id=int(contest),
        cf_index=index,
        cf_rating=1200,
        cf_points=500.0,
        cf_tags=["dp", "math"],
        is_description_translated=False,
        time_limit_seconds=limit,
        memory_limit_bytes=memory,
        public_tests=groups[0],
        private_tests=groups[1],
        generated_tests=groups[2],
        correct_solutions=list(ac),
        incorrect_solutions=[IncorrectSolution(index=10 + i, source=s) for i, s in enumerate(wa)],
    )


@pytest.fixture()
def make_raw():
    """Factory of raw problems: ``make_raw(problem_id, ac=..., wa=[...], n_tests=(a, b, c))``."""
    return _make_raw
