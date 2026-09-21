"""Validate ONE problem end to end and persist its folder (FR-011a, FR-019 to FR-024).

The folder is built in ``data/work/building/<id>/`` and closed with a single atomic rename, so an
interruption never leaves a half-written problem in ``problems/``. Three outcomes are possible:

- ``complete``: `AC_ref` passed the whole official suite and exactly 100 WA were retained;
- ``pending_triage``: `AC_ref` failed in the engine (FR-011b); the folder keeps only
  ``validacao.json`` and ``AC_candidate.cpp`` and no WA candidate is even compiled;
- ``discarded``: fewer than 100 WA can be validated (D4); only ``validacao.json`` is kept.

``InfraError`` is not an outcome: it propagates and the problem stays in ``building/``.
"""

import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from dataset import config
from dataset.filtering.classification import classify
from dataset.persistence import store
from dataset.schemas.metadata import Metadata
from dataset.schemas.pool import RawProblem
from dataset.schemas.testes import Testes
from dataset.schemas.validacao import CodeValidation, EngineInfo, Validacao
from dataset.validation import ac, wa
from dataset.validation.runtime import Runtime
from dataset.validation.suite import Suite, suite_from_raw
from sandbox.compiler import COMPILE_FLAGS, STANDARD_CASCADE
from sandbox.limits import STACK_LIMIT_BYTES
from sandbox.types import ExecutionLimits


def utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class ProblemResult:
    problem_id: str
    status: str  # complete | pending_triage | discarded
    discard_reason: str | None = None
    ac_verdict: str | None = None  # verdict of AC_ref, None if it was not run
    stats: Counter = field(default_factory=Counter)  # WA candidates consumed, by outcome
    consumed: int = 0
    seconds: float = 0.0


def engine_info(engine_gcc: str, limits: ExecutionLimits) -> EngineInfo:
    return EngineInfo(
        gcc_version=engine_gcc,
        flags=list(COMPILE_FLAGS),
        standard_cascade=list(STANDARD_CASCADE),
        stack_limit_bytes=STACK_LIMIT_BYTES,
        time_limit_seconds=limits.time_limit_seconds,
        memory_limit_bytes=limits.memory_limit_bytes,
        stability_runs=config.STABILITY_RUNS,
    )


def _metadata(raw: RawProblem, raw_wa: int, timestamp: str) -> Metadata:
    return Metadata(
        problem_id=raw.problem_id,
        cf_contest_id=raw.cf_contest_id,
        cf_index=raw.cf_index,
        name=raw.name,
        source="CODEFORCES",
        cf_rating=raw.cf_rating,
        cf_points=raw.cf_points,
        cf_tags=raw.cf_tags,
        macrocategoria=classify(raw.cf_tags),
        time_limit_seconds=raw.time_limit_seconds,
        memory_limit_bytes=raw.memory_limit_bytes,
        is_description_translated=False,
        dataset_split_origem=raw.split,
        num_wa_brutos_disponiveis=raw_wa,
        num_wa_validados=config.WA_PER_PROBLEM,
        extraction_timestamp=timestamp,
    )


def _testes(raw: RawProblem) -> Testes:
    return Testes.from_parallel_lists(
        raw.problem_id,
        public=(raw.public_tests.input, raw.public_tests.output),
        private=(raw.private_tests.input, raw.private_tests.output),
        generated=(raw.generated_tests.input, raw.generated_tests.output),
    )


def _close_discarded(
    root: Path, folder: Path, pid: str, engine: EngineInfo, code: CodeValidation | None, reason: str
) -> None:
    validacao = Validacao(
        problem_id=pid,
        status="discarded",
        engine=engine,
        ac_ref=code,
        wa=[],
        discard_reason=reason,  # type: ignore[arg-type]
        triage=None,
    )
    store.write_problem_json(folder, "validacao.json", validacao)
    store.finalize_building(root, pid)


def validate_problem(
    root: Path,
    raw: RawProblem,
    runtime: Runtime,
    *,
    now: Callable[[], str] = utc_now,
) -> ProblemResult:
    """Validate ``raw`` with the engine of ``runtime`` and close its folder."""
    started = time.monotonic()
    pid = raw.problem_id
    suite: Suite = suite_from_raw(raw)
    limits = ExecutionLimits(raw.time_limit_seconds, raw.memory_limit_bytes)
    engine = engine_info(runtime.engine.gcc_version, limits)
    folder = store.start_building(root, pid)
    candidates, raw_count = wa.select_candidates(raw)

    def finish(result: ProblemResult) -> ProblemResult:
        result.seconds = time.monotonic() - started
        return result

    if raw_count < config.WA_PER_PROBLEM:  # the extraction pre-check, kept as a safeguard
        _close_discarded(root, folder, pid, engine, None, "insufficient_raw_wa")
        return finish(ProblemResult(pid, "discarded", "insufficient_raw_wa"))

    source = ac.choose_ac_source(raw)
    outcome = ac.run_ac(
        pid,
        source,
        suite,
        limits,
        runtime.engine,
        runtime.main_slot,
        stage="selection",
        file_name=ac.AC_REF_FILE,
    )
    verdict = outcome.code.verdict.value
    if not outcome.passed:
        code = outcome.code.model_copy(update={"file": ac.AC_CANDIDATE_FILE})
        validacao = Validacao(
            problem_id=pid,
            status="pending_triage",
            engine=engine,
            ac_ref=code,
            wa=[],
            discard_reason=None,
            triage=outcome.triage,
        )
        store.write_problem_text(folder, ac.AC_CANDIDATE_FILE, source)
        store.write_problem_json(folder, "validacao.json", validacao)
        store.finalize_building(root, pid)
        return finish(ProblemResult(pid, "pending_triage", ac_verdict=verdict))

    collected = wa.collect_wa(candidates, runtime.submitter(suite, limits), window=runtime.window)
    if collected.insufficient:
        _close_discarded(root, folder, pid, engine, outcome.code, "insufficient_wa")
        return finish(
            ProblemResult(
                pid,
                "discarded",
                "insufficient_wa",
                verdict,
                collected.stats,
                collected.consumed,
            )
        )

    timestamp = store.preserved_timestamp(folder, now=now())
    metadata = _metadata(raw, raw_count, timestamp)
    validacao = Validacao(
        problem_id=pid,
        status="complete",
        engine=engine,
        ac_ref=outcome.code,
        wa=[item.validation for item in collected.retained],
        discard_reason=None,
        triage=None,
    )
    store.write_problem_text(folder, "enunciado.md", raw.description)
    store.write_problem_text(folder, ac.AC_REF_FILE, source)
    for item in collected.retained:
        store.write_problem_text(folder, item.validation.file, item.source)
    store.write_problem_json(folder, "testes.json", _testes(raw))
    store.write_problem_json(folder, "metadata.json", metadata)
    store.write_problem_json(folder, "validacao.json", validacao)
    store.finalize_building(root, pid)
    return finish(
        ProblemResult(pid, "complete", None, verdict, collected.stats, collected.consumed)
    )
