"""Schemas of the commercial models (specs/004-llm-test-generation/data-model.md, sections 2 and 3).

Every file is written once and never changed. ``suite.json`` keeps the file contract of the SLM
(``schema_version`` 2 and the same top-level keys, so the common reader ``SuiteView`` reads the three
models alike), but it is validated by ``LlmSuite``: ``SlmSuite`` checks every attempt against the
seed policy of the SLM (research R1). The other files are new, at ``schema_version`` 1.
"""

import re
from datetime import date
from enum import Enum
from typing import Annotated, Any, Literal

from pydantic import Field, field_validator, model_validator

from ai_clients.llm import config
from ai_clients.schemas.common import NonNegative, Scenario, Sha256Hex, SuiteStatus
from ai_clients.schemas.suite import ManualCloseInfo
from ai_clients.schemas.template_change import SupersededCombination
from dataset.schemas.common import PROBLEM_ID_PATTERN, Schema
from dataset.schemas.manifest import FileHash
from dataset.schemas.testes import TestCase

LlmModel = Literal["gpt", "gemini"]
LlmAttemptNumber = Annotated[int, Field(ge=1, le=config.MAX_ATTEMPTS)]
LlmTemplateKind = Literal["llm"]

# Never sent to a model (FR-002, FR-003, A3, A11, A13): the request must carry no sampling
# parameter, no instruction outside the single user message, no state kept by the provider and no
# safety settings. Checked recursively in every recorded request.
FORBIDDEN_PARAMETERS = frozenset(
    {
        "temperature",
        "top_p",
        "topP",
        "top_k",
        "topK",
        "seed",
        "instructions",
        "systemInstruction",
        "system_instruction",
        "safetySettings",
        "previous_response_id",
        "conversation",
        "cachedContent",
    }
)


class FormatFailure(str, Enum):
    """The seven reasons that consume an attempt (FR-015; research R6); nothing else does."""

    EMPTY_RESPONSE = "empty_response"
    NOT_JSON = "not_json"
    SCHEMA_VIOLATION = "schema_violation"
    TRUNCATED = "truncated"  # cut by the output ceiling (reasoning and answer share it)
    REFUSAL = "refusal"
    SAFETY_BLOCK = "safety_block"
    NO_USABLE_TEST = "no_usable_test"


def forbidden_keys(value: Any) -> set[str]:
    """Every forbidden key found anywhere inside ``value`` (dicts and lists, recursively)."""
    found: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if key in FORBIDDEN_PARAMETERS:
                found.add(key)
            found |= forbidden_keys(item)
    elif isinstance(value, list):
        for item in value:
            found |= forbidden_keys(item)
    return found


def _no_forbidden(parameters: dict[str, Any]) -> dict[str, Any]:
    found = forbidden_keys(parameters)
    if found:
        raise ValueError(f"never sent to a model: {', '.join(sorted(found))}")
    return parameters


def _complete_text(text: str, what: str) -> str:
    if not text.strip():
        raise ValueError(f"{what} is empty")
    if not text.endswith("\n") or text.endswith("\n\n"):
        raise ValueError(f"{what} must end with exactly one newline")
    return text


# ------------------------------------------------------------------------------------- prices


class PriceRow(Schema):
    """One row of the price table, in US$ per million tokens (research R9)."""

    model_key: LlmModel
    valid_from: date
    input_per_mtok: float = Field(ge=0)
    cached_input_per_mtok: float = Field(ge=0)
    output_per_mtok: float = Field(ge=0)
    source: str = Field(min_length=1)
    accessed_on: date


def price_table() -> list[PriceRow]:
    """``config.PRICE_TABLE`` as recorded in run.json."""
    return [PriceRow(**row._asdict()) for row in config.PRICE_TABLE]


# ---------------------------------------------------------------------------------- run.json


class LlmRunConfig(Schema):
    """``run.json``: the identity of one run of one model, compared by every ``--resume``."""

    schema_version: Literal[1] = 1
    model_key: LlmModel
    model_requested: str = Field(min_length=1)
    endpoint: str = Field(min_length=1)
    request_parameters: dict[str, Any]
    response_schema: dict[str, Any]
    template_sha256: Sha256Hex
    max_attempts: Literal[3] = 3
    dataset_manifest_sha256: Sha256Hex
    price_table: list[PriceRow] = Field(min_length=1)  # not compared: a price change is recorded
    created_at: str  # informative; not compared

    @field_validator("request_parameters")
    @classmethod
    def _allowed_parameters(cls, parameters: dict[str, Any]) -> dict[str, Any]:
        return _no_forbidden(parameters)

    def differences(self, other: "LlmRunConfig") -> list[tuple[str, object, object]]:
        """``(field, value here, value in other)`` for every compared field that differs.

        ``request_parameters`` key by key (``request_parameters.reasoning``), so the refusal says
        exactly what changed; ``price_table`` and ``created_at`` are never compared.
        """
        skip = {"created_at", "price_table"}
        mine = self.model_dump(mode="json", exclude=skip)
        theirs = other.model_dump(mode="json", exclude=skip)
        out = []
        for key in sorted(mine):
            if key == "request_parameters":
                for sub in sorted(set(mine[key]) | set(theirs[key])):
                    here, there = mine[key].get(sub), theirs[key].get(sub)
                    if here != there:
                        out.append((f"request_parameters.{sub}", here, there))
            elif mine[key] != theirs[key]:
                out.append((key, mine[key], theirs[key]))
        return out

    def with_changes(self, changes: list["LlmTemplateChange"]) -> "LlmRunConfig":
        """This run with its template changes applied in order: its current template.

        ``ValueError`` if a change does not start from the template current at its point.
        """
        current = self
        for change in changes:
            if change.from_sha256 != current.template_sha256:
                raise ValueError(
                    f"template change {change.number} starts from {change.from_sha256}, but the "
                    f"current template is {current.template_sha256}"
                )
            current = current.model_copy(update={"template_sha256": change.to_sha256})
        return current


# ------------------------------------------------------------------------------- one call


class Finish(Schema):
    """Why the API stopped: OpenAI ``status``/``incomplete_details.reason``; Gemini
    ``finishReason`` or ``promptFeedback.blockReason`` (with the blocked safety categories)."""

    status: str
    reason: str | None = None
    safety_categories: list[str] = Field(default_factory=list)


class Usage(Schema):
    """Tokens as reported by the API; ``output_tokens`` is what is billed as output (it includes
    the reasoning); ``reasoning_tokens`` is ``None`` when the API did not report it."""

    input_tokens: NonNegative
    cached_input_tokens: NonNegative
    output_tokens: NonNegative
    reasoning_tokens: NonNegative | None


class LlmParsed(Schema):
    """A usable answer: the analysis and the kept tests, with what was dropped (FR-013)."""

    ok: Literal[True]
    edge_cases_analysis: str
    tests: list[TestCase] = Field(min_length=1)  # the outputs are the model's, never checked
    empty_tests: NonNegative
    abbreviated_tests: NonNegative
    markdown_fences_removed: NonNegative
    duplicate_inputs: NonNegative
    conflicting_outputs: NonNegative  # repeated inputs with a different output (subset)
    example_copies: NonNegative  # tests equal to the few-shot example (kept)

    @field_validator("edge_cases_analysis")
    @classmethod
    def _not_blank(cls, text: str) -> str:
        if not text.strip():
            raise ValueError("the analysis is empty")
        return text

    @field_validator("tests")
    @classmethod
    def _complete_tests(cls, tests: list[TestCase]) -> list[TestCase]:
        for index, test in enumerate(tests):
            _complete_text(test.input, f"the input of test {index}")
            _complete_text(test.output, f"the output of test {index}")
        inputs = [test.input for test in tests]
        if len(inputs) != len(set(inputs)):
            raise ValueError("a kept input appears twice")
        return tests


class LlmFormatFailure(Schema):
    """An answer that cannot give a suite: the attempt failed by format (FR-015)."""

    ok: Literal[False]
    failure: FormatFailure
    detail: str


class _CallRecord(Schema):
    """What every answered call records (FR-010, FR-011, FR-020)."""

    schema_version: Literal[1] = 1
    problem_id: str = Field(pattern=PROBLEM_ID_PATTERN)
    scenario: Scenario
    model_requested: str = Field(min_length=1)
    model_returned: str
    response_id: str
    prompt_sha256: Sha256Hex
    template_sha256: Sha256Hex
    request_parameters: dict[str, Any]
    requested_at: str
    latency_s: float = Field(ge=0)
    http_status: Literal[200] = 200
    raw_body: str  # the whole HTTP body, as received
    finish: Finish
    usage: Usage
    cost_usd: float = Field(ge=0)
    price_row: PriceRow

    @field_validator("request_parameters")
    @classmethod
    def _allowed_parameters(cls, parameters: dict[str, Any]) -> dict[str, Any]:
        return _no_forbidden(parameters)


class LlmAttempt(_CallRecord):
    """``attempt_<n>.json``: one call that counts as an attempt of its combination."""

    attempt: LlmAttemptNumber
    parse: LlmParsed | LlmFormatFailure

    @model_validator(mode="after")
    def _reasoned(self) -> "LlmAttempt":
        if not self.usage.reasoning_tokens:
            raise ValueError(
                "an answer without reasoning tokens is a BarredResponse, not an attempt"
            )
        return self


class BarredResponse(_CallRecord):
    """``barred/<id>/<scenario>/<n>.json``: an answer reporting no reasoning (FR-018a)."""

    reason: Literal["no_reasoning_tokens"] = "no_reasoning_tokens"
    barred_at: str

    @model_validator(mode="after")
    def _not_reasoned(self) -> "BarredResponse":
        if self.usage.reasoning_tokens:
            raise ValueError("an answer with reasoning tokens is never barred")
        return self


# ----------------------------------------------------------------------------- suite.json


class LlmAttemptSummary(Schema):
    attempt: LlmAttemptNumber
    failure: FormatFailure | None  # null only for the attempt the suite comes from
    detail: str  # the failure detail, or the kept/dropped counts
    model_returned: str
    cost_usd: float = Field(ge=0)


class LlmSuite(Schema):
    """``suite.json`` of a commercial model: the top-level keys of ``SlmSuite``, LLM values."""

    schema_version: Literal[2] = 2
    problem_id: str = Field(pattern=PROBLEM_ID_PATTERN)
    scenario: Scenario
    model: str = Field(min_length=1)  # the model requested (run.json)
    model_digest: str | None  # the model returned for the accepted attempt
    status: SuiteStatus
    accepted_phase: None = None  # always null: the commercial models have no phases
    attempts: list[LlmAttemptSummary] = Field(min_length=1, max_length=config.MAX_ATTEMPTS)
    accepted_attempt: LlmAttemptNumber | None
    tests: list[TestCase]
    suite_size: NonNegative
    discarded_inputs: list[Any] = Field(max_length=0)  # always []: nothing is run
    duplicate_inputs: NonNegative
    manual_close: ManualCloseInfo | None = None

    @model_validator(mode="after")
    def _terminal_state(self) -> "LlmSuite":
        numbers = [a.attempt for a in self.attempts]
        if numbers != list(range(1, len(numbers) + 1)):
            raise ValueError("attempts are numbered from 1 without gaps")
        if self.suite_size != len(self.tests):
            raise ValueError("suite_size is the number of tests")
        *earlier, last = self.attempts
        if any(a.failure is None for a in earlier):
            raise ValueError("only the last attempt can have succeeded")
        if self.status is SuiteStatus.DISCARDED_MANUAL:
            if len(self.attempts) != config.MAX_ATTEMPTS or last.failure is None:
                raise ValueError(
                    f"a suite closed by the authors has {config.MAX_ATTEMPTS} failed attempts"
                )
            if self.tests or self.manual_close is None:
                raise ValueError("a suite closed by the authors has no tests and a manual_close")
            if self.accepted_attempt is not None or self.model_digest is not None:
                raise ValueError("a suite closed by the authors has no accepted attempt")
            return self
        if self.status is not SuiteStatus.ACCEPTED_PREDICTED:
            raise ValueError(
                "a suite of a commercial model is accepted_predicted or discarded_manual"
            )
        if self.manual_close is not None:
            raise ValueError("only a suite closed by the authors has manual_close")
        if last.failure is not None or not self.tests:
            raise ValueError("an accepted_predicted suite comes from its last attempt, with tests")
        if self.accepted_attempt != last.attempt or self.model_digest is None:
            raise ValueError("an accepted_predicted suite names its attempt and the model returned")
        return self


# --------------------------------------------------------------------- the answer of a model


class LlmAnswerTest(Schema):
    input: str
    output: str


class LlmAnswer(Schema):
    """The JSON object a model must answer (research R4): exactly these fields."""

    edge_cases_analysis: str
    tests: list[LlmAnswerTest]


def response_schema() -> dict[str, Any]:
    """The JSON Schema sent to both APIs (research R4): the analysis before the tests, every field
    required, nothing else allowed, no length keyword (handled by the interpretation)."""
    test = {
        "type": "object",
        "properties": {"input": {"type": "string"}, "output": {"type": "string"}},
        "required": ["input", "output"],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {
            "edge_cases_analysis": {"type": "string"},
            "tests": {"type": "array", "items": test},
        },
        "required": ["edge_cases_analysis", "tests"],
        "additionalProperties": False,
    }


# --------------------------------------------------------------------- template changes


class LlmTemplateChange(Schema):
    """``template_changes/<NNN>.json``: the text-base changed during a run (data-model §3.9)."""

    schema_version: Literal[1] = 1
    number: int = Field(ge=1)
    template: LlmTemplateKind = "llm"
    from_sha256: Sha256Hex
    to_sha256: Sha256Hex
    changed_at: str
    reason: str
    superseded: list[SupersededCombination]

    @field_validator("reason")
    @classmethod
    def _not_blank(cls, text: str) -> str:
        if not text.strip():
            raise ValueError("the reason is required")
        return text

    @model_validator(mode="after")
    def _a_change(self) -> "LlmTemplateChange":
        if self.from_sha256 == self.to_sha256:
            raise ValueError("a change goes to another template")
        keys = [(c.problem_id, c.scenario.value) for c in self.superseded]
        if len(keys) != len(set(keys)):
            raise ValueError("a combination is listed twice")
        return self


# ------------------------------------------------------------------------------ manifest


def _suite_path(model: str) -> re.Pattern:
    root = re.escape(config.zip_root(model))
    combination = r"\d+_[A-Za-z0-9]+/(black_box|white_box|hybrid)"
    files = rf"(attempt_[1-{config.MAX_ATTEMPTS}]\.json|suite\.json|manual_close\.json)"
    return re.compile(
        rf"^{root}/(run\.json|problems/{combination}/{files}|"
        rf"{config.BARRED_DIR}/{combination}/\d+\.json|"
        rf"{config.TEMPLATE_CHANGES_DIR}/\d{{3}}\.json|"
        rf"{config.SUPERSEDED_DIR}/\d{{3}}/{combination}/{files})$"
    )


class LlmSuitesManifest(Schema):
    """``manifests/<model>_suites.manifest.json`` (data-model §3.7)."""

    schema_version: Literal[1] = 1
    model_key: LlmModel
    suites_zip: FileHash
    files: list[FileHash]  # one per file inside the zip, `path` as inside the zip, sorted

    @model_validator(mode="after")
    def _well_formed(self) -> "LlmSuitesManifest":
        expected = config.zip_path(self.model_key).as_posix()
        if self.suites_zip.path != expected:
            raise ValueError(f'suites_zip.path must be "{expected}"')
        paths = [item.path for item in self.files]
        if paths != sorted(paths):
            raise ValueError("files must be ordered by path")
        pattern = _suite_path(self.model_key)
        for path in paths:
            if not pattern.match(path):
                raise ValueError(f"{path!r} is not a file of a {self.model_key} run")
        return self
