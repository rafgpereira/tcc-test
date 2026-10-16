"""The public helpers that the commercial models reuse give exactly what the prediction parser does.

``strip_data_fence`` (normalize a predicted input or output and remove a fence wrapping all of it)
and ``is_abbreviated`` are the rules of the SLM prediction (research R27), now public for
``ai_clients.llm.interpret``; the SLM parser keeps using them, so nothing of the SLM changes.
"""

import pytest

from ai_clients.parser import is_abbreviated, parse_prediction, strip_data_fence

CASES = [
    ("1\n", "1\n", False),
    ("\n\n  1 2\n\n", "  1 2\n", False),
    ("```\n1 2\n```\n", "1 2\n", True),
    ("```text\nYES\n```", "YES\n", True),
    ("```txt\n3\n4\n```\n", "3\n4\n", True),
    ("```plaintext\nx\n```\n", "x\n", True),
    ("```python\nx\n```\n", "```python\nx\n```\n", False),  # not a fence of data
    ("```\nx\n", "```\nx\n", False),  # not closed: stays
    ("", "", False),
]


def prediction_of(given: str) -> tuple[str, int] | None:
    """What ``parse_prediction`` keeps of an input written as ``given`` (output fixed)."""
    raw = (
        "<edge_cases_analysis>\nok\n</edge_cases_analysis>\n<tests>\n"
        f"<test>\n<input>{given}</input>\n<output>\n1\n</output>\n</test>\n"
        "<test>\n<input>\n9\n</input>\n<output>\n9\n</output>\n</test>\n</tests>\n"
    )
    result = parse_prediction(raw)
    kept = [t.input for t in result.tests if t.input != "9\n"]
    return (kept[0] if kept else "", result.markdown_fences_removed)


@pytest.mark.parametrize("given, text, removed", CASES)
def test_strip_data_fence(given, text, removed):
    assert strip_data_fence(given) == (text, removed)


@pytest.mark.parametrize("given, text, removed", CASES)
def test_strip_data_fence_matches_the_prediction_parser(given, text, removed):
    assert prediction_of(given) == (text, int(removed))


@pytest.mark.parametrize(
    "text, expected",
    [
        ("1 2 ... 100\n", True),
        ("1 1 … 1\n", True),
        ("3\n...\n#.#\n", False),  # a grid row of dots alone is data
        ("repeated 5 times\n", False),
        ("1 2 3\n", False),
    ],
)
def test_is_abbreviated(text, expected):
    assert is_abbreviated(text) is expected
