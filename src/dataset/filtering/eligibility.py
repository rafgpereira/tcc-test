"""Eligibility of a problem (spec FR-004 and FR-005; methodology section 1.2).

``evaluate`` never short-circuits: it returns EVERY reason a row fails, so the decision is auditable.
"""

from collections.abc import Mapping
from typing import Any

from dataset import config
from dataset.schemas.pool import RejectionReason as R


def count_cpp(solutions: Mapping[str, Any] | None) -> int:
    """Number of C++ submissions in a ``solutions``/``incorrect_solutions`` field."""
    languages = (solutions or {}).get("language") or []
    return sum(1 for language in languages if language == config.HF_LANGUAGE_CPP)


def evaluate(row: Mapping[str, Any]) -> list[R]:
    """Return the rejection reasons of ``row``; an empty list means it is eligible."""
    reasons: list[R] = []

    if row.get("source") != config.HF_SOURCE_CODEFORCES:
        reasons.append(R.NOT_CODEFORCES)

    rating = row.get("cf_rating")
    if not rating or not config.RATING_MIN <= rating <= config.RATING_MAX:
        reasons.append(R.RATING_OUT_OF_RANGE)

    tags = set(row.get("cf_tags") or [])
    if not tags & config.ALLOWED_TAGS:
        reasons.append(R.NO_ALLOWED_TAG)
    if tags & config.FORBIDDEN_TAGS:
        reasons.append(R.FORBIDDEN_TAG)

    statement = (row.get("description") or "").lower()
    if any(term in statement for term in config.VISUAL_TERMS):
        reasons.append(R.VISUAL_DEPENDENCY)

    if row.get("is_description_translated"):
        reasons.append(R.TRANSLATED)

    if row.get("input_file") or row.get("output_file"):
        reasons.append(R.FILE_IO)

    correct = count_cpp(row.get("solutions"))
    incorrect = count_cpp(row.get("incorrect_solutions"))
    if correct == 0:
        reasons.append(R.NO_CPP_CORRECT)
    if incorrect == 0:
        reasons.append(R.NO_CPP_INCORRECT)
    elif incorrect < config.WA_PER_PROBLEM:
        reasons.append(R.INSUFFICIENT_RAW_WA)

    return reasons
