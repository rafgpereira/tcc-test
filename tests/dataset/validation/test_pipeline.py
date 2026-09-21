"""Tests for the `validate` and `audit` orchestration over the pool (T068; FR-011b, FR-023, FR-024)."""

import json

import pytest

from dataset import config
from dataset.filtering.classification import classify
from dataset.persistence import store
from dataset.schemas.pool import Pool, PoolCounts, PoolProblem
from dataset.validation import pipeline
from dataset.validation.runtime import InlineRuntime
from sandbox.selfcheck import CaseResult, SelfCheckReport
from sandbox.types import InfraError, Verdict


def wa_sources(n=120, mark="WA@0", tag=""):
    return [f"// {mark}\nint main(){{return {i};}} {tag}" for i in range(n)]


@pytest.fixture()
def root(tmp_path):
    store.ensure_work_dir(tmp_path)
    return tmp_path


@pytest.fixture()
def prepare(root):
    """`prepare(raws)` writes pool.json (in the given order) and the raw files."""

    def _prepare(raws):
        problems = {
            raw.problem_id: PoolProblem(
                split=raw.split,
                shard_index=0,
                macrocategoria=classify(raw.cf_tags),
                raw_wa_count=len(raw.incorrect_solutions),
                raw_ac_count=len(raw.correct_solutions),
                source_row=i,
            )
            for i, raw in enumerate(raws)
        }
        pool = Pool(
            hf_dataset=config.HF_DATASET,
            hf_revision=config.HF_REVISION,
            seed=42,
            counts=PoolCounts(funnel={"read": len(raws)}, rejections={}, eligible=len(raws)),
            order=[raw.problem_id for raw in raws],
            problems=problems,
        )
        store.atomic_write_json(root / config.STAGING_DIR / "pool.json", pool)
        for raw in raws:
            store.atomic_write_json_gz(root / config.RAW_DIR / f"{raw.problem_id}.json.gz", raw)

    return _prepare


def selfcheck_ok():
    case = CaseResult("ac", Verdict.AC, Verdict.AC, "gnu++20", True, True)
    return SelfCheckReport(ok=True, cases=(case,))


def selfcheck_bad():
    case = CaseResult("wa", Verdict.WA, Verdict.AC, "gnu++20", True, False)
    return SelfCheckReport(ok=False, cases=(case,))


class Factory:
    def __init__(self, fake):
        self.fake, self.workers, self.made, self.closed = fake, [], 0, 0

    def __call__(self, workers):
        self.workers.append(workers)
        self.made += 1
        outer = self

        class Rt(InlineRuntime):
            def close(self):
                outer.closed += 1

        return Rt(self.fake.as_engine())


@pytest.fixture()
def factory(fake):
    return Factory(fake)


def validate(root, factory, *, target=2, workers=3, problem=None, selfcheck=selfcheck_ok):
    lines = []
    code = pipeline.run_validate(
        root,
        target=target,
        workers=workers,
        problem=problem,
        runtime_factory=factory,
        selfcheck_fn=selfcheck,
        out=lines.append,
    )
    return code, lines


def statuses(root):
    return {
        p.name: json.loads((p / "validacao.json").read_text())["status"]
        for p in sorted((root / config.PROBLEMS_DIR).iterdir())
    }


def test_validate_aborts_when_the_selfcheck_fails_and_validates_nothing(
    root, prepare, factory, make_raw
):
    prepare([make_raw("1_A", wa=wa_sources())])
    code, lines = validate(root, factory, selfcheck=selfcheck_bad)
    assert code == 1
    assert factory.made == 0  # no engine, no problem touched
    assert list((root / config.PROBLEMS_DIR).iterdir()) == []
    assert any("selfcheck" in line.lower() and "FAIL" in line for line in lines)


def test_the_selfcheck_result_is_saved_for_the_report(root, prepare, factory, make_raw):
    prepare([make_raw("1_A", wa=wa_sources())])
    validate(root, factory, target=1)
    saved = json.loads((root / config.REPORTS_DIR / "selfcheck.json").read_text())
    assert saved["ok"] is True and saved["passed"] == 1


def test_the_pool_is_processed_in_the_recorded_order_until_the_target(
    root, prepare, factory, make_raw
):
    raws = [make_raw(f"{i}_A", wa=wa_sources(tag=str(i))) for i in (7, 3, 9, 1, 5)]
    prepare(raws)
    code, _ = validate(root, factory, target=2)
    assert code == 0
    assert statuses(root) == {"3_A": "complete", "7_A": "complete"}  # the first two of the order


def test_the_worker_count_reaches_the_runtime_and_the_runtime_is_closed(
    root, prepare, factory, make_raw
):
    prepare([make_raw("1_A", wa=wa_sources())])
    validate(root, factory, target=1, workers=4)
    assert factory.workers == [4] and factory.closed == 1


def test_already_closed_problems_are_skipped_and_still_count_for_the_target(
    root, prepare, factory, make_raw, fake
):
    raws = [make_raw(f"{i}_A", wa=wa_sources(tag=str(i))) for i in (1, 2, 3)]
    prepare(raws)
    validate(root, factory, target=1)
    fake.compiled.clear()
    code, _ = validate(root, factory, target=2)
    assert code == 0
    assert statuses(root) == {"1_A": "complete", "2_A": "complete"}
    assert all("main(){return" in s for s in fake.compiled)  # 1_A was NOT rebuilt


def test_a_partial_building_folder_is_discarded_and_rebuilt_on_the_next_run(
    root, prepare, factory, make_raw
):
    prepare([make_raw("1_A", wa=wa_sources())])
    partial = store.start_building(root, "1_A")
    store.write_problem_text(partial, "AC_ref.cpp", "half")
    validate(root, factory, target=1)
    assert statuses(root) == {"1_A": "complete"}
    assert list((root / config.BUILDING_DIR).iterdir()) == []


def test_an_ac_failure_is_recorded_and_the_next_problem_is_processed(
    root, prepare, factory, make_raw
):
    prepare(
        [
            make_raw("1_A", ac=("// WA@0\nx",), wa=wa_sources()),
            make_raw("2_A", wa=wa_sources(tag="2")),
            make_raw("3_A", wa=wa_sources(tag="3")),
        ]
    )
    code, lines = validate(root, factory, target=2)
    assert statuses(root) == {
        "1_A": "pending_triage",
        "2_A": "complete",
        "3_A": "complete",
    }
    assert code == 1  # the target was reached but there is a NEW triage case
    assert any("1_A" in line and "pending_triage" in line for line in lines)


def test_a_discarded_problem_does_not_count_and_does_not_stop_the_run(
    root, prepare, factory, make_raw
):
    prepare(
        [
            make_raw("1_A", wa=wa_sources(60) * 2),
            make_raw("2_A", wa=wa_sources(tag="2")),
        ]
    )
    code, _ = validate(root, factory, target=1)
    assert statuses(root) == {"1_A": "discarded", "2_A": "complete"}
    assert code == 0


def test_exit_code_1_when_the_pool_ends_before_the_target(root, prepare, factory, make_raw):
    prepare([make_raw("1_A", wa=wa_sources())])
    code, lines = validate(root, factory, target=5)
    assert code == 1
    assert any("deficit 4" in line for line in lines)


def test_a_single_problem_ignores_the_target(root, prepare, factory, make_raw):
    raws = [make_raw(f"{i}_A", wa=wa_sources(tag=str(i))) for i in (1, 2, 3)]
    prepare(raws)
    code, _ = validate(root, factory, target=200, problem="2_A")
    assert code == 0 and statuses(root) == {"2_A": "complete"}


def test_a_single_problem_in_triage_exits_with_1(root, prepare, factory, make_raw):
    prepare([make_raw("1_A", ac=("// WA@1\nx",), wa=wa_sources())])
    code, _ = validate(root, factory, problem="1_A")
    assert code == 1 and statuses(root) == {"1_A": "pending_triage"}


def test_a_problem_that_is_not_in_the_pool_is_a_usage_error(root, prepare, factory, make_raw):
    prepare([make_raw("1_A", wa=wa_sources())])
    with pytest.raises(pipeline.UsageError, match="9_Z"):
        validate(root, factory, problem="9_Z")


def test_a_closed_problem_is_not_reprocessed_even_when_asked_for_it(
    root, prepare, factory, make_raw, fake
):
    prepare([make_raw("1_A", wa=wa_sources())])
    validate(root, factory, problem="1_A")
    fake.compiled.clear()
    code, lines = validate(root, factory, problem="1_A")
    assert fake.compiled == [] and code == 0
    assert any("already closed" in line for line in lines)


def test_without_a_pool_the_command_asks_for_the_extraction(root, factory):
    with pytest.raises(pipeline.UsageError, match="extract"):
        validate(root, factory)


def test_an_infra_error_is_retried_once_and_then_propagates_leaving_building(
    root, prepare, factory, make_raw, fake
):
    prepare([make_raw("1_A", wa=wa_sources())])
    engine = fake.as_engine()
    attempts = []

    def broken(source, slot):
        attempts.append(1)
        raise InfraError("tmpfs is full")

    class Rt(InlineRuntime):
        pass

    def broken_factory(workers):
        return Rt(type(engine)(gcc_version="13.2.0", compile=broken, run_suite=engine.run_suite))

    with pytest.raises(InfraError):
        pipeline.run_validate(
            root,
            target=1,
            workers=1,
            problem=None,
            runtime_factory=broken_factory,
            selfcheck_fn=selfcheck_ok,
            out=lambda line: None,
        )
    assert len(attempts) == 2  # first attempt + one retry
    assert store.problem_status(root, "1_A") is None
    assert (root / config.BUILDING_DIR / "1_A").is_dir()


def test_an_infra_error_that_goes_away_is_absorbed_by_the_retry(root, prepare, make_raw, fake):
    prepare([make_raw("1_A", wa=wa_sources())])
    engine = fake.as_engine()
    calls = []

    def flaky(source, slot):
        calls.append(1)
        if len(calls) == 1:
            raise InfraError("transient")
        return engine.compile(source, slot)

    def flaky_factory(workers):
        return InlineRuntime(
            type(engine)(gcc_version="13.2.0", compile=flaky, run_suite=engine.run_suite)
        )

    code = pipeline.run_validate(
        root,
        target=1,
        workers=1,
        problem=None,
        runtime_factory=flaky_factory,
        selfcheck_fn=selfcheck_ok,
        out=lambda line: None,
    )
    assert code == 0 and statuses(root) == {"1_A": "complete"}


def test_a_summary_line_is_printed_per_problem_with_the_candidate_statistics(
    root, prepare, factory, make_raw
):
    prepare([make_raw("1_A", wa=wa_sources(120) + wa_sources(5, "TLE@0", "t"))])
    _, lines = validate(root, factory, target=1)
    line = next(line for line in lines if line.startswith("1_A"))
    assert "complete" in line and "wa=100" in line and "s)" in line


def test_the_validation_log_records_one_json_line_per_problem(root, prepare, factory, make_raw):
    prepare([make_raw("1_A", wa=wa_sources()), make_raw("2_A", wa=wa_sources(tag="2"))])
    validate(root, factory, target=2)
    log = (root / config.REPORTS_DIR / "validation_log.jsonl").read_text().splitlines()
    records = [json.loads(line) for line in log]
    assert [r["problem_id"] for r in records] == ["1_A", "2_A"]
    assert records[0]["status"] == "complete" and records[0]["stats"]["wa"] == 100
    assert "seconds" in records[0]


def test_the_report_is_written_at_the_end_with_the_ac_numbers(root, prepare, factory, make_raw):
    prepare(
        [
            make_raw("1_A", ac=("// TLE@1\nx",), wa=wa_sources()),
            make_raw("2_A", wa=wa_sources(tag="2")),
        ]
    )
    validate(root, factory, target=1)
    report = json.loads((root / config.REPORTS_DIR / "extraction_report.json").read_text())
    assert report["ac_tested"] == 2
    assert report["triage_by_cause"] == {"format_only": 0, "tle": 1, "other": 0}
    assert report["engine_selfcheck"]["ok"] is True
    assert report["funnel"]["included"] == 1


# ---------------------------------------------------------------------------- audit


def audit(root, factory, problems=()):
    lines = []
    code = pipeline.run_audit(
        root, problems=list(problems), workers=2, runtime_factory=factory, out=lines.append
    )
    return code, lines


def test_audit_defaults_to_every_complete_problem_and_exits_0_when_all_match(
    root, prepare, factory, make_raw
):
    prepare([make_raw(f"{i}_A", wa=wa_sources(tag=str(i))) for i in (1, 2)])
    validate(root, factory, target=2)
    code, lines = audit(root, factory)
    assert code == 0
    assert sum("1_A" in line or "2_A" in line for line in lines) >= 2


def test_audit_exits_1_on_any_divergence_and_lists_it(root, prepare, factory, make_raw):
    prepare([make_raw("1_A", wa=wa_sources()), make_raw("2_A", wa=wa_sources(tag="2"))])
    validate(root, factory, target=2)
    (root / config.PROBLEMS_DIR / "2_A" / "AC_ref.cpp").write_text("// WA@0\nx\n")
    code, lines = audit(root, factory)
    assert code == 1
    assert any("2_A" in line and "audit" in line for line in lines)
    assert statuses(root)["2_A"] == "pending_triage" and statuses(root)["1_A"] == "complete"


def test_audit_can_be_limited_to_some_problems(root, prepare, factory, make_raw, fake):
    prepare([make_raw(f"{i}_A", wa=wa_sources(tag=str(i))) for i in (1, 2, 3)])
    validate(root, factory, target=3)
    fake.compiled.clear()
    audit(root, factory, ["2_A"])
    assert len(fake.compiled) == 101  # AC_ref + 100 WA of one problem only


def test_audit_reports_a_wa_mismatch_without_touching_the_problem(root, prepare, factory, make_raw):
    prepare([make_raw("1_A", wa=wa_sources())])
    validate(root, factory, target=1)
    (root / config.PROBLEMS_DIR / "1_A" / "WA_9.cpp").write_text("// TLE@0\nx\n")
    code, lines = audit(root, factory)
    assert code == 1 and any("WA_9.cpp" in line for line in lines)
    assert statuses(root) == {"1_A": "complete"}


def test_audit_refreshes_the_report_so_the_triage_list_is_current(root, prepare, factory, make_raw):
    prepare([make_raw("1_A", wa=wa_sources())])
    validate(root, factory, target=1)
    (root / config.PROBLEMS_DIR / "1_A" / "AC_ref.cpp").write_text("// WA@0\nx\n")
    audit(root, factory)
    report = json.loads((root / config.REPORTS_DIR / "extraction_report.json").read_text())
    assert [p["problem_id"] for p in report["pending_triage"]] == ["1_A"]
    assert report["pending_triage"][0]["stage"] == "audit"
