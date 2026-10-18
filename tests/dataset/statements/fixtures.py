"""Small statement pages written by hand with the structure measured on Codeforces (research R2).

No page of the site is copied here. ``page(...)`` wraps the parts in the real layout (header,
description, input, output, examples, note); ``enunciado(...)`` is the matching ``enunciado.md``
as the dataset has it: the parts flattened, with the examples block.
"""

HEADER = (
    '<div class="header"><div class="title">A. Test</div>'
    '<div class="time-limit"><div class="property-title">time limit per test</div>1 second</div>'
    "</div>"
)


def page(
    legend: str,
    input_spec: str = "One line.",
    output_spec: str = "One number.",
    note: str | None = "It works.",
    extra: str = "",
) -> str:
    note_html = (
        f'<div class="note"><div class="section-title">Note</div><p>{note}</p></div>'
        if note is not None
        else ""
    )
    return (
        '<html><head><title>x</title></head><body><div class="menu">Home</div>'
        '<div class="problem-statement">'
        f"{HEADER}"
        f"<div><p>{legend}</p></div>"
        f'<div class="input-specification"><div class="section-title">Input</div>'
        f"<p>{input_spec}</p></div>"
        f'<div class="output-specification"><div class="section-title">Output</div>'
        f"<p>{output_spec}</p></div>"
        f"{extra}"
        '<div class="sample-tests"><div class="section-title">Examples</div>'
        '<div class="sample-test"><div class="input"><div class="title">Input</div>'
        '<pre>1</pre></div><div class="output"><div class="title">Output</div><pre>1</pre>'
        "</div></div></div>"
        f"{note_html}"
        "</div><script>var x = 1;</script></body></html>"
    )


def enunciado(
    legend: str,
    input_spec: str = "One line.",
    output_spec: str = "One number.",
    note: str | None = "It works.",
    extra: str = "",
) -> str:
    text = f"{legend}\n\nInput\n\n{input_spec}\n\nOutput\n\n{output_spec}\n\n"
    if extra:
        text += f"{extra}\n\n"
    text += "Examples\n\nInput\n\n1\n\n\nOutput\n\n1\n\n"
    if note is not None:
        text += f"Note\n\n{note}\n"
    return text


OLD_LEGEND_HTML = (
    'Read n <span class="tex-span">(1&thinsp;≤&thinsp;<i>n</i>&thinsp;≤&thinsp;10'
    '<sup class="upper-index">5</sup>)</span> and the numbers <span class="tex-span">'
    '<i>a</i><sub class="lower-index"><i>i</i></sub></span>.'
)
OLD_LEGEND_OURS = "Read n (1 ≤ n ≤ 105) and the numbers ai."

NEW_LEGEND_HTML = r"Read $$$n$$$ ($$$1 \le n \le 10^5$$$) and the numbers $$$a_i$$$."
NEW_LEGEND_OURS = "Read n (1 ≤ n ≤ 10^5) and the numbers a_i."

BIG_POWER_HTML = 'Read n (0 ≤ n ≤ 10<sup class="upper-index">100000</sup>).'
BIG_POWER_OURS = "Read n (0 ≤ n ≤ 10100000)."
