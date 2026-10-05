"""Tests for the generation report (spec FR-013; contracts/file-formats.md)."""

import json

import pytest
from pydantic import ValidationError

import mutation.__main__ as cli
from mutation import config, report
from mutation.dataset_gate import DatasetMismatchError
from mutation.schemas.report import MutationReport
from mutation.types import DiscardReason, MutationOperator


@pytest.fixture()
def repo(tmp_path, dataset_builder, write_problem, monkeypatch):
    dataset_builder(tmp_path, {pid: {"AC_ref.cpp": pid} for pid in ("1_A", "2_A", "3_A")})
    monkeypatch.chdir(tmp_path)
    write_problem(tmp_path, "1_A")
    write_problem(tmp_path, "2_A")
    write_problem(tmp_path, "3_A", excluded=True)
    return tmp_path


def built(repo):
    return report.build_report(repo)


def test_the_funnel_sums_the_discards_of_every_problem_including_excluded_ones(repo):
    funnel = built(repo).funnel
    assert funnel[DiscardReason.COMPILE_ERROR] == 2  # one per complete problem
    assert all(funnel[r] == 0 for r in DiscardReason if r is not DiscardReason.COMPILE_ERROR)


def test_every_reason_order_and_operator_is_present_even_when_zero(repo):
    result = built(repo)
    assert set(result.funnel) == set(DiscardReason)
    assert set(result.order_distribution) == {1, 2, 3}
    assert set(result.operator_distribution) == set(MutationOperator)


def test_the_distributions_count_mutants_by_order_and_by_operator_use(repo):
    result = built(repo)
    assert result.order_distribution == {1: 180, 2: 20, 3: 0}  # 90 + 10 per complete problem
    # a first-order mutant uses one ROR, a second-order one uses two
    assert result.operator_distribution[MutationOperator.ROR] == 180 + 2 * 20
    assert result.operator_distribution[MutationOperator.UOI] == 0


def test_the_problem_counts_split_first_order_only_from_higher_order(repo):
    counts = built(repo).problems
    assert (counts.closed, counts.complete, counts.excluded) == (3, 2, 1)
    assert (counts.first_order_only, counts.higher_order) == (0, 2)


def test_the_exclusion_alerts_list_the_excluded_problems(repo):
    (alert,) = built(repo).exclusion_alerts
    assert (alert.problem_id, alert.mutants_reached, alert.highest_order_attempted) == ("3_A", 5, 3)


def test_exclusion_alerts_is_an_empty_list_never_omitted_when_there_is_none(
    tmp_path, dataset_builder, write_problem
):
    dataset_builder(tmp_path, {"1_A": {"AC_ref.cpp": "a"}})
    write_problem(tmp_path, "1_A")
    data = json.loads(built(tmp_path).model_dump_json())
    assert data["exclusion_alerts"] == []


def test_the_report_carries_the_dataset_manifest_hash(repo):
    from mutation import dataset_gate

    result = built(repo)
    assert result.dataset_manifest_sha256 == dataset_gate.dataset_manifest_sha256(repo)


def test_a_dataset_that_differs_from_its_manifest_is_refused(repo):
    (repo / "data" / "dataset" / "problems" / "1_A" / "AC_ref.cpp").write_text("tampered")
    with pytest.raises(DatasetMismatchError):
        built(repo)


def test_an_empty_run_gives_a_valid_report_of_zeros(tmp_path, dataset_builder):
    dataset_builder(tmp_path, {"1_A": {"AC_ref.cpp": "a"}})
    result = built(tmp_path)
    assert result.problems.closed == 0 and sum(result.funnel.values()) == 0


def test_the_report_is_idempotent_byte_for_byte_with_no_timestamp(repo):
    first = report.write_report(repo, built(repo)).read_bytes()
    second = report.write_report(repo, built(repo)).read_bytes()
    assert first == second and b"timestamp" not in first and first.endswith(b"}\n")


def test_the_written_file_has_the_documented_keys_and_lowercase_reasons(repo):
    data = json.loads(report.write_report(repo, built(repo)).read_text())
    assert set(data) == {
        "schema_version",
        "problems",
        "funnel",
        "order_distribution",
        "operator_distribution",
        "exclusion_alerts",
        "dataset_manifest_sha256",
    }
    assert data["schema_version"] == 1 and set(data["funnel"]) == {r.value for r in DiscardReason}
    assert set(data["order_distribution"]) == {"1", "2", "3"}
    assert MutationReport.model_validate(data)  # what is written can be read back


def test_the_report_only_reflects_the_generation_records_so_it_works_on_partial_runs(repo):
    import shutil

    shutil.rmtree(repo / config.PROBLEMS_DIR / "2_A")
    assert built(repo).problems.closed == 2


# ------------------------------------------------------------------ the schema itself


@pytest.fixture()
def payload(repo):
    """The JSON of a valid report, as a function that applies overrides on top of it."""

    def make(**overrides):
        base = json.loads(built(repo).model_dump_json())
        base.update(overrides)
        return base

    return make


class TestSchema:
    def test_schema_version_must_be_one(self, payload):
        with pytest.raises(ValidationError):
            MutationReport.model_validate(payload(schema_version=2))

    def test_a_missing_funnel_reason_is_an_error(self, payload):
        funnel = payload()["funnel"]
        del funnel["tle"]
        with pytest.raises(ValidationError, match="funnel"):
            MutationReport.model_validate(payload(funnel=funnel))

    def test_an_unknown_operator_is_an_error(self, payload):
        ops = payload()["operator_distribution"]
        ops["XYZ"] = 1
        with pytest.raises(ValidationError):
            MutationReport.model_validate(payload(operator_distribution=ops))

    def test_a_code_revision_field_is_not_part_of_the_report(self, payload):
        with pytest.raises(ValidationError):
            MutationReport.model_validate(payload(code_revision="0" * 40))

    def test_the_dataset_hash_must_be_sha256(self, payload):
        with pytest.raises(ValidationError):
            MutationReport.model_validate(payload(dataset_manifest_sha256="xyz"))

    def test_alerts_must_match_the_excluded_problems_and_be_ordered(self, payload):
        with pytest.raises(ValidationError, match="one exclusion alert"):
            MutationReport.model_validate(payload(exclusion_alerts=[]))

    def test_negative_counts_are_errors(self, payload):
        funnel = payload()["funnel"]
        funnel["tle"] = -1
        with pytest.raises(ValidationError, match="negative"):
            MutationReport.model_validate(payload(funnel=funnel))

    def test_problem_counts_must_add_up(self, payload):
        counts = payload()["problems"]
        counts["complete"] = 5
        with pytest.raises(ValidationError):
            MutationReport.model_validate(payload(problems=counts))


# ------------------------------------------------------------------ the command


def test_the_report_command_writes_the_file(repo, capsys):
    assert cli.main(["report"]) == 0
    assert "report:" in capsys.readouterr().out
    assert (repo / config.REPORT_PATH).is_file()


def test_the_report_command_refuses_a_dataset_that_differs(repo, capsys):
    (repo / "data" / "dataset" / "problems" / "1_A" / "AC_ref.cpp").write_text("tampered")
    assert cli.main(["report"]) == cli.EXIT_DATA_FAILURE
    assert "manifest" in capsys.readouterr().err
