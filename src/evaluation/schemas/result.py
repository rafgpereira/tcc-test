"""``<scenario>.json``: the evaluation of one suite against the AC, the WAs and the mutants.

specs/009-suite-evaluation/data-model.md, "CombinationResult". Every rule that ties two fields
together is checked here, so a result that contradicts itself can never be written or read.
"""

import re
from typing import Literal

from pydantic import Field, model_validator

from dataset.schemas.common import PROBLEM_ID_PATTERN, Schema, SchemaVersion

SetName = Literal["slm", "gpt", "gemini", "claude", "slm-attempt1"]
Model = Literal["slm", "gpt", "gemini", "claude"]
Scenario = Literal["black_box", "white_box", "hybrid"]
ErrorKind = Literal["RE", "TLE", "MLE"]
AcVerdict = Literal["passed", "wrong_output", "runtime_error"]
RunVerdict = Literal["passed", "wrong_output", "RE", "TLE", "MLE"]
DetectionVerdict = Literal["wrong_output", "RE", "TLE", "MLE"]
SuiteStatus = Literal[
    "accepted", "accepted_fallback", "accepted_predicted", "accepted_barred", "discarded_manual"
]
NoSuiteReason = Literal[
    "discarded_manual", "attempt_without_tests", "prediction_attempt", "attempt_missing"
]

_TARGET = re.compile(r"^(WA|Mutant)_([1-9]\d*)$")
_SHA = r"^[0-9a-f]{64}$"


class RunOutcome(Schema):
    verdict: RunVerdict
    cpu_time_s: float = Field(ge=0)
    peak_memory_bytes: int = Field(ge=0)


class AcTest(Schema):
    index: int = Field(ge=0)
    verdict: AcVerdict
    error_kind: ErrorKind | None
    actual_output: str
    cpu_time_s: float = Field(ge=0)
    peak_memory_bytes: int = Field(ge=0)
    unstable: bool
    runs: list[RunOutcome] | None

    @model_validator(mode="after")
    def _coherent(self) -> "AcTest":
        if (self.verdict == "runtime_error") != (self.error_kind is not None):
            raise ValueError("error_kind is set if and only if the verdict is runtime_error")
        if self.verdict == "runtime_error" and self.actual_output:
            raise ValueError("a runtime_error has no actual_output")
        if self.runs is not None and len(self.runs) != 3:
            raise ValueError("runs has exactly 3 items when the test was repeated")
        if self.unstable and self.runs is None:
            raise ValueError("an unstable test keeps its 3 runs")
        if self.unstable and self.verdict == "runtime_error":
            raise ValueError("an unstable test ends without a runtime error")
        return self


class AcResult(Schema):
    approved: bool
    standard_used: str = Field(min_length=1)
    tests: list[AcTest] = Field(min_length=1)

    @model_validator(mode="after")
    def _coherent(self) -> "AcResult":
        if [t.index for t in self.tests] != list(range(len(self.tests))):
            raise ValueError("the AC tests are indexed 0..n-1, in the order of the suite")
        if self.approved != all(t.verdict == "passed" for t in self.tests):
            raise ValueError("approved if and only if every test is passed")
        return self


class Detection(Schema):
    detected: bool
    test_index: int | None = Field(default=None, ge=0)
    verdict: DetectionVerdict | None = None

    @model_validator(mode="after")
    def _coherent(self) -> "Detection":
        if self.detected != (self.test_index is not None) or self.detected != (
            self.verdict is not None
        ):
            raise ValueError("test_index and verdict are set if and only if detected")
        return self


NOT_DETECTED = Detection(detected=False)


class TargetResult(Schema):
    target: str
    kind: Literal["wa", "mutant"]
    compiled: bool
    declared: Detection
    corrected: Detection
    tests_run: int = Field(ge=0)
    unstable_tests: list[int]

    @model_validator(mode="after")
    def _coherent(self) -> "TargetResult":
        match = _TARGET.match(self.target)
        if match is None or (match.group(1) == "WA") != (self.kind == "wa"):
            raise ValueError(f"{self.target!r} is not a target of kind {self.kind}")
        if not self.compiled and (
            self.declared.detected or self.corrected.detected or self.tests_run
        ):
            raise ValueError("a target that did not compile runs nothing and is never detected")
        return self


class DetectedSets(Schema):
    declared_wa: list[str]
    declared_mutants: list[str]
    corrected_wa: list[str]
    corrected_mutants: list[str]


def target_order(name: str) -> tuple[int, int]:
    match = _TARGET.match(name)
    if match is None:
        raise ValueError(f"{name!r} is not a target")
    return (0 if match.group(1) == "WA" else 1, int(match.group(2)))


def detected_sets(targets: list[TargetResult]) -> DetectedSets:
    def names(kind: str, oracle: str) -> list[str]:
        return [t.target for t in targets if t.kind == kind and getattr(t, oracle).detected]

    return DetectedSets(
        declared_wa=names("wa", "declared"),
        declared_mutants=names("mutant", "declared"),
        corrected_wa=names("wa", "corrected"),
        corrected_mutants=names("mutant", "corrected"),
    )


class SuiteSource(Schema):
    status: SuiteStatus | None
    tree: str = Field(min_length=1)
    attempt: int | None = Field(default=None, ge=1)
    suite_sha256: str | None = Field(default=None, pattern=_SHA)


class CombinationResult(Schema):
    schema_version: SchemaVersion = 1
    set: SetName
    model: Model
    problem_id: str = Field(pattern=PROBLEM_ID_PATTERN)
    scenario: Scenario
    suite_source: SuiteSource
    has_suite: bool
    no_suite_reason: NoSuiteReason | None
    suite_size: int = Field(ge=0)
    ac: AcResult | None
    corrected_oracle_tests: int = Field(ge=0)
    corrected_oracle_excluded: int = Field(ge=0)
    targets: list[TargetResult]
    detected: DetectedSets
    elapsed_s: float = Field(ge=0)

    @model_validator(mode="after")
    def _coherent(self) -> "CombinationResult":
        if self.has_suite == (self.no_suite_reason is not None):
            raise ValueError("no_suite_reason is set if and only if there is no suite")
        if not self.has_suite:
            if self.ac is not None or self.targets or self.suite_size:
                raise ValueError("a combination without a suite has no AC, targets or tests")
        else:
            if self.ac is None or len(self.ac.tests) != self.suite_size or not self.targets:
                raise ValueError("a combination with a suite has the AC on every test and targets")
            valid = sum(t.verdict != "runtime_error" for t in self.ac.tests)
            if self.corrected_oracle_tests != valid:
                raise ValueError("corrected_oracle_tests counts the AC tests without an error")
        if self.corrected_oracle_excluded != self.suite_size - self.corrected_oracle_tests:
            raise ValueError("corrected_oracle_excluded == suite_size - corrected_oracle_tests")
        names = [t.target for t in self.targets]
        if names != sorted(names, key=target_order) or len(set(names)) != len(names):
            raise ValueError("targets are unique and ordered WA_1.., then Mutant_1..")
        for kind, prefix in (("wa", "WA"), ("mutant", "Mutant")):
            numbers = [target_order(t.target)[1] for t in self.targets if t.kind == kind]
            if numbers != list(range(1, len(numbers) + 1)):
                raise ValueError(f"the {prefix} targets are numbered 1..n without a gap")
        for t in self.targets:
            for oracle in ("declared", "corrected"):
                index = getattr(t, oracle).test_index
                if index is not None and index >= self.suite_size:
                    raise ValueError(f"{t.target}: test_index outside the suite")
        if self.detected != detected_sets(self.targets):
            raise ValueError("detected must be the sets derived from targets")
        return self
