"""Tests for the choice and the validation of `AC_ref` (T056; FR-011, FR-011b, D8, D13)."""

import pytest

from dataset.persistence import store
from dataset.validation import ac
from dataset.validation.suite import suite_from_raw
from sandbox.types import ExecutionLimits, InfraError, Verdict

LIMITS = ExecutionLimits(time_limit_seconds=2.0, memory_limit_bytes=256_000_000)


@pytest.fixture()
def run(fake, make_raw):
    def _run(source, raw=None, stage="selection"):
        raw = raw or make_raw(ac=(source,))
        return ac.run_ac(
            raw.problem_id,
            source,
            suite_from_raw(raw),
            LIMITS,
            fake.as_engine(),
            slot=9,
            stage=stage,
            file_name=ac.AC_REF_FILE,
        )

    return _run


def test_ac_ref_is_the_first_correct_cpp_solution_in_the_original_order(make_raw):
    raw = make_raw(ac=("// AC\nfirst", "// AC\nsecond", "// AC\nthird"))
    assert ac.choose_ac_source(raw) == "// AC\nfirst"


def test_the_chosen_source_is_normalized_like_the_persisted_file(make_raw):
    raw = make_raw(ac=("// AC\r\nint main(){}\r\n",))
    assert ac.choose_ac_source(raw) == store.normalize_text("// AC\r\nint main(){}\r\n")
    assert "\r" not in ac.choose_ac_source(raw)


def test_a_problem_without_a_correct_solution_is_an_error_not_a_silent_skip(make_raw):
    with pytest.raises(ValueError, match="no correct"):
        ac.choose_ac_source(make_raw(ac=()))


def test_an_ac_that_passes_the_whole_suite_is_accepted(fake, run):
    outcome = run("// AC\nok")
    assert outcome.passed and outcome.triage is None
    assert outcome.code.verdict is Verdict.AC
    assert outcome.code.file == "AC_ref.cpp"
    assert outcome.code.tests_run == 4  # 1 public + 1 private + 2 generated
    assert outcome.code.standard_used == "gnu++20"


def test_the_sha256_is_of_the_persisted_source():
    import hashlib

    assert ac.sha256_of("abc") == hashlib.sha256(b"abc").hexdigest()


def test_an_ac_with_a_divergent_output_is_recorded_for_triage(fake, run, make_raw):
    """T056: 'AC divergente é registrado em validacao.json e interrompe o problema'."""
    raw = make_raw(ac=("// WA@1\nx",))  # diverges on the second test in suite order
    outcome = run("// WA@1\nx", raw)
    assert not outcome.passed
    triage = outcome.triage
    assert triage.problem_id == raw.problem_id
    assert triage.stage == "selection" and triage.verdict == "WA"
    assert "private_tests[0]" in triage.reason and "WA" in triage.reason
    assert "selection" in triage.reason  # FR-011b: verdict AND stage in the reason
    div = triage.divergence
    assert (div.group, div.index) == ("private_tests", 0)
    assert div.expected == "0\n" and div.actual == "WRONG\n" and div.input == "0\n"
    assert outcome.code.file == "AC_ref.cpp" and outcome.code.verdict is Verdict.WA


def test_the_group_and_index_are_relative_to_the_group_not_the_suite(fake, run, make_raw):
    raw = make_raw(ac=("// WA@3\nx",))  # 4th test = generated_tests[1]
    triage = run("// WA@3\nx", raw).triage
    assert (triage.divergence.group, triage.divergence.index) == ("generated_tests", 1)


def test_a_formatting_only_divergence_is_flagged_but_stays_a_wa(fake, run):
    triage = run("// FMT@0\nx").triage
    assert triage.verdict == "WA"
    assert triage.divergence.format_only is True


def test_a_real_divergence_is_not_format_only(fake, run):
    assert run("// WA@0\nx").triage.divergence.format_only is False


def test_only_the_first_correct_solution_is_ever_compiled(fake, make_raw):
    """No substitute is tried: the problem goes to triage (D8)."""
    raw = make_raw(ac=("// WA@0\nfirst", "// AC\nsecond", "// AC\nthird"))
    source = ac.choose_ac_source(raw)
    ac.run_ac(
        raw.problem_id,
        source,
        suite_from_raw(raw),
        LIMITS,
        fake.as_engine(),
        slot=0,
        stage="selection",
        file_name="AC_ref.cpp",
    )
    assert fake.compiled == ["// WA@0\nfirst"]


def test_a_compile_failure_in_every_standard_records_the_four_diagnostics(fake, run):
    outcome = run("// CE\nx")
    triage = outcome.triage
    assert triage.verdict == "CE" and triage.divergence is None
    for standard in ("gnu++20", "gnu++17", "gnu++14", "gnu++11"):
        assert standard in triage.engine_diagnostic
    assert outcome.code.verdict is Verdict.CE and outcome.code.tests_run == 0


@pytest.mark.parametrize("name", ["TLE", "MLE", "RE"])
def test_each_ac_failure_type_produces_a_triage_record(fake, name, run):
    outcome = run(f"// {name}@2\nx")
    triage = outcome.triage
    assert triage.verdict == name and triage.stage == "selection"
    assert triage.divergence is None and triage.engine_diagnostic
    assert "generated_tests[0]" in triage.reason


def test_the_suite_stops_at_the_first_failure_of_the_ac(fake, run):
    outcome = run("// TLE@1\nx")
    assert outcome.code.tests_run == 2


def test_an_infra_error_is_not_an_ac_failure_and_creates_no_triage(fake, make_raw):
    engine = fake.as_engine()

    def broken(*args):
        raise InfraError("tmpfs is full")

    engine = type(engine)(gcc_version="13.2.0", compile=broken, run_suite=engine.run_suite)
    raw = make_raw()
    with pytest.raises(InfraError):
        ac.run_ac(
            raw.problem_id,
            "// AC\nx",
            suite_from_raw(raw),
            LIMITS,
            engine,
            slot=0,
            stage="selection",
            file_name="AC_ref.cpp",
        )


def test_the_audit_stage_is_recorded_in_the_triage(fake, run):
    triage = run("// WA@0\nx", stage="audit").triage
    assert triage.stage == "audit"


def test_no_wa_candidate_is_evaluated_when_the_ac_fails(fake, run, make_raw):
    raw = make_raw(ac=("// WA@0\nx",))
    run("// WA@0\nx", raw)
    assert all(not src.startswith("// WA@") or src == "// WA@0\nx" for src in fake.compiled)
    assert len(fake.compiled) == 1
