"""The files of ``python -m dataset revise`` (specs/007, data-model.md §1 and §3)."""

from typing import Literal

from pydantic import Field, model_validator

from dataset.schemas.common import PROBLEM_ID_PATTERN, Schema

_SHA = r"^[0-9a-f]{64}$"


class SuggestedDifference(Schema):
    kind: str
    original: str
    ours: str
    context: str


class StatementDecision(Schema):
    """``manifests/statement_decisions/<id>.json``: the authors' decision on one statement under
    review (F1). A draft (``decision`` null) is written by ``revise --draft-decisions``."""

    schema_version: Literal[1] = 1
    problem_id: str = Field(pattern=PROBLEM_ID_PATTERN)
    decision: Literal["correct", "keep"] | None
    enunciado: str | None
    reason: str
    reviewed_by: str
    reviewed_at: str
    sha256_before: str = Field(pattern=_SHA)
    # Help for the authors, ignored by revise: the differences found and the text with the lost
    # exponents and indices already marked.
    differences: list[SuggestedDifference] = Field(default_factory=list)
    suggested_enunciado: str | None = None

    @property
    def is_draft(self) -> bool:
        return self.decision is None

    @model_validator(mode="after")
    def _complete(self) -> "StatementDecision":
        if self.decision is None:
            return self
        if (self.enunciado is not None) != (self.decision == "correct"):
            raise ValueError('enunciado is set exactly when decision is "correct"')
        for name in ("reason", "reviewed_by", "reviewed_at"):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} must not be empty")
        return self


class ChangedStatement(Schema):
    problem_id: str = Field(pattern=PROBLEM_ID_PATTERN)
    origin: Literal["automatic", "manual"]
    markups: dict[str, int] = Field(default_factory=dict)  # automatic only
    reason: str | None = None  # manual only
    sha256_before: str = Field(pattern=_SHA)
    sha256_after: str = Field(pattern=_SHA)

    @model_validator(mode="after")
    def _origin(self) -> "ChangedStatement":
        if (self.reason is not None) != (self.origin == "manual"):
            raise ValueError('reason is set exactly when origin is "manual"')
        return self


class KeptStatement(Schema):
    problem_id: str = Field(pattern=PROBLEM_ID_PATTERN)
    reason: str


class DatasetRevision(Schema):
    """``manifests/dataset_revision.json``: what revision 2 changed and why."""

    schema_version: Literal[1] = 1
    revision: int = Field(ge=2)
    previous_manifest_sha256: str = Field(pattern=_SHA)
    changed: list[ChangedStatement]
    kept: list[KeptStatement]

    @model_validator(mode="after")
    def _disjoint(self) -> "DatasetRevision":
        changed = [c.problem_id for c in self.changed]
        kept = [k.problem_id for k in self.kept]
        if changed != sorted(changed) or kept != sorted(kept):
            raise ValueError("changed and kept are sorted by problem_id")
        if set(changed) & set(kept) or len(set(changed)) != len(changed):
            raise ValueError("the problem_id of changed and kept are disjoint and unique")
        return self
