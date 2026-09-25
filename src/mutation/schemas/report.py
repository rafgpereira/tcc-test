"""Schema of ``manifests/mutation_report.json`` (spec FR-013; contracts/file-formats.md).

Every count is present even when it is zero (a missing key would be ambiguous with "not measured"),
and ``exclusion_alerts`` is always there, an empty list in the expected case. There is no timestamp:
the same ``data/mutants/`` always gives the same bytes.
"""

from pydantic import Field, field_validator, model_validator

from dataset.schemas.common import PROBLEM_ID_PATTERN, Schema, SchemaVersion
from mutation import config
from mutation.types import DiscardReason, MutationOperator

SHA256_PATTERN = r"^[0-9a-f]{64}$"


class ExclusionAlertEntry(Schema):
    problem_id: str = Field(pattern=PROBLEM_ID_PATTERN)
    mutants_reached: int = Field(ge=0, lt=config.MUTANTS_PER_PROBLEM)
    highest_order_attempted: int = Field(ge=1, le=config.HOM_MAX_ORDER)


class ProblemCounts(Schema):
    """How the problems closed (only problems already generated are counted)."""

    closed: int = Field(ge=0)
    complete: int = Field(ge=0)  # 100 mutants
    first_order_only: int = Field(ge=0)  # complete, every mutant of first order
    higher_order: int = Field(ge=0)  # complete, at least one pair or triple
    excluded: int = Field(ge=0)  # ended in an alert

    @model_validator(mode="after")
    def _counts_add_up(self) -> "ProblemCounts":
        if self.complete + self.excluded != self.closed:
            raise ValueError("complete + excluded must equal closed")
        if self.first_order_only + self.higher_order != self.complete:
            raise ValueError("first_order_only + higher_order must equal complete")
        return self


class MutationReport(Schema):
    schema_version: SchemaVersion = 1
    problems: ProblemCounts
    funnel: dict[DiscardReason, int]
    order_distribution: dict[int, int]
    operator_distribution: dict[MutationOperator, int]
    exclusion_alerts: list[ExclusionAlertEntry]  # never omitted, [] when there is none
    dataset_manifest_sha256: str = Field(pattern=SHA256_PATTERN)

    @field_validator("funnel")
    @classmethod
    def _funnel_has_every_reason(cls, value):
        return _require_keys(value, set(DiscardReason), "funnel")

    @field_validator("order_distribution")
    @classmethod
    def _orders_are_one_to_three(cls, value):
        return _require_keys(value, set(range(1, config.HOM_MAX_ORDER + 1)), "order_distribution")

    @field_validator("operator_distribution")
    @classmethod
    def _operators_are_all_five(cls, value):
        return _require_keys(value, set(MutationOperator), "operator_distribution")

    @field_validator("funnel", "order_distribution", "operator_distribution")
    @classmethod
    def _counts_are_not_negative(cls, value):
        if any(count < 0 for count in value.values()):
            raise ValueError("counts cannot be negative")
        return value

    @model_validator(mode="after")
    def _alerts_match_the_excluded_problems(self) -> "MutationReport":
        if len(self.exclusion_alerts) != self.problems.excluded:
            raise ValueError("one exclusion alert per excluded problem")
        ids = [a.problem_id for a in self.exclusion_alerts]
        if ids != sorted(ids):
            raise ValueError("exclusion_alerts must be ordered by problem_id")
        return self


def _require_keys(value: dict, expected: set, name: str) -> dict:
    if set(value) != expected:
        raise ValueError(f"{name} must have exactly the keys {sorted(map(str, expected))}")
    return value
