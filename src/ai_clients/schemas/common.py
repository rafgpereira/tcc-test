"""Enumerations and field types shared by the SLM suite schemas (data-model.md, section 2)."""

from enum import Enum
from typing import Annotated, Literal

from pydantic import Field

from ai_clients import config

# Every file of this module is at version 2 since the 5-phase policy (2026-10-06, research
# R22); a file of version 1 (the pilots 1 to 5) is never read. The dataset stays at 1.
SchemaVersion = Literal[2]
Sha256Hex = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Attempt = Annotated[int, Field(ge=1, le=config.MAX_ATTEMPTS)]
NonNegative = Annotated[int, Field(ge=0)]
AttemptPhase = Literal[1, 2, 4]  # the phases that make calls (config.ATTEMPT_POLICY)
SuitePhase = Literal[1, 2, 3, 4]  # 3: the fallback, chosen among the 12 without a call


class Scenario(str, Enum):
    """The three context scenarios, in canonical processing order."""

    BLACK_BOX = "black_box"  # the statement only
    WHITE_BOX = "white_box"  # AC_ref.cpp only
    HYBRID = "hybrid"  # both


class AttemptFailure(str, Enum):
    """The four reasons that consume an attempt; nothing else does."""

    REPETITION = "repetition"  # the model failed the call: Ollama's "token repeat limit reached"
    UNPARSEABLE_RESPONSE = "unparseable_response"
    PUBLIC_TEST_FAILED = "public_test_failed"
    ALL_INPUTS_FAILED = "all_inputs_failed"  # runtime error and/or timeout on every input


class InputDiscard(str, Enum):
    """Why one generated input was dropped while the others stayed."""

    TIMEOUT = "timeout"  # verdict TLE
    RUNTIME_ERROR = "runtime_error"  # verdict RE or MLE (kept in `verdict`)
    NON_UTF8_OUTPUT = "non_utf8_output"


class SuiteStatus(str, Enum):
    """How the suite of a problem × scenario was obtained (config.py, in the order tried)."""

    ACCEPTED = "accepted"  # its solution passed every public test
    ACCEPTED_FALLBACK = "accepted_fallback"  # its solution failed a public test by WA
    ACCEPTED_PREDICTED = "accepted_predicted"  # outputs written by the model, nothing run
    DISCARDED_MANUAL = "discarded_manual"  # closed by the authors, with a reason (no suite)
    # Commercial models only: outputs written by the model in an answer that reported no
    # reasoning, taken after 3 such answers (FR-018a, amended on 2026-10-20).
    ACCEPTED_BARRED = "accepted_barred"


class AttemptKind(str, Enum):
    """What an attempt asks for: the ``template`` of its row in ``config.ATTEMPT_POLICY``."""

    SOLUTION = "solution"  # inputs and a Python solution (the main template)
    PREDICTION = "prediction"  # inputs and expected outputs (the prediction template)


assert tuple(s.value for s in Scenario) == config.SCENARIOS
