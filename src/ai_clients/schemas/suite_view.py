"""The common reader of ``suite.json``, for the evaluation: the same view of the three models.

The SLM writes ``SlmSuite`` and the commercial models ``LlmSuite`` (each checks its own attempt
policy), with the same file contract (``schema_version`` 2 and the same top-level keys). The
evaluation needs only what is common, read here without knowing which model wrote the file:
unknown keys are ignored on purpose, and only the coherence of the common part is checked.
"""

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ai_clients.schemas.common import NonNegative, Scenario, SuiteStatus
from dataset.schemas.common import PROBLEM_ID_PATTERN
from dataset.schemas.testes import TestCase


class SuiteView(BaseModel):
    model_config = ConfigDict(extra="ignore")

    schema_version: Literal[2]
    problem_id: str = Field(pattern=PROBLEM_ID_PATTERN)
    scenario: Scenario
    model: str = Field(min_length=1)
    status: SuiteStatus
    tests: list[TestCase]
    suite_size: NonNegative

    @model_validator(mode="after")
    def _coherent(self) -> "SuiteView":
        if self.suite_size != len(self.tests):
            raise ValueError("suite_size is the number of tests")
        if (self.status is SuiteStatus.DISCARDED_MANUAL) != (not self.tests):
            raise ValueError("only a suite closed by the authors has no tests")
        return self


def read_suite_view(path: Path) -> SuiteView:
    """The common view of any ``suite.json`` (SLM, GPT or Gemini); ``ValueError`` if incoherent."""
    return SuiteView.model_validate_json(Path(path).read_bytes())
