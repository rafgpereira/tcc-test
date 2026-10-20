"""``data/suites/slm/provenance.json``: where each combination of a merged package comes from.

Revision 2 of the dataset (specs/007, F2) redoes only the combinations whose statement changed;
the others keep the suites of the run of revision 1. The package has both trees side by side, and
this file says, for every problem × scenario, which tree holds its suite in force, and which
dataset revision that run used. An entry of the old tree that was redone has ``superseded_in``.
"""

from typing import Literal

from pydantic import Field, model_validator

from dataset.schemas.common import PROBLEM_ID_PATTERN, Schema


class CombinationOrigin(Schema):
    problem_id: str = Field(pattern=PROBLEM_ID_PATTERN)
    scenario: Literal["black_box", "white_box", "hybrid"]
    tree: str  # inside the package and under data/: "suites/slm" or "suites/slm-rev1"
    dataset_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    dataset_revision: int = Field(ge=1)
    superseded_in: str | None = None  # the tree that redid it (only in the old tree's entries)


class SlmProvenance(Schema):
    schema_version: Literal[1] = 1
    combinations: list[CombinationOrigin]

    @model_validator(mode="after")
    def _once_in_force(self) -> "SlmProvenance":
        seen: set[tuple[str, str]] = set()
        for c in self.combinations:
            if c.superseded_in is not None:
                continue
            key = (c.problem_id, c.scenario)
            if key in seen:
                raise ValueError(f"{key[0]} {key[1]} is in force more than once")
            seen.add(key)
        return self

    def in_force(self) -> dict[tuple[str, str], CombinationOrigin]:
        return {(c.problem_id, c.scenario): c for c in self.combinations if c.superseded_in is None}
