"""Schema of the extraction report (spec FR-018, FR-018a)."""

from typing import Any, Literal

from pydantic import Field, model_validator

from dataset.schemas.common import Macrocategoria, Schema, SchemaVersion


class ReportFunnel(Schema):
    read: int
    stages: dict[str, int]  # rows that survive each eligibility stage, in order
    rejected_by_reason: dict[str, int]
    discarded_by_reason: dict[str, int] = Field(default_factory=dict)
    included: int  # complete problems in the sample


class CategoryAlert(Schema):
    macrocategoria: Macrocategoria
    count: int
    threshold: int


class PendingTriageItem(Schema):
    problem_id: str
    stage: Literal["selection", "audit"]
    reason: str


class Provenance(Schema):
    hf_dataset: str
    hf_revision: str
    seed: int
    gcc_version: str | None = None


class ExtractionReport(Schema):
    schema_version: SchemaVersion = 1
    funnel: ReportFunnel
    pool_distribution: dict[Macrocategoria, int]
    distribution: dict[Macrocategoria, int]
    selection_final: bool
    category_alerts: list[CategoryAlert]
    pending_triage: list[PendingTriageItem]
    target: int
    deficit: int
    engine_selfcheck: dict[str, Any] | None = None
    # ACs whose `AC_ref` was executed by the engine, and the failures among them by cause (only the
    # selection stage): the numbers of the reopening criterion of decision D13.
    ac_tested: int = 0
    triage_by_cause: dict[str, int] = Field(
        default_factory=lambda: {"format_only": 0, "tle": 0, "other": 0}
    )
    provenance: Provenance

    @model_validator(mode="after")
    def _numbers_are_consistent(self) -> "ExtractionReport":
        if self.deficit != max(0, self.target - self.funnel.included):
            raise ValueError("`deficit` must be max(0, target - included)")
        if self.funnel.included != sum(self.distribution.values()):
            raise ValueError("`included` must equal the sum of `distribution`")
        return self
