"""Tests for the audit: re-running `AC_ref` first, then the WA (T059; FR-015a, FR-011b)."""

import pytest

from dataset import config
from dataset.persistence import store
from dataset.schemas.validacao import Validacao
from dataset.validation import audit, problem
from dataset.validation.runtime import InlineRuntime
from sandbox.types import InfraError

NOW = "2026-09-21T12:00:00Z"


def wa_sources(n, mark="WA@0"):
    return [f"// {mark}\nint main(){{return {i};}}" for i in range(n)]


@pytest.fixture()
def built(tmp_path, fake, make_raw):
    """A complete problem on disk plus the runtime to audit it (the fake engine's log is reset)."""
    store.ensure_work_dir(tmp_path)
    raw = make_raw(wa=wa_sources(130))
    runtime = InlineRuntime(fake.as_engine())
    problem.validate_problem(tmp_path, raw, runtime, now=lambda: NOW)
    fake.compiled.clear()
    fake.suite_runs.clear()
    folder = tmp_path / config.PROBLEMS_DIR / raw.problem_id
    return tmp_path, raw.problem_id, folder, runtime


def test_a_matching_problem_passes_and_its_files_are_untouched(built, fake):
    root, pid, folder, runtime = built
    before = {p.name: p.read_bytes() for p in folder.iterdir()}
    result = audit.audit_problem(root, pid, runtime)
    assert result.ac_ok and result.wa_checked == 100
    assert result.wa_mismatches == [] and result.triage is None and not result.diverged
    assert {p.name: p.read_bytes() for p in folder.iterdir()} == before


def test_the_ac_is_rerun_first(built, fake):
    root, pid, folder, runtime = built
    audit.audit_problem(root, pid, runtime)
    assert fake.compiled[0] == (folder / "AC_ref.cpp").read_text()
    assert len(fake.compiled) == 101


def test_an_ac_that_now_fails_interrupts_the_problem_and_goes_to_triage(built, fake):
    root, pid, folder, runtime = built
    (folder / "AC_ref.cpp").write_text("// WA@0\nint main(){}\n")
    result = audit.audit_problem(root, pid, runtime)
    assert result.diverged and result.ac_ok is False
    assert result.triage.stage == "audit" and result.triage.verdict == "WA"
    assert len(fake.compiled) == 1  # the WA were NOT evaluated
    assert result.wa_checked == 0
    validacao = Validacao.from_folder(folder)
    assert validacao.status == "pending_triage" and validacao.triage.stage == "audit"
    assert validacao.wa == []


def test_the_engine_verdict_is_recorded_when_the_ac_now_times_out(built):
    root, pid, folder, runtime = built
    (folder / "AC_ref.cpp").write_text("// TLE@2\nint main(){}\n")
    result = audit.audit_problem(root, pid, runtime)
    assert result.triage.verdict == "TLE" and result.triage.stage == "audit"


def test_a_pending_triage_problem_is_not_audited_again_and_not_reprocessed(built, fake):
    root, pid, folder, runtime = built
    (folder / "AC_ref.cpp").write_text("// WA@0\nint main(){}\n")
    audit.audit_problem(root, pid, runtime)
    fake.compiled.clear()
    again = audit.audit_problem(root, pid, runtime)
    assert again.skipped and fake.compiled == []
    assert store.problem_status(root, pid) == "pending_triage"


def test_a_wa_whose_verdict_changed_is_only_reported(built, fake):
    root, pid, folder, runtime = built
    (folder / "WA_5.cpp").write_text("// TLE@0\nint main(){}\n")
    before = (folder / "validacao.json").read_bytes()
    result = audit.audit_problem(root, pid, runtime)
    assert result.ac_ok and result.diverged
    assert [m.file for m in result.wa_mismatches] == ["WA_5.cpp"]
    assert result.wa_mismatches[0].obtained == "tle"
    assert result.triage is None and result.wa_checked == 100  # the problem is NOT interrupted
    assert (folder / "validacao.json").read_bytes() == before
    assert store.problem_status(root, pid) == "complete"


def test_a_wa_that_now_fails_on_another_test_is_reported(built):
    root, pid, folder, runtime = built
    (folder / "WA_7.cpp").write_text("// WA@3\nint main(){}\n")
    recorded = Validacao.from_folder(folder).wa[6].deciding_test
    result = audit.audit_problem(root, pid, runtime)
    assert [m.file for m in result.wa_mismatches] == ["WA_7.cpp"]
    assert result.wa_mismatches[0].obtained == "wa"
    assert recorded.index != 3 or recorded.group != "generated_tests"


def test_several_mismatches_are_listed_in_file_order(built):
    root, pid, folder, runtime = built
    for n in (40, 3, 77):
        (folder / f"WA_{n}.cpp").write_text("// CE\nint main(){}\n")
    result = audit.audit_problem(root, pid, runtime)
    assert [m.file for m in result.wa_mismatches] == ["WA_3.cpp", "WA_40.cpp", "WA_77.cpp"]


def test_only_complete_problems_are_audited(tmp_path, fake, make_raw):
    store.ensure_work_dir(tmp_path)
    raw = make_raw(wa=wa_sources(40))  # discarded
    runtime = InlineRuntime(fake.as_engine())
    problem.validate_problem(tmp_path, make_raw(ac=("// WA@0\nx",), wa=wa_sources(120)), runtime)
    result = audit.audit_problem(tmp_path, raw.problem_id, runtime)
    assert result.skipped and "pending_triage" in result.skipped


def test_an_unknown_problem_is_an_error(tmp_path, fake):
    store.ensure_work_dir(tmp_path)
    with pytest.raises(FileNotFoundError):
        audit.audit_problem(tmp_path, "9999_Z", InlineRuntime(fake.as_engine()))


def test_an_infra_error_during_the_audit_propagates_and_changes_nothing(built, fake):
    root, pid, folder, _runtime = built
    before = {p.name: p.read_bytes() for p in folder.iterdir()}
    engine = fake.as_engine()

    def broken(source, slot):
        raise InfraError("no compiler")

    bad = InlineRuntime(
        type(engine)(gcc_version="13.2.0", compile=broken, run_suite=engine.run_suite)
    )
    with pytest.raises(InfraError):
        audit.audit_problem(root, pid, bad)
    assert {p.name: p.read_bytes() for p in folder.iterdir()} == before


def test_the_audit_uses_the_limits_recorded_with_the_problem(built, fake):
    root, pid, _folder, _runtime = built
    seen = []
    engine = fake.as_engine()
    original = engine.run_suite

    def spy(binary, tests, limits, slot):
        seen.append(limits)
        return original(binary, tests, limits, slot)

    spied = InlineRuntime(type(engine)(gcc_version="13.2.0", compile=engine.compile, run_suite=spy))
    audit.audit_problem(root, pid, spied)
    assert {(l.time_limit_seconds, l.memory_limit_bytes) for l in seen} == {(2.0, 256_000_000)}
