"""Building blocks shared by the dataset schemas (Constitution, Principle IV)."""

import json
from enum import Enum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

# Every JSON contract carries `schema_version`; changing a schema means incrementing it on purpose.
SchemaVersion = Literal[1]

Split = Literal["train", "valid", "test"]


class Schema(BaseModel):
    """Base of every schema: unknown fields are errors, so a typo never becomes silent data."""

    model_config = ConfigDict(extra="forbid")


class Macrocategoria(str, Enum):
    """The three mutually exclusive algorithmic macro-categories (methodology, section 1.3)."""

    MATEMATICA = "matematica"
    ESTRUTURAL_OTIMIZACAO = "estrutural_otimizacao"
    LOGICA_DIRETA = "logica_direta"


PROBLEM_ID_PATTERN = r"^\d+_[A-Za-z0-9]+$"


def read_in_folder(model: type, folder: Path, filename: str):
    """Load ``folder/filename`` into ``model`` and check that ``problem_id`` equals the folder name."""
    folder = Path(folder)
    loaded = model.model_validate(json.loads((folder / filename).read_text(encoding="utf-8")))
    if loaded.problem_id != folder.name:
        raise ValueError(
            f"{filename}: problem_id {loaded.problem_id!r} differs from the folder name "
            f"{folder.name!r}"
        )
    return loaded
