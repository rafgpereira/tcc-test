"""Build ``manifests/slm_generation_report.json`` from ``data/suites/slm/`` (read only).

The scope is always every problem of the dataset × the 3 scenarios, so the discard rate is over
all of them (N is never reduced to the suites that survived). A damaged combination stops the
report: numbers over files that do not agree with each other would be worthless.
"""

from collections import Counter
from pathlib import Path

from ai_clients import config, store
from ai_clients.problem import list_problem_ids
from ai_clients.schemas.common import AttemptFailure, InputDiscard
from ai_clients.schemas.report import (
    GROUPS,
    TOTAL,
    AttemptCounts,
    CombinationCounts,
    SizeStats,
    SlmGenerationReport,
    TokenCounts,
)
from dataset.persistence import store as files


class DamagedTreeError(Exception):
    """Some combinations are damaged; ``damaged`` lists them."""

    def __init__(self, damaged: list[store.DamagedCombination]) -> None:
        self.damaged = damaged
        super().__init__(f"{len(damaged)} damaged combination(s)")


def _quantile(values: list[int], q: float) -> float:
    """Linear interpolation between the closest ranks (the default of numpy)."""
    position = q * (len(values) - 1)
    low = int(position)
    high = min(low + 1, len(values) - 1)
    return values[low] + (values[high] - values[low]) * (position - low)


def size_stats(sizes: list[int]) -> SizeStats:
    values = sorted(sizes)
    if not values:
        return SizeStats(count=0, min=None, p25=None, median=None, p75=None, max=None, histogram={})
    return SizeStats(
        count=len(values),
        min=values[0],
        p25=_quantile(values, 0.25),
        median=_quantile(values, 0.5),
        p75=_quantile(values, 0.75),
        max=values[-1],
        histogram={str(size): count for size, count in sorted(Counter(values).items())},
    )


def build_report(root: Path) -> SlmGenerationReport:
    """Aggregate every combination; ``DamagedTreeError`` if any is damaged."""
    root = Path(root)
    run = store.read_run(root)
    counts = {group: Counter() for group in GROUPS}
    sizes: dict[str, list[int]] = {group: [] for group in GROUPS}
    failures = {reason: Counter() for reason in AttemptFailure}
    discards: Counter = Counter()
    hardware: Counter = Counter()
    seeds: dict[str, list[int]] = {}
    damaged: list[store.DamagedCombination] = []
    length, fences, empty = Counter(), Counter(), Counter()
    calls = failed = duplicates = prompt_total = eval_total = prompt_max = 0
    duration_ns = 0
    for problem_id in list_problem_ids(root):
        for scenario in config.SCENARIOS:
            try:
                state = store.combination_state(root, problem_id, scenario, run)
                attempts = store.attempt_files(root, problem_id, scenario, run)
                # terminal: suite.json itself; finalizable: the suite.json still to be written
                suite = store.expected_suite(root, problem_id, scenario, run)
            except store.DamagedCombination as exc:
                damaged.append(exc)
                continue
            kind = state.kind if suite is None else suite.status.value
            if kind == "accepted":
                for group in (TOTAL, scenario):
                    sizes[group].append(suite.suite_size)
                duplicates += suite.duplicate_inputs
            for group in (TOTAL, scenario):
                counts[group][kind] += 1
            for generation in attempts.generations:
                calls += 1
                hardware[generation.hardware_label] += 1
                seeds.setdefault(f"{problem_id}/{scenario}", []).append(generation.seed)
                meta = generation.ollama
                if meta is not None:  # None: the model failed the call, nothing was answered
                    prompt_total += meta.prompt_eval_count
                    eval_total += meta.eval_count
                    prompt_max = max(prompt_max, meta.prompt_eval_count)
                    duration_ns += meta.total_duration_ns
                parse = generation.parse
                for group in (TOTAL, scenario):
                    length[group] += meta is not None and meta.done_reason == "length"
                    if parse.ok:
                        fences[group] += parse.markdown_fence_removed
                        empty[group] += parse.empty_inputs
                execution = attempts.executions.get(generation.attempt)
                if generation.model_failure is not None:
                    reason = AttemptFailure(generation.model_failure.reason)
                elif not parse.ok:
                    reason = AttemptFailure.UNPARSEABLE_RESPONSE
                elif execution is None or execution.outcome == "accepted":
                    reason = None
                else:
                    reason = AttemptFailure(execution.outcome)
                if execution is not None:
                    discards.update(item.discard for item in execution.inputs if not item.kept)
                if reason is not None:
                    failed += 1
                    failures[reason][str(generation.attempt)] += 1
    if damaged:
        raise DamagedTreeError(damaged)
    combinations = {
        group: CombinationCounts(
            total=sum(counts[group].values()),
            accepted=counts[group]["accepted"],
            discarded=counts[group]["discarded"],
            pending_generation=counts[group]["pending_generation"],
            pending_execution=counts[group]["pending_execution"],
        )
        for group in GROUPS
    }
    numbers = [str(n) for n in range(1, config.MAX_ATTEMPTS + 1)]
    return SlmGenerationReport(
        model=run.model,
        model_digest=run.model_digest,
        ollama_version=run.ollama_version,
        options=run.options,
        seed_base=run.seed_base,
        prompt_template_sha256=run.prompt_template_sha256,
        dataset_manifest_sha256=run.dataset_manifest_sha256,
        combinations=combinations,
        discard_rate={
            group: (c.discarded / c.total if c.total else 0.0) for group, c in combinations.items()
        },
        suite_size={group: size_stats(sizes[group]) for group in GROUPS},
        attempts=AttemptCounts(total=calls, failed=failed),
        attempt_failures={
            reason: {n: failures[reason][n] for n in numbers} for reason in AttemptFailure
        },
        input_discards={reason: discards[reason] for reason in InputDiscard},
        duplicate_inputs=duplicates,
        done_reason_length={group: length[group] for group in GROUPS},
        markdown_fences_removed={group: fences[group] for group in GROUPS},
        empty_inputs={group: empty[group] for group in GROUPS},
        tokens=TokenCounts(prompt_total=prompt_total, eval_total=eval_total, prompt_max=prompt_max),
        duration_s_total=duration_ns / 1e9,
        hardware=dict(sorted(hardware.items())),
        seeds=dict(sorted(seeds.items())),
    )


def write_report(root: Path, report: SlmGenerationReport) -> Path:
    path = Path(root) / config.REPORT_PATH
    path.parent.mkdir(parents=True, exist_ok=True)  # `manifests/` is versioned, ordinary mode
    files.atomic_write_json(path, report)
    return path
