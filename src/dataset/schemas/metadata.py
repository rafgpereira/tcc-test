"""`metadata.json` of a problem (data-model.md section 1.1; methodology 1.5).

The keys defined by the methodology keep their Portuguese names (`macrocategoria`,
`dataset_split_origem`, `num_wa_validados`, `num_wa_brutos_disponiveis`).
"""

from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator

from dataset import config
from dataset.filtering.classification import classify
from dataset.schemas.common import (
    PROBLEM_ID_PATTERN,
    Macrocategoria,
    Schema,
    SchemaVersion,
    Split,
    read_in_folder,
)

TIMESTAMP_PATTERN = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$"


class Metadata(Schema):
    schema_version: SchemaVersion = 1
    problem_id: str = Field(pattern=PROBLEM_ID_PATTERN)
    cf_contest_id: int = Field(gt=0)
    cf_index: str = Field(min_length=1)
    name: str = Field(min_length=1)
    source: Literal["CODEFORCES"]
    cf_rating: int = Field(ge=config.RATING_MIN, le=config.RATING_MAX)
    cf_points: float = Field(ge=0)
    cf_tags: list[str]
    macrocategoria: Macrocategoria
    time_limit_seconds: float = Field(gt=0)
    memory_limit_bytes: int = Field(gt=0)
    is_description_translated: Literal[False]
    dataset_split_origem: Split
    num_wa_brutos_disponiveis: int = Field(ge=config.WA_PER_PROBLEM)  # counted before deduplication
    num_wa_validados: Literal[100]
    extraction_timestamp: str = Field(pattern=TIMESTAMP_PATTERN)  # written once, then preserved

    @field_validator("cf_tags")
    @classmethod
    def _sorted_for_determinism(cls, tags: list[str]) -> list[str]:
        return sorted(tags)

    @model_validator(mode="after")
    def _category_is_the_classification_of_the_tags(self) -> "Metadata":
        if classify(self.cf_tags) is not self.macrocategoria:
            raise ValueError(
                f"macrocategoria {self.macrocategoria.value!r} differs from the classification "
                f"of the tags {self.cf_tags}"
            )
        return self

    @classmethod
    def from_folder(cls, folder: Path) -> "Metadata":
        return read_in_folder(cls, folder, "metadata.json")
