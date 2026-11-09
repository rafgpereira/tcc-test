"""The summary of an evaluation set and the consolidated table (FR-017; data-model.md).

``results.csv`` is derived from the scenario files only (research R6), in a fixed order (problem,
scenario, then the order of the targets), so it never diverges from them and is byte for byte the
same when rebuilt.
"""

import csv
import io
from collections import Counter
from pathlib import Path

from dataset.persistence import store as base_store
from evaluation import config, sources, store
from evaluation.schemas.report import EvaluationReport
from evaluation.schemas.result import CombinationResult

CSV_COLUMNS = (
    "set",
    "model",
    "problem_id",
    "scenario",
    "suite_status",
    "has_suite",
    "suite_size",
    "ac_approved",
    "ac_wrong_output_tests",
    "ac_runtime_error_tests",
    "ac_unstable_tests",
    "corrected_oracle_tests",
    "target",
    "kind",
    "compiled",
    "declared_detected",
    "declared_test_index",
    "declared_verdict",
    "corrected_detected",
    "corrected_test_index",
    "corrected_verdict",
    "tests_run",
)


def _cell(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _rows(result: CombinationResult) -> list[list[str]]:
    ac = result.ac
    head = [
        result.set,
        result.model,
        result.problem_id,
        result.scenario,
        result.suite_source.status,
        result.has_suite,
        result.suite_size,
        ac.approved if ac else None,
        sum(t.verdict == "wrong_output" for t in ac.tests) if ac else None,
        sum(t.verdict == "runtime_error" for t in ac.tests) if ac else None,
        sum(t.unstable for t in ac.tests) if ac else None,
        result.corrected_oracle_tests if ac else None,
    ]
    if not result.targets:
        return [[_cell(v) for v in head + [None] * 10]]
    rows = []
    for t in result.targets:
        rows.append(
            [
                _cell(v)
                for v in head
                + [
                    t.target,
                    t.kind,
                    t.compiled,
                    t.declared.detected,
                    t.declared.test_index,
                    t.declared.verdict,
                    t.corrected.detected,
                    t.corrected.test_index,
                    t.corrected.verdict,
                    t.tests_run,
                ]
            ]
        )
    return rows


def load_set(base: Path, set_name: str) -> dict[tuple[str, str], CombinationResult]:
    results = {}
    for problem_id in store.closed_problems(base, set_name):
        for scenario, result in store.read_problem(base, set_name, problem_id).items():
            results[(problem_id, scenario)] = result
    return results


def results_csv(results: dict[tuple[str, str], CombinationResult]) -> str:
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(CSV_COLUMNS)
    order = {s: i for i, s in enumerate(config.SCENARIOS)}
    for key in sorted(results, key=lambda k: (k[0], order[k[1]])):
        writer.writerows(_rows(results[key]))
    return out.getvalue()


def build_report(root: Path, base: Path, set_name: str) -> EvaluationReport:
    results = load_set(base, set_name)
    run_file = store.set_dir(base, set_name) / config.RUN_FILE
    expected = sources.dataset_problem_ids(root)
    missing = [f"{p} {s}" for p in expected for s in config.SCENARIOS if (p, s) not in results]
    without: Counter = Counter()
    ac_tests: Counter = Counter()
    ac_errors: Counter = Counter()
    unstable_targets: Counter = Counter()
    detected: Counter = Counter()
    not_compiled = []
    approved = rejected = ac_unstable = excluded = largest = 0
    elapsed = 0.0
    for (problem_id, scenario), r in sorted(results.items()):
        elapsed += r.elapsed_s
        excluded += r.corrected_oracle_excluded
        if not r.has_suite:
            without[r.no_suite_reason] += 1
            continue
        approved += r.ac.approved
        rejected += not r.ac.approved
        for t in r.ac.tests:
            ac_tests[t.verdict] += 1
            ac_unstable += t.unstable
            if t.error_kind:
                ac_errors[t.error_kind] += 1
            largest = max(largest, len(t.actual_output.encode("utf-8")))
        wa = sum(t.kind == "wa" for t in r.targets)
        mutants = sum(t.kind == "mutant" for t in r.targets)
        if (wa, mutants) != (config.WA_PER_PROBLEM, config.MUTANTS_PER_PROBLEM):
            missing.append(f"{problem_id} {scenario}: {wa} WAs and {mutants} mutants")
        for t in r.targets:
            unstable_targets[t.kind] += len(t.unstable_tests)
            if not t.compiled:
                not_compiled.append(f"{problem_id} {scenario} {t.target}")
        for name, values in r.detected.model_dump().items():
            detected[name] += len(values)
    return EvaluationReport(
        set=set_name,
        run_sha256=store.sha256_of_file(run_file) if run_file.is_file() else "",
        complete=not missing,
        missing=missing,
        problems=len({p for p, _ in results}),
        combinations=len(results),
        evaluated=sum(r.has_suite for r in results.values()),
        without_suite=dict(sorted(without.items())),
        ac_approved=approved,
        ac_rejected=rejected,
        ac_tests={k: ac_tests.get(k, 0) for k in ("passed", "wrong_output", "runtime_error")},
        ac_errors={k: ac_errors.get(k, 0) for k in ("RE", "TLE", "MLE")},
        ac_unstable_tests=ac_unstable,
        target_unstable_tests={k: unstable_targets.get(k, 0) for k in ("wa", "mutant")},
        detected={
            k: detected.get(k, 0)
            for k in ("declared_wa", "declared_mutants", "corrected_wa", "corrected_mutants")
        },
        corrected_oracle_excluded_tests=excluded,
        targets_not_compiled=not_compiled,
        largest_ac_output_bytes=largest,
        elapsed_s=round(elapsed, 3),
    )


def write_outputs(root: Path, base: Path, set_name: str) -> tuple[Path, Path, EvaluationReport]:
    """Write ``results.csv`` (next to the set) and the report.

    The report of the default tree goes to ``manifests/`` (it is versioned with the package); the
    one of another tree (a check, a kept pilot) stays next to that tree, so it never touches the
    versioned files.
    """
    csv_path = store.set_dir(base, set_name) / config.RESULTS_CSV
    base_store.atomic_write_text(csv_path, results_csv(load_set(base, set_name)))
    report = build_report(root, base, set_name)
    if Path(base).resolve() == (Path(root) / config.EVALUATION_DIR).resolve():
        report_path = Path(root) / config.report_path(set_name)
    else:
        report_path = Path(base) / config.report_path(set_name).name
    report_path.parent.mkdir(parents=True, exist_ok=True)
    base_store.atomic_write_json(report_path, report)
    return csv_path, report_path, report


def render(report: EvaluationReport) -> str:
    d = report.detected
    state = "complete" if report.complete else f"INCOMPLETE ({len(report.missing)} missing)"
    lines = [
        (
            f"{report.set}: {report.combinations} combinations ({report.evaluated} evaluated, "
            f"{sum(report.without_suite.values())} without a suite), {state}"
        ),
        (
            f"  AC approved {report.ac_approved}, rejected {report.ac_rejected}; "
            f"AC tests {report.ac_tests}; errors {report.ac_errors}; "
            f"unstable {report.ac_unstable_tests}"
        ),
        (
            f"  detected (declared) WA {d['declared_wa']}, mutants {d['declared_mutants']}; "
            f"(corrected) WA {d['corrected_wa']}, mutants {d['corrected_mutants']}"
        ),
        (
            f"  tests excluded from the corrected oracle {report.corrected_oracle_excluded_tests}; "
            f"unstable target tests {report.target_unstable_tests}; "
            f"targets not compiled {len(report.targets_not_compiled)}; "
            f"evaluation time {report.elapsed_s:.0f} s"
        ),
    ]
    return "\n".join(lines)
