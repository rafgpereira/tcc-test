"""Replace a WA candidate that failed the audit's re-check (decision D18; T072 follow-up).

A real run of `validate` on the full pool found 13 WA (in 12 of 200 complete problems) whose result
was not reproducible: `audit` re-ran them and got a different verdict or a different deciding test.
Inspection of the sources showed the common pattern: the candidate reads past the end of an array,
uses an uninitialized variable, or sits right at the time limit boundary, so its exact behavior
depends on things outside the input (uninitialized memory content, scheduling jitter) rather than on
the input alone. Such a candidate is a bad "ground truth" fault for the metrics, which assume a
fixed, reproducible failure (FR-014 already requires exactly 100 WA in a fixed order; this makes the
"exactly" hold up under re-execution too).

The fix does not touch the engine or `outputs_equal`: it raises the bar for how many times a
candidate must independently agree before it is trusted (from 2 runs to CONFIRMATION_PASSES
independent calls of the same two-run stability check of `wa.evaluate_candidate`, ALL of which must
agree with EACH OTHER, not just the last two), and, for any candidate that still fails, walks the
SAME deterministic order used by the original selection (FR-014, `wa.select_candidates`) to the
next untried candidate, keeping the `WA_<n>.cpp` numbering and the 100 count fixed. It never
weakens a verdict and never accepts a candidate on the strength of a single confirmation.

**Bug found and fixed (2026-09-22, second real run)**: the first version of this module ran
``CONFIRMATION_PASSES`` calls in a loop but only kept the LAST one (each iteration overwrote the
same variable), then made one more separate call and compared only those last two — the very
first call was used solely to gate on "still WA", never cross-checked, and a fourth, completely
separate call supplied the value actually written to disk without ever being compared to anything.
So a candidate could be recorded on the strength of two calls agreeing by chance while an earlier,
never-compared call had already disagreed. This explains why several repaired candidates from the
first real run showed up divergent again on the very next audit. Fixed by collecting every pass
and requiring all of them to agree with the first one, and by writing the same, already-confirmed
outcome that was checked (never an extra, unchecked call). ``CONFIRMATION_PASSES`` was also raised
from 2 to 3 (6 runs, not 4) given how often a real repaired candidate still turned out flaky.
"""

from dataclasses import dataclass, field
from pathlib import Path

from dataset import config
from dataset.persistence import store
from dataset.schemas.pool import RawProblem
from dataset.schemas.validacao import Validacao
from dataset.validation import ac, wa
from dataset.validation.audit import WaMismatch
from dataset.validation.runtime import Runtime
from dataset.validation.suite import suite_from_raw
from sandbox.types import ExecutionLimits

CONFIRMATION_PASSES = 3  # each is wa.STABILITY_RUNS (2) independent runs: 6 runs in total,
# raised from 2 after the second real audit still found repaired candidates flaky (see above)


class RepairExhausted(Exception):
    """No untried candidate of the deterministic order could be independently confirmed."""


@dataclass
class RepairOutcome:
    problem_id: str
    repaired: list[str] = field(default_factory=list)  # WA_<n>.cpp files actually replaced
    failed: list[str] = field(default_factory=list)  # left as recorded (should stay empty)


def _load_raw(root: Path, problem_id: str) -> RawProblem:
    path = Path(root) / config.RAW_DIR / f"{problem_id}.json.gz"
    return RawProblem.model_validate(store.read_json_gz(path))


def _confirm(candidate: wa.Candidate, suite, limits, engine, slot: int):
    """Run ``CONFIRMATION_PASSES`` independent stability-checked evaluations of ``candidate``.

    Each pass already runs the candidate twice (``wa.STABILITY_RUNS``) and requires them to agree
    with each other; here EVERY pass, not just the last two, must also agree with the first pass
    (same verdict WA, same deciding test) before the candidate is trusted. Returns the confirmed
    ``WaValidation`` — one of the passes that were actually checked, never an extra unchecked call
    — or ``None`` if any pass disagreed.
    """
    passes: list[wa.CandidateOutcome] = []
    for _ in range(CONFIRMATION_PASSES):
        outcome = wa.evaluate_candidate(candidate, suite, limits, engine, slot)
        if outcome.kind != "wa":
            return None
        passes.append(outcome)
    reference = passes[0].validation.deciding_test
    if any(p.validation.deciding_test != reference for p in passes[1:]):
        return None
    return passes[-1].validation


def repair_problem(
    root: Path,
    problem_id: str,
    mismatches: list[WaMismatch],
    runtime: Runtime,
    *,
    consumed: int,
    raw: RawProblem | None = None,
) -> RepairOutcome:
    """Replace each mismatched ``WA_<n>.cpp`` with the next untried, doubly-confirmed candidate."""
    outcome = RepairOutcome(problem_id)
    if not mismatches:
        return outcome
    raw = raw or _load_raw(root, problem_id)
    folder = store.problem_path(root, problem_id)
    validacao = Validacao.from_folder(folder)
    existing_sha = {item.sha256 for item in validacao.wa}
    candidates, _ = wa.select_candidates(raw)
    untried = iter(candidates[consumed:])
    suite = suite_from_raw(raw)
    limits = ExecutionLimits(raw.time_limit_seconds, raw.memory_limit_bytes)

    by_file = {item.file: item for item in validacao.wa}
    for mismatch in mismatches:
        for candidate in untried:
            if ac.sha256_of(candidate.source) in existing_sha:
                continue  # already one of the other 99 (candidates are pre-deduplicated globally)
            confirmed = _confirm(candidate, suite, limits, runtime.engine, runtime.main_slot)
            if confirmed is None:
                continue
            replacement = confirmed.model_copy(update={"file": mismatch.file})
            store.write_problem_text(folder, mismatch.file, candidate.source)
            by_file[mismatch.file] = replacement
            existing_sha.add(replacement.sha256)
            outcome.repaired.append(mismatch.file)
            break
        else:
            raise RepairExhausted(
                f"{problem_id}: no untried candidate left to replace {mismatch.file}"
            )

    ordered = [by_file[f"WA_{i}.cpp"] for i in range(1, config.WA_PER_PROBLEM + 1)]
    updated = validacao.model_copy(update={"wa": ordered})
    store.write_problem_json(folder, "validacao.json", updated)
    return outcome
