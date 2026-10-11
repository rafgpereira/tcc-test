"""``manifests/slm_generation_report.json``: the numbers of the SLM suite generation.

Rebuilt from the files of ``data/suites/slm/`` at any time, even in the middle of a run (pending
combinations are counted). Every count is present even when it is zero, and there is no timestamp:
the same tree always gives the same bytes. The control sums are validated here: the states of the
combinations add up to the number of combinations of the scope (never a reduced N), the phase and
attempt of acceptance add up to the combinations with a suite, the calls per phase add up to the
calls, and the funnel of failed attempts adds up to the number of failed attempts. Everything about
the suites is split by status, so suites whose expected outputs were not checked are never mixed
in silently.
"""

from pydantic import Field, model_validator

from ai_clients import config
from ai_clients.schemas.common import (
    AttemptFailure,
    AttemptKind,
    InputDiscard,
    NonNegative,
    SchemaVersion,
    Sha256Hex,
    SuiteStatus,
)
from ai_clients.schemas.run import AttemptRow, SamplingOptions
from dataset.schemas.common import Schema

TOTAL = "total"
GROUPS = (TOTAL, *config.SCENARIOS)  # every per-scenario table also has the total
STATUSES = tuple(status.value for status in SuiteStatus)
WITH_TESTS = tuple(s for s in STATUSES if s != SuiteStatus.DISCARDED_MANUAL.value)
STATES = (*STATUSES, "awaiting_manual", "pending_generation", "pending_execution")
SUITE_PHASES = ("1", "2", "3", "4")  # 3: the fallback, chosen without a call
CALL_PHASES = tuple(str(p) for p in sorted({spec.phase for spec in config.ATTEMPT_POLICY}))
ATTEMPT_NUMBERS = tuple(str(n) for n in range(1, config.MAX_ATTEMPTS + 1))


class CombinationCounts(Schema):
    total: NonNegative
    accepted: NonNegative
    accepted_fallback: NonNegative  # solution failed a public test by WA (config.py)
    accepted_predicted: NonNegative  # outputs written by the model
    discarded_manual: NonNegative  # closed by the authors
    awaiting_manual: NonNegative
    pending_generation: NonNegative
    pending_execution: NonNegative

    @model_validator(mode="after")
    def _add_up(self) -> "CombinationCounts":
        if sum(getattr(self, state) for state in STATES) != self.total:
            raise ValueError(f"{' + '.join(STATES)} must add up to total")
        return self


class Acceptance(Schema):
    """Where the combinations with a suite got it: the phase and the attempt of their suite."""

    by_phase: dict[str, NonNegative]  # "1".."4" -> combinations (3: the fallback)
    by_attempt: dict[str, NonNegative]  # "1".."15" -> combinations whose suite comes from it

    @model_validator(mode="after")
    def _complete(self) -> "Acceptance":
        if set(self.by_phase) != set(SUITE_PHASES) or set(self.by_attempt) != set(ATTEMPT_NUMBERS):
            raise ValueError("acceptance has every phase and every attempt number")
        if sum(self.by_phase.values()) != sum(self.by_attempt.values()):
            raise ValueError("acceptance by phase and by attempt count the same combinations")
        return self


class PhaseCounts(Schema):
    """The calls of one phase: how many, how many failed, their tokens and model time."""

    calls: NonNegative
    failed: NonNegative
    prompt_tokens: NonNegative
    eval_tokens: NonNegative
    duration_s: float = Field(ge=0)


class SizeStats(Schema):
    """Sizes of the suites of one status; linear quartiles; ``None`` without any."""

    count: NonNegative
    min: int | None
    p25: float | None
    median: float | None
    p75: float | None
    max: int | None
    histogram: dict[str, NonNegative]  # suite size (as text, for JSON) -> number of suites


class AttemptCounts(Schema):
    total: NonNegative  # calls answered (one generation record each)
    failed: NonNegative  # attempts that failed (the 4 reasons), the chosen fallback ones included


class TokenCounts(Schema):
    prompt_total: NonNegative
    eval_total: NonNegative
    prompt_max: NonNegative  # the largest prompt_eval_count (checked against num_ctx)


class TemplateChangeSummary(Schema):
    """One template change of the run (research R27); its moved attempts are not in any count."""

    number: int = Field(ge=1)
    template: AttemptKind
    from_sha256: Sha256Hex
    to_sha256: Sha256Hex
    changed_at: str
    reason: str
    combinations: NonNegative  # made again with the new template
    files: NonNegative  # moved to superseded/<NNN>/


class SlmGenerationReport(Schema):
    schema_version: SchemaVersion = 2
    model: str
    model_digest: str
    ollama_version: str
    options: SamplingOptions
    attempt_policy: list[AttemptRow]
    prompt_template_sha256: Sha256Hex  # the current templates: run.json with its changes
    predict_template_sha256: Sha256Hex
    template_changes: list[TemplateChangeSummary]  # in order; empty if none (R27)
    dataset_manifest_sha256: Sha256Hex
    combinations: dict[str, CombinationCounts]
    status_rate: dict[str, dict[str, float]]  # status -> group -> share of the scope
    acceptance: dict[str, Acceptance]  # group -> phase and attempt of the suites
    suite_size: dict[str, dict[str, SizeStats]]  # status (with tests) -> group -> sizes
    attempts: AttemptCounts
    per_phase: dict[str, PhaseCounts]  # phase with calls ("1", "2", "4") -> its calls
    attempt_failures: dict[AttemptFailure, dict[str, NonNegative]]  # reason -> attempt -> count
    input_discards: dict[InputDiscard, NonNegative]  # over every executed attempt
    duplicate_inputs: NonNegative  # repeated inputs kept in the suites
    done_reason_length: dict[str, NonNegative]  # answers cut by num_predict, per scenario
    markdown_fences_removed: dict[str, NonNegative]  # fences removed (solutions and predictions)
    empty_inputs: dict[str, NonNegative]  # empty <input> blocks dropped by the parser
    empty_tests: dict[str, NonNegative]  # predicted tests with an empty input or output, dropped
    abbreviated_tests: dict[str, NonNegative]  # predicted tests eliding values, dropped (R27)
    tokens: TokenCounts
    duration_s_total: float = Field(ge=0)
    hardware: dict[str, NonNegative]  # hardware label -> calls
    seeds: dict[str, list[int]]  # "<id>/<scenario>" -> seeds used, in order

    @model_validator(mode="after")
    def _control_sums(self) -> "SlmGenerationReport":
        per_group = (
            self.combinations,
            self.acceptance,
            self.done_reason_length,
            self.markdown_fences_removed,
            self.empty_inputs,
            self.empty_tests,
            self.abbreviated_tests,
            *self.status_rate.values(),
            *self.suite_size.values(),
        )
        for table in per_group:
            if set(table) != set(GROUPS):
                raise ValueError(f"every table has the keys {', '.join(GROUPS)}")
        if set(self.status_rate) != set(STATUSES) or set(self.suite_size) != set(WITH_TESTS):
            raise ValueError("status_rate has every status and suite_size every status with tests")
        counted = (
            self.done_reason_length,
            self.markdown_fences_removed,
            self.empty_inputs,
            self.empty_tests,
            self.abbreviated_tests,
        )
        for table in counted:
            if sum(table[s] for s in config.SCENARIOS) != table[TOTAL]:
                raise ValueError("the scenarios do not add up to the total")
        for field in ("total", *STATES):
            parts = sum(getattr(self.combinations[s], field) for s in config.SCENARIOS)
            if parts != getattr(self.combinations[TOTAL], field):
                raise ValueError(f"the scenarios do not add up to the total in {field!r}")
        for group in GROUPS:
            with_suite = sum(getattr(self.combinations[group], status) for status in WITH_TESTS)
            if sum(self.acceptance[group].by_phase.values()) != with_suite:
                raise ValueError("acceptance must add up to the combinations with a suite")
        for number in ATTEMPT_NUMBERS:
            parts = sum(self.acceptance[s].by_attempt[number] for s in config.SCENARIOS)
            if parts != self.acceptance[TOTAL].by_attempt[number]:
                raise ValueError("the scenarios do not add up to the total in acceptance")
        if set(self.per_phase) != set(CALL_PHASES):
            raise ValueError(f"per_phase has the phases {', '.join(CALL_PHASES)}")
        if sum(p.calls for p in self.per_phase.values()) != self.attempts.total:
            raise ValueError("the calls per phase must add up to the attempts")
        if sum(p.failed for p in self.per_phase.values()) != self.attempts.failed:
            raise ValueError("the failed calls per phase must add up to the failed attempts")
        if set(self.attempt_failures) != set(AttemptFailure) or any(
            set(by_attempt) != set(ATTEMPT_NUMBERS) for by_attempt in self.attempt_failures.values()
        ):
            raise ValueError("attempt_failures has every reason and every attempt number")
        funnel = sum(sum(by_attempt.values()) for by_attempt in self.attempt_failures.values())
        if funnel != self.attempts.failed:
            raise ValueError("attempt_failures must add up to the failed attempts")
        if set(self.input_discards) != set(InputDiscard):
            raise ValueError("input_discards has every reason")
        if sum(self.hardware.values()) != self.attempts.total:
            raise ValueError("the calls per hardware label must add up to the attempts")
        return self
