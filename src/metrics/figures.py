"""Figures of the thesis (FR-017; research R7): one chart per figure, with filters.

Each figure is drawn from the per-problem table (cut by the filters) with the same metric
functions as the tables, so a filtered figure is never a second source of numbers. The chart is
the one the dashboard shows (``metrics.charts``), rendered to a file by vl-convert: the picture
downloaded from the dashboard and the one the command writes are the same drawing. The subtitle
and the file name carry the filters and the source. PNG and SVG are the same bytes on every call
(the SVG's clip ids are renumbered in order); a PDF draws the same, but vl-convert orders its font
objects differently from call to call, so it is never packaged.
"""

import re

import numpy as np
import pandas as pd
import vl_convert

from metrics import charts, config, cuts, iic, primary

LABEL = {"black_box": "caixa-preta", "white_box": "caixa-branca", "hybrid": "híbrido"}
SET_LABEL = {"slm-attempt1": "SLM 1ª tent."}
FILTER_KEYS = ("macrocategorias", "statuses", "sets", "scenarios", "problems")
SHORT = {
    "macrocategorias": "macrocategoria",
    "statuses": "status",
    "sets": "set",
    "scenarios": "scenario",
    "problems": "problem",
}
FORMATS = ("png", "svg", "pdf")
PACKAGED_FORMATS = config.PACKAGED_FIGURE_FORMATS
PNG_SCALE = 2  # twice the screen size, for print


def _sets(frame: pd.DataFrame) -> list[str]:
    return [s for s in config.SETS if s in set(frame["set"])]


FIGURES = (
    "tdf_by_model",
    "tdf_declared_vs_corrected",
    "ms_declared_vs_corrected",
    "tfp_by_cause",
    "iic_distribution",
    "cost_per_detection",
)
NO_PROBLEM_CUTS = {"cost_per_detection"}  # cost exists per set × scenario, not per problem


def _per_problem_filter(filters: dict) -> bool:
    """A filter that selects problems (the cost exists only per set × scenario)."""
    return any(filters.get(k) for k in ("macrocategorias", "statuses", "problems"))


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


def chart(name: str, tables: dict, filters: dict | None, source: str, mode: str = "light"):
    """The chart of a figure with the filters, as the dashboard draws it in theme ``mode``."""
    filters = {k: list(v) for k, v in (filters or {}).items() if v}
    values = figure_data(name, tables, filters)
    if values.empty:
        raise cuts.CutError("no data with these filters")
    title, y_title = TITLES[name]
    return charts.chart(
        values,
        title,
        y_title,
        footer(filters, source),
        KIND.get(name, "grouped"),
        VALUE_FORMAT.get(name, ".1f"),
        mode,
    )


def _renumber_clips(svg: str) -> str:
    ids: dict[str, int] = {}

    def number(match: re.Match) -> str:
        return f"clip{ids.setdefault(match.group(1), len(ids) + 1)}"

    return re.sub(r"clip(\d+)", number, svg)


def render(
    name: str, tables: dict, filters: dict | None, fmt: str, source: str, mode: str = "light"
) -> tuple[str, bytes]:
    """(file name, bytes) of a figure with the filters, drawn as the dashboard shows it."""
    filters = {k: list(v) for k, v in (filters or {}).items() if v}
    if fmt not in FORMATS:
        raise ValueError(f"unknown format {fmt!r}; choose one of {', '.join(FORMATS)}")
    spec = chart(name, tables, filters, source, mode).to_dict()
    if fmt == "png":
        data = vl_convert.vegalite_to_png(spec, scale=PNG_SCALE)
    elif fmt == "svg":
        data = _renumber_clips(vl_convert.vegalite_to_svg(spec)).encode()
    else:
        data = vl_convert.vegalite_to_pdf(spec)
    return file_name(name, filters, fmt), data


TITLES = {
    "tdf_by_model": ("Taxa de Detecção de Falhas reais por modelo e cenário", "TDF (%)"),
    "tdf_declared_vs_corrected": (
        "TDF pelo oráculo declarado e pelo corrigido (Δ_oráculo)",
        "%",
    ),
    "ms_declared_vs_corrected": ("Escore de mutação pelo oráculo declarado e pelo corrigido", "%"),
    "tfp_by_cause": ("Falsos positivos por teste, por causa", "% dos testes que reprovam o AC"),
    "iic_distribution": (
        "Influência do contexto (híbrido sobre caixa-preta e sobre caixa-branca)",
        "IIC por problema (%)",
    ),
    "cost_per_detection": (
        "Custo por detecção (modelos comerciais)",
        "US$ por 1.000 WAs detectados",
    ),
}
KIND = {"tfp_by_cause": "stacked", "iic_distribution": "box"}  # the others: grouped bars
VALUE_FORMAT = {"cost_per_detection": ".3f"}  # the others: one decimal


def _pairs(table: pd.DataFrame, columns: dict[str, str]) -> pd.DataFrame:
    """Long form with one panel per scenario: ``x`` is the set, ``panel`` the scenario."""
    rows = []
    for _, r in table.iterrows():
        for column, series in columns.items():
            rows.append(
                {
                    "x": SET_LABEL.get(r["set"], r["set"]),
                    "series": series,
                    "value": r[column],
                    "panel": LABEL[r["scenario"]],
                }
            )
    return pd.DataFrame(rows, columns=["x", "series", "value", "panel"])


def figure_data(name: str, tables: dict, filters: dict | None) -> pd.DataFrame:
    """The values a figure plots, in long form (``x``, ``series``, ``value``, ``panel``).

    ``panel`` splits a figure into one panel per scenario (empty when it has a single panel).

    Computed with the same functions as the tables, so a chart never is a second source of
    numbers.
    """
    filters = {k: list(v) for k, v in (filters or {}).items() if v}
    if name not in FIGURES:
        raise ValueError(f"unknown figure {name!r}; choose one of {', '.join(FIGURES)}")
    if name in NO_PROBLEM_CUTS and _per_problem_filter(filters):
        raise cuts.CutError(f"{name} has no cut by macrocategoria, status or problem")
    per_problem, detected = cuts.apply(
        tables["per_problem"], detected_wa=tables["detected_wa"], **filters
    )
    if per_problem.empty:
        raise cuts.CutError("no combination with these filters")
    if name == "iic_distribution":
        rows = []
        for set_name in _sets(per_problem):
            problems = set(per_problem.loc[per_problem["set"] == set_name, "problem"])
            for direction, label in (("cod", "IIC_cod"), ("req", "IIC_req")):
                values, _ = iic.per_problem_values(
                    detected, set_name, "declared", direction, problems
                )
                x = SET_LABEL.get(set_name, set_name)
                rows += [{"x": x, "series": label, "value": v, "panel": ""} for v in values]
        return pd.DataFrame(rows, columns=["x", "series", "value", "panel"])
    if name == "cost_per_detection":
        cost = tables["cost"]
        keys = set(zip(per_problem["set"], per_problem["scenario"], strict=True))
        cost = cost[
            [
                s in config.COMMERCIAL and (s, c) in keys
                for s, c in zip(cost["set"], cost["scenario"], strict=True)
            ]
        ]
        per_thousand = cost.assign(
            k_declared=(1000 * cost["cpd_wa_declared"]).round(4),
            k_corrected=(1000 * cost["cpd_wa_corrected"]).round(4),
        )
        return _pairs(
            per_thousand,
            {"k_declared": "gabarito da IA", "k_corrected": "gabarito do AC"},
        )
    table = primary.table(per_problem)
    if name == "tdf_by_model":
        return pd.DataFrame(
            {
                "x": [SET_LABEL.get(s, s) for s in table["set"]],
                "series": [LABEL[c] for c in table["scenario"]],
                "value": table["TDF"],
                "panel": "",
            }
        ).reset_index(drop=True)
    if name == "tdf_declared_vs_corrected":
        return _pairs(table, {"TDF": "TDF (gabarito da IA)", "TDF_star": "TDF* (gabarito do AC)"})
    if name == "ms_declared_vs_corrected":
        return _pairs(table, {"MS": "MS (gabarito da IA)", "MS_star": "MS* (gabarito do AC)"})
    total = table["total_tests"].replace(0, np.nan)
    shares = table.assign(
        oracle=(100 * table["FP_tests_oracle"] / total).round(config.DECIMALS),
        invalid=(100 * table["FP_tests_invalid_input"] / total).round(config.DECIMALS),
    )
    return _pairs(
        shares,
        {"oracle": "saída esperada errada (oráculo)", "invalid": "entrada inválida (AC falha)"},
    )


def source_label(run: dict) -> str:
    """Short, stable description of the inputs: the first characters of their manifests' hashes."""
    hashes = "".join(v[:4] for _, v in sorted(run.get("evaluation_manifests", {}).items()))
    return f"data/metrics (avaliação {hashes[:12] or '?'})"
