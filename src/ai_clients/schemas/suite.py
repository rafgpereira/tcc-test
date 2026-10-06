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
    kind: AttemptKind
    hardware_label: str = Field(min_length=1)
    failure: AttemptFailure | None  # null only for an attempt that passed or a parsed prediction
    detail: str  # parser code, failing public test and verdict, and/or kept/discarded counts
    # Only for a solution that failed a public test and kept some generated input: by WA it could
    # be the fallback suite, by RE/TLE/MLE the low-confidence one (config.py).
    fallback_eligible: bool = False
    low_confidence_eligible: bool = False


class DiscardedInput(Schema):
    index: NonNegative
    discard: InputDiscard
    verdict: Verdict | None


class ManualCloseInfo(Schema):
    """The decision of the authors, copied from ``manual_close.json``."""

    reason: str = Field(min_length=1)
    closed_at: str


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
    manual_close: ManualCloseInfo | None = None

    @model_validator(mode="after")
    def _terminal_state(self) -> "SlmSuite":
        strict, solution = config.STRICT_ATTEMPTS, config.SOLUTION_ATTEMPTS
        numbers = [a.attempt for a in self.attempts]
        if numbers != list(range(1, len(numbers) + 1)):
            raise ValueError("attempts are numbered from 1 without gaps")
        for a in self.attempts:
            if a.seed != config.seed_for(a.attempt):
                raise ValueError(f"attempt {a.attempt} must use seed {config.seed_for(a.attempt)}")
            if a.kind.value != config.attempt_kind(a.attempt):
                raise ValueError(f"attempt {a.attempt} is a {config.attempt_kind(a.attempt)}")
            if (a.fallback_eligible or a.low_confidence_eligible) and (
                a.kind is not AttemptKind.SOLUTION
                or a.failure is not AttemptFailure.PUBLIC_TEST_FAILED
            ):
                raise ValueError("only a solution that failed a public test can be a fallback")
            if a.fallback_eligible and a.low_confidence_eligible:
                raise ValueError("an attempt is a possible fallback or low confidence, not both")
        if self.suite_size != len(self.tests):
            raise ValueError("suite_size is the number of tests")
        *earlier, last = self.attempts
        if any(a.failure is None for a in earlier):
            raise ValueError("only the last attempt can have succeeded")
        n = len(self.attempts)
        fallback = [a.attempt for a in self.attempts if a.fallback_eligible]
        low = [a.attempt for a in self.attempts if a.low_confidence_eligible]
        if n > strict and set(fallback) - {last.attempt}:
            raise ValueError(
                f"a possible fallback before attempt {last.attempt} would have ended the attempts"
            )
        if n > solution and (fallback or low):
            raise ValueError("a prediction comes only when no solution could be the suite")
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
            return self
        if not self.tests or self.accepted_attempt is None:
            raise ValueError("a suite is never empty and always has the attempt it comes from")
        if (last.failure is None) != (
            status in (SuiteStatus.ACCEPTED, SuiteStatus.ACCEPTED_PREDICTED)
        ):
            raise ValueError(f"the last attempt of an {status.value} suite has the wrong outcome")
        if status in (SuiteStatus.ACCEPTED, SuiteStatus.ACCEPTED_PREDICTED):
            kind = (
                AttemptKind.SOLUTION if status is SuiteStatus.ACCEPTED else AttemptKind.PREDICTION
            )
            if last.kind is not kind or self.accepted_attempt != last.attempt:
                raise ValueError(f"an {status.value} suite comes from its last attempt")
            if status is SuiteStatus.ACCEPTED_PREDICTED and self.discarded_inputs:
                raise ValueError("nothing of a predicted suite was run, so nothing was discarded")
        elif status is SuiteStatus.ACCEPTED_FALLBACK:
            if self.accepted_attempt not in fallback:
                raise ValueError("a fallback suite comes from an attempt that can be a fallback")
            if not (n == strict or (strict < n <= solution and fallback == [last.attempt])):
                raise ValueError(
                    f"a fallback suite has {strict} attempts, or more and then it comes from the "
                    "last one, the only one that can be a fallback"
                )
        else:  # ACCEPTED_LOW_CONFIDENCE
            if n != solution or fallback:
                raise ValueError(
                    f"a low-confidence suite comes after {solution} attempts without a fallback"
                )
            if not low or self.accepted_attempt != low[0]:
                raise ValueError("a low-confidence suite comes from the first eligible attempt")
        return self
