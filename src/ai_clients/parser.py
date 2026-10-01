"""Reading the answer of the SLM: three blocks, strict rules, no heuristic correction.

Rules (docs/metodologia-referencia.md, section 3; research R6), applied to the raw text after only
``\\r\\n`` -> ``\\n``:

1. ``<edge_cases_analysis>``, ``<inputs>`` and ``<reference_py>`` each open and close exactly once,
   in this order, without overlapping; anything else fails with the exact reason.
2. Text outside the three blocks is ignored and its non-blank characters are counted; it never
   changes what is read.
3. ``<inputs>`` holds one or more ``<input>...</input>``, not nested, with only whitespace between.
4. Each block loses the whitespace-only lines at its two ends and gets exactly one final ``\\n``;
   spaces inside the lines are never touched. A block (or input) left empty fails.
5. The code is kept as it came: a Markdown fence around it is NOT removed (it becomes a
   ``SyntaxError`` and fails the public tests). Repeated inputs are kept and counted.

``parse_response`` is pure and never raises: every answer is either parsed or has an error code.
"""

from ai_clients.schemas.generation import ParsedResponse, UnparsedResponse

TAGS = ("edge_cases_analysis", "inputs", "reference_py")


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


def _inputs(body: str) -> list[str]:
    inputs, position = [], 0
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
        if not text:
            raise _Unparseable("empty_input")
        inputs.append(text)
        position = end + len("</input>")
    if not inputs:
        raise _Unparseable("no_inputs")
    return inputs


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
    code = _normalize_block(blocks["reference_py"])
    for tag, value in (("edge_cases_analysis", analysis), ("reference_py", code)):
        if not value:
            raise _Unparseable(f"empty_block:{tag}")
    inputs = _inputs(blocks["inputs"])
    return ParsedResponse(
        ok=True,
        edge_cases_analysis=analysis,
        inputs=inputs,
        reference_py=code,
        extraneous_chars=sum(len("".join(part.split())) for part in outside),
        duplicate_inputs=len(inputs) - len(set(inputs)),
    )


def parse_response(raw: str) -> ParsedResponse | UnparsedResponse:
    """Parse the raw answer of the model; never raises."""
    try:
        return _parse(raw)
    except _Unparseable as exc:
        return UnparsedResponse(ok=False, error=str(exc))
