"""Build ``manifests/mutation_report.json`` from the generated problems (spec FR-013).

Everything comes from the ``generation.json`` of each closed problem, so the report can be rebuilt at
any time, even in the middle of a development run, without generating anything; it always says what
``data/mutants/`` holds now. It also carries the hash of the dataset manifest verified before reading
(which ties the numbers to the exact dataset they were computed on).
"""

from collections import Counter
from pathlib import Path

from dataset.persistence import store
from mutation import config, dataset_gate, persistence
from mutation.schemas.report import (
    ExclusionAlertEntry,
    MutationReport,
    ProblemCounts,
)
from mutation.types import DiscardReason, MutationOperator


def build_report(root: Path) -> MutationReport:
    """Aggregate the generation records; raises ``DatasetMismatchError`` if the dataset differs."""
    root = Path(root)
    dataset_gate.verify_dataset(root)
    funnel: Counter = Counter()
    orders: Counter = Counter()
    operators: Counter = Counter()
    alerts: list[ExclusionAlertEntry] = []
    complete = first_order_only = 0
    closed = persistence.closed_problems(root)
    for problem_id in closed:
        record = persistence.read_generation(root, problem_id)
        for discard in record.discards:
            funnel[discard.reason] += discard.count
        if record.status == "excluded":
            assert record.exclusion is not None
            alerts.append(
                ExclusionAlertEntry(
                    problem_id=problem_id,
                    mutants_reached=record.exclusion.mutants_reached,
                    highest_order_attempted=record.exclusion.highest_order_attempted,
                )
            )
            continue
        complete += 1
        first_order_only += all(m.order == 1 for m in record.mutants)
        for mutant in record.mutants:
            orders[mutant.order] += 1
            for use in mutant.operators:
                operators[use.operator] += 1
    return MutationReport(
        problems=ProblemCounts(
            closed=len(closed),
            complete=complete,
            first_order_only=first_order_only,
            higher_order=complete - first_order_only,
            excluded=len(alerts),
        ),
        funnel={reason: funnel[reason] for reason in DiscardReason},
        order_distribution={order: orders[order] for order in range(1, config.HOM_MAX_ORDER + 1)},
        operator_distribution={op: operators[op] for op in MutationOperator},
        exclusion_alerts=alerts,
        dataset_manifest_sha256=dataset_gate.dataset_manifest_sha256(root),
    )


def write_report(root: Path, report: MutationReport) -> Path:
    path = Path(root) / config.REPORT_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    store.atomic_write_json(path, report)
    return path
