"""Tests for `Validacao` and its parts: every invariant of data-model.md section 1.3 (T054)."""

import json

import pytest
from pydantic import ValidationError

from dataset.schemas.validacao import (
    MAX_TEXT_BYTES,
    CodeValidation,
    Divergence,
    EngineInfo,
    TriageRecord,
    Validacao,
    WaValidation,
    truncate_text,
)
from sandbox.types import Verdict

ENGINE = {
    "gcc_version": "13.2.0",
    "flags": ["-Wall", "-Wextra", "-Wconversion", "-static", "-DONLINE_JUDGE", "-O2"],
    "standard_cascade": ["gnu++20", "gnu++17", "gnu++14", "gnu++11"],
    "stack_limit_bytes": 268435456,
    "time_limit_seconds": 2.0,
    "memory_limit_bytes": 256_000_000,
    "stability_runs": 2,
}


def sha(i: int) -> str:
    return f"{i:064x}"


def ac(**changes) -> dict:
    base = {
        "file": "AC_ref.cpp",
        "sha256": sha(0),
        "verdict": "AC",
        "standard_used": "gnu++20",
        "max_cpu_time_s": 0.21,
        "max_memory_bytes": 3145728,
        "tests_run": 214,
    }
    return {**base, **changes}


def wa(i: int, **changes) -> dict:
    base = {
        "file": f"WA_{i + 1}.cpp",
        "sha256": sha(i + 1),
        "verdict": "WA",
        "standard_used": "gnu++17",
        "max_cpu_time_s": 0.02,
        "max_memory_bytes": 2621440,
        "tests_run": 3,
        "source_index": 41 + i,
        "deciding_test": {"group": "private_tests", "index": 0},
        "stable": True,
    }
    return {**base, **changes}


def triage(**changes) -> dict:
    base = {
        "problem_id": "1234_C",
        "stage": "selection",
        "verdict": "WA",
        "reason": "AC diverged from the official answer on public_tests[1]",
        "divergence": {
            "group": "public_tests",
            "index": 1,
            "input": "3\n1 2 3\n",
            "expected": "YES\n",
            "actual": "NO\n",
            "truncated": False,
            "format_only": False,
        },
        "engine_diagnostic": None,
    }
    return {**base, **changes}


def complete(**changes) -> dict:
    base = {
        "schema_version": 1,
        "problem_id": "1234_C",
        "status": "complete",
        "engine": ENGINE,
        "ac_ref": ac(),
        "wa": [wa(i) for i in range(100)],
        "discard_reason": None,
        "triage": None,
    }
    return {**base, **changes}


def pending(**changes) -> dict:
    base = complete(
        status="pending_triage",
        ac_ref=ac(file="AC_candidate.cpp", verdict="WA"),
        wa=[],
        triage=triage(),
    )
    return {**base, **changes}


def discarded(**changes) -> dict:
    base = complete(status="discarded", wa=[], discard_reason="insufficient_wa")
    return {**base, **changes}


def test_a_complete_problem_is_accepted():
    model = Validacao.model_validate(complete())
    assert model.status == "complete" and len(model.wa) == 100


def test_a_pending_triage_problem_is_accepted():
    assert Validacao.model_validate(pending()).triage is not None


def test_a_discarded_problem_is_accepted():
    assert Validacao.model_validate(discarded()).discard_reason == "insufficient_wa"


@pytest.mark.parametrize("status", ["done", "COMPLETE", "", "triage"])
def test_status_must_be_one_of_the_three_values(status):
    with pytest.raises(ValidationError):
        Validacao.model_validate(complete(status=status))


@pytest.mark.parametrize("count", [0, 1, 99, 101])
def test_a_complete_problem_has_exactly_100_wa(count):
    with pytest.raises(ValidationError):
        Validacao.model_validate(complete(wa=[wa(i) for i in range(count)]))


def test_wa_must_be_empty_unless_the_problem_is_complete():
    with pytest.raises(ValidationError):
        Validacao.model_validate(pending(wa=[wa(0)]))
    with pytest.raises(ValidationError):
        Validacao.model_validate(discarded(wa=[wa(0)]))


@pytest.mark.parametrize("reason", ["insufficient_wa", "insufficient_raw_wa"])
def test_discard_reason_is_required_when_discarded(reason):
    assert Validacao.model_validate(discarded(discard_reason=reason))
    with pytest.raises(ValidationError):
        Validacao.model_validate(discarded(discard_reason=None))


def test_discard_reason_only_accepts_the_two_known_reasons():
    with pytest.raises(ValidationError):
        Validacao.model_validate(discarded(discard_reason="whatever"))


def test_discard_reason_is_forbidden_unless_discarded():
    with pytest.raises(ValidationError):
        Validacao.model_validate(complete(discard_reason="insufficient_wa"))


def test_triage_is_required_when_pending_and_forbidden_otherwise():
    with pytest.raises(ValidationError):
        Validacao.model_validate(pending(triage=None))
    with pytest.raises(ValidationError):
        Validacao.model_validate(complete(triage=triage()))
    with pytest.raises(ValidationError):
        Validacao.model_validate(discarded(triage=triage()))


def test_complete_requires_the_reference_solution_to_be_ac():
    with pytest.raises(ValidationError, match="AC"):
        Validacao.model_validate(complete(ac_ref=ac(verdict="WA")))
    with pytest.raises(ValidationError):
        Validacao.model_validate(complete(ac_ref=None))


@pytest.mark.parametrize("verdict", ["AC", "TLE", "MLE", "RE", "CE"])
def test_complete_requires_every_wa_to_have_the_verdict_wa(verdict):
    wrong = [wa(i) for i in range(100)]
    wrong[57] = wa(57, verdict=verdict)
    with pytest.raises(ValidationError):
        Validacao.model_validate(complete(wa=wrong))


def test_the_100_sha256_must_be_distinct():
    dup = [wa(i) for i in range(100)]
    dup[10] = wa(10, sha256=sha(1))  # same as WA_1
    with pytest.raises(ValidationError, match="distinct"):
        Validacao.model_validate(complete(wa=dup))


def test_wa_files_are_named_in_sequence_from_one():
    wrong = [wa(i) for i in range(100)]
    wrong[3] = wa(3, file="WA_9.cpp")
    with pytest.raises(ValidationError, match="WA_4.cpp"):
        Validacao.model_validate(complete(wa=wrong))


def test_a_retained_wa_must_be_stable():
    wrong = [wa(i) for i in range(100)]
    wrong[0] = wa(0, stable=False)
    with pytest.raises(ValidationError):
        Validacao.model_validate(complete(wa=wrong))


def test_the_triage_problem_id_must_match_the_problem():
    with pytest.raises(ValidationError, match="problem_id"):
        Validacao.model_validate(pending(triage=triage(problem_id="9999_Z")))


def test_the_verdict_is_the_engine_enum_and_infra_does_not_exist():
    assert CodeValidation.model_validate(ac(verdict="CE")).verdict is Verdict.CE
    with pytest.raises(ValidationError):
        CodeValidation.model_validate(ac(verdict="INFRA"))


def test_engine_info_records_the_exact_configuration():
    info = EngineInfo.model_validate(ENGINE)
    assert info.stack_limit_bytes == 268435456
    assert "-std=gnu++20" not in info.flags and info.stability_runs == 2


@pytest.mark.parametrize("flag", ["-std=gnu++20", "-std=c++17"])
def test_engine_flags_must_not_carry_the_standard(flag):
    with pytest.raises(ValidationError):
        EngineInfo.model_validate({**ENGINE, "flags": [*ENGINE["flags"], flag]})


def test_triage_record_has_the_fields_of_fr_011b():
    record = TriageRecord.model_validate(triage())
    assert record.stage == "selection" and record.verdict == "WA"
    assert record.divergence is not None and record.divergence.format_only is False
    assert set(record.model_dump()) == {
        "problem_id",
        "stage",
        "verdict",
        "reason",
        "divergence",
        "engine_diagnostic",
    }


@pytest.mark.parametrize("verdict", ["WA", "TLE", "MLE", "RE", "CE", "AUDIT_MISMATCH"])
def test_triage_verdict_is_a_verdict_or_audit_mismatch(verdict):
    assert TriageRecord.model_validate(triage(verdict=verdict))


@pytest.mark.parametrize("bad", ["AC", "INFRA", "OK"])
def test_triage_verdict_rejects_anything_else(bad):
    with pytest.raises(ValidationError):
        TriageRecord.model_validate(triage(verdict=bad))


def test_triage_stage_is_selection_or_audit():
    assert TriageRecord.model_validate(triage(stage="audit"))
    with pytest.raises(ValidationError):
        TriageRecord.model_validate(triage(stage="later"))


def test_a_compile_failure_has_no_divergence_but_a_diagnostic():
    record = TriageRecord.model_validate(
        triage(verdict="CE", divergence=None, engine_diagnostic="gnu++20: error")
    )
    assert record.divergence is None and record.engine_diagnostic


def test_the_triage_record_has_no_timestamp():
    with pytest.raises(ValidationError):
        TriageRecord.model_validate(triage(timestamp="2026-09-21T00:00:00Z"))


def test_long_text_is_truncated_at_64_kib_and_flagged():
    long = "x" * (MAX_TEXT_BYTES + 500)
    text, truncated = truncate_text(long)
    assert len(text.encode()) <= MAX_TEXT_BYTES and truncated
    short, flag = truncate_text("ok")
    assert short == "ok" and not flag


def test_truncation_never_splits_a_multibyte_character():
    text, truncated = truncate_text("é" * (MAX_TEXT_BYTES // 2 + 10))
    assert truncated and text.encode().decode("utf-8") == text
    assert len(text.encode()) <= MAX_TEXT_BYTES


def test_divergence_build_truncates_each_field_and_sets_the_flag():
    long = "y" * (MAX_TEXT_BYTES * 2)
    div = Divergence.build("public_tests", 0, input_="in", expected="out", actual=long)
    assert div.truncated and len(div.actual.encode()) <= MAX_TEXT_BYTES
    assert div.input == "in" and div.expected == "out"


def test_divergence_build_computes_format_only_from_the_tokens():
    same_tokens = Divergence.build(
        "public_tests", 0, input_="", expected="1 2\n", actual="1  2\n\n"
    )
    different = Divergence.build("public_tests", 0, input_="", expected="1 2\n", actual="1 3\n")
    assert same_tokens.format_only is True
    assert different.format_only is False


def test_untruncated_oversized_text_is_rejected_by_the_schema():
    with pytest.raises(ValidationError, match="64 KiB"):
        Divergence.model_validate(
            {
                "group": "public_tests",
                "index": 0,
                "input": "",
                "expected": "",
                "actual": "z" * (MAX_TEXT_BYTES + 1),
                "truncated": False,
                "format_only": False,
            }
        )


def test_wa_validation_extends_the_code_validation():
    model = WaValidation.model_validate(wa(0))
    assert model.source_index == 41 and model.deciding_test.group == "private_tests"


def test_the_problem_id_must_equal_the_folder_name(tmp_path):
    folder = tmp_path / "9999_Z"
    folder.mkdir()
    (folder / "validacao.json").write_text(json.dumps(complete()))
    with pytest.raises(ValueError, match="folder"):
        Validacao.from_folder(folder)
