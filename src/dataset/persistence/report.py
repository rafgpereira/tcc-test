"""Extraction report: funnel, distribution, alerts and pending triage (spec FR-018, FR-018a).

Alerts are INFORMATIVE: they never block a run, change the selection or relax a criterion. They are
computed only once the selection is final, because a partial sample naturally has few problems per
category. The selection is final when the target is reached OR every problem of the pool has been
closed (complete, pending triage or discarded), so a run that ends with a deficit also alerts.
"""

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dataset import config
from dataset.persistence import store
from dataset.schemas.common import Macrocategoria
from dataset.schemas.pool import Pool
from dataset.schemas.report import (
    CategoryAlert,
    ExtractionReport,
    PendingTriageItem,
    Provenance,
    ReportFunnel,
)


def build_report(
    pool: Pool,
    *,
    included: Sequence[Macrocategoria] = (),
    pending_triage: Sequence[PendingTriageItem] = (),
    discarded_by_reason: Mapping[str, int] | None = None,
    selection_final: bool = False,
    target: int = config.TARGET_PROBLEMS,
    engine_selfcheck: dict[str, Any] | None = None,
) -> ExtractionReport:
    """Build the report from the pool and the state of the validation. Inputs are not modified."""
    counts = pool.counts
    # Funnel order, not the order of the stored JSON (its keys are sorted); unknown stages last.
    known = [s for s in config.FUNNEL_STAGES if s in counts.funnel]
    extra = sorted(s for s in counts.funnel if s != "read" and s not in config.FUNNEL_STAGES)
    funnel = ReportFunnel(
        read=counts.funnel.get("read", 0),
        stages={stage: counts.funnel[stage] for stage in (*known, *extra)},
        rejected_by_reason=dict(counts.rejections),
        discarded_by_reason=dict(discarded_by_reason or {}),
        included=len(included),
    )
    pool_distribution = {
        category: sum(1 for p in pool.problems.values() if p.macrocategoria is category)
        for category in Macrocategoria
    }
    distribution = {
        category: sum(1 for c in included if c is category) for category in Macrocategoria
    }
    alerts = [
        CategoryAlert(
            macrocategoria=category,
            count=distribution[category],
            threshold=config.CATEGORY_ALERT_THRESHOLD,
        )
        for category in Macrocategoria
        if selection_final and distribution[category] < config.CATEGORY_ALERT_THRESHOLD
    ]
    return ExtractionReport(
        funnel=funnel,
        pool_distribution=pool_distribution,
        distribution=distribution,
        selection_final=selection_final,
        category_alerts=alerts,
        pending_triage=list(pending_triage),
        target=target,
        deficit=max(0, target - len(included)),
        engine_selfcheck=engine_selfcheck,
        provenance=Provenance(
            hf_dataset=pool.hf_dataset, hf_revision=pool.hf_revision, seed=pool.seed
        ),
    )


def render_markdown(report: ExtractionReport) -> str:
    """Human-readable report; alerts and pending triage are highlighted."""
    lines = ["# Relatório de extração", ""]
    provenance = report.provenance
    lines += [
        (
            f"Dataset `{provenance.hf_dataset}`, revisão `{provenance.hf_revision}`, seed "
            f"`{provenance.seed}`."
        ),
        "",
        "## Funil de elegibilidade",
        "",
        "| Etapa | Linhas que restam |",
        "|---|---:|",
        f"| lidas | {report.funnel.read} |",
    ]
    lines += [f"| {stage} | {n} |" for stage, n in report.funnel.stages.items()]
    lines += ["", "### Linhas com cada motivo de rejeição", ""]
    if report.funnel.rejected_by_reason:
        lines += ["| Motivo | Linhas |", "|---|---:|"]
        lines += [f"| {r} | {n} |" for r, n in report.funnel.rejected_by_reason.items()]
    else:
        lines += ["Nenhuma."]
    if report.funnel.discarded_by_reason:
        lines += ["", "### Descartes na validação", "", "| Motivo | Problemas |", "|---|---:|"]
        lines += [f"| {r} | {n} |" for r, n in report.funnel.discarded_by_reason.items()]

    lines += ["", "## Distribuição por macrocategoria", ""]
    lines += ["| Macrocategoria | Pool elegível | Amostra |", "|---|---:|---:|"]
    for category in Macrocategoria:
        lines.append(
            f"| {category.value} | {report.pool_distribution[category]} | "
            f"{report.distribution[category]} |"
        )
    lines += ["", f"Problemas completos na amostra: {report.funnel.included} de {report.target}."]
    lines += [f"Déficit da meta: {report.deficit}."]

    for alert in report.category_alerts:
        lines += [
            "",
            (
                f"> **ALERTA**: a macrocategoria `{alert.macrocategoria.value}` ficou com "
                f"{alert.count} problemas (limiar: {alert.threshold}). Alerta informativo: não "
                "bloqueia, não altera a seleção e não relaxa critérios."
            ),
        ]

    if report.pending_triage:
        lines += ["", "## Pendentes de triagem", ""]
        lines += [
            (
                "> **PENDENTE DE TRIAGEM**: cada problema abaixo exige inspeção individual antes "
                "de prosseguir com o experimento, sem limiar de tolerância."
            ),
            "",
            "| Problema | Etapa | Motivo |",
            "|---|---|---|",
        ]
        lines += [f"| {i.problem_id} | {i.stage} | {i.reason} |" for i in report.pending_triage]
    return "\n".join(lines) + "\n"


def write_report(root: Path, report: ExtractionReport) -> tuple[Path, Path]:
    """Write ``extraction_report.json`` and ``.md`` under ``data/work/reports/``."""
    store.ensure_work_dir(root)
    folder = Path(root) / config.REPORTS_DIR
    json_path, md_path = folder / "extraction_report.json", folder / "extraction_report.md"
    store.atomic_write_json(json_path, report)
    store.atomic_write_text(md_path, render_markdown(report))
    return json_path, md_path


@dataclass
class ValidationState:
    included: list[Macrocategoria] = field(default_factory=list)
    pending: list[PendingTriageItem] = field(default_factory=list)
    discarded: dict[str, int] = field(default_factory=dict)
    closed: int = 0  # pool problems with a final status (complete, pending triage or discarded)

    def selection_is_final(self, pool: Pool, target: int = config.TARGET_PROBLEMS) -> bool:
        """The target was reached, or there is nothing left to validate in the pool."""
        if len(self.included) >= target:
            return True
        return bool(pool.problems) and self.closed >= len(pool.problems)


def collect_validation_state(root: Path, pool: Pool) -> ValidationState:
    """Read ``validacao.json`` of every closed problem to know what is included, pending or discarded."""
    state = ValidationState()
    discarded: Counter[str] = Counter()
    problems = Path(root) / config.PROBLEMS_DIR
    if not problems.is_dir():
        return state
    for folder in sorted(problems.iterdir()):
        path = folder / "validacao.json"
        if not path.is_file():
            continue
        data = store.read_json(path)
        pid, status = data.get("problem_id", folder.name), data.get("status")
        if pid in pool.problems and status in ("complete", "pending_triage", "discarded"):
            state.closed += 1
        if status == "complete" and pid in pool.problems:
            state.included.append(pool.problems[pid].macrocategoria)
        elif status == "pending_triage":
            triage = data.get("triage") or {}
            reason = triage.get("reason") or str(triage.get("verdict") or "unknown")
            state.pending.append(
                PendingTriageItem(
                    problem_id=pid, stage=triage.get("stage") or "selection", reason=reason
                )
            )
        elif status == "discarded":
            discarded[data.get("discard_reason") or "unknown"] += 1
    state.discarded = dict(sorted(discarded.items()))
    return state
