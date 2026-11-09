"""What one problem gives to the evaluation: its programs, its limits and the suites to run.

contracts/evaluation-api.md, ``evaluation.sources``. The suites and the attempts are read with a
small view of the fields this module needs (``status``, ``tests``; the template, the parse and the
kept inputs of an attempt): their full schemas belong to ``ai_clients``, whose packages are already
checked by ``ai_clients verify`` and by ``cli check --deep`` before an evaluation starts (FR-002).
The rule that turns an attempt into tests is the one of ``ai_clients.store._build_suite``: the
kept inputs, in order, with the output of the model's own solution.
"""

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from evaluation import config
from evaluation.schemas.result import SuiteSource
from sandbox.types import ExecutionLimits, Test

_NUMBERED = re.compile(r"^(WA|Mutant)_([1-9]\d*)\.cpp$")


class _View(BaseModel):
    model_config = ConfigDict(extra="ignore")


class _TestView(_View):
    input: str
    output: str


class _SuiteView(_View):
    status: str
    tests: list[_TestView]


class _ParseView(_View):
    ok: bool
    inputs: list[str] | None = None


class _GenerationView(_View):
    attempt: int
    template: str
    model_failure: dict | None = None
    parse: _ParseView


class _InputView(_View):
    index: int
    kept: bool
    output: str | None = None


class _ExecutionView(_View):
    attempt: int
    inputs: list[_InputView] = []


@dataclass(frozen=True)
class Target:
    name: str  # WA_<n> or Mutant_<n>
    kind: str  # "wa" or "mutant"
    source: str


@dataclass(frozen=True)
class ProblemTargets:
    problem_id: str
    ac_source: str
    targets: tuple[Target, ...]  # WA_1..WA_n, then Mutant_1..Mutant_m
    limits: ExecutionLimits


@dataclass(frozen=True)
class SuiteToEvaluate:
    tests: tuple[Test, ...]
    source: SuiteSource
    no_suite_reason: str | None  # set if and only if there are no tests


def _sha256(*blobs: bytes) -> str:
    digest = hashlib.sha256()
    for blob in blobs:
        digest.update(blob)
    return digest.hexdigest()


def _numbered(folder: Path, prefix: str) -> list[tuple[int, Path]]:
    found = []
    for path in folder.iterdir():
        match = _NUMBERED.match(path.name)
        if match and match.group(1) == prefix:
            found.append((int(match.group(2)), path))
    found.sort()
    numbers = [n for n, _ in found]
    if numbers != list(range(1, len(numbers) + 1)):
        raise ValueError(f"{folder}: {prefix}_<n>.cpp are not numbered 1..n without a gap")
    return found


def problem_targets(root: Path, problem_id: str) -> ProblemTargets:
    """``AC_ref``, the WAs, the mutants and the limits of the problem (never a fixed limit)."""
    root = Path(root)
    dataset = root / config.DATASET_PROBLEMS_DIR / problem_id
    mutants = root / config.MUTANTS_PROBLEMS_DIR / problem_id
    metadata = json.loads((dataset / "metadata.json").read_text(encoding="utf-8"))
    limits = ExecutionLimits(
        time_limit_seconds=float(metadata["time_limit_seconds"]),
        memory_limit_bytes=int(metadata["memory_limit_bytes"]),
    )
    targets = [
        Target(path.stem, "wa", path.read_text(encoding="utf-8"))
        for _, path in _numbered(dataset, "WA")
    ] + [
        Target(path.stem, "mutant", path.read_text(encoding="utf-8"))
        for _, path in _numbered(mutants, "Mutant")
    ]
    return ProblemTargets(
        problem_id=problem_id,
        ac_source=(dataset / "AC_ref.cpp").read_text(encoding="utf-8"),
        targets=tuple(targets),
        limits=limits,
    )


def suite_tree(root: Path, model: str, problem_id: str, scenario: str) -> str:
    """The tree that holds the suite in force, relative to ``data/`` (e.g. ``suites/slm-rev1``)."""
    if model == "slm":
        provenance = Path(root) / config.SLM_PROVENANCE
        if provenance.is_file():
            entries = json.loads(provenance.read_text(encoding="utf-8"))["combinations"]
            for entry in entries:
                in_force = not entry.get("superseded_in")
                if in_force and (entry["problem_id"], entry["scenario"]) == (problem_id, scenario):
                    return entry["tree"]
            raise ValueError(f"{problem_id} {scenario}: not in {config.SLM_PROVENANCE}")
    return f"suites/{model}"


def _combination_dir(root: Path, tree: str, problem_id: str, scenario: str) -> Path:
    return Path(root) / config.DATA_DIR / tree / "problems" / problem_id / scenario


def final_suite(root: Path, model: str, problem_id: str, scenario: str) -> SuiteToEvaluate:
    """The ``suite.json`` in force; ``discarded_manual`` is a combination without a suite."""
    tree = suite_tree(root, model, problem_id, scenario)
    raw = (_combination_dir(root, tree, problem_id, scenario) / config.SUITE_FILE).read_bytes()
    suite = _SuiteView.model_validate_json(raw)
    source = SuiteSource(status=suite.status, tree=tree, attempt=None, suite_sha256=_sha256(raw))
    if suite.status == "discarded_manual":
        return SuiteToEvaluate((), source, "discarded_manual")
    if not suite.tests:
        raise ValueError(f"{tree} {problem_id} {scenario}: a {suite.status} suite has no tests")
    tests = tuple(Test(input=t.input, output=t.output) for t in suite.tests)
    return SuiteToEvaluate(tests, source, None)


def attempt_suite(root: Path, problem_id: str, scenario: str, attempt: int) -> SuiteToEvaluate:
    """The tests of one attempt of the local model, even if it was rejected on a public test."""
    tree = suite_tree(root, "slm", problem_id, scenario)
    folder = _combination_dir(root, tree, problem_id, scenario)
    generation_path = folder / f"attempt_{attempt}.generation.json"
    execution_path = folder / f"attempt_{attempt}.execution.json"

    def without(reason: str, *blobs: bytes) -> SuiteToEvaluate:
        sha = _sha256(*blobs) if blobs else None
        source = SuiteSource(status=None, tree=tree, attempt=attempt, suite_sha256=sha)
        return SuiteToEvaluate((), source, reason)

    if not generation_path.is_file():
        return without("attempt_missing")
    generation_raw = generation_path.read_bytes()
    generation = _GenerationView.model_validate_json(generation_raw)
    if generation.template == "prediction":
        return without("prediction_attempt", generation_raw)
    if generation.model_failure is not None or not generation.parse.ok:
        return without("attempt_without_tests", generation_raw)
    if not execution_path.is_file():
        return without("attempt_without_tests", generation_raw)
    execution_raw = execution_path.read_bytes()
    execution = _ExecutionView.model_validate_json(execution_raw)
    inputs = generation.parse.inputs or []
    tests = tuple(
        Test(input=inputs[item.index], output=item.output)
        for item in execution.inputs
        if item.kept and item.output is not None
    )
    if not tests:
        return without("attempt_without_tests", generation_raw, execution_raw)
    source = SuiteSource(
        status=None, tree=tree, attempt=attempt, suite_sha256=_sha256(generation_raw, execution_raw)
    )
    return SuiteToEvaluate(tests, source, None)


def suite_for(root: Path, set_name: str, problem_id: str, scenario: str) -> SuiteToEvaluate:
    """The suite an evaluation set runs for one combination."""
    model = config.SET_MODEL[set_name]
    attempt = config.SET_ATTEMPT.get(set_name)
    if attempt is not None:
        return attempt_suite(root, problem_id, scenario, attempt)
    return final_suite(root, model, problem_id, scenario)


def dataset_problem_ids(root: Path) -> list[str]:
    folder = Path(root) / config.DATASET_PROBLEMS_DIR
    return sorted(p.name for p in folder.iterdir() if p.is_dir()) if folder.is_dir() else []
