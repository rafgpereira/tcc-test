"""Building blocks shared by the dataset schemas (Constitution, Principle IV)."""

from enum import Enum
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
