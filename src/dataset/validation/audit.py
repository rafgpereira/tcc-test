"""Audit of a validated problem: run the engine again and compare with `validacao.json` (FR-015a).

`AC_ref` goes first. If it no longer gets AC, that problem is interrupted at once: its
`validacao.json` becomes ``pending_triage`` with a triage record of stage ``audit`` and the WA are
NOT evaluated (FR-011b, decision D8). A WA whose verdict or deciding test changed is only REPORTED:
the audit never rewrites a problem because of a WA. Infrastructure failure propagates.
"""

from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

from dataset import config
from dataset.persistence import store
from dataset.schemas.testes import Testes
from dataset.schemas.validacao import TriageRecord, Validacao
from dataset.validation import ac, wa
from dataset.validation.runtime import Runtime
from dataset.validation.suite import suite_from_testes
from sandbox.types import ExecutionLimits


@dataclass(frozen=True)
class WaMismatch:
    file: str
    recorded: str  # what validacao.json says
    obtained: str  # the outcome kind now: wa (other test), tle, mle, re, ce, ac or unstable


@dataclass
class AuditResult:
    problem_id: str
    ac_ok: bool | None = None  # None when the problem was skipped
    wa_checked: int = 0
    wa_mismatches: list[WaMismatch] = field(default_factory=list)
    triage: TriageRecord | None = None
    skipped: str | None = None  # why the problem was not audited

    @property
    def diverged(self) -> bool:
        return self.triage is not None or bool(self.wa_mismatches)


def audit_problem(root: Path, problem_id: str, runtime: Runtime) -> AuditResult:
    """Audit one problem of ``data/work/problems/``; only `complete` problems are audited."""
    folder = store.problem_path(root, problem_id)
    if not (folder / "validacao.json").is_file():
        raise FileNotFoundError(f"{problem_id} is not a closed problem of {config.PROBLEMS_DIR}")
    validacao = Validacao.from_folder(folder)
    if validacao.status != "complete":
        return AuditResult(problem_id, skipped=validacao.status)

    suite = suite_from_testes(Testes.from_folder(folder))
    limits = ExecutionLimits(
        validacao.engine.time_limit_seconds, validacao.engine.memory_limit_bytes
    )
    source = (folder / ac.AC_REF_FILE).read_text(encoding="utf-8")
    outcome = ac.run_ac(
        problem_id,
        source,
        suite,
        limits,
        runtime.engine,
        runtime.main_slot,
        stage="audit",
        file_name=ac.AC_REF_FILE,
    )
    if not outcome.passed:
        interrupted = validacao.model_copy(
            update={
                "status": "pending_triage",
                "ac_ref": outcome.code,
                "wa": [],
                "triage": outcome.triage,
            }
        )
        store.write_problem_json(folder, "validacao.json", interrupted)
        return AuditResult(problem_id, ac_ok=False, triage=outcome.triage)

    result = AuditResult(problem_id, ac_ok=True)
    submit = runtime.submitter(suite, limits)
    pending: deque = deque()
    recorded = list(validacao.wa)
    next_index = 0
    while next_index < len(recorded) or pending:
        while next_index < len(recorded) and len(pending) < max(1, runtime.window):
            item = recorded[next_index]
            text = (folder / item.file).read_text(encoding="utf-8")
            candidate = wa.Candidate(next_index, item.source_index, text)
            pending.append((item, submit(candidate)))
            next_index += 1
        item, future = pending.popleft()
        outcome_wa = future.result()
        result.wa_checked += 1
        same_test = (
            outcome_wa.validation is not None
            and outcome_wa.validation.deciding_test == item.deciding_test
        )
        if outcome_wa.kind != "wa" or not same_test:
            result.wa_mismatches.append(WaMismatch(item.file, "wa", outcome_wa.kind))
    return result
