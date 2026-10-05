"""Tests for validating one whole problem into its folder (T058; FR-011a, FR-019 to FR-024).

The unit tests use a fake engine; the integration test at the end runs the REAL engine, so it only
runs in the `sandbox` service.
"""

import hashlib
import json

import pytest

from dataset import config
from dataset.persistence import store
from dataset.schemas.metadata import Metadata
from dataset.schemas.testes import Testes
from dataset.schemas.validacao import Validacao
from dataset.validation import problem
from dataset.validation.runtime import InlineRuntime, ThreadRuntime
from sandbox.compiler import COMPILE_FLAGS, STANDARD_CASCADE
from sandbox.types import InfraError

NOW = "2026-09-21T12:00:00Z"
SIX = {"enunciado.md", "AC_ref.cpp", "testes.json", "metadata.json", "validacao.json"}


@pytest.fixture()
def root(tmp_path):
    store.ensure_work_dir(tmp_path)
    return tmp_path


@pytest.fixture()
def runtime(fake):
    return InlineRuntime(fake.as_engine(), main_slot=9)


def wa_sources(n, mark="WA@0"):
    return [f"// {mark}\nint main(){{return {i};}}" for i in range(n)]


def run(root, raw, runtime):
    return problem.validate_problem(root, raw, runtime, now=lambda: NOW)


def test_a_complete_problem_folder_has_all_the_file_types(root, runtime, make_raw):
    raw = make_raw(wa=wa_sources(120))
    result = run(root, raw, runtime)
    assert result.status == "complete"
    folder = root / config.PROBLEMS_DIR / raw.problem_id
    names = {p.name for p in folder.iterdir()}
    assert names == SIX | {f"WA_{i}.cpp" for i in range(1, 101)}
    assert list((root / config.BUILDING_DIR).iterdir()) == []  # closed by an atomic rename


def test_every_json_file_validates_with_its_model(root, runtime, make_raw):
    raw = make_raw(wa=wa_sources(120))
    run(root, raw, runtime)
    folder = root / config.PROBLEMS_DIR / raw.problem_id
    metadata = Metadata.from_folder(folder)
    Testes.from_folder(folder)
    validacao = Validacao.from_folder(folder)
    assert validacao.status == "complete" and len(validacao.wa) == 100
    assert metadata.num_wa_validados == 100
    assert metadata.extraction_timestamp == NOW


def test_metadata_reports_the_raw_wa_count_before_deduplication(root, runtime, make_raw):
    sources = wa_sources(120) + wa_sources(10)  # 10 duplicates
    raw = make_raw(wa=sources)
    run(root, raw, runtime)
    meta = Metadata.from_folder(root / config.PROBLEMS_DIR / raw.problem_id)
    assert meta.num_wa_brutos_disponiveis == 130
    assert meta.dataset_split_origem == "train" and meta.cf_tags == ["dp", "math"]
    assert meta.macrocategoria.value == "estrutural_otimizacao"


def test_the_statement_only_normalizes_encoding_and_line_breaks(root, runtime, make_raw):
    raw = make_raw(wa=wa_sources(120))
    run(root, raw, runtime)
    text = (root / config.PROBLEMS_DIR / raw.problem_id / "enunciado.md").read_bytes()
    assert text == b"Read n.\nPrint 2n.\n"


def test_ac_ref_is_the_first_correct_solution_in_the_original_order(root, runtime, make_raw):
    raw = make_raw(ac=("// AC\nfirst", "// AC\nsecond"), wa=wa_sources(120))
    run(root, raw, runtime)
    folder = root / config.PROBLEMS_DIR / raw.problem_id
    assert (folder / "AC_ref.cpp").read_text() == "// AC\nfirst"


def test_every_persisted_code_was_executed_by_the_engine_with_the_expected_verdict(
    root, runtime, make_raw, fake
):
    """The dataset invariant (FR-011a): nothing is persisted without passing the engine."""
    raw = make_raw(wa=wa_sources(150) + wa_sources(20, "TLE@0"))
    run(root, raw, runtime)
    folder = root / config.PROBLEMS_DIR / raw.problem_id
    validacao = Validacao.from_folder(folder)
    assert validacao.ac_ref.verdict.value == "AC"
    for item in validacao.wa:
        source = (folder / item.file).read_text()
        assert source in fake.suite_runs  # it went through the engine
        assert item.verdict.value == "WA" and item.stable
        assert hashlib.sha256(source.encode()).hexdigest() == item.sha256
    assert "// AC\nint main(){return 0;}" in fake.suite_runs


def test_no_discarded_candidate_is_persisted(root, runtime, make_raw):
    sources = wa_sources(140) + wa_sources(30, "TLE@0") + wa_sources(30, "CE")
    raw = make_raw(wa=sources)
    run(root, raw, runtime)
    folder = root / config.PROBLEMS_DIR / raw.problem_id
    saved = "\n".join((folder / f"WA_{i}.cpp").read_text() for i in range(1, 101))
    assert "TLE@0" not in saved and "CE" not in saved


def test_the_engine_configuration_is_recorded(root, runtime, make_raw):
    raw = make_raw(wa=wa_sources(120), limit=1.5, memory=128_000_000)
    run(root, raw, runtime)
    engine = Validacao.from_folder(root / config.PROBLEMS_DIR / raw.problem_id).engine
    assert engine.gcc_version == "13.2.0"
    assert engine.flags == list(COMPILE_FLAGS) and engine.standard_cascade == list(STANDARD_CASCADE)
    assert engine.stack_limit_bytes == 268435456
    assert engine.time_limit_seconds == 1.5 and engine.memory_limit_bytes == 128_000_000
    assert engine.stability_runs == 2


def test_the_limits_come_from_the_problem_metadata(root, make_raw, fake):
    captured = []
    engine = fake.as_engine()
    original = engine.run_suite

    def spy(binary, tests, limits, slot):
        captured.append(limits)
        return original(binary, tests, limits, slot)

    engine = type(engine)(gcc_version="13.2.0", compile=engine.compile, run_suite=spy)
    run(root, make_raw(wa=wa_sources(120), limit=0.75, memory=99_000_000), InlineRuntime(engine))
    assert {(l.time_limit_seconds, l.memory_limit_bytes) for l in captured} == {(0.75, 99_000_000)}


def test_the_test_suite_is_persisted_in_execution_order(root, runtime, make_raw):
    raw = make_raw(wa=wa_sources(120), n_tests=(2, 1, 3))
    run(root, raw, runtime)
    testes = Testes.from_folder(root / config.PROBLEMS_DIR / raw.problem_id)
    assert (len(testes.public_tests), len(testes.private_tests), len(testes.generated_tests)) == (
        2,
        1,
        3,
    )


def test_an_ac_that_diverges_leaves_only_the_triage_files(root, runtime, make_raw, fake):
    raw = make_raw(ac=("// WA@1\nx",), wa=wa_sources(120))
    result = run(root, raw, runtime)
    assert result.status == "pending_triage"
    folder = root / config.PROBLEMS_DIR / raw.problem_id
    assert {p.name for p in folder.iterdir()} == {"validacao.json", "AC_candidate.cpp"}
    validacao = Validacao.from_folder(folder)
    assert validacao.status == "pending_triage" and validacao.triage.stage == "selection"
    assert validacao.wa == [] and validacao.ac_ref.file == "AC_candidate.cpp"
    assert fake.compiled == ["// WA@1\nx"]  # no WA candidate was evaluated


def test_a_problem_with_too_few_unique_wa_is_discarded_with_only_the_validation(
    root, runtime, make_raw
):
    raw = make_raw(wa=wa_sources(60) * 2)  # 120 raw submissions, 60 distinct texts
    result = run(root, raw, runtime)
    assert result.status == "discarded" and result.discard_reason == "insufficient_wa"
    folder = root / config.PROBLEMS_DIR / raw.problem_id
    assert {p.name for p in folder.iterdir()} == {"validacao.json"}
    validacao = Validacao.from_folder(folder)
    assert validacao.discard_reason == "insufficient_wa" and validacao.wa == []
    assert validacao.ac_ref.verdict.value == "AC"


def test_a_problem_that_cannot_reach_100_wa_along_the_way_is_discarded(root, runtime, make_raw):
    raw = make_raw(wa=wa_sources(50) + wa_sources(70, "TLE@0"))
    result = run(root, raw, runtime)
    assert result.status == "discarded" and result.discard_reason == "insufficient_wa"


def test_fewer_than_100_raw_wa_is_discarded_without_running_anything(root, runtime, make_raw, fake):
    raw = make_raw(wa=wa_sources(99))
    result = run(root, raw, runtime)
    assert result.status == "discarded" and result.discard_reason == "insufficient_raw_wa"
    assert fake.compiled == []
    validacao = Validacao.from_folder(root / config.PROBLEMS_DIR / raw.problem_id)
    assert validacao.ac_ref is None


def test_an_infra_error_leaves_the_problem_in_building_and_is_not_a_verdict(root, make_raw, fake):
    engine = fake.as_engine()
    calls = []

    def flaky(source, slot):
        calls.append(source)
        if len(calls) == 3:
            raise InfraError("tmpfs is full")
        return engine.compile(source, slot)

    broken = type(engine)(gcc_version="13.2.0", compile=flaky, run_suite=engine.run_suite)
    raw = make_raw(wa=wa_sources(120))
    with pytest.raises(InfraError):
        run(root, raw, InlineRuntime(broken))
    assert store.problem_status(root, raw.problem_id) is None  # not closed: redone on resume
    assert (root / config.BUILDING_DIR / raw.problem_id).is_dir()


def test_the_same_input_gives_byte_identical_files(tmp_path, make_raw, fake):
    raw = make_raw(wa=wa_sources(130))
    outputs = []
    for name in ("a", "b"):
        root = tmp_path / name
        store.ensure_work_dir(root)
        problem.validate_problem(root, raw, InlineRuntime(fake.as_engine()), now=lambda: NOW)
        folder = root / config.PROBLEMS_DIR / raw.problem_id
        outputs.append({p.name: p.read_bytes() for p in sorted(folder.iterdir())})
    assert outputs[0] == outputs[1]


def test_the_result_does_not_depend_on_the_number_of_workers(tmp_path, make_raw, fake):
    raw = make_raw(
        wa=[f"// {'WA@0' if i % 3 else 'TLE@0'}\nint main(){{return {i};}}" for i in range(400)]
    )
    files = []
    for name, rt in (
        ("one", InlineRuntime(fake.as_engine())),
        ("many", ThreadRuntime(fake.as_engine(), 5)),
    ):
        root = tmp_path / name
        store.ensure_work_dir(root)
        problem.validate_problem(root, raw, rt, now=lambda: NOW)
        rt.close()
        folder = root / config.PROBLEMS_DIR / raw.problem_id
        files.append({p.name: p.read_bytes() for p in sorted(folder.iterdir())})
    assert files[0] == files[1]


def test_the_result_reports_the_statistics_of_the_candidates(root, runtime, make_raw):
    sources = wa_sources(120) + wa_sources(10, "TLE@0") + wa_sources(5, "CE")
    result = run(root, make_raw(wa=sources), runtime)
    assert result.stats["wa"] == 100
    assert result.consumed == sum(result.stats.values())
    assert result.seconds >= 0


def test_the_validation_json_is_deterministic_json(root, runtime, make_raw):
    raw = make_raw(wa=wa_sources(120))
    run(root, raw, runtime)
    text = (root / config.PROBLEMS_DIR / raw.problem_id / "validacao.json").read_text()
    assert text.endswith("}\n") and json.loads(text)["status"] == "complete"
    assert text == store.dumps_json(json.loads(text))


# ---------------------------------------------------------------------------- real engine

DOUBLE = '#include <cstdio>\nint main(){ long n; if (std::scanf("%ld",&n)!=1) return 2; std::printf("%ld\\n", 2*n); }\n'


def wrong_program(k: int) -> str:
    return (
        '#include <cstdio>\nint main(){ long n; if (std::scanf("%ld",&n)!=1) return 2; '
        f'std::printf("%ld\\n", 2*n + {k}); }}\n'
    )


@pytest.mark.integration
def test_a_real_problem_is_validated_end_to_end_with_the_real_engine(tmp_path, make_raw):
    from dataset.validation.runtime import PoolRuntime
    from sandbox import judge

    sources = [wrong_program(k) for k in range(1, 121)]
    sources += ["int main( { return 0 }\n"] * 3  # a compile error (identical, counts once)
    sources += ["int main(){ for(;;){} }\n"]  # a TLE
    raw = make_raw(ac=(DOUBLE,), wa=sources, n_tests=(1, 1, 3), limit=1.0)
    store.ensure_work_dir(tmp_path)
    runtime = PoolRuntime(workers=2)
    try:
        result = problem.validate_problem(tmp_path, raw, runtime, now=lambda: NOW)
    finally:
        runtime.close()
    assert result.status == "complete", result
    folder = tmp_path / config.PROBLEMS_DIR / raw.problem_id
    validacao = Validacao.from_folder(folder)
    assert validacao.ac_ref.verdict.value == "AC" and validacao.engine.gcc_version.startswith("13.")
    assert len(validacao.wa) == 100
    # FR-011a: every persisted WA, re-run alone, ends with a wrong answer within the limits.
    from dataset.validation.suite import suite_from_raw
    from sandbox import isolation
    from sandbox.types import ExecutionLimits, Verdict

    suite = suite_from_raw(raw)
    limits = ExecutionLimits(1.0, 256_000_000)
    slot = 5
    workdir = isolation.prepare_slot_workdir(slot)
    for item in validacao.wa[:10]:
        again = judge.judge_source(
            (folder / item.file).read_text(), suite.tests, limits, slot, workdir
        )
        assert again.verdict is Verdict.WA
    ac_again = judge.judge_source(
        (folder / "AC_ref.cpp").read_text(), suite.tests, limits, slot, workdir
    )
    assert ac_again.verdict is Verdict.AC
