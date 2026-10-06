"""``attempt_<n>.execution.json``: the reference solution of one attempt, run in the sandbox.

Exists only for a solution attempt whose answer was parsed (never for a prediction). Written once by
``execute``, never changed. ``AC_ref.cpp`` plays no part in it: the solution is judged by the public
tests of the problem only. The generated inputs always run, even after a public test failed: by WA
the attempt can still become a fallback suite, by RE, TLE or MLE a low-confidence one
(``config.py``).
"""

from typing import Literal

from pydantic import Field, model_validator

from ai_clients.schemas.common import Attempt, AttemptFailure, InputDiscard, NonNegative, Scenario
from dataset.schemas.common import PROBLEM_ID_PATTERN, Schema, SchemaVersion
from sandbox.types import Verdict


class EffectiveLimits(Schema):
    """The limits the Python solution ran under, and the limits of the problem they come from."""

    time_limit_seconds: float = Field(gt=0)
    memory_limit_bytes: int = Field(gt=0)
    problem_time_limit_seconds: float = Field(gt=0)
    problem_memory_limit_bytes: int = Field(gt=0)


class PublicTestsSummary(Schema):
    total: int = Field(ge=1)
    passed: NonNegative
    failed_index: NonNegative | None  # the first public test that was not AC (short-circuit)
    failed_verdict: Verdict | None
    # Diagnosis of the failing run only (the expected output is the one of `testes.json` at
    # `failed_index`). Null without a failure, and in records written before they existed.
    failed_output_head: str | None = None  # start of the real stdout, never normalized
    failed_stderr_tail: str | None = None
    failed_cpu_time_s: float | None = Field(default=None, ge=0)
    failed_peak_rss_bytes: NonNegative | None = None

    @model_validator(mode="after")
    def _coherent(self) -> "PublicTestsSummary":
        if (self.failed_index is None) != (self.failed_verdict is None):
            raise ValueError("failed_index and failed_verdict are both set or both null")
        diagnosis = (
            self.failed_output_head,
            self.failed_stderr_tail,
            self.failed_cpu_time_s,
            self.failed_peak_rss_bytes,
        )
        if self.failed_index is None and any(item is not None for item in diagnosis):
            raise ValueError("only a failing public test has a diagnosis")
        if self.failed_verdict is Verdict.AC:
            raise ValueError("an AC is not a failure")
        if self.failed_index is None and self.passed != self.total:
            raise ValueError("without a failure every public test passed")
        if self.failed_index is not None and (
            self.failed_index >= self.total or self.passed != self.failed_index
        ):
            raise ValueError("the tests before the failing one passed, and only those")
        return self


class InputOutcome(Schema):
    index: NonNegative  # position in the `inputs` of the generation
    kept: bool
    output: str | None  # the real stdout, never normalized; only for a kept input
    discard: InputDiscard | None
    verdict: Verdict | None
    cpu_time_s: float = Field(ge=0)
    peak_rss_bytes: NonNegative
    stderr_tail: str

    @model_validator(mode="after")
    def _kept_or_discarded(self) -> "InputOutcome":
        if self.kept and (self.output is None or self.discard is not None):
            raise ValueError("a kept input has an output and no discard reason")
        if not self.kept and (self.output is not None or self.discard is None):
            raise ValueError("a discarded input has a reason and no output")
        return self


class ExecutionRecord(Schema):
    schema_version: SchemaVersion = 1
    problem_id: str = Field(pattern=PROBLEM_ID_PATTERN)
    scenario: Scenario
    attempt: Attempt
    limits: EffectiveLimits
    interpreter: str = Field(min_length=1)
    public_tests: PublicTestsSummary
    inputs: list[InputOutcome]
    outcome: Literal["accepted"] | AttemptFailure

    @model_validator(mode="after")
    def _outcome_follows_from_the_runs(self) -> "ExecutionRecord":
        if [item.index for item in self.inputs] != list(range(len(self.inputs))):
            raise ValueError("inputs are listed in the order of the generation, one per input")
        if not self.inputs:
            raise ValueError("every generated input has an outcome, even after a public failure")
        if self.public_tests.failed_index is not None:
            expected = AttemptFailure.PUBLIC_TEST_FAILED
        elif not any(item.kept for item in self.inputs):
            expected = AttemptFailure.ALL_INPUTS_FAILED
        else:
            expected = "accepted"
        if self.outcome != expected:
            raise ValueError(f"outcome must be {getattr(expected, 'value', expected)!r}")
        return self
