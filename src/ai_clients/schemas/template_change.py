"""``template_changes/<NNN>.json``: a template changed in the middle of a run (research R27).

Written once by ``python -m ai_clients change-template``, never changed. The run keeps ONE version of
each template: the attempts made with the old one (from the first of them in each combination, with
``suite.json`` and ``manual_close.json``) are moved to ``superseded/<NNN>/`` and made again with the
new one and the same seeds. ``run.json`` is never rewritten: the current template of a run is the
one of ``run.json`` with these changes applied in order.
"""

from pydantic import Field, field_validator, model_validator

from ai_clients.schemas.common import AttemptKind, Scenario, SchemaVersion, Sha256Hex
from dataset.schemas.common import PROBLEM_ID_PATTERN, Schema


class SupersededCombination(Schema):
    """The files one change moved out of ``problems/<problem_id>/<scenario>/``."""

    problem_id: str = Field(pattern=PROBLEM_ID_PATTERN)
    scenario: Scenario
    files: list[str] = Field(min_length=1)  # in the order they are moved


class TemplateChange(Schema):
    schema_version: SchemaVersion = 2
    number: int = Field(ge=1)  # the file is template_changes/<number, 3 digits>.json
    template: AttemptKind
    from_sha256: Sha256Hex  # the current template of the run before the change
    to_sha256: Sha256Hex
    changed_at: str
    reason: str
    superseded: list[SupersededCombination]

    @field_validator("reason")
    @classmethod
    def _not_blank(cls, text: str) -> str:
        if not text.strip():
            raise ValueError("the reason is required")
        return text

    @model_validator(mode="after")
    def _a_change(self) -> "TemplateChange":
        if self.from_sha256 == self.to_sha256:
            raise ValueError("a change goes to another template")
        keys = [(c.problem_id, c.scenario.value) for c in self.superseded]
        if len(keys) != len(set(keys)):
            raise ValueError("a combination is listed twice")
        return self
