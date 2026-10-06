"""``suite.json``: the terminal state of one problem × scenario (the unified suite format).

A pure function of the files next to it. The test cases have EXACTLY the shape of the existing
test-case contract of ``testes.json`` (``dataset.schemas.testes.TestCase``: ``input``,
``output``), so the evaluation turns each one into a ``sandbox.types.Test`` without renaming
fields. ``output`` is the expected output, obtained by really running the Python solution, except
in an ``accepted_predicted`` suite, where the model wrote it.
"""

from pydantic import Field, model_validator

from ai_clients import config
from ai_clients.schemas.common import (
    Attempt,
    AttemptFailure,
    AttemptKind,
    AttemptPhase,
    InputDiscard,
    NonNegative,
    Scenario,
    SchemaVersion,
    SuitePhase,
    SuiteStatus,
)
from dataset.schemas.common import PROBLEM_ID_PATTERN, Schema
from dataset.schemas.testes import TestCase
from sandbox.types import Verdict


class AttemptSummary(Schema):
    attempt: Attempt
    phase: AttemptPhase
    seed: int
    temperature: float
    template: AttemptKind
    hardware_label: str = Field(min_length=1)
    failure: AttemptFailure | None  # null only for an accepted solution or a parsed prediction
    detail: str  # parser code, failing public test and verdict, and/or kept/discarded counts
    # Only for a solution that failed a public test by WA and kept some generated input.
    fallback_eligible: bool = False


class DiscardedInput(Schema):
    index: NonNegative
    discard: InputDiscard
    verdict: Verdict | None


class ManualCloseInfo(Schema):
    """The decision of the authors, copied from ``manual_close.json``."""

    reason: str = Field(min_length=1)
    closed_at: str


class SlmSuite(Schema):
    schema_version: SchemaVersion = 2
    problem_id: str = Field(pattern=PROBLEM_ID_PATTERN)
    scenario: Scenario
    model: str = Field(min_length=1)
    model_digest: str = Field(min_length=1)
    status: SuiteStatus
    accepted_phase: SuitePhase | None  # 1 or 2 (accepted), 3 (fallback), 4 (predicted)
    attempts: list[AttemptSummary] = Field(min_length=1, max_length=config.MAX_ATTEMPTS)
    accepted_attempt: Attempt | None
    tests: list[TestCase]
    suite_size: NonNegative
    discarded_inputs: list[DiscardedInput]
    duplicate_inputs: NonNegative
    manual_close: ManualCloseInfo | None = None

    @model_validator(mode="after")
    def _terminal_state(self) -> "SlmSuite":
        solutions = config.SOLUTION_ATTEMPTS
        numbers = [a.attempt for a in self.attempts]
        if numbers != list(range(1, len(numbers) + 1)):
            raise ValueError("attempts are numbered from 1 without gaps")
        for a in self.attempts:
            spec = config.attempt_spec(a.attempt)
            row = (a.phase, a.seed, a.temperature, a.template.value)
            if row != (spec.phase, spec.seed, spec.temperature, spec.template):
                raise ValueError(f"attempt {a.attempt} is not the row of the attempt policy")
            if a.fallback_eligible and (
                a.template is not AttemptKind.SOLUTION
                or a.failure is not AttemptFailure.PUBLIC_TEST_FAILED
            ):
                raise ValueError("only a solution that failed a public test can be a fallback")
        if self.suite_size != len(self.tests):
            raise ValueError("suite_size is the number of tests")
        *earlier, last = self.attempts
        if any(a.failure is None for a in earlier):
            raise ValueError("only the last attempt can have succeeded")
        n = len(self.attempts)
        fallback = [a.attempt for a in self.attempts if a.fallback_eligible]
        if n > solutions and fallback:
            raise ValueError("a prediction comes only when no solution can be the fallback")
        status = self.status
        if (status is SuiteStatus.DISCARDED_MANUAL) != (self.manual_close is not None):
            raise ValueError("only a suite closed by the authors has manual_close")
        if status is SuiteStatus.DISCARDED_MANUAL:
            if n != config.MAX_ATTEMPTS or last.failure is None:
                raise ValueError(
                    f"a suite closed by the authors has {config.MAX_ATTEMPTS} failed attempts"
                )
            if self.accepted_attempt is not None or self.tests or self.discarded_inputs:
                raise ValueError("a suite closed by the authors has no tests")
            if self.accepted_phase is not None:
                raise ValueError("a suite closed by the authors has no accepted phase")
            return self
        if not self.tests or self.accepted_attempt is None:
            raise ValueError("a suite is never empty and always has the attempt it comes from")
        if (last.failure is None) != (
            status in (SuiteStatus.ACCEPTED, SuiteStatus.ACCEPTED_PREDICTED)
        ):
            raise ValueError(f"the last attempt of an {status.value} suite has the wrong outcome")
        if status is SuiteStatus.ACCEPTED:
            if last.template is not AttemptKind.SOLUTION or self.accepted_attempt != last.attempt:
                raise ValueError("an accepted suite comes from its last attempt, a solution")
            phase = last.phase
        elif status is SuiteStatus.ACCEPTED_PREDICTED:
            if last.template is not AttemptKind.PREDICTION or self.accepted_attempt != last.attempt:
                raise ValueError("a predicted suite comes from its last attempt, a prediction")
            if self.discarded_inputs:
                raise ValueError("nothing of a predicted suite was run, so nothing was discarded")
            phase = 4
        else:  # ACCEPTED_FALLBACK
            if n != solutions or self.accepted_attempt not in fallback:
                raise ValueError(
                    f"a fallback suite comes after {solutions} failed solutions, from one of them "
                    "that can be a fallback"
                )
            phase = config.FALLBACK_PHASE
        if self.accepted_phase != phase:
            raise ValueError(f"an {status.value} suite has accepted_phase {phase}")
        return self
