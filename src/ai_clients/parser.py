"""Reading the answer of the SLM: three blocks, strict rules, no heuristic correction.

Rules (docs/metodologia-referencia.md, section 3; research R6), applied to the raw text after only
``\\r\\n`` -> ``\\n``:

1. ``<edge_cases_analysis>``, ``<inputs>`` and ``<reference_py>`` each open and close exactly once,
   in this order, without overlapping; anything else fails with the exact reason.
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
"""

from ai_clients.schemas.generation import ParsedResponse, UnparsedResponse

TAGS = ("edge_cases_analysis", "inputs", "reference_py")
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


def _strip_fence(code: str) -> tuple[str, bool]:
    """Remove a Markdown fence that wraps the whole (normalized) code block, and only that one."""
    lines = code.split("\n")[:-1]  # a normalized block ends with exactly one "\n"
    opened = len(lines) >= 2 and lines[0].rstrip() in FENCE_OPENINGS
    if opened and lines[-1].rstrip() == FENCE_CLOSING:
        return _normalize_block("\n".join(lines[1:-1])), True
    return code, False


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


def _parse(raw: str) -> ParsedResponse:
    text = raw.replace("\r\n", "\n")
    spans = [_span(text, tag) for tag in TAGS]
    starts = [span[0] for span in spans]
    if starts != sorted(starts):
        raise _Unparseable("wrong_order")
    if any(spans[i][3] > spans[i + 1][0] for i in range(len(spans) - 1)):
        raise _Unparseable("overlapping_blocks")
    blocks = {tag: text[span[1] : span[2]] for tag, span in zip(TAGS, spans, strict=True)}
    outside = [text[: spans[0][0]]]
    outside += [text[spans[i][3] : spans[i + 1][0]] for i in range(len(spans) - 1)]
    outside.append(text[spans[-1][3] :])
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
        extraneous_chars=sum(len("".join(part.split())) for part in outside),
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
