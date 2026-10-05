"""Tests for the ordered official suite and where a test lives (T064 support; FR-012)."""

from dataset.schemas.testes import Testes
from dataset.validation.suite import suite_from_raw, suite_from_testes


def test_the_suite_runs_public_then_private_then_generated(make_raw):
    raw = make_raw(n_tests=(2, 1, 3))
    suite = suite_from_raw(raw)
    assert len(suite.tests) == 6
    assert [loc for loc in suite.locations] == [
        ("public_tests", 0),
        ("public_tests", 1),
        ("private_tests", 0),
        ("generated_tests", 0),
        ("generated_tests", 1),
        ("generated_tests", 2),
    ]


def test_each_test_keeps_its_input_and_expected_output(make_raw):
    suite = suite_from_raw(make_raw(n_tests=(1, 1, 1)))
    assert suite.tests[0].input == "0\n" and suite.tests[0].output == "0\n"


def test_location_of_a_deciding_index(make_raw):
    suite = suite_from_raw(make_raw(n_tests=(1, 1, 2)))
    assert suite.location(0) == ("public_tests", 0)
    assert suite.location(3) == ("generated_tests", 1)


def test_the_suite_from_testes_json_is_the_same_as_from_the_raw_problem(make_raw):
    raw = make_raw(n_tests=(2, 0, 2))
    testes = Testes.from_parallel_lists(
        raw.problem_id,
        public=(raw.public_tests.input, raw.public_tests.output),
        private=(raw.private_tests.input, raw.private_tests.output),
        generated=(raw.generated_tests.input, raw.generated_tests.output),
    )
    assert suite_from_testes(testes) == suite_from_raw(raw)
