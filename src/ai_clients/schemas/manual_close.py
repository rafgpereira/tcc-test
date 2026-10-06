"""``manual_close.json``: the authors closing a problem × scenario that awaits manual handling.

Written once by ``python -m ai_clients close``, never changed. It is the only way a combination
ends without a suite (``discarded_manual``); ``suite.json`` copies ``reason`` and ``closed_at``.
"""

from pydantic import Field, field_validator

from ai_clients.schemas.common import Scenario, SchemaVersion
from dataset.schemas.common import PROBLEM_ID_PATTERN, Schema


class ManualClose(Schema):
    schema_version: SchemaVersion = 2
    problem_id: str = Field(pattern=PROBLEM_ID_PATTERN)
    scenario: Scenario
    reason: str
    closed_at: str

    @field_validator("reason")
    @classmethod
    def _not_blank(cls, text: str) -> str:
        if not text.strip():
            raise ValueError("the reason is required")
        return text
