"""The schemas of check-statements and correct-statements (data-model.md)."""

import pytest
from pydantic import ValidationError

from dataset.schemas.statements import (
    CorrectedStatement,
    CorrectionChecks,
    CorrectionSummary,
    FidelityTotals,
    OriginalEntry,
    OriginalsManifest,
    ProblemFidelity,
    ReviewEntry,
)

SHA = "a" * 64


def entry(pid="1_A", **kw):
    data = dict(
        problem_id=pid,
        url="u",
        fetched_at="t",
        http_status=200,
        page_bytes=1,
        page_sha256=SHA,
        statement_sha256=SHA,
    )
    data.update(kw)
    return OriginalEntry(**data)


def test_an_entry_has_an_error_exactly_when_it_has_no_page():
    entry()
    OriginalEntry(problem_id="1_A", url="u", fetched_at="t", http_status=404, error="http_404")
    with pytest.raises(ValidationError):
        entry(error="http_404")
    with pytest.raises(ValidationError):
        OriginalEntry(problem_id="1_A", url="u", fetched_at="t", http_status=200)


def test_the_problem_ids_are_unique_and_sorted():
    kw = dict(dataset_manifest_sha256=SHA, user_agent="x", min_interval_s=3)
    OriginalsManifest(originals=[entry("1_A"), entry("2_B")], **kw)
    with pytest.raises(ValidationError):
        OriginalsManifest(originals=[entry("1_A"), entry("1_A")], **kw)
    with pytest.raises(ValidationError):
        OriginalsManifest(originals=[entry("2_B"), entry("1_A")], **kw)
    with pytest.raises(ValidationError):
        OriginalsManifest(
            originals=[], dataset_manifest_sha256=SHA, user_agent="x", min_interval_s=1
        )


def test_the_status_of_a_problem_is_coherent():
    ProblemFidelity(problem_id="1_A", format="marked", status="faithful")
    ProblemFidelity(problem_id="1_A", format=None, status="unchecked", unchecked_reason="http_404")
    with pytest.raises(ValidationError):
        ProblemFidelity(problem_id="1_A", format=None, status="unchecked")
    with pytest.raises(ValidationError):
        ProblemFidelity(problem_id="1_A", format="marked", status="losses")


def test_the_totals_add_up():
    zero = {k: 0 for k in ("lost_exponent", "lost_index", "formula", "image", "table", "other")}
    FidelityTotals(
        problems=3, faithful=1, with_losses=1, unchecked=1, by_kind=zero, problems_by_kind=zero
    )
    with pytest.raises(ValidationError):
        FidelityTotals(
            problems=3, faithful=1, with_losses=1, unchecked=0, by_kind=zero, problems_by_kind=zero
        )


def test_a_corrected_statement_passed_the_checks_and_each_problem_is_listed_once():
    ok = CorrectionChecks(text_equal=True, all_marks_present=True, only_markup_diff=True)
    good = CorrectedStatement(
        problem_id="1_A",
        file="1_A.md",
        markups_inserted={},
        checks=ok,
        sha256_before=SHA,
        sha256_after=SHA,
    )
    with pytest.raises(ValidationError):
        CorrectedStatement(
            problem_id="1_A",
            file="1_A.md",
            markups_inserted={},
            checks=ok.model_copy(update={"text_equal": False}),
            sha256_before=SHA,
            sha256_after=SHA,
        )
    CorrectionSummary(report_sha256=SHA, corrected=[good], unchanged=["2_B"], review=[])
    with pytest.raises(ValidationError):
        CorrectionSummary(report_sha256=SHA, corrected=[good], unchanged=["1_A"], review=[])
    with pytest.raises(ValidationError):
        ReviewEntry(problem_id="1_A", reasons=[])
