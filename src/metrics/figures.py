"""Figures of the thesis (FR-017; research R7): one function per figure, with filters.

Each figure is drawn from the per-problem table (cut by the filters) with the same metric
functions as the tables, so a filtered figure is never a second source of numbers. The footer and
the file name carry the filters and the source; ``render`` returns the same bytes on every call
(no date in the PNG/PDF metadata), so a figure downloaded from the dashboard equals the one the
command writes.
"""

import io
import os

# The container root is read only: matplotlib and fontconfig keep their caches in /tmp.
os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")
os.environ.setdefault("XDG_CACHE_HOME", "/tmp/cache")

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from metrics import config, cuts, iic, primary

LABEL = {"black_box": "caixa-preta", "white_box": "caixa-branca", "hybrid": "híbrido"}
TICK = {"black_box": "c-preta", "white_box": "c-branca", "hybrid": "híbrido"}
SET_LABEL = {"slm-attempt1": "SLM 1ª tent."}
FILTER_KEYS = ("macrocategorias", "statuses", "sets", "scenarios")
SHORT = {
    "macrocategorias": "macrocategoria",
    "statuses": "status",
    "sets": "set",
    "scenarios": "scenario",
}

plt.rcParams.update({"svg.hashsalt": "tcc-metrics", "figure.dpi": 100, "font.size": 9})


def _sets(frame: pd.DataFrame) -> list[str]:
    return [s for s in config.SETS if s in set(frame["set"])]


def _scenarios(frame: pd.DataFrame) -> list[str]:
    return [s for s in config.SCENARIOS if s in set(frame["scenario"])]


def _grouped_bars(ax, table, value_columns, labels) -> None:
    """Bars per set × scenario, one bar per value column."""
    keys = list(zip(table["set"], table["scenario"], strict=True))
    x = np.arange(len(keys))
    width = 0.8 / len(value_columns)
    for i, (column, label) in enumerate(zip(value_columns, labels, strict=True)):
        ax.bar(x + i * width - 0.4 + width / 2, table[column], width, label=label)
    ax.set_xticks(x, [f"{SET_LABEL.get(s, s)}\n{TICK[c]}" for s, c in keys], fontsize=7)
    ax.legend(fontsize=8)


def tdf_by_model(per_problem, detected_wa, cost):
    table = primary.table(per_problem)
    fig, ax = plt.subplots(figsize=(8, 4))
    sets, scenarios = _sets(table), _scenarios(table)
    x = np.arange(len(sets))
    width = 0.8 / max(1, len(scenarios))
    for i, scenario in enumerate(scenarios):
        values = [
            table[(table["set"] == s) & (table["scenario"] == scenario)]["TDF"].sum() for s in sets
        ]
        ax.bar(x + i * width - 0.4 + width / 2, values, width, label=LABEL[scenario])
    ax.set_xticks(x, [SET_LABEL.get(s, s) for s in sets])
    ax.set_ylabel("TDF (%)")
    ax.set_title("Taxa de Detecção de Falhas reais por modelo e cenário")
    ax.legend(fontsize=8)
    return fig


def tdf_declared_vs_corrected(per_problem, detected_wa, cost):
    table = primary.table(per_problem)
    fig, ax = plt.subplots(figsize=(12, 4))
    _grouped_bars(ax, table, ["TDF", "TDF_star"], ["TDF (gabarito da IA)", "TDF* (gabarito do AC)"])
    ax.set_ylabel("%")
    ax.set_title("TDF pelo oráculo declarado e pelo corrigido (Δ_oráculo)")
    return fig


def ms_declared_vs_corrected(per_problem, detected_wa, cost):
    table = primary.table(per_problem)
    fig, ax = plt.subplots(figsize=(12, 4))
    _grouped_bars(ax, table, ["MS", "MS_star"], ["MS (gabarito da IA)", "MS* (gabarito do AC)"])
    ax.set_ylabel("%")
    ax.set_title("Escore de mutação pelo oráculo declarado e pelo corrigido")
    return fig


def tfp_by_cause(per_problem, detected_wa, cost):
    table = primary.table(per_problem)
    total = table["total_tests"].replace(0, np.nan)
    oracle = 100 * table["FP_tests_oracle"] / total
    invalid = 100 * table["FP_tests_invalid_input"] / total
    keys = list(zip(table["set"], table["scenario"], strict=True))
    fig, ax = plt.subplots(figsize=(12, 4))
    x = np.arange(len(keys))
    ax.bar(x, oracle, label="saída esperada errada (oráculo)")
    ax.bar(x, invalid, bottom=oracle, label="entrada inválida (AC falha)")
    ax.set_xticks(x, [f"{SET_LABEL.get(s, s)}\n{TICK[c]}" for s, c in keys], fontsize=7)
    ax.set_ylabel("% dos testes que reprovam o AC")
    ax.set_title("Falsos positivos por teste, por causa")
    ax.legend(fontsize=8)
    return fig


def iic_distribution(per_problem, detected_wa, cost):
    data, labels = [], []
    for set_name in _sets(per_problem):
        problems = set(per_problem.loc[per_problem["set"] == set_name, "problem"])
        for direction, name in (("cod", "IIC_cod"), ("req", "IIC_req")):
            values, _ = iic.per_problem_values(
                detected_wa, set_name, "declared", direction, problems
            )
            data.append(values or [np.nan])
            labels.append(f"{set_name}\n{name}")
    fig, ax = plt.subplots(figsize=(12, 4))
    ax.boxplot(data, tick_labels=labels, showfliers=False)
    ax.axhline(0, color="grey", linewidth=0.8)
    ax.tick_params(axis="x", labelsize=7)
    ax.set_ylabel("IIC por problema (%)")
    ax.set_title("Influência do contexto (híbrido sobre caixa-preta e sobre caixa-branca)")
    return fig


def cost_per_detection(per_problem, detected_wa, cost):
    table = cost[cost["set"].isin(config.COMMERCIAL)]
    keys = set(zip(per_problem["set"], per_problem["scenario"], strict=True))
    table = table[[(s, c) in keys for s, c in zip(table["set"], table["scenario"], strict=True)]]
    fig, ax = plt.subplots(figsize=(8, 4))
    _grouped_bars(
        ax,
        table.reset_index(drop=True),
        ["cpd_wa_declared", "cpd_wa_corrected"],
        ["por WA (gabarito da IA)", "por WA (gabarito do AC)"],
    )
    ax.set_ylabel("US$ por WA detectado")
    ax.set_title("Custo por detecção (modelos comerciais)")
    return fig


FIGURES = {
    "tdf_by_model": tdf_by_model,
    "tdf_declared_vs_corrected": tdf_declared_vs_corrected,
    "ms_declared_vs_corrected": ms_declared_vs_corrected,
    "tfp_by_cause": tfp_by_cause,
    "iic_distribution": iic_distribution,
    "cost_per_detection": cost_per_detection,
}
NO_PROBLEM_CUTS = {"cost_per_detection"}  # cost exists per set × scenario, not per problem


def file_name(name: str, filters: dict, fmt: str) -> str:
    parts = [name]
    for key in FILTER_KEYS:
        values = sorted(filters.get(key) or [])
        if values:
            parts.append(f"{SHORT[key]}-{'+'.join(values)}")
    return "__".join(parts) + f".{fmt}"


def footer(filters: dict, source: str) -> str:
    applied = [
        f"{SHORT[k]} = {', '.join(sorted(filters[k]))}" for k in FILTER_KEYS if filters.get(k)
    ]
    return f"filtros: {'; '.join(applied) or 'nenhum'}  ·  fonte: {source}"


def render(
    name: str, tables: dict, filters: dict | None, fmt: str, source: str
) -> tuple[str, bytes]:
    """(file name, bytes) of a figure with the filters; the same bytes on every call."""
    filters = {k: list(v) for k, v in (filters or {}).items() if v}
    if name not in FIGURES:
        raise ValueError(f"unknown figure {name!r}; choose one of {', '.join(FIGURES)}")
    if name in NO_PROBLEM_CUTS and (filters.get("macrocategorias") or filters.get("statuses")):
        raise cuts.CutError(f"{name} has no cut by macrocategoria or status")
    per_problem, detected = cuts.apply(
        tables["per_problem"], detected_wa=tables["detected_wa"], **filters
    )
    if per_problem.empty:
        raise cuts.CutError("no combination with these filters")
    fig = FIGURES[name](per_problem, detected, tables["cost"])
    fig.text(0.01, 0.005, footer(filters, source), fontsize=6, color="#555555")
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    buffer = io.BytesIO()
    if fmt == "pdf":
        fig.savefig(
            buffer, format="pdf", metadata={"CreationDate": None, "Producer": "tcc-metrics"}
        )
    elif fmt == "png":
        fig.savefig(buffer, format="png", dpi=200, metadata={"Software": None})
    else:
        plt.close(fig)
        raise ValueError(f"unknown format {fmt!r}")
    plt.close(fig)
    return file_name(name, filters, fmt), buffer.getvalue()


def source_label(run: dict) -> str:
    """Short, stable description of the inputs: the first characters of their manifests' hashes."""
    hashes = "".join(v[:4] for _, v in sorted(run.get("evaluation_manifests", {}).items()))
    return f"data/metrics (avaliação {hashes[:12] or '?'})"
