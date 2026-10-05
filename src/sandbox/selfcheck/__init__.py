"""Known-verdict suite that gates ``validate`` (FR-010a)."""

from sandbox.selfcheck.selfcheck import (
    PROGRAMS_DIR,
    REPEATS,
    CaseResult,
    KnownCase,
    SelfCheckReport,
    default_cases,
    engine_judge,
    run_cases,
    selfcheck,
)

__all__ = [
    "PROGRAMS_DIR",
    "REPEATS",
    "CaseResult",
    "KnownCase",
    "SelfCheckReport",
    "default_cases",
    "engine_judge",
    "run_cases",
    "selfcheck",
]
