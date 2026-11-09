"""The gate before computing (FR-002): consistency with hashes, and complete evaluations."""

import json
from collections.abc import Callable
from pathlib import Path

from metrics import config

LAYERS = [
    "dataset",
    "slm_suites",
    "gpt_suites",
    "gemini_suites",
    "claude_suites",
    *("evaluation_" + s.replace("-", "_") for s in config.SETS),
]


def _real_checks(root: Path, only: list[str]) -> tuple[bool, str]:
    from cli import consistency

    report = consistency.run_checks(Path(root), only, deep=True)
    return report.ok, report.render()


def run_gate(
    root: Path, *, checks: Callable[[Path, list[str]], tuple[bool, str]] = _real_checks
) -> list[str]:
    """The reasons not to compute (empty when everything is in place)."""
    failures = []
    for set_name in config.SETS:
        path = Path(root) / config.evaluation_report(set_name)
        try:
            complete = json.loads(path.read_text(encoding="utf-8"))["complete"]
        except (OSError, ValueError, KeyError):
            complete = False
        if not complete:
            failures.append(f"the evaluation of {set_name} is not complete ({path})")
    if failures:
        return failures
    ok, text = checks(Path(root), LAYERS)
    if not ok:
        failures.append("`cli check --deep` failed:\n" + text)
    return failures
