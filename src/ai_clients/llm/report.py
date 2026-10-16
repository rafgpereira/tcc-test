"""``manifests/<model>_generation_report.json`` from ``data/suites/<model>/`` (FR-025; read only).

The scope is always every problem of the dataset x the 3 scenarios (N is never reduced). A damaged
combination stops the report. No date is written: the same tree gives the same bytes. The total
cost is exactly the sum of the cost of every recorded call, barred ones included (SC-003).
"""

from collections import Counter
from pathlib import Path
from statistics import median

from pydantic import Field

from ai_clients.llm import config, store
from ai_clients.llm.schemas import LlmModel, PriceRow
from ai_clients.problem import list_problem_ids
from ai_clients.report import DamagedTreeError, size_stats
from ai_clients.schemas.common import NonNegative, Sha256Hex
from ai_clients.schemas.report import SizeStats
from dataset.persistence import store as files
from dataset.schemas.common import Schema

TOTAL = "total"
GROUPS = (*config.SCENARIOS, TOTAL)
DISCARD_COUNTERS = (
    "empty_tests",
    "abbreviated_tests",
    "markdown_fences_removed",
    "duplicate_inputs",
    "conflicting_outputs",
    "example_copies",
)


class CombinationCounts(Schema):
    total: NonNegative = 0
    accepted_predicted: NonNegative = 0
    discarded_manual: NonNegative = 0
    awaiting_manual: NonNegative = 0
    pending: NonNegative = 0


class Tokens(Schema):
    input: NonNegative = 0
    cached_input: NonNegative = 0
    output: NonNegative = 0
    reasoning: NonNegative = 0


class Costs(Schema):
    by_group: dict[str, float]  # scenario or total -> US$ of the attempts
    barred_cost_usd: float
    total: float  # attempts + barred answers (SC-003)
    price_rows_used: list[PriceRow]


class Latency(Schema):
    calls: NonNegative
    total_s: float
    mean_s: float | None
    median_s: float | None
    max_s: float | None


class Barred(Schema):
    count: NonNegative
    combinations: list[str]


class TemplateChangeLine(Schema):
    number: NonNegative
    from_sha256: Sha256Hex
    to_sha256: Sha256Hex
    changed_at: str
    reason: str
    combinations: NonNegative
    files: NonNegative


class LlmGenerationReport(Schema):
    schema_version: int = Field(1, ge=1, le=1)
    model_key: LlmModel
    model_requested: str
    request_parameters: dict
    template_sha256: Sha256Hex
    dataset_manifest_sha256: Sha256Hex
    models_returned: dict[str, NonNegative]
    combinations: dict[str, CombinationCounts]
    attempts_by_number: dict[str, NonNegative]  # "1".."3" -> calls recorded as that attempt
    failures: dict[str, dict[str, NonNegative]]  # failure -> attempt number -> attempts
    safety_blocks_by_category: dict[str, NonNegative] | None  # Gemini only (A13)
    truncated: dict[str, NonNegative]
    test_discards: dict[str, dict[str, NonNegative]]
    suite_size: dict[str, SizeStats]
    tokens: dict[str, Tokens]
    cost_usd: Costs
    latency_s: Latency
    barred: Barred
    template_changes: list[TemplateChangeLine]


def _round(value: float) -> float:
    return round(value, 8)


def build_report(root: Path, model: str) -> LlmGenerationReport:
    root = Path(root)
    run = store.read_run(root, model)
    problems = list_problem_ids(root)
    counts = {g: CombinationCounts() for g in GROUPS}
    by_number: Counter = Counter()
    failures: dict[str, Counter] = {}
    returned: Counter = Counter()
    blocks: Counter = Counter()
    truncated = Counter()
    discards = {g: Counter() for g in GROUPS}
    sizes: dict[str, list[int]] = {g: [] for g in GROUPS}
    tokens = {g: Counter() for g in GROUPS}
    costs: Counter = Counter()
    latencies: list[float] = []
    rows: dict[tuple, PriceRow] = {}
    damaged = []

    def account(record, group: str) -> None:
        for g in (group, TOTAL):
            tokens[g]["input"] += record.usage.input_tokens
            tokens[g]["cached_input"] += record.usage.cached_input_tokens
            tokens[g]["output"] += record.usage.output_tokens
            tokens[g]["reasoning"] += record.usage.reasoning_tokens or 0
        returned[record.model_returned] += 1
        latencies.append(record.latency_s)
        row = record.price_row
        rows[(row.model_key, row.valid_from)] = row

    for problem_id in problems:
        for scenario in config.SCENARIOS:
            try:
                state = store.combination_state(root, model, problem_id, scenario, run)
                attempts = store.attempt_files(root, model, problem_id, scenario, run).attempts
            except store.DamagedCombination as exc:
                damaged.append(exc)
                continue
            for g in (scenario, TOTAL):
                counts[g].total += 1
            if state.kind == "terminal":
                suite = store.read_suite(root, model, problem_id, scenario)
                for g in (scenario, TOTAL):
                    setattr(
                        counts[g], suite.status.value, getattr(counts[g], suite.status.value) + 1
                    )
                    if suite.tests:
                        sizes[g].append(suite.suite_size)
            else:
                kind = "awaiting_manual" if state.kind == "awaiting_manual" else "pending"
                for g in (scenario, TOTAL):
                    setattr(counts[g], kind, getattr(counts[g], kind) + 1)
            for record in attempts:
                by_number[str(record.attempt)] += 1
                account(record, scenario)
                for g in (scenario, TOTAL):
                    costs[g] += record.cost_usd
                parse = record.parse
                if parse.ok:
                    for g in (scenario, TOTAL):
                        for name in DISCARD_COUNTERS:
                            discards[g][name] += getattr(parse, name)
                    continue
                failure = parse.failure.value
                failures.setdefault(failure, Counter())[str(record.attempt)] += 1
                if failure == "truncated":
                    for g in (scenario, TOTAL):
                        truncated[g] += 1
                for category in record.finish.safety_categories:
                    blocks[category] += 1
                if failure == "safety_block" and not record.finish.safety_categories:
                    blocks[record.finish.reason or record.finish.status or "unknown"] += 1
    if damaged:
        raise DamagedTreeError(damaged)
    barred = store.read_barred(root, model)
    barred_cost = 0.0
    for record in barred:
        account(record, record.scenario.value)
        barred_cost += record.cost_usd
    attempts_cost = costs[TOTAL]
    numbers = [str(n) for n in range(1, config.MAX_ATTEMPTS + 1)]
    changes = store.template_changes(root, model)
    ordered = sorted(latencies)
    return LlmGenerationReport(
        model_key=model,
        model_requested=run.model_requested,
        request_parameters=run.request_parameters,
        template_sha256=run.template_sha256,
        dataset_manifest_sha256=run.dataset_manifest_sha256,
        models_returned=dict(sorted(returned.items())),
        combinations=counts,
        attempts_by_number={n: by_number[n] for n in numbers},
        failures={f: {n: c[n] for n in numbers} for f, c in sorted(failures.items())},
        safety_blocks_by_category=dict(sorted(blocks.items())) if model == "gemini" else None,
        truncated={g: truncated[g] for g in GROUPS},
        test_discards={g: {n: discards[g][n] for n in DISCARD_COUNTERS} for g in GROUPS},
        suite_size={g: size_stats(sizes[g]) for g in GROUPS},
        tokens={g: Tokens(**tokens[g]) for g in GROUPS},
        cost_usd=Costs(
            by_group={g: _round(costs[g]) for g in GROUPS},
            barred_cost_usd=_round(barred_cost),
            total=_round(attempts_cost + barred_cost),
            price_rows_used=[rows[k] for k in sorted(rows)],
        ),
        latency_s=Latency(
            calls=len(ordered),
            total_s=_round(sum(ordered)),
            mean_s=_round(sum(ordered) / len(ordered)) if ordered else None,
            median_s=_round(median(ordered)) if ordered else None,
            max_s=ordered[-1] if ordered else None,
        ),
        barred=Barred(
            count=len(barred),
            combinations=[f"{b.problem_id} {b.scenario.value}" for b in barred],
        ),
        template_changes=[
            TemplateChangeLine(
                number=c.number,
                from_sha256=c.from_sha256,
                to_sha256=c.to_sha256,
                changed_at=c.changed_at,
                reason=c.reason,
                combinations=len(c.superseded),
                files=sum(len(s.files) for s in c.superseded),
            )
            for c in changes
        ],
    )


def write_report(root: Path, model: str, report: LlmGenerationReport) -> Path:
    path = Path(root) / config.report_path(model)
    path.parent.mkdir(parents=True, exist_ok=True)  # `manifests/` is versioned, ordinary mode
    files.atomic_write_json(path, report)
    return path
