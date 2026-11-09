"""``data/evaluation/<set>/run.json``: what an evaluation set was run on (research R8).

Every resumption compares these fields (except ``created_at``) with the current inputs, so results
evaluated on different datasets, mutants, suites or compilers are never mixed in one set.
"""

from typing import Literal

from pydantic import Field, model_validator

from dataset.schemas.common import Schema, SchemaVersion
from evaluation.schemas.result import Model, SetName

_SHA = r"^[0-9a-f]{64}$"


class RunConfig(Schema):
    schema_version: SchemaVersion = 1
    set: SetName
    model: Model
    attempt: int | None = Field(ge=1)
    dataset_manifest_sha256: str = Field(pattern=_SHA)
    dataset_revision: int = Field(ge=1)
    mutants_manifest_sha256: str = Field(pattern=_SHA)
    suites_manifest_sha256: str = Field(pattern=_SHA)
    gcc_version: str = Field(min_length=1)
    error_runs: Literal[3] = 3
    created_at: str = Field(min_length=1)

    @model_validator(mode="after")
    def _attempt_only_for_the_attempt_set(self) -> "RunConfig":
        if (self.set == "slm-attempt1") != (self.attempt == 1):
            raise ValueError("attempt is 1 for slm-attempt1 and null for the other sets")
        if self.set == "slm-attempt1" and self.model != "slm":
            raise ValueError("slm-attempt1 evaluates the local model")
        if self.set in ("slm", "gpt", "gemini", "claude") and self.model != self.set:
            raise ValueError("a final set evaluates the model of the same name")
        return self

    def differences(self, other: "RunConfig") -> list[str]:
        """The fields (other than ``created_at``) whose values differ."""
        mine = self.model_dump(exclude={"created_at"})
        theirs = other.model_dump(exclude={"created_at"})
        return sorted(key for key in mine if mine[key] != theirs[key])
