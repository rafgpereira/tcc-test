"""The gates before any code runs (research R11; FR-002).

1. The known-verdict selfcheck of the engine (the same one that gates the dataset validation).
2. ``cli check --deep`` on the layers the evaluation reads: the dataset, the mutants and the suites
   of every model requested. Any failure: nothing is executed.
"""

from collections.abc import Callable, Iterable
from pathlib import Path

from evaluation import config


def layers_for(sets: Iterable[str]) -> list[str]:
    """The ``cli check`` layers an evaluation of ``sets`` depends on."""
    models = sorted({config.SET_MODEL[s] for s in sets})
    return ["dataset", "mutants"] + [f"{model}_suites" for model in models]


def _real_selfcheck() -> tuple[bool, str]:
    from sandbox.selfcheck import selfcheck

    report = selfcheck()
    return report.ok, report.render()


def _real_checks(root: Path, only: list[str]) -> tuple[bool, str]:
    from cli import consistency

    report = consistency.run_checks(Path(root), only, deep=True)
    return report.ok, report.render()


def run_gates(
    root: Path,
    sets: Iterable[str],
    *,
    selfcheck: Callable[[], tuple[bool, str]] = _real_selfcheck,
    checks: Callable[[Path, list[str]], tuple[bool, str]] = _real_checks,
) -> list[str]:
    """The reasons not to run (empty when every gate passed)."""
    failures = []
    ok, text = selfcheck()
    if not ok:
        failures.append("the engine selfcheck failed:\n" + text)
        return failures  # never judge anything with an engine that gives wrong verdicts
    only = layers_for(sets)
    ok, text = checks(Path(root), only)
    if not ok:
        failures.append(f"`cli check --deep --only {','.join(only)}` failed:\n" + text)
    return failures
