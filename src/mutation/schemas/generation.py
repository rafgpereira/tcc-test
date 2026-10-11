"""Record of how the mutants of ONE problem were reached (``generation.json``).

It lives next to the mutants in ``data/mutants/problems/<id>/`` and is never packaged: it is the
memory that lets ``report`` recompute the funnel, the order and the operator distributions of the
whole run later, without re-running anything (contracts/file-formats.md).
"""

from typing import Literal

from pydantic import Field, model_validator

from dataset.schemas.common import PROBLEM_ID_PATTERN, Schema, SchemaVersion
from mutation import config
from mutation.types import DiscardReason, MutationOperator


class OperatorUse(Schema):
    operator: MutationOperator
    variant: int = Field(ge=0)


class MutantRecord(Schema):
    file: str  # Mutant_<n>.cpp
    order: int = Field(ge=1, le=config.HOM_MAX_ORDER)
    operators: list[OperatorUse]  # one per site changed, so `order` of them
    sha256: str

    @model_validator(mode="after")
    def _one_operator_use_per_order(self) -> "MutantRecord":
        if len(self.operators) != self.order:
            raise ValueError("a mutant of order N has exactly N operator uses")
        return self


class DiscardCount(Schema):
    order: int = Field(ge=1, le=config.HOM_MAX_ORDER)
    reason: DiscardReason
    count: int = Field(ge=1)


class Exclusion(Schema):
    mutants_reached: int = Field(ge=0, lt=config.MUTANTS_PER_PROBLEM)
    highest_order_attempted: int = Field(ge=1, le=config.HOM_MAX_ORDER)


class Generation(Schema):
    schema_version: SchemaVersion = 1
    problem_id: str = Field(pattern=PROBLEM_ID_PATTERN)
    status: Literal["complete", "excluded"]
    mutants: list[MutantRecord]
    discards: list[DiscardCount]  # sorted by (order, reason), one row per pair
    exclusion: Exclusion | None = None

    @model_validator(mode="after")
    def _status_decides_what_is_present(self) -> "Generation":
        if self.status == "complete":
            if len(self.mutants) != config.MUTANTS_PER_PROBLEM or self.exclusion is not None:
                raise ValueError(
                    f"a complete problem has exactly {config.MUTANTS_PER_PROBLEM} mutants and "
                    "no exclusion"
                )
        elif self.mutants or self.exclusion is None:
            raise ValueError("an excluded problem has no mutants and states its exclusion")
        return self

    @model_validator(mode="after")
    def _mutant_files_are_numbered_in_order(self) -> "Generation":
        expected = [config.mutant_file_name(i) for i in range(1, len(self.mutants) + 1)]
        if [m.file for m in self.mutants] != expected:
            raise ValueError("mutant files must be Mutant_1.cpp, Mutant_2.cpp, ... in order")
        return self
