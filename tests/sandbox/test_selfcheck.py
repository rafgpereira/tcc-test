"""Tests for the known-verdict suite that gates `validate` (T041; FR-010a, SC-013).

The report logic is tested with a fake judge (unit); running the nine real programs through the
real engine is an integration test that only runs in the `sandbox` service.
"""

from pathlib import Path

import pytest

from sandbox import selfcheck as sc
from sandbox.types import ExecutionLimits, InfraError, SuiteVerdict, Verdict


def suite(verdict: Verdict, standard: str | None = "gnu++20") -> SuiteVerdict:
    return SuiteVerdict(
        verdict=verdict,
        standard_used=None if verdict is Verdict.CE else standard,
        deciding_index=None if verdict is Verdict.AC else 0,
        tests_run=1,
        max_cpu_time_s=0.0,
        max_memory_bytes=0,
        first_failure=None,
    )


LIMITS = ExecutionLimits(1.0, 256 * 1024 * 1024)
CASES = (
    sc.KnownCase("ok", "ac.cpp", (), LIMITS, Verdict.AC),
    sc.KnownCase("wrong", "wa.cpp", (), LIMITS, Verdict.WA),
)


def fake_judge(mapping):
    def judge(case, slot):
        return mapping[case.name]

    return judge


def test_success_only_when_every_case_gets_its_expected_verdict():
    report = sc.run_cases(
        CASES, fake_judge({"ok": suite(Verdict.AC), "wrong": suite(Verdict.WA)}), repeats=2
    )
    assert report.ok
    assert [c.passed for c in report.cases] == [True, True]


def test_one_wrong_verdict_makes_the_report_fail():
    report = sc.run_cases(
        CASES, fake_judge({"ok": suite(Verdict.AC), "wrong": suite(Verdict.AC)}), repeats=2
    )
    assert not report.ok
    wrong = report.cases[1]
    assert not wrong.passed
    assert wrong.expected is Verdict.WA and wrong.obtained is Verdict.AC


def test_an_unstable_case_fails_even_if_one_run_matches():
    answers = iter([suite(Verdict.AC), suite(Verdict.TLE)])
    report = sc.run_cases(CASES[:1], lambda case, slot: next(answers), repeats=2)
    assert not report.ok
    assert not report.cases[0].stable


def test_the_expected_standard_is_checked_when_given():
    case = sc.KnownCase("fallback", "cascade_fallback.cpp", (), LIMITS, Verdict.AC, "gnu++14")
    good = sc.run_cases((case,), lambda c, s: suite(Verdict.AC, "gnu++14"), repeats=1)
    bad = sc.run_cases((case,), lambda c, s: suite(Verdict.AC, "gnu++20"), repeats=1)
    assert good.ok
    assert not bad.ok
    assert bad.cases[0].standard_used == "gnu++20"


def test_infra_error_from_the_engine_propagates_and_is_not_a_failed_case():
    def broken(case, slot):
        raise InfraError("no compiler")

    with pytest.raises(InfraError):
        sc.run_cases(CASES, broken, repeats=1)


def test_the_report_text_lists_each_case_with_expected_and_obtained_verdict():
    report = sc.run_cases(
        CASES, fake_judge({"ok": suite(Verdict.AC), "wrong": suite(Verdict.AC)}), repeats=1
    )
    text = report.render()
    assert "ok" in text and "wrong" in text
    assert "expected WA" in text and "obtained AC" in text
    assert "FAIL" in text


def test_the_default_suite_covers_every_verdict_and_the_special_cases():
    cases = {c.name: c for c in sc.default_cases()}
    assert {c.expected for c in cases.values()} == set(Verdict)
    for name in ("deep_recursion", "cascade_fallback", "stable"):
        assert name in cases
    assert cases["cascade_fallback"].expected_standard == "gnu++14"
    assert cases["deep_recursion"].expected is Verdict.AC
    for case in cases.values():
        assert (sc.PROGRAMS_DIR / case.program).is_file(), case.program


def test_every_program_of_the_suite_is_a_real_source_file():
    files = {p.name for p in Path(sc.PROGRAMS_DIR).glob("*.cpp")}
    assert files == {c.program for c in sc.default_cases()}


@pytest.mark.integration
def test_the_real_suite_passes_on_the_real_engine():
    report = sc.selfcheck()
    assert report.ok, report.render()
    assert len(report.cases) == len(sc.default_cases())
    fallback = next(c for c in report.cases if c.name == "cascade_fallback")
    assert fallback.standard_used == "gnu++14"
