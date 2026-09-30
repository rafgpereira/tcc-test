"""Enumerations and field types shared by the SLM suite schemas (data-model.md, section 2)."""

from enum import Enum
from typing import Annotated

from pydantic import Field

from ai_clients import config

Sha256Hex = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Attempt = Annotated[int, Field(ge=1, le=config.MAX_ATTEMPTS)]
NonNegative = Annotated[int, Field(ge=0)]


class Scenario(str, Enum):
    """The three context scenarios, in canonical processing order."""

    BLACK_BOX = "black_box"  # the statement only
    WHITE_BOX = "white_box"  # AC_ref.cpp only
    HYBRID = "hybrid"  # both


class AttemptFailure(str, Enum):
    """The three reasons that consume one of the 6 attempts; nothing else does."""

    UNPARSEABLE_RESPONSE = "unparseable_response"
    PUBLIC_TEST_FAILED = "public_test_failed"
    ALL_INPUTS_FAILED = "all_inputs_failed"  # runtime error and/or timeout on every input


class InputDiscard(str, Enum):
    """Why one generated input was dropped while the others stayed."""

    TIMEOUT = "timeout"  # verdict TLE
    RUNTIME_ERROR = "runtime_error"  # verdict RE or MLE (kept in `verdict`)
    NON_UTF8_OUTPUT = "non_utf8_output"


class SuiteStatus(str, Enum):
    ACCEPTED = "accepted"
    DISCARDED = "discarded"


assert tuple(s.value for s in Scenario) == config.SCENARIOS
