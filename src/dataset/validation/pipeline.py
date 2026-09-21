"""The `validate` and `audit` commands, without the command line (so they can be tested).

`validate` runs the engine self-check FIRST and aborts if it fails (FR-010a). Then it walks the pool
in the recorded order, skipping closed problems, until enough problems are `complete` (FR-016).
An AC that fails is interrupted at once and goes to triage, and the run continues with the next
problem (FR-011b); the manual inspection of those cases is DEFERRED (decision D17): they are
inspected only if the target is missed once the rest of the pool is done, so the exit code is 0
whenever the target is reached. Problems with too few WA are discarded (D4); an `InfraError` is retried once and, if it persists, propagates
with the problem left in ``building/`` (FR-010). Nothing here relaxes a criterion: a deficit is
reported, never hidden (FR-017).
"""

import json
from collections.abc import Callable
from pathlib import Path

from dataset import config
from dataset.persistence import report as reporting
from dataset.persistence import store
from dataset.schemas.pool import Pool, RawProblem
from dataset.validation import audit as auditing
from dataset.validation import problem as validating
from dataset.validation.runtime import Runtime
from sandbox.types import InfraError

EXIT_OK = 0
EXIT_FAILURE = 1
INFRA_RETRIES = 1

RuntimeFactory = Callable[[int], Runtime]
Out = Callable[[str], None]


class UsageError(Exception):
    """A request that cannot be served (for example a problem outside the pool)."""


class NoPoolError(UsageError):
    """There is no `pool.json`: the extraction has not run (a data failure, exit code 1)."""


def _read_pool(root: Path) -> Pool:
    path = Path(root) / config.STAGING_DIR / "pool.json"
    if not path.is_file():
        raise NoPoolError("no pool found; run `python -m dataset extract` first")
    return Pool.model_validate(store.read_json(path))


def _selfcheck_payload(report) -> dict:
    return {
        "ok": report.ok,
        "passed": sum(case.passed for case in report.cases),
        "cases": [
            {
                "name": case.name,
                "expected": case.expected.value,
                "obtained": case.obtained.value,
                "standard_used": case.standard_used,
                "stable": case.stable,
                "passed": case.passed,
            }
            for case in report.cases
        ],
    }


def _write_report(root: Path, pool: Pool) -> None:
    state = reporting.collect_validation_state(root, pool)
    report = reporting.build_report(
        pool,
        included=state.included,
        pending_triage=state.pending,
        discarded_by_reason=state.discarded,
        selection_final=state.selection_is_final(pool),
        engine_selfcheck=reporting.load_selfcheck(root),
        ac_tested=state.ac_tested,
        triage_by_cause=state.triage_by_cause,
    )
    reporting.write_report(root, report)


def _validate_with_retry(root: Path, raw: RawProblem, runtime: Runtime) -> validating.ProblemResult:
    attempt = 0
    while True:
        try:
            return validating.validate_problem(root, raw, runtime)
        except InfraError:
            attempt += 1
            if attempt > INFRA_RETRIES:
                raise  # the problem stays in building/; the command ends with exit code 3


def _summary(result: validating.ProblemResult) -> str:
    stats = " ".join(f"{kind}={n}" for kind, n in sorted(result.stats.items()))
    detail = f", {result.discard_reason}" if result.discard_reason else ""
    return (
        f"{result.problem_id}: {result.status}{detail} "
        f"(AC {result.ac_verdict or '-'}; {result.consumed} candidates: {stats or '-'}; "
        f"{result.seconds:.1f} s)"
    )


def _log(root: Path, result: validating.ProblemResult) -> None:
    path = Path(root) / config.REPORTS_DIR / "validation_log.jsonl"
    record = {
        "problem_id": result.problem_id,
        "status": result.status,
        "discard_reason": result.discard_reason,
        "ac_verdict": result.ac_verdict,
        "stats": dict(sorted(result.stats.items())),
        "consumed": result.consumed,
        "seconds": round(result.seconds, 3),
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
    store.chown_to_host(path)


def run_validate(
    root: Path,
    *,
    target: int,
    workers: int,
    problem: str | None,
    runtime_factory: RuntimeFactory,
    selfcheck_fn: Callable,
    out: Out = print,
) -> int:
    """Validate the pool in order; return the exit code (0 target reached with no new triage)."""
    root = Path(root)
    check = selfcheck_fn()
    out(check.render())
    if not check.ok:
        out("selfcheck FAILED: the engine is not trustworthy, nothing was validated")
        return EXIT_FAILURE
    store.ensure_work_dir(root)
    store.atomic_write_json(root / config.REPORTS_DIR / "selfcheck.json", _selfcheck_payload(check))
    pool = _read_pool(root)
    if problem is not None and problem not in pool.problems:
        raise UsageError(f"{problem} is not in the pool")
    removed = store.reset_building(root)
    if removed:
        out(f"discarded {removed} partial problem(s) left in building/ by an interrupted run")

    order = [problem] if problem is not None else list(pool.order)
    state = reporting.collect_validation_state(root, pool)
    included = len(state.included)
    processed_any = False
    runtime = runtime_factory(workers)
    try:
        for pid in order:
            if problem is None and included >= target:
                break
            if store.is_closed(root, pid):
                out(f"{pid}: already closed ({store.problem_status(root, pid)}), skipped")
                continue
            raw = RawProblem.model_validate(
                store.read_json_gz(root / config.RAW_DIR / f"{pid}.json.gz")
            )
            result = _validate_with_retry(root, raw, runtime)
            processed_any = True
            out(_summary(result))
            _log(root, result)
            if result.status == "complete":
                included += 1
    finally:
        runtime.close()
    _write_report(root, pool)

    if problem is not None:
        ok = store.problem_status(root, problem) == "complete"
        return EXIT_OK if ok else EXIT_FAILURE
    deficit = max(0, target - included)
    out(f"included {included} of {target} (deficit {deficit})")
    waiting = len(reporting.collect_validation_state(root, pool).pending)
    if waiting and deficit == 0:
        out(
            f"{waiting} problem(s) set aside in pending_triage and not inspected: the target was "
            "reached without them (decision D17)"
        )
    elif waiting:
        out(
            f"{waiting} problem(s) in pending_triage need individual inspection now: the target "
            "was not reached with the rest of the pool (decision D17)"
        )
    if not processed_any and deficit:
        out("nothing left to validate in the pool")
    return EXIT_OK if deficit == 0 else EXIT_FAILURE


def run_audit(
    root: Path,
    *,
    problems: list[str],
    workers: int,
    runtime_factory: RuntimeFactory,
    out: Out = print,
) -> int:
    """Re-run the engine over closed problems; exit 1 on any divergence (FR-015a)."""
    root = Path(root)
    pool = _read_pool(root)
    if not problems:
        state_dir = root / config.PROBLEMS_DIR
        problems = (
            sorted(
                p.name
                for p in state_dir.iterdir()
                if store.problem_status(root, p.name) == "complete"
            )
            if state_dir.is_dir()
            else []
        )
    diverged = False
    runtime = runtime_factory(workers)
    try:
        for pid in problems:
            result = auditing.audit_problem(root, pid, runtime)
            if result.skipped:
                out(f"{pid}: skipped (status {result.skipped})")
            elif result.triage is not None:
                diverged = True
                out(f"{pid}: audit FAILED, AC_ref is now {result.triage.verdict}; pending_triage")
            elif result.wa_mismatches:
                diverged = True
                names = ", ".join(f"{m.file} ({m.obtained})" for m in result.wa_mismatches)
                out(f"{pid}: WA divergence (reported only): {names}")
            else:
                out(f"{pid}: ok (AC_ref and {result.wa_checked} WA as recorded)")
    finally:
        runtime.close()
    _write_report(root, pool)
    return EXIT_FAILURE if diverged else EXIT_OK
