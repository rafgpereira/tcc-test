"""The schemas refuse a result that contradicts itself (data-model.md; T004)."""

import pytest
from pydantic import ValidationError

from evaluation.schemas.result import (
    NOT_DETECTED,
    AcResult,
    AcTest,
    CombinationResult,
    Detection,
    RunOutcome,
    SuiteSource,
    TargetResult,
    detected_sets,
)
from evaluation.schemas.run import RunConfig

SHA = "a" * 64


def ac_test(index=0, verdict="passed", **extra):
    fields = dict(
        index=index,
        verdict=verdict,
        error_kind=None,
        actual_output="2\n",
        cpu_time_s=0.0,
        peak_memory_bytes=0,
        unstable=False,
        runs=None,
    )
    fields.update(extra)
    return AcTest(**fields)


def target(name="WA_1", kind="wa", declared=NOT_DETECTED, corrected=NOT_DETECTED, compiled=True):
    return TargetResult(
        target=name,
        kind=kind,
        compiled=compiled,
        declared=declared,
        corrected=corrected,
        tests_run=1 if compiled else 0,
        unstable_tests=[],
    )


def combination(**extra):
    targets = [target("WA_1"), target("Mutant_1", "mutant")]
    fields = dict(
        set="gpt",
        model="gpt",
        problem_id="1_A",
        scenario="black_box",
        suite_source=SuiteSource(status="accepted", tree="suites/gpt", suite_sha256=SHA),
        has_suite=True,
        no_suite_reason=None,
        suite_size=1,
        ac=AcResult(approved=True, standard_used="gnu++20", tests=[ac_test()]),
        corrected_oracle_tests=1,
        corrected_oracle_excluded=0,
        targets=targets,
        detected=detected_sets(targets),
        elapsed_s=0.0,
    )
    fields.update(extra)
    return CombinationResult(**fields)


def test_a_coherent_result_is_accepted():
    assert combination().ac.approved


def test_without_a_suite_there_is_no_ac_nor_targets():
    with pytest.raises(ValidationError):
        combination(has_suite=False, no_suite_reason="discarded_manual")
    no_suite = combination(
        has_suite=False,
        no_suite_reason="discarded_manual",
        suite_size=0,
        ac=None,
        corrected_oracle_tests=0,
        targets=[],
        detected=detected_sets([]),
    )
    assert no_suite.no_suite_reason == "discarded_manual"


def test_no_suite_reason_is_required_without_a_suite():
    with pytest.raises(ValidationError):
        combination(has_suite=False, no_suite_reason=None, suite_size=0, ac=None, targets=[])


def test_approved_if_and_only_if_every_test_passed():
    with pytest.raises(ValidationError):
        AcResult(approved=True, standard_used="x", tests=[ac_test(verdict="wrong_output")])


def test_error_kind_if_and_only_if_runtime_error():
    with pytest.raises(ValidationError):
        ac_test(verdict="runtime_error", actual_output="")
    with pytest.raises(ValidationError):
        ac_test(error_kind="TLE")
    with pytest.raises(ValidationError):  # an error has no output
        ac_test(verdict="runtime_error", error_kind="TLE")
    runs = [RunOutcome(verdict="TLE", cpu_time_s=1, peak_memory_bytes=0)] * 2
    with pytest.raises(ValidationError):  # repeated: exactly 3 runs
        ac_test(unstable=True, runs=runs)


def test_detection_has_index_and_verdict_if_and_only_if_detected():
    with pytest.raises(ValidationError):
        Detection(detected=True)
    with pytest.raises(ValidationError):
        Detection(detected=False, test_index=0, verdict="TLE")


def test_detected_sets_must_match_the_targets():
    found = Detection(detected=True, test_index=0, verdict="wrong_output")
    targets = [target("WA_1", declared=found), target("Mutant_1", "mutant")]
    with pytest.raises(ValidationError):
        combination(targets=targets)  # `detected` still says nothing was detected
    assert combination(targets=targets, detected=detected_sets(targets)).detected.declared_wa == [
        "WA_1"
    ]


def test_corrected_oracle_counts_follow_the_ac():
    error = ac_test(verdict="runtime_error", error_kind="TLE", actual_output="")
    ac = AcResult(approved=False, standard_used="x", tests=[error])
    with pytest.raises(ValidationError):
        combination(ac=ac)  # corrected_oracle_tests must be 0
    assert combination(ac=ac, corrected_oracle_tests=0, corrected_oracle_excluded=1)


def test_targets_are_ordered_and_numbered_without_a_gap():
    with pytest.raises(ValidationError):
        targets = [target("WA_2"), target("Mutant_1", "mutant")]
        combination(targets=targets, detected=detected_sets(targets))
    with pytest.raises(ValidationError):
        targets = [target("Mutant_1", "mutant"), target("WA_1")]
        combination(targets=targets, detected=detected_sets(targets))


def test_unknown_fields_are_errors():
    with pytest.raises(ValidationError):
        combination(extra_field=1)


def test_run_config_attempt_only_in_the_attempt_set():
    fields = dict(
        dataset_manifest_sha256=SHA,
        dataset_revision=2,
        mutants_manifest_sha256=SHA,
        suites_manifest_sha256=SHA,
        gcc_version="13.2.0",
        created_at="2026-11-04T00:00:00Z",
    )
    assert RunConfig(set="slm-attempt1", model="slm", attempt=1, **fields)
    with pytest.raises(ValidationError):
        RunConfig(set="gpt", model="gpt", attempt=1, **fields)
    with pytest.raises(ValidationError):
        RunConfig(set="gpt", model="slm", attempt=None, **fields)
    a = RunConfig(set="gpt", model="gpt", attempt=None, **fields)
    b = a.model_copy(update={"gcc_version": "14", "created_at": "later"})
    assert a.differences(b) == ["gcc_version"]
