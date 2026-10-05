"""``attempt_<n>.generation.json``: one call to the model and how its answer was read.

Written once by ``generate``, never changed. The raw response is kept whole, so the execution phase
(or a repetition of it) never needs to call the model again for an answer already received. When
the model itself failed the call (Ollama's ``token repeat limit reached``), there is no answer: the
record keeps the reason in ``model_failure`` instead, and the attempt is failed (``repetition``).
"""

from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator

from ai_clients import config
from ai_clients.schemas.common import Attempt, NonNegative, Scenario, Sha256Hex
from dataset.schemas.common import PROBLEM_ID_PATTERN, Schema, SchemaVersion


class OllamaMeta(Schema):
    """What Ollama reported about the call: tokens, why it stopped, durations."""

    model: str = Field(min_length=1)
    created_at: str
    done_reason: str  # "stop" or "length" (the answer hit num_predict)
    prompt_eval_count: NonNegative
    eval_count: NonNegative
    total_duration_ns: NonNegative
    load_duration_ns: NonNegative
    prompt_eval_duration_ns: NonNegative
    eval_duration_ns: NonNegative


class ParsedResponse(Schema):
    """The three blocks of a well-formed answer."""

    ok: Literal[True]
    edge_cases_analysis: str
    inputs: list[str] = Field(min_length=1)
    reference_py: str
    extraneous_chars: NonNegative  # text outside the three blocks, ignored (never corrected)
    duplicate_inputs: NonNegative  # inputs equal to an earlier one of the same answer (kept)
    empty_inputs: NonNegative = 0  # empty <input> blocks, dropped alone (not in `inputs`)
    markdown_fence_removed: bool = False  # a fence wrapping the whole <reference_py> was removed

    @field_validator("edge_cases_analysis", "reference_py")
    @classmethod
    def _not_blank(cls, text: str) -> str:
        if not text.strip():
            raise ValueError("the block is empty")
        return text

    @field_validator("inputs")
    @classmethod
    def _complete_stdin(cls, inputs: list[str]) -> list[str]:
        for index, text in enumerate(inputs):
            if not text.strip():
                raise ValueError(f"input {index} is empty")
            if not text.endswith("\n") or text.endswith("\n\n"):
                raise ValueError(f"input {index} must end with exactly one newline")
        return inputs


class UnparsedResponse(Schema):
    """An answer whose blocks could not be read: the attempt is `unparseable_response`."""

    ok: Literal[False]
    error: str = Field(min_length=1)  # parser code, e.g. "missing_block:reference_py"


class ModelFailure(Schema):
    """The model failed the call itself (Ollama answered an error, not an answer)."""

    reason: Literal["repetition"]  # Ollama: "token repeat limit reached" (HTTP 500)
    detail: str  # the error text of Ollama, as received


class GenerationRecord(Schema):
    schema_version: SchemaVersion = 1
    problem_id: str = Field(pattern=PROBLEM_ID_PATTERN)
    scenario: Scenario
    attempt: Attempt
    seed: int
    model_digest: str = Field(min_length=1)  # of the model that answered (also in run.json)
    prompt_sha256: Sha256Hex
    raw_response: str
    ollama: OllamaMeta | None  # null only with `model_failure` (there was no answer)
    hardware_label: str = Field(min_length=1)
    requested_at: str
    parse: Annotated[ParsedResponse | UnparsedResponse, Field(discriminator="ok")]
    model_failure: ModelFailure | None = None

    @model_validator(mode="after")
    def _seed_of_the_attempt(self) -> "GenerationRecord":
        if self.seed != config.seed_for(self.attempt):
            raise ValueError(
                f"attempt {self.attempt} must use seed {config.seed_for(self.attempt)}, "
                f"got {self.seed}"
            )
        return self

    @model_validator(mode="after")
    def _answer_or_model_failure(self) -> "GenerationRecord":
        if self.model_failure is None:
            if self.ollama is None:
                raise ValueError("an answered call has its ollama metadata")
            return self
        if self.ollama is not None or self.raw_response:
            raise ValueError("a model failure has no answer and no ollama metadata")
        if self.parse.ok or self.parse.error != self.model_failure.reason:
            raise ValueError(f"a model failure is not parsed: error {self.model_failure.reason!r}")
        return self
