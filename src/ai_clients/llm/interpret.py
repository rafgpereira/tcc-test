"""Reading the answer of a commercial model (research R6; FR-013, FR-015). Pure, never raises.

The checks run in this order and the first one that fails decides:

1. reasoning (``needs_barrier``): an answer reporting 0 reasoning tokens, or none, is not an
   attempt at all; the coordinator bars it (FR-018a);
2. how the API stopped: cut by the output ceiling (``truncated``), a refusal (``refusal``) or a
   safety block (``safety_block``, with the blocked categories of Gemini);
3. the text: empty (``empty_response``), not JSON (``not_json``), not the answer schema
   (``schema_violation``);
4. the tests, with the rules of the SLM prediction (``ai_clients.parser``): a fence wrapping a
   whole input or output is removed and counted; each text gets exactly one final newline; a test
   with an empty or abbreviated input or output is dropped alone and counted; a repeated input is
   kept once (the first) and counted, and a different output for it counts as a conflict; a copy
   of the few-shot example is kept and counted. No test left: ``no_usable_test``.

The predicted outputs are never checked: there is no program to run (FR-014).
"""

import json

from pydantic import ValidationError

from ai_clients.llm.providers import ProviderAnswer
from ai_clients.llm.schemas import FormatFailure, LlmAnswer, LlmFormatFailure, LlmParsed
from ai_clients.parser import is_abbreviated, strip_data_fence
from dataset.schemas.testes import TestCase

# Gemini finishReason values that mean the candidate was blocked for its content.
GEMINI_SAFETY = frozenset(
    {"SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST", "SPII", "RECITATION", "IMAGE_SAFETY"}
)


def needs_barrier(answer: ProviderAnswer) -> bool:
    """Whether the answer reports no reasoning: 0 tokens or no count at all (FR-018a)."""
    return not answer.usage.reasoning_tokens


def _failure(failure: FormatFailure, detail: str) -> LlmFormatFailure:
    return LlmFormatFailure(ok=False, failure=failure, detail=detail)


def _finish_failure(answer: ProviderAnswer) -> LlmFormatFailure | None:
    finish = answer.finish
    if finish.status == "incomplete":  # OpenAI
        if finish.reason == "max_output_tokens":
            return _failure(FormatFailure.TRUNCATED, "incomplete: max_output_tokens")
        if finish.reason == "content_filter":
            return _failure(FormatFailure.SAFETY_BLOCK, "incomplete: content_filter")
        return _failure(FormatFailure.TRUNCATED, f"incomplete: {finish.reason}")
    if answer.refusal is not None:
        return _failure(FormatFailure.REFUSAL, f"refusal: {answer.refusal[:200]}")
    if finish.status == "PROMPT_BLOCKED":  # Gemini
        return _failure(FormatFailure.SAFETY_BLOCK, f"prompt blocked: {finish.reason}")
    if finish.status == "MAX_TOKENS":
        return _failure(FormatFailure.TRUNCATED, "finishReason MAX_TOKENS")
    if finish.status in GEMINI_SAFETY:
        categories = ", ".join(finish.safety_categories) or "no category reported"
        return _failure(FormatFailure.SAFETY_BLOCK, f"finishReason {finish.status}: {categories}")
    return None


def _reason(exc: ValidationError) -> str:
    error = exc.errors()[0]
    where = ".".join(str(part) for part in error["loc"])
    return f"{where}: {error['msg']}" if where else error["msg"]


def _is_utf8(text: str) -> bool:
    try:
        text.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def interpret(answer: ProviderAnswer, example: TestCase) -> LlmParsed | LlmFormatFailure:
    """The parsed answer or the format failure (after the barrier, which the caller applies)."""
    failure = _finish_failure(answer)
    if failure is not None:
        return failure
    text = answer.text
    if text is None or not text.strip():
        return _failure(FormatFailure.EMPTY_RESPONSE, "the answer has no text")
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError, RecursionError) as exc:
        return _failure(FormatFailure.NOT_JSON, str(exc)[:200] or type(exc).__name__)
    try:
        parsed = LlmAnswer.model_validate(data)
    except ValidationError as exc:
        return _failure(FormatFailure.SCHEMA_VIOLATION, _reason(exc)[:200])
    if not parsed.edge_cases_analysis.strip():
        return _failure(FormatFailure.SCHEMA_VIOLATION, "edge_cases_analysis is empty")
    texts = [parsed.edge_cases_analysis, *(s for t in parsed.tests for s in (t.input, t.output))]
    if not all(_is_utf8(text) for text in texts):
        # A lone surrogate (``\ud800``) is valid JSON but not text: it could not be recorded.
        return _failure(FormatFailure.SCHEMA_VIOLATION, "a text is not valid UTF-8")
    example_pair = (strip_data_fence(example.input)[0], strip_data_fence(example.output)[0])
    kept: dict[str, str] = {}
    empty = abbreviated = fences = duplicates = conflicts = copies = 0
    for test in parsed.tests:
        given, fenced_in = strip_data_fence(test.input)
        expected, fenced_out = strip_data_fence(test.output)
        fences += fenced_in + fenced_out
        if not (given and expected):
            empty += 1
        elif is_abbreviated(given) or is_abbreviated(expected):
            abbreviated += 1
        elif given in kept:
            duplicates += 1
            conflicts += kept[given] != expected
        else:
            kept[given] = expected
            copies += (given, expected) == example_pair
    if not kept:
        return _failure(
            FormatFailure.NO_USABLE_TEST,
            f"{len(parsed.tests)} tests: {empty} empty, {abbreviated} abbreviated",
        )
    return LlmParsed(
        ok=True,
        edge_cases_analysis=parsed.edge_cases_analysis,
        tests=[TestCase(input=i, output=o) for i, o in kept.items()],
        empty_tests=empty,
        abbreviated_tests=abbreviated,
        markdown_fences_removed=fences,
        duplicate_inputs=duplicates,
        conflicting_outputs=conflicts,
        example_copies=copies,
    )
