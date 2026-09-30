"""``suite.json``: the terminal state of one problem × scenario (the unified suite format).

A pure function of the attempt files next to it. The test cases have EXACTLY the shape of the
existing test-case contract of ``testes.json`` (``dataset.schemas.testes.TestCase``: ``input``,
``output``), so the evaluation turns each one into a ``sandbox.types.Test`` without renaming
fields. ``output`` is the expected output, obtained by really running the Python solution.
"""

from pydantic import Field, model_validator

from ai_clients import config
from ai_clients.schemas.common import (
    Attempt,
    AttemptFailure,
    InputDiscard,
    NonNegative,
    Scenario,
    SuiteStatus,
)
from dataset.schemas.common import PROBLEM_ID_PATTERN, Schema, SchemaVersion
from dataset.schemas.testes import TestCase
from sandbox.types import Verdict


class AttemptSummary(Schema):
    attempt: Attempt
    seed: int
    hardware_label: str = Field(min_length=1)
    failure: AttemptFailure | None  # null only for the accepted attempt
    detail: str  # parser code, failing public test and verdict, or kept/discarded counts


class DiscardedInput(Schema):
    index: NonNegative
    discard: InputDiscard
    verdict: Verdict | None


class SlmSuite(Schema):
    schema_version: SchemaVersion = 1
    problem_id: str = Field(pattern=PROBLEM_ID_PATTERN)
    scenario: Scenario
    model: str = Field(min_length=1)
    model_digest: str = Field(min_length=1)
    status: SuiteStatus
    attempts: list[AttemptSummary] = Field(min_length=1, max_length=config.MAX_ATTEMPTS)
    accepted_attempt: Attempt | None
    tests: list[TestCase]
    suite_size: NonNegative
    discarded_inputs: list[DiscardedInput]
    duplicate_inputs: NonNegative

    @model_validator(mode="after")
    def _terminal_state(self) -> "SlmSuite":
        numbers = [a.attempt for a in self.attempts]
        if numbers != list(range(1, len(numbers) + 1)):
            raise ValueError("attempts are numbered from 1 without gaps")
        for a in self.attempts:
            if a.seed != config.seed_for(a.attempt):
                raise ValueError(f"attempt {a.attempt} must use seed {config.seed_for(a.attempt)}")
        if self.suite_size != len(self.tests):
            raise ValueError("suite_size is the number of tests")
        *earlier, last = self.attempts
        if any(a.failure is None for a in earlier):
            raise ValueError("only the last attempt can have succeeded")
        if self.status is SuiteStatus.ACCEPTED:
            if last.failure is not None or self.accepted_attempt != last.attempt:
                raise ValueError("an accepted suite comes from its last attempt, which succeeded")
            if not self.tests:
                raise ValueError("an accepted suite is never empty")
        else:
            if len(self.attempts) != config.MAX_ATTEMPTS or last.failure is None:
                raise ValueError(
                    f"a discarded suite has exactly {config.MAX_ATTEMPTS} failed attempts"
                )
            if self.accepted_attempt is not None or self.tests or self.discarded_inputs:
                raise ValueError("a discarded suite has no tests and no accepted attempt")
        return self
