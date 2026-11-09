"""A fake engine (no C++, no root) and a minimal repository tree for the evaluation tests.

A "program" is the text ``prog:<name>``; the fake engine compiles it to ``Path(<name>)`` (or fails
for ``prog:CE``) and runs it with a Python behaviour: ``behaviour(input, nth_call) -> RunResult``.
Every run is recorded, so a test can check which tests were (not) executed.
"""

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from evaluation.problem_task import Engine
from sandbox.types import CompileResult, ExecutionLimits, RunResult, RunStatus, Test

LIMITS = ExecutionLimits(time_limit_seconds=1.0, memory_limit_bytes=256 * 1024 * 1024)


def ok(stdout: str) -> RunResult:
    return RunResult(RunStatus.OK, 0, None, stdout.encode(), b"", 0.01, 0.01, 1000)


def tle() -> RunResult:
    return RunResult(RunStatus.TIMEOUT, None, 9, b"", b"", 2.0, 2.0, 1000)


def re_() -> RunResult:
    return RunResult(RunStatus.NONZERO_EXIT, 1, None, b"", b"boom", 0.01, 0.01, 1000)


def double(text: str, _call: int = 0) -> RunResult:
    """The reference behaviour: print twice the integer read."""
    return ok(f"{2 * int(text.strip())}\n")


Behaviour = Callable[[str, int], RunResult]


class FakeEngine:
    def __init__(self, programs: dict[str, Behaviour] | None = None) -> None:
        self.programs = dict(programs or {})
        self.compiled: list[str] = []
        self.runs: list[tuple[str, str]] = []
        self._counts: dict[tuple[str, str], int] = {}

    def compile(self, source: str, slot: int) -> CompileResult:
        name = source.removeprefix("prog:").strip()
        self.compiled.append(name)
        if name == "CE":
            return CompileResult(False, None, None, ())
        return CompileResult(True, Path(name), "gnu++20", ())

    def run(self, binary: Path, stdin: bytes, limits: ExecutionLimits, slot: int) -> RunResult:
        name, text = str(binary), stdin.decode()
        self.runs.append((name, text))
        key = (name, text)
        nth = self._counts.get(key, 0)
        self._counts[key] = nth + 1
        return self.programs.get(name, double)(text, nth)

    def runs_of(self, name: str) -> list[str]:
        return [text for program, text in self.runs if program == name]

    def engine(self) -> Engine:
        return Engine(gcc_version="13.2.0", compile=self.compile, run=self.run)


@pytest.fixture
def fake() -> FakeEngine:
    return FakeEngine()


def suite_of(*pairs: tuple[str, str]) -> tuple[Test, ...]:
    return tuple(Test(input=i, output=o) for i, o in pairs)


def _write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, str):
        path.write_text(data, encoding="utf-8")
    else:
        path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


DEFAULT_TESTS = [{"input": "1\n", "output": "2\n"}, {"input": "3\n", "output": "6\n"}]


def make_tree(
    root: Path,
    problems: tuple[str, ...] = ("1_A",),
    *,
    was: int = 2,
    mutants: int = 2,
    suites: dict | None = None,
    slm_attempts: dict | None = None,
    provenance: dict | None = None,
) -> Path:
    """A repository with ``problems``; every suite defaults to DEFAULT_TESTS, status accepted.

    ``suites[(model, problem, scenario)]`` overrides a suite.json (a dict); ``slm_attempts[(problem,
    scenario, n)] = (generation, execution or None)``; ``provenance[(problem, scenario)] = tree``
    writes ``data/suites/slm/provenance.json``.
    """
    root = Path(root)
    suites = suites or {}
    for pid in problems:
        folder = root / "data/dataset/problems" / pid
        _write(folder / "metadata.json", {"time_limit_seconds": 1.0, "memory_limit_bytes": 1 << 28})
        _write(folder / "AC_ref.cpp", "prog:AC")
        for i in range(1, was + 1):
            _write(folder / f"WA_{i}.cpp", f"prog:WA_{i}")
        for i in range(1, mutants + 1):
            _write(root / "data/mutants/problems" / pid / f"Mutant_{i}.cpp", f"prog:Mutant_{i}")
        for model in ("slm", "gpt", "gemini", "claude"):
            for scenario in ("black_box", "white_box", "hybrid"):
                suite = suites.get(
                    (model, pid, scenario), {"status": "accepted", "tests": DEFAULT_TESTS}
                )
                tree = (provenance or {}).get((pid, scenario), f"suites/{model}")
                if model != "slm":
                    tree = f"suites/{model}"
                _write(root / "data" / tree / "problems" / pid / scenario / "suite.json", suite)
    for (pid, scenario, n), (generation, execution) in (slm_attempts or {}).items():
        tree = (provenance or {}).get((pid, scenario), "suites/slm")
        folder = root / "data" / tree / "problems" / pid / scenario
        _write(folder / f"attempt_{n}.generation.json", generation)
        if execution is not None:
            _write(folder / f"attempt_{n}.execution.json", execution)
    if provenance:
        entries = [
            {"problem_id": p, "scenario": s, "tree": t, "superseded_in": None}
            for (p, s), t in sorted(provenance.items())
        ]
        _write(root / "data/suites/slm/provenance.json", {"combinations": entries})
    _write(
        root / "manifests/dataset.manifest.json", {"revision": 2, "problem_count": len(problems)}
    )
    _write(root / "manifests/mutants.manifest.json", {"files": []})
    for model in ("slm", "gpt", "gemini", "claude"):
        _write(root / f"manifests/{model}_suites.manifest.json", {"model": model})
    return root


def solution_attempt(inputs: list[str], outputs: list[str | None], template: str = "solution"):
    """(generation, execution) of an attempt; ``None`` in ``outputs`` is a discarded input."""
    generation = {
        "attempt": 1,
        "template": template,
        "model_failure": None,
        "parse": {"ok": True, "inputs": inputs},
    }
    execution = {
        "attempt": 1,
        "inputs": [
            {"index": i, "kept": out is not None, "output": out} for i, out in enumerate(outputs)
        ],
    }
    return generation, execution
