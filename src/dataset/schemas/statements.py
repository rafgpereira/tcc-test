"""The files of check-statements and correct-statements (specs/006, data-model.md)."""

from typing import Literal

from pydantic import Field, model_validator

from dataset.schemas.common import PROBLEM_ID_PATTERN, Schema, SchemaVersion

Sha256 = str
DifferenceKind = Literal["lost_exponent", "lost_index", "formula", "image", "table", "other"]
KINDS: tuple[str, ...] = ("lost_exponent", "lost_index", "formula", "image", "table", "other")


class OriginalEntry(Schema):
    problem_id: str = Field(pattern=PROBLEM_ID_PATTERN)
    url: str
    fetched_at: str
    http_status: int | None
    page_bytes: int | None = Field(default=None, ge=0)
    page_sha256: Sha256 | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    statement_sha256: Sha256 | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    error: str | None = None  # http_404, no_statement_block, ...: a definitive failure

    @model_validator(mode="after")
    def _coherent(self) -> "OriginalEntry":
        ok = self.error is None
        if ok != (self.http_status == 200 and self.page_sha256 is not None):
            raise ValueError("error is null exactly when http_status is 200 and page_sha256 is set")
        if ok and self.statement_sha256 is None:
            raise ValueError("a page without error has its statement block")
        return self


class OriginalsManifest(Schema):
    schema_version: SchemaVersion = 1
    dataset_manifest_sha256: Sha256 = Field(pattern=r"^[0-9a-f]{64}$")
    user_agent: str
    min_interval_s: float = Field(ge=3)
    originals: list[OriginalEntry]

    @model_validator(mode="after")
    def _unique(self) -> "OriginalsManifest":
        ids = [e.problem_id for e in self.originals]
        if len(ids) != len(set(ids)):
            raise ValueError("problem_id must be unique")
        if ids != sorted(ids):
            raise ValueError("originals must be sorted by problem_id")
        return self

    def entry(self, problem_id: str) -> OriginalEntry | None:
        return next((e for e in self.originals if e.problem_id == problem_id), None)


class Difference(Schema):
    kind: DifferenceKind
    original: str  # the original, marked (e.g. "10^{5}")
    ours: str  # our text (e.g. "105")
    context: str  # up to 30 characters around, from our text
    ours_offset: int = Field(ge=0)  # where the difference starts in enunciado.md
    ours_length: int = Field(ge=0)  # how many characters of enunciado.md it covers


class ProblemFidelity(Schema):
    problem_id: str = Field(pattern=PROBLEM_ID_PATTERN)
    format: Literal["marked", "latex", "mixed"] | None  # None when unchecked
    status: Literal["faithful", "losses", "unchecked"]
    unchecked_reason: str | None = None
    differences: list[Difference] = Field(default_factory=list)

    @model_validator(mode="after")
    def _coherent(self) -> "ProblemFidelity":
        if (self.unchecked_reason is not None) != (self.status == "unchecked"):
            raise ValueError('unchecked_reason is set exactly when status is "unchecked"')
        if self.status != "unchecked" and (not self.differences) != (self.status == "faithful"):
            raise ValueError('differences is empty exactly when status is "faithful"')
        return self


class FidelityTotals(Schema):
    problems: int = Field(ge=0)
    faithful: int = Field(ge=0)
    with_losses: int = Field(ge=0)
    unchecked: int = Field(ge=0)
    by_kind: dict[DifferenceKind, int]
    problems_by_kind: dict[DifferenceKind, int]

    @model_validator(mode="after")
    def _sum(self) -> "FidelityTotals":
        if self.faithful + self.with_losses + self.unchecked != self.problems:
            raise ValueError("faithful + with_losses + unchecked must be problems")
        return self


class FidelityReport(Schema):
    schema_version: SchemaVersion = 1
    dataset_manifest_sha256: Sha256 = Field(pattern=r"^[0-9a-f]{64}$")
    originals_manifest_sha256: Sha256 = Field(pattern=r"^[0-9a-f]{64}$")
    equivalences: dict[str, str]
    problems: list[ProblemFidelity]
    totals: FidelityTotals

    @model_validator(mode="after")
    def _totals(self) -> "FidelityReport":
        if self.totals.problems != len(self.problems):
            raise ValueError("totals.problems must be the number of problems")
        return self


class CorrectionChecks(Schema):
    text_equal: bool
    all_marks_present: bool
    only_markup_diff: bool

    @property
    def passed(self) -> bool:
        return self.text_equal and self.all_marks_present and self.only_markup_diff


class CorrectedStatement(Schema):
    problem_id: str = Field(pattern=PROBLEM_ID_PATTERN)
    file: str
    markups_inserted: dict[DifferenceKind, int]
    checks: CorrectionChecks
    sha256_before: Sha256 = Field(pattern=r"^[0-9a-f]{64}$")
    sha256_after: Sha256 = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def _passed(self) -> "CorrectedStatement":
        if not self.checks.passed:
            raise ValueError("a corrected statement must pass the three checks")
        return self


class ReviewEntry(Schema):
    problem_id: str = Field(pattern=PROBLEM_ID_PATTERN)
    reasons: list[str] = Field(min_length=1)


class CorrectionSummary(Schema):
    schema_version: SchemaVersion = 1
    report_sha256: Sha256 = Field(pattern=r"^[0-9a-f]{64}$")
    corrected: list[CorrectedStatement]
    unchanged: list[str]
    review: list[ReviewEntry]

    @model_validator(mode="after")
    def _each_once(self) -> "CorrectionSummary":
        ids = (
            [c.problem_id for c in self.corrected]
            + list(self.unchanged)
            + [r.problem_id for r in self.review]
        )
        if len(ids) != len(set(ids)):
            raise ValueError("each problem_id is in exactly one of corrected, unchanged, review")
        return self
