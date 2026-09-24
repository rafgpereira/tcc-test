"""Shared fixtures for the mutation tests: a fake execution engine and a tiny official suite."""

import hashlib
import zipfile
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pytest

from dataset import config as dataset_config
from dataset.integrity import manifest as manifest_module
from dataset.integrity import packaging
from dataset.persistence import store
from dataset.schemas.report import Provenance
from dataset.validation.engine import Engine
from dataset.validation.suite import Suite
from sandbox.types import (
    CompileAttempt,
    CompileResult,
    ExecutionLimits,
    SuiteVerdict,
    Test,
    Verdict,
)

CE = "CE"  # compilation failure in the script of a fake engine

LIMITS = ExecutionLimits(time_limit_seconds=2.0, memory_limit_bytes=256_000_000)


@pytest.fixture()
def limits() -> ExecutionLimits:
    return LIMITS


@pytest.fixture()
def suite() -> Suite:
    return Suite(
        tests=(Test("1\n", "1\n"), Test("2\n", "2\n")),
        locations=(("public_tests", 0), ("private_tests", 0)),
    )


@dataclass
class FakeEngine:
    """An engine that answers from a script instead of compiling anything.

    ``script`` maps a source text to the answers of its successive suite runs (``Verdict`` values,
    or ``CE`` to fail the compilation); the last answer repeats. A source that is not in the
    script gets ``default``. It may also be a function of the source text. ``compiles`` and ``runs`` count the calls per source.
    """

    script: "dict[str, list] | Callable[[str], list]"
    default: Verdict = Verdict.WA
    deciding: dict[str, list[int]] | None = None  # deciding test per run, when not always 0

    def __post_init__(self) -> None:
        self.compiles: Counter = Counter()
        self.runs: Counter = Counter()
        self._by_binary: dict[Path, str] = {}

    def _answers(self, source: str) -> list:
        if callable(self.script):
            return self.script(source)
        return self.script.get(source, [self.default])

    def compile(self, source: str, slot: int) -> CompileResult:
        self.compiles[source] += 1
        if self._answers(source)[0] == CE:
            attempts = tuple(
                CompileAttempt(s, False, "error")
                for s in ("gnu++20", "gnu++17", "gnu++14", "gnu++11")
            )
            return CompileResult(False, None, None, attempts)
        binary = Path("/fake") / hashlib.sha256(source.encode("utf-8")).hexdigest()
        self._by_binary[binary] = source
        return CompileResult(True, binary, "gnu++20", (CompileAttempt("gnu++20", True, ""),))

    def run_suite(self, binary, tests, limits, slot) -> SuiteVerdict:
        source = self._by_binary[binary]
        call = self.runs[source]
        self.runs[source] += 1
        answers = self._answers(source)
        verdict = answers[min(call, len(answers) - 1)]
        if verdict is Verdict.AC:
            return SuiteVerdict(Verdict.AC, None, None, len(tests), 0.01, 1000, None)
        deciding = self.deciding.get(source, [0]) if self.deciding else [0]
        index = deciding[min(call, len(deciding) - 1)]
        return SuiteVerdict(verdict, None, index, index + 1, 0.01, 1000, None)

    def as_engine(self) -> Engine:
        return Engine(gcc_version="13.2.0", compile=self.compile, run_suite=self.run_suite)


@pytest.fixture()
def make_engine():
    def _make(script=None, default=Verdict.WA, deciding=None) -> FakeEngine:
        return FakeEngine(script or {}, default, deciding)

    return _make


FIXTURES = Path(__file__).parent / "fixtures"
PROVENANCE = Provenance(
    hf_dataset=dataset_config.HF_DATASET, hf_revision=dataset_config.HF_REVISION, seed=42
)


def build_dataset(root: Path, problems: dict[str, dict[str, str]]) -> Path:
    """Write a packaged, manifested and extracted dataset under ``root`` (like a fresh clone).

    ``problems`` maps a problem id to its files (name -> text); each problem also gets the
    ``validacao.json`` the packager needs to consider it complete.
    """
    store.ensure_work_dir(root)
    for problem_id, files in problems.items():
        folder = store.start_building(root, problem_id)
        for name, content in files.items():
            store.write_problem_text(folder, name, content)
        store.write_problem_json(
            folder, "validacao.json", {"problem_id": problem_id, "status": "complete"}
        )
        store.finalize_building(root, problem_id)
    result = packaging.build_dataset_zip(root, root / "data" / "dataset.zip")
    manifest = manifest_module.build_manifest(root, result.zip_path, provenance=PROVENANCE)
    manifest_module.write_manifest(root, manifest)
    with zipfile.ZipFile(result.zip_path) as archive:
        archive.extractall(root / "data")
    return root


@pytest.fixture()
def dataset_builder():
    return build_dataset


@pytest.fixture()
def dense_problem() -> dict[str, str]:
    """The files of the real problem 189_C (kept under ``tests/mutation/fixtures/``).

    Its ``AC_ref.cpp`` has 259 first-order candidates, more than the quota of 100.
    """
    folder = FIXTURES / "189_C"
    return {p.name: p.read_text(encoding="utf-8") for p in sorted(folder.iterdir())}


@pytest.fixture()
def sparse_problem(dense_problem) -> dict[str, str]:
    """Problem ``189_D``: its ``AC_ref.cpp`` has far fewer than 100 first-order candidates."""
    renamed = {
        name: text.replace('"problem_id": "189_C"', '"problem_id": "189_D"')
        for name, text in dense_problem.items()
    }
    return {**renamed, "AC_ref.cpp": "int a, b;\nint main() { return a < b; }\n"}
