"""Reading the answer of the SLM: three blocks, strict rules, no heuristic correction.

Rules (docs/metodologia-referencia.md, section 3; research R6), applied to the raw text after only
``\\r\\n`` -> ``\\n``:

1. ``<edge_cases_analysis>``, ``<reference_py>`` and ``<inputs>`` each open and close exactly once,
   in this order (the one the prompt asks for), without overlapping; anything else fails with the exact reason.
2. Text outside the three blocks is ignored and its non-blank characters are counted; it never
   changes what is read.
3. ``<inputs>`` holds one or more ``<input>...</input>``, not nested, with only whitespace between.
4. Each block loses the whitespace-only lines at its two ends and gets exactly one final ``\\n``;
   spaces inside the lines are never touched. An analysis or code block left empty fails. An
   ``<input>`` left empty is dropped alone and counted (``empty_inputs``); only when every input
   is empty does the answer fail (``only_empty_inputs``).
5. The code is kept as it came, with ONE fixed exception: a Markdown fence wrapping the whole
   block (first line exactly ```` ```python ````, ```` ```py ```` or ```` ``` ````, last line
   exactly ```` ``` ````) is removed and recorded (``markdown_fence_removed``). Any other fence
   stays (it becomes a ``SyntaxError`` and fails the public tests). Repeated inputs are kept and
   counted.

``parse_response`` is pure and never raises: every answer is either parsed or has an error code.
``parse_prediction`` does the same for the answer of a prediction attempt (end of this file).
"""

import re

from ai_clients.schemas.generation import ParsedResponse, PredictionParse, UnparsedResponse
from dataset.schemas.testes import TestCase

TAGS = ("edge_cases_analysis", "reference_py", "inputs")
FENCE_OPENINGS = ("```python", "```py", "```")
FENCE_CLOSING = "```"


class _Unparseable(Exception):
    pass


def _normalize_block(text: str) -> str:
    lines = text.split("\n")
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines) + "\n" if lines else ""


def _span(text: str, tag: str) -> tuple[int, int, int, int]:
    """(start of the open tag, start of the content, end of the content, end of the close tag)."""
    opening, closing = f"<{tag}>", f"</{tag}>"
    opens, closes = text.count(opening), text.count(closing)
    if opens == 0 and closes == 0:
        raise _Unparseable(f"missing_block:{tag}")
    if opens > 1 or closes > 1:
        raise _Unparseable(f"duplicated_block:{tag}")
    if opens != closes:
        raise _Unparseable(f"unclosed_block:{tag}")
    start, end = text.index(opening), text.index(closing)
    if end < start:
        raise _Unparseable(f"unclosed_block:{tag}")
    return start, start + len(opening), end, end + len(closing)


def _strip_fence(block: str, openings: tuple[str, ...] = FENCE_OPENINGS) -> tuple[str, bool]:
    """Remove a Markdown fence that wraps the whole (normalized) block, and only that one."""
    lines = block.split("\n")[:-1]  # a normalized block ends with exactly one "\n"
    opened = len(lines) >= 2 and lines[0].rstrip() in openings
    if opened and lines[-1].rstrip() == FENCE_CLOSING:
        return _normalize_block("\n".join(lines[1:-1])), True
    return block, False


def _inputs(body: str) -> tuple[list[str], int]:
    """The non-empty inputs, in order, and how many empty ones were dropped."""
    inputs, empty, position = [], 0, 0
    while True:
        start = body.find("<input>", position)
        gap = body[position:] if start < 0 else body[position:start]
        if gap.strip():
            raise _Unparseable("text_between_inputs")
        if start < 0:
            break
        content_start = start + len("<input>")
        end = body.find("</input>", content_start)
        if end < 0:
            raise _Unparseable("unclosed_block:input")
        content = body[content_start:end]
        if "<input>" in content:
            raise _Unparseable("nested_input")
        text = _normalize_block(content)
        if text:
            inputs.append(text)
        else:
            empty += 1
        position = end + len("</input>")
    if not inputs:
        raise _Unparseable("only_empty_inputs" if empty else "no_inputs")
    return inputs, empty


def _blocks(raw: str, tags: tuple[str, ...]) -> tuple[dict[str, str], int]:
    """The content of each top-level block, and the non-blank characters outside them."""
    text = raw.replace("\r\n", "\n")
    spans = [_span(text, tag) for tag in tags]
    starts = [span[0] for span in spans]
    if starts != sorted(starts):
        raise _Unparseable("wrong_order")
    if any(spans[i][3] > spans[i + 1][0] for i in range(len(spans) - 1)):
        raise _Unparseable("overlapping_blocks")
    blocks = {tag: text[span[1] : span[2]] for tag, span in zip(tags, spans, strict=True)}
    outside = [text[: spans[0][0]]]
    outside += [text[spans[i][3] : spans[i + 1][0]] for i in range(len(spans) - 1)]
    outside.append(text[spans[-1][3] :])
    return blocks, sum(len("".join(part.split())) for part in outside)


def _parse(raw: str) -> ParsedResponse:
    blocks, extraneous = _blocks(raw, TAGS)
    analysis = _normalize_block(blocks["edge_cases_analysis"])
    code, fence_removed = _strip_fence(_normalize_block(blocks["reference_py"]))
    for tag, value in (("edge_cases_analysis", analysis), ("reference_py", code)):
        if not value:
            raise _Unparseable(f"empty_block:{tag}")
    inputs, empty = _inputs(blocks["inputs"])
    return ParsedResponse(
        ok=True,
        edge_cases_analysis=analysis,
        inputs=inputs,
        reference_py=code,
        extraneous_chars=extraneous,
        duplicate_inputs=len(inputs) - len(set(inputs)),
        empty_inputs=empty,
        markdown_fence_removed=fence_removed,
    )


def parse_response(raw: str) -> ParsedResponse | UnparsedResponse:
    """Parse the raw answer of the model; never raises."""
    try:
        return _parse(raw)
    except _Unparseable as exc:
        return UnparsedResponse(ok=False, error=str(exc))


# ------------------------------------------------------------------------------- prediction
#
# The answer of a prediction attempt (research R19, item 4): ``<edge_cases_analysis>`` and
# ``<tests>``, with the same rules 1, 2 and 4 as above; inside ``<tests>``, one or more ``<test>``
# with only whitespace between them, each holding exactly one ``<input>`` followed by one
# ``<output>`` and nothing else but whitespace. Rule 5 applies to each ``<input>`` and ``<output>``
# with the fences of data (```` ``` ````, ```` ```text ````, ```` ```txt ````, ```` ```plaintext
# ````): one wrapping the whole block is removed and counted (``markdown_fences_removed``), any
# other stays. A test with an empty input or output is dropped alone and counted (``empty_tests``),
# and so is one with an abbreviated input or output (``abbreviated_tests``, research R27): a line
# holding a token made only of 3 or more dots next to other tokens (``1 2 ... 100``), or a ``…``
# anywhere. A line of dots alone (a grid row such as ``...``) is data and stays: 0 of the 47,492
# inputs and outputs of the dataset's tests match the rule, 67 contain ``...``. Only when every
# test is dropped does the answer fail. The predicted output is kept as written (only rules 4 and
# 5), never checked: there is no program to run.

PREDICTION_TAGS = ("edge_cases_analysis", "tests")
_TEST_PARTS = ("input", "output")
DATA_FENCE_OPENINGS = ("```", "```text", "```txt", "```plaintext")
_DOTS = re.compile(r"^\.{3,}$")


def is_abbreviated(text: str) -> bool:
    """Whether a predicted input or output elides values (``1 1 ... 1``) instead of writing them."""
    if "…" in text:
        return True
    for line in text.splitlines():
        tokens = line.split()
        if len(tokens) > 1 and any(_DOTS.match(token) for token in tokens):
            return True
    return False


def _test(content: str) -> tuple[str, str]:
    """The (input, output) of the content of one ``<test>``, not yet normalized."""
    rest, parts = content.strip(), []
    for tag in _TEST_PARTS:
        opening, closing = f"<{tag}>", f"</{tag}>"
        end = rest.find(closing)
        if not rest.startswith(opening) or end < 0:
            raise _Unparseable("malformed_test")
        body = rest[len(opening) : end]
        if any(f"<{t}>" in body or f"</{t}>" in body for t in _TEST_PARTS):
            raise _Unparseable("malformed_test")
        parts.append(body)
        rest = rest[end + len(closing) :].strip()
    if rest:
        raise _Unparseable("malformed_test")
    return parts[0], parts[1]


def _tests(body: str) -> tuple[list[TestCase], int, int, int]:
    """The tests with a complete input and output, in order, how many were dropped for being
    empty, how many for being abbreviated, and how many fences were removed."""
    tests, empty, abbreviated, fences, position = [], 0, 0, 0, 0
    while True:
        start = body.find("<test>", position)
        gap = body[position:] if start < 0 else body[position:start]
        if gap.strip():
            raise _Unparseable("text_between_tests")
        if start < 0:
            break
        content_start = start + len("<test>")
        end = body.find("</test>", content_start)
        if end < 0:
            raise _Unparseable("unclosed_block:test")
        content = body[content_start:end]
        if "<test>" in content:
            raise _Unparseable("nested_test")
        parts = []
        for part in _test(content):
            text, removed = _strip_fence(_normalize_block(part), DATA_FENCE_OPENINGS)
            fences += removed
            parts.append(text)
        given, expected = parts
        if not (given and expected):
            empty += 1
        elif is_abbreviated(given) or is_abbreviated(expected):
            abbreviated += 1
        else:
            tests.append(TestCase(input=given, output=expected))
        position = end + len("</test>")
    if not tests:
        if empty and abbreviated:
            raise _Unparseable("only_empty_or_abbreviated_tests")
        if abbreviated:
            raise _Unparseable("only_abbreviated_tests")
        raise _Unparseable("only_empty_tests" if empty else "no_tests")
    return tests, empty, abbreviated, fences


def _parse_prediction(raw: str) -> PredictionParse:
    blocks, extraneous = _blocks(raw, PREDICTION_TAGS)
    analysis = _normalize_block(blocks["edge_cases_analysis"])
    if not analysis:
        raise _Unparseable("empty_block:edge_cases_analysis")
    tests, empty, abbreviated, fences = _tests(blocks["tests"])
    inputs = [test.input for test in tests]
    return PredictionParse(
        ok=True,
        edge_cases_analysis=analysis,
        tests=tests,
        extraneous_chars=extraneous,
        duplicate_inputs=len(inputs) - len(set(inputs)),
        empty_tests=empty,
        abbreviated_tests=abbreviated,
        markdown_fences_removed=fences,
    )


def parse_prediction(raw: str) -> PredictionParse | UnparsedResponse:
    """Parse the raw answer of a prediction attempt; never raises."""
    try:
        return _parse_prediction(raw)
    except _Unparseable as exc:
        return UnparsedResponse(ok=False, error=str(exc))
