"""Report fields fed by the validation: ACs tested and AC failures by cause (T069; D13)."""

import json

import pytest

from dataset import config
from dataset.persistence import report as rep
from dataset.persistence import store
from dataset.schemas.common import Macrocategoria as M
from dataset.schemas.pool import Pool, PoolCounts, PoolProblem
from dataset.schemas.report import ExtractionReport

ENGINE = {
    "gcc_version": "13.2.0",
    "flags": ["-O2"],
    "standard_cascade": ["gnu++20"],
    "stack_limit_bytes": 268435456,
    "time_limit_seconds": 2.0,
    "memory_limit_bytes": 256000000,
    "stability_runs": 2,
}


def code(verdict="AC", file="AC_ref.cpp"):
    return {
        "file": file,
        "sha256": "0" * 64,
        "verdict": verdict,
        "standard_used": "gnu++20",
        "max_cpu_time_s": 0.1,
        "max_memory_bytes": 1,
        "tests_run": 3,
    }


def triage(pid, verdict, format_only=False, stage="selection"):
    divergence = None
    if verdict == "WA":
        divergence = {
            "group": "public_tests",
            "index": 0,
            "input": "",
            "expected": "1 2\n",
            "actual": "1  2\n" if format_only else "1 3\n",
            "truncated": False,
            "format_only": format_only,
        }
    return {
        "problem_id": pid,
        "stage": stage,
        "verdict": verdict,
        "reason": f"AC ended with {verdict}",
        "divergence": divergence,
        "engine_diagnostic": None if divergence else "diag",
    }


def write_problem(root, pid, status, *, ac_ref=None, tri=None, discard=None):
    folder = root / config.PROBLEMS_DIR / pid
    folder.mkdir(parents=True)
    data = {
        "schema_version": 1,
        "problem_id": pid,
        "status": status,
        "engine": ENGINE,
        "ac_ref": ac_ref,
        "wa": [],
        "discard_reason": discard,
        "triage": tri,
    }
    (folder / "validacao.json").write_text(json.dumps(data))


def make_pool(ids):
    problems = {
        pid: PoolProblem(
            split="train",
            shard_index=0,
            macrocategoria=M.LOGICA_DIRETA,
            raw_wa_count=120,
            raw_ac_count=2,
            source_row=i,
        )
        for i, pid in enumerate(ids)
    }
    counts = PoolCounts(funnel={"read": 10}, rejections={}, eligible=len(ids))
    return Pool(
        hf_dataset=config.HF_DATASET,
        hf_revision=config.HF_REVISION,
        seed=42,
        counts=counts,
        order=sorted(problems),
        problems=problems,
    )


@pytest.fixture()
def root(tmp_path):
    store.ensure_work_dir(tmp_path)
    return tmp_path


def test_every_problem_whose_ac_ran_counts_as_an_ac_tested(root):
    write_problem(root, "1_A", "discarded", ac_ref=code(), discard="insufficient_wa")
    write_problem(root, "2_A", "pending_triage", ac_ref=code("TLE"), tri=triage("2_A", "TLE"))
    write_problem(root, "3_A", "discarded", ac_ref=None, discard="insufficient_raw_wa")
    state = rep.collect_validation_state(root, make_pool(["1_A", "2_A", "3_A"]))
    assert state.ac_tested == 2  # the third never ran its AC


def test_triage_by_cause_splits_format_only_tle_and_the_rest(root):
    write_problem(root, "1_A", "pending_triage", ac_ref=code("WA"), tri=triage("1_A", "WA", True))
    write_problem(root, "2_A", "pending_triage", ac_ref=code("TLE"), tri=triage("2_A", "TLE"))
    write_problem(root, "3_A", "pending_triage", ac_ref=code("WA"), tri=triage("3_A", "WA", False))
    write_problem(root, "4_A", "pending_triage", ac_ref=code("RE"), tri=triage("4_A", "RE"))
    write_problem(root, "5_A", "pending_triage", ac_ref=code("CE"), tri=triage("5_A", "CE"))
    state = rep.collect_validation_state(root, make_pool([f"{i}_A" for i in range(1, 6)]))
    assert state.triage_by_cause == {"format_only": 1, "tle": 1, "other": 3}


def test_only_selection_stage_failures_count_by_cause(root):
    write_problem(
        root, "1_A", "pending_triage", ac_ref=code("TLE"), tri=triage("1_A", "TLE", stage="audit")
    )
    state = rep.collect_validation_state(root, make_pool(["1_A"]))
    assert state.triage_by_cause == {"format_only": 0, "tle": 0, "other": 0}
    assert len(state.pending) == 1  # it is still listed for triage


def test_the_report_carries_both_numbers(root):
    write_problem(root, "1_A", "pending_triage", ac_ref=code("TLE"), tri=triage("1_A", "TLE"))
    pool = make_pool(["1_A"])
    state = rep.collect_validation_state(root, pool)
    report = rep.build_report(
        pool,
        pending_triage=state.pending,
        ac_tested=state.ac_tested,
        triage_by_cause=state.triage_by_cause,
    )
    assert report.ac_tested == 1
    assert report.triage_by_cause == {"format_only": 0, "tle": 1, "other": 0}
    assert ExtractionReport.model_validate_json(report.model_dump_json()) == report


def test_a_report_without_validation_has_zero_ac_tested_and_zero_causes():
    report = rep.build_report(make_pool(["1_A"]))
    assert report.ac_tested == 0
    assert report.triage_by_cause == {"format_only": 0, "tle": 0, "other": 0}


def test_the_markdown_shows_the_ratios_against_the_reopening_threshold():
    report = rep.build_report(
        make_pool(["1_A"]),
        ac_tested=10,
        triage_by_cause={"format_only": 2, "tle": 0, "other": 0},
    )
    text = rep.render_markdown(report)
    assert "ACs testados: 10" in text
    assert "20%" in text and "10%" in text  # ratio and threshold
    assert "reabrir" in text.lower()  # 20% > 10%: the rule must be reopened


def test_the_markdown_does_not_ask_to_reopen_within_the_threshold():
    report = rep.build_report(
        make_pool(["1_A"]),
        ac_tested=12,
        triage_by_cause={"format_only": 1, "tle": 1, "other": 0},  # 8.3% each
    )
    assert "reabrir" not in rep.render_markdown(report).lower()


def test_the_ratio_is_not_computed_when_no_ac_was_tested():
    text = rep.render_markdown(rep.build_report(make_pool(["1_A"])))
    assert "ACs testados: 0" in text and "%" not in text.split("ACs testados")[1].split("\n")[0]


def test_the_selfcheck_result_is_read_from_the_saved_file(root):
    assert rep.load_selfcheck(root) is None
    store.atomic_write_json(root / config.REPORTS_DIR / "selfcheck.json", {"ok": True, "passed": 9})
    assert rep.load_selfcheck(root) == {"ok": True, "passed": 9}
