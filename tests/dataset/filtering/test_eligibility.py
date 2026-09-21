"""Tests for the eligibility criteria FR-004(a)-(h) and the rejection reasons FR-005 (T022)."""

import pytest

from dataset.filtering.eligibility import evaluate
from dataset.schemas.pool import RejectionReason as R


def test_an_eligible_problem_has_no_rejection_reason(row_factory):
    assert evaluate(row_factory()) == []


def test_rating_boundaries_are_inclusive(row_factory):
    assert evaluate(row_factory(cf_rating=1000)) == []
    assert evaluate(row_factory(cf_rating=1600)) == []
    assert evaluate(row_factory(cf_rating=999)) == [R.RATING_OUT_OF_RANGE]
    assert evaluate(row_factory(cf_rating=1601)) == [R.RATING_OUT_OF_RANGE]


@pytest.mark.parametrize("rating", [0, None])
def test_a_missing_rating_is_rejected(row_factory, rating):
    assert evaluate(row_factory(cf_rating=rating)) == [R.RATING_OUT_OF_RANGE]


def test_only_codeforces_is_accepted(row_factory):
    assert evaluate(row_factory(source=1)) == [R.NOT_CODEFORCES]  # CODECHEF


def test_a_problem_without_an_allowed_tag_is_rejected(row_factory):
    assert evaluate(row_factory(cf_tags=["number theory"])) == [R.NO_ALLOWED_TAG]
    assert evaluate(row_factory(cf_tags=[])) == [R.NO_ALLOWED_TAG]


def test_a_forbidden_tag_prevails_over_an_allowed_one(row_factory):
    reasons = evaluate(row_factory(cf_tags=["dp", "constructive algorithms"]))
    assert reasons == [R.FORBIDDEN_TAG]


@pytest.mark.parametrize("tag", ["geometry", "interactive", "games", "probabilities"])
def test_each_forbidden_tag_rejects(row_factory, tag):
    assert evaluate(row_factory(cf_tags=["math", tag])) == [R.FORBIDDEN_TAG]


@pytest.mark.parametrize(
    "term", ["figure", "image", "picture", "shown below", "as follows", "http", ".png", ".jpg"]
)
def test_each_visual_term_rejects_in_any_case(row_factory, term):
    for text in (term, term.upper(), term.title()):
        row = row_factory(description=f"See the {text} for details.")
        assert evaluate(row) == [R.VISUAL_DEPENDENCY], text


def test_a_translated_statement_is_rejected(row_factory):
    assert evaluate(row_factory(is_description_translated=True)) == [R.TRANSLATED]


def test_a_problem_without_a_cpp_correct_solution_is_rejected(row_factory):
    assert evaluate(row_factory(cpp_ac=0)) == [R.NO_CPP_CORRECT]


def test_a_problem_without_cpp_incorrect_submissions_is_rejected(row_factory):
    assert evaluate(row_factory(cpp_wa=0)) == [R.NO_CPP_INCORRECT]


def test_file_input_or_output_is_rejected(row_factory):
    both = row_factory(input_file="input.txt", output_file="output.txt")
    assert evaluate(both) == [R.FILE_IO]
    assert evaluate(row_factory(input_file="input.txt")) == [R.FILE_IO]
    assert evaluate(row_factory(output_file="output.txt")) == [R.FILE_IO]


def test_fewer_than_100_raw_cpp_incorrect_submissions_are_rejected(row_factory):
    assert evaluate(row_factory(cpp_wa=99)) == [R.INSUFFICIENT_RAW_WA]
    assert evaluate(row_factory(cpp_wa=100)) == []
    assert evaluate(row_factory(cpp_wa=250)) == []


def test_only_cpp_solutions_are_counted(row_factory):
    """Python submissions do not count toward the 100 raw C++ incorrect ones."""
    row = row_factory(cpp_wa=99)
    row["incorrect_solutions"]["language"] += [3] * 50
    row["incorrect_solutions"]["solution"] += ["print(1)"] * 50
    assert evaluate(row) == [R.INSUFFICIENT_RAW_WA]


def test_a_problem_failing_several_criteria_gets_every_reason(row_factory):
    """FR-005: the decision is auditable, so the evaluation never short-circuits."""
    row = row_factory(
        source=1,
        cf_rating=900,
        cf_tags=["geometry"],
        description="An image is shown below.",
        is_description_translated=True,
        input_file="input.txt",
        cpp_ac=0,
        cpp_wa=10,
    )
    assert set(evaluate(row)) == {
        R.NOT_CODEFORCES,
        R.RATING_OUT_OF_RANGE,
        R.NO_ALLOWED_TAG,
        R.FORBIDDEN_TAG,
        R.VISUAL_DEPENDENCY,
        R.TRANSLATED,
        R.FILE_IO,
        R.NO_CPP_CORRECT,
        R.INSUFFICIENT_RAW_WA,
    }


def test_missing_optional_fields_do_not_crash(row_factory):
    row = row_factory()
    for key in ("solutions", "incorrect_solutions", "cf_tags", "description"):
        row[key] = None
    reasons = evaluate(row)
    assert R.NO_CPP_CORRECT in reasons and R.NO_CPP_INCORRECT in reasons
    assert R.NO_ALLOWED_TAG in reasons
