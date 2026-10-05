"""``manifests/slm_generation_report.json``: the numbers of the SLM suite generation.

Rebuilt from the files of ``data/suites/slm/`` at any time, even in the middle of a run (pending
combinations are counted). Every count is present even when it is zero, and there is no timestamp:
the same tree always gives the same bytes. The control sums are validated here: the states of the
combinations add up to the number of combinations of the scope (never a reduced N), and the funnel
of failed attempts adds up to the number of failed attempts.
"""

from pydantic import Field, model_validator

from ai_clients import config
from ai_clients.schemas.common import AttemptFailure, InputDiscard, NonNegative, Sha256Hex
from ai_clients.schemas.run import SamplingOptions
from dataset.schemas.common import Schema, SchemaVersion

TOTAL = "total"
GROUPS = (TOTAL, *config.SCENARIOS)  # every per-scenario table also has the total


class CombinationCounts(Schema):
    total: NonNegative
    accepted: NonNegative
    discarded: NonNegative
    pending_generation: NonNegative
    pending_execution: NonNegative

    @model_validator(mode="after")
    def _add_up(self) -> "CombinationCounts":
        states = self.accepted + self.discarded + self.pending_generation + self.pending_execution
        if states != self.total:
            raise ValueError(
                "accepted + discarded + pending_generation + pending_execution must add up to total"
            )
        return self


class SizeStats(Schema):
    """Sizes of the accepted suites; quartiles by linear interpolation; ``None`` without any."""

    count: NonNegative
    min: int | None
    p25: float | None
    median: float | None
    p75: float | None
    max: int | None
    histogram: dict[str, NonNegative]  # suite size (as text, for JSON) -> number of suites


class AttemptCounts(Schema):
    total: NonNegative  # calls answered (one generation record each)
    failed: NonNegative  # attempts that consumed one of the 6 (the 4 reasons)


class TokenCounts(Schema):
    prompt_total: NonNegative
    eval_total: NonNegative
    prompt_max: NonNegative  # the largest prompt_eval_count (checked against num_ctx)


class SlmGenerationReport(Schema):
    schema_version: SchemaVersion = 1
    model: str
    model_digest: str
    ollama_version: str
    options: SamplingOptions
    seed_base: int
    prompt_template_sha256: Sha256Hex
    dataset_manifest_sha256: Sha256Hex
    combinations: dict[str, CombinationCounts]
    discard_rate: dict[str, float]  # discarded / total of the scope
    suite_size: dict[str, SizeStats]
    attempts: AttemptCounts
    attempt_failures: dict[AttemptFailure, dict[str, NonNegative]]  # reason -> attempt -> count
    input_discards: dict[InputDiscard, NonNegative]  # over every executed attempt
    duplicate_inputs: NonNegative  # repeated inputs kept in the accepted suites
    done_reason_length: dict[str, NonNegative]  # answers cut by num_predict, per scenario
    markdown_fences_removed: dict[str, NonNegative]  # answers whose code fence was removed
    empty_inputs: dict[str, NonNegative]  # empty <input> blocks dropped by the parser
    tokens: TokenCounts
    duration_s_total: float = Field(ge=0)
    hardware: dict[str, NonNegative]  # hardware label -> calls
    seeds: dict[str, list[int]]  # "<id>/<scenario>" -> seeds used, in order

    @model_validator(mode="after")
    def _control_sums(self) -> "SlmGenerationReport":
        per_group = (
            self.combinations,
            self.discard_rate,
            self.suite_size,
            self.done_reason_length,
            self.markdown_fences_removed,
            self.empty_inputs,
        )
        for table in per_group:
            if set(table) != set(GROUPS):
                raise ValueError(f"every table has the keys {', '.join(GROUPS)}")
        for table in (self.done_reason_length, self.markdown_fences_removed, self.empty_inputs):
            if sum(table[s] for s in config.SCENARIOS) != table[TOTAL]:
                raise ValueError("the scenarios do not add up to the total")
        for field in ("total", "accepted", "discarded", "pending_generation", "pending_execution"):
            parts = sum(getattr(self.combinations[s], field) for s in config.SCENARIOS)
            if parts != getattr(self.combinations[TOTAL], field):
                raise ValueError(f"the scenarios do not add up to the total in {field!r}")
        numbers = {str(n) for n in range(1, config.MAX_ATTEMPTS + 1)}
        if set(self.attempt_failures) != set(AttemptFailure) or any(
            set(by_attempt) != numbers for by_attempt in self.attempt_failures.values()
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
