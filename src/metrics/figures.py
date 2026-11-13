"""Figures of the thesis (FR-017; research R7; feature 012): one chart per figure, with filters.

Each figure is drawn from the per-problem table (cut by the filters) with the same metric
functions as the tables (``primary``, ``iic``, and ``story`` over them), so a filtered figure is
never a second source of numbers. The chart is the one the dashboard shows (``metrics.charts``),
rendered to a file by vl-convert; the file adds the title and the subtitle that the dashboard
writes as page text. The title of a narrative figure is the conclusion of the cut
(``story.conclusion``): it names the leader of the cut, so it changes with the filters. The
subtitle and the file name carry the filters and the source. PNG and SVG are the same bytes on
every call (the SVG's clip ids are renumbered in order); a PDF draws the same, but vl-convert
orders its font objects differently from call to call, so it is never packaged.
"""

import re

import altair as alt
import numpy as np
import pandas as pd
import vl_convert

from metrics import charts, config, cuts, iic, primary, story

LABEL = {"black_box": "caixa-preta", "white_box": "caixa-branca", "hybrid": "híbrido"}
SET_LABEL = {"slm-attempt1": "SLM 1ª tent."}
FILTER_KEYS = ("macrocategorias", "ratings", "statuses", "sets", "scenarios", "problems")
SHORT = {
    "macrocategorias": "macrocategoria",
    "ratings": "rating",
    "statuses": "status",
    "sets": "set",
    "scenarios": "scenario",
    "problems": "problem",
}
FORMATS = ("png", "svg", "pdf")
PACKAGED_FORMATS = config.PACKAGED_FIGURE_FORMATS
PNG_SCALE = 2  # twice the screen size, for print
ORACLES = ("corrected", "declared")


def _sets(frame: pd.DataFrame) -> list[str]:
    return [s for s in config.SETS if s in set(frame["set"])]


FIGURES = (
    "scoreboard",
    "tdf_by_model",
    "tdf_declared_vs_corrected",
    "ms_declared_vs_corrected",
    "tradeoff",
    "tfp_by_cause",
    "scenario_shift",
    "iic_diverging",
    "iic_distribution",
    "cost_per_detection",
    "choice_guide",
)
SECTION = {  # figure -> section of story.conclusion (its title is the conclusion of the cut)
    "scoreboard": "scoreboard",
    "tdf_by_model": "tdf",
    "ms_declared_vs_corrected": "ms",
    "tradeoff": "tfp",
    "tfp_by_cause": "tfp_cause",
    "scenario_shift": "context",
    "iic_diverging": "iic",
    "cost_per_detection": "cost",
    "choice_guide": "guide",
}
LEGACY = ("tdf_declared_vs_corrected", "tfp_by_cause", "iic_distribution")  # charts.chart kinds
TITLES = {  # the figures whose title is a theme (support and diagnosis), with the y-axis title
    "tdf_declared_vs_corrected": (
        "TDF pelo gabarito da IA e pelo do AC, por cenário (Δ_oráculo)",
        "%",
    ),
    "tfp_by_cause": ("Falsos positivos por teste, por causa", "% dos testes que reprovam o AC"),
    "iic_distribution": (
        "Influência do contexto por problema (híbrido sobre caixa-preta e sobre caixa-branca)",
        "IIC por problema (%)",
    ),
}
KIND = {"tfp_by_cause": "stacked", "iic_distribution": "box"}  # the others: grouped bars
CRITERION_HEADER = {
    "tdf_star": "falhas reais (TDF*)",
    "ms_star": "mutantes (MS*)",
    "tfp": "reprova o AC (TFP)",
    "delta_tdf": "erro do gabarito (Δ)",
    "tc": "entrega suíte (TC)",
    "cost": "custo (US$/1.000 WAs)",
}
SHORT_STATE = {story.DIFFER: "diferem", story.TIE: "empate", story.UNTESTED: "não testado"}


def _clean(filters: dict | None) -> dict:
    return {k: list(v) for k, v in (filters or {}).items() if v}


def file_name(name: str, filters: dict, fmt: str, oracle: str = "corrected") -> str:
    parts = [name]
    for key in FILTER_KEYS:
        values = sorted(filters.get(key) or [])
        if values:
            parts.append(f"{SHORT[key]}-{'+'.join(str(v) for v in values)}")
    if oracle == "declared" and name == "iic_diverging":
        parts.append("gabarito-ia")
    return "__".join(parts) + f".{fmt}"


def footer(filters: dict, source: str) -> str:
    applied = [
        f"{SHORT[k]} = {', '.join(str(v) for v in sorted(filters[k]))}"
        for k in FILTER_KEYS
        if filters.get(k)
    ]
    return f"filtros: {'; '.join(applied) or 'nenhum'}  ·  fonte: {source}"


def title(name: str, tables: dict, filters: dict | None, oracle: str = "corrected"):
    """The ``story.Titulo`` of a figure for the cut: the conclusion, or the theme of a support
    figure (``rule`` = the figure name)."""
    if name in SECTION:
        recorte = story.Recorte.from_filters(_clean(filters))
        return story.conclusion(tables, recorte, SECTION[name], oracle)
    return story.Titulo(TITLES[name][0], "", name)


def _value(criterion: str, value: float) -> str:
    if pd.isna(value):
        return "—"
    if criterion == "cost":
        return f"US$ {story.num(value, 3)}"
    if criterion == "delta_tdf":
        return f"{story.num(value, 2)} pontos"
    return story.pct(value)


def _means(tables: dict, recorte: story.Recorte) -> pd.DataFrame:
    """Per set: the mean over the scenarios of the cut of TDF, TDF*, MS and MS*."""
    table = primary.table(cuts.apply(tables["per_problem"], **recorte.cut_kwargs()))
    means = table.groupby("set", sort=False)[["TDF", "TDF_star", "MS", "MS_star"]].mean()
    return means.reindex(_sets(table))


def _ranked_frame(means: pd.DataFrame, after: str, before: str) -> pd.DataFrame:
    """Best first. Two short annotations on the bars (how far ahead the leader is; how much the
    set that loses the most drops when the answer key is corrected), spelled out in ``note``."""
    frame = means.sort_values(after, ascending=False, kind="stable")
    delta = frame[before] - frame[after]
    rows = []
    for i, (set_name, r) in enumerate(frame.iterrows()):
        label, note = story.pct(r[after]), ""
        if i == 0 and len(frame) > 1:
            ahead = r[after] - frame[after].iloc[1]
            label += f" · +{story.num(ahead)}"
            note = (
                f"{story.name(set_name)} fica {story.num(ahead)} pontos à frente do 2º "
                f"({story.name(frame.index[1])})."
            )
        elif set_name == delta.idxmax() and delta.max() > 0:
            label += f" · −{story.num(delta.max())}"
            note = (
                f"{story.name(set_name)} é quem mais perde quando o gabarito é corrigido: "
                f"{story.num(delta.max())} pontos (de {story.pct(r[before])} para "
                f"{story.pct(r[after])})."
            )
        rows.append(
            {
                "y": story.name(set_name),
                "value": round(float(r[after]), 2),
                "before": round(float(r[before]), 2),
                "label": label,
                "first": i == 0,
                "note": note,
            }
        )
    return pd.DataFrame(rows)


def _guide_frame(tables: dict, recorte: story.Recorte) -> pd.DataFrame:
    rows = []
    for c in story.guide(tables, recorte):
        if c.criterion == story.LOCAL_CRITERION:
            line1 = story.name(c.leader) if c.leader else "fora do recorte"
            line2 = "sem custo em dinheiro" if c.leader else ""
        elif c.leader is None:
            line1, line2 = "—", ""
        else:
            if c.tied:
                names = ", ".join(story.name(s) for s in c.tied)
                line1 = f"empate entre {len(c.tied)} IAs · {_value(c.criterion, c.value)}"
                line2 = names if len(names) <= 34 else "mesmo valor"
            else:
                line1 = f"{story.name(c.leader)} · {_value(c.criterion, c.value)}"
                second = (
                    f"2º {story.name(c.second)} {_value(c.criterion, c.second_value)}"
                    if c.second
                    else "sem 2º"
                )
                line2 = f"{second} · {SHORT_STATE[c.state]}"
        rows.append(
            {
                "row": c.label,
                "col": story.SCENARIO_NAME[c.scenario],
                "text": f"{line1}\n{line2}".strip(),
                "tip": f"{line1} · {line2}".strip(" ·"),
                "criterion": c.criterion,
                "leader": c.leader,
                "value": c.value,
                "second": c.second,
                "second_value": c.second_value,
                "state": c.state,
            }
        )
    return pd.DataFrame(rows)


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


def figure_data(
    name: str, tables: dict, filters: dict | None, oracle: str = "corrected"
) -> pd.DataFrame:
    """The values a figure plots, computed with the same functions as the tables.

    The figures of feature 010 (``LEGACY``) are in long form (``x``, ``series``, ``value``,
    ``panel``); the narrative ones in the columns their chart kind reads.
    """
    filters = _clean(filters)
    if name not in FIGURES:
        raise ValueError(f"unknown figure {name!r}; choose one of {', '.join(FIGURES)}")
    if oracle not in ORACLES:
        raise ValueError(f"unknown oracle {oracle!r}; choose one of {', '.join(ORACLES)}")
    recorte = story.Recorte.from_filters(filters)
    per_problem, detected = cuts.apply(
        tables["per_problem"], detected_wa=tables["detected_wa"], **filters
    )
    if per_problem.empty:
        raise cuts.CutError("no combination with these filters")
    if name == "scoreboard":
        board = story.scoreboard(tables, recorte)
        rows = []
        for _, r in board.iterrows():
            ranked = not pd.isna(r["rank"])
            value = _value(r["criterion"], r["value"])
            if r["criterion"] == "cost" and r["set"] in story.LOCAL:
                value = "sem custo"
            text = f"{int(r['rank'])}º\n{value}" if ranked else f"—\n{value}"
            rows.append(
                {
                    "row": story.name(r["set"]),
                    "col": CRITERION_HEADER[r["criterion"]],
                    "text": text,
                    "tip": text.replace("\n", " · "),
                    "first": bool(ranked and r["rank"] == 1),
                    "set": r["set"],
                    "criterion": r["criterion"],
                    "value": r["value"],
                    "rank": r["rank"],
                }
            )
        return pd.DataFrame(rows)
    if name == "tdf_by_model":
        return _ranked_frame(_means(tables, recorte), "TDF_star", "TDF")
    if name == "ms_declared_vs_corrected":
        return _ranked_frame(_means(tables, recorte), "MS_star", "MS")
    if name == "tradeoff":
        vals = story.values(tables, recorte)
        tdf_first = vals["tdf_star"].idxmax()
        tfp_first = vals["tfp"].idxmin()
        accent = {tdf_first: 0} | ({tfp_first: 1} if tfp_first != tdf_first else {})
        return pd.DataFrame(
            {
                "label": [story.name(s) for s in vals.index],
                "x": vals["tfp"].round(2).to_numpy(),
                "y": vals["tdf_star"].round(2).to_numpy(),
                "accent": [accent.get(s, -1) for s in vals.index],
                "set": list(vals.index),
            }
        )
    if name == "scenario_shift":
        if len(story.scenarios_of(tables, recorte)) < 2:
            raise cuts.CutError("scenario_shift needs two scenarios or more")
        shift = story.scenario_shift(tables, recorte)
        spread = story.shift_spread(tables, recorte)
        accent = {spread.idxmax(): 0} | (
            {spread.idxmin(): 1} if spread.idxmin() != spread.idxmax() else {}
        )
        return pd.DataFrame(
            {
                "set": [story.name(s) for s in shift["set"]],
                "scenario": [story.SCENARIO_NAME[c] for c in shift["scenario"]],
                "value": shift["value"].round(2),
                "accent": [accent.get(s, -1) for s in shift["set"]],
            }
        )
    if name == "iic_diverging":
        frame = story.iic_values(tables, recorte, oracle).dropna(subset=["iic"])
        if frame.empty:
            raise cuts.CutError("no WA detected in a base scenario: no IIC in this cut")
        return pd.DataFrame(
            {
                "y": [story.name(s) for s in frame["set"]],
                "value": frame["iic"].round(2),
                "label": [("+" if v > 0 else "") + story.pct(v) for v in frame["iic"]],
                "panel": [story.DIRECTION_NAME[d] for d in frame["direction"]],
            }
        )
    if name == "cost_per_detection":
        cost = story.values(tables, recorte)["cost"].dropna().sort_values(kind="stable")
        return pd.DataFrame(
            {
                "y": [story.name(s) for s in cost.index],
                "value": cost.round(4).to_numpy(),
                "label": [f"US$ {story.num(v, 3)}" for v in cost],
                "first": [i == 0 for i in range(len(cost))],
            }
        )
    if name == "choice_guide":
        return _guide_frame(tables, recorte)
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
    table = primary.table(per_problem)
    if name == "tdf_declared_vs_corrected":
        return _pairs(table, {"TDF": "TDF (gabarito da IA)", "TDF_star": "TDF* (gabarito do AC)"})
    total = table["total_tests"].replace(0, np.nan)
    shares = table.assign(
        oracle=(100 * table["FP_tests_oracle"] / total).round(config.DECIMALS),
        invalid=(100 * table["FP_tests_invalid_input"] / total).round(config.DECIMALS),
    )
    return _pairs(
        shares,
        {"oracle": "saída esperada errada (oráculo)", "invalid": "entrada inválida (AC falha)"},
    )


IIC_PANEL_WIDTH = 330


def _body(name: str, values: pd.DataFrame, mode: str, highlight: str | None):
    """The chart of a narrative figure, without title (``charts.card`` or ``charts.framed``)."""
    if name == "scoreboard":
        return charts.scoreboard_grid(values, mode)
    if name in ("tdf_by_model", "ms_declared_vs_corrected"):
        x_title = "TDF* (%)" if name == "tdf_by_model" else "MS* (%)"
        return charts.ranked_bars(values, x_title, mode)
    if name == "tradeoff":
        return charts.tradeoff_scatter(
            values, float(values["x"].median()), float(values["y"].median()), mode
        )
    if name == "scenario_shift":
        order = list(dict.fromkeys(values["scenario"]))
        return charts.scenario_lines(values, order, mode)
    if name == "iic_diverging":
        limit = float(values["value"].abs().max()) * 1.5 + 0.5
        _, ink, _ = charts._theme(mode)
        panels = [
            charts.diverging_bars(values[values["panel"] == p], limit, mode).properties(
                width=IIC_PANEL_WIDTH,
                title=alt.TitleParams(
                    PANEL_TITLE[p], anchor="start", fontSize=13, color=ink["secondary"]
                ),
            )
            for p in story.DIRECTION_NAME.values()
            if p in set(values["panel"])
        ]
        return alt.hconcat(*panels, spacing=36)
    if name == "cost_per_detection":
        return charts.ranked_bars(values, "US$ por 1.000 WAs", mode, percent=False)
    if name == "choice_guide":
        rows = list(dict.fromkeys(values["row"]))
        columns = list(dict.fromkeys(values["col"]))
        return charts.guide_grid(values, rows, columns, highlight, mode)
    raise ValueError(name)


PANEL_TITLE = {
    "+ código": "+ código: híbrido sobre caixa-preta",
    "+ requisito": "+ requisito: híbrido sobre caixa-branca",
}


def _drawing(
    name: str,
    tables: dict,
    filters: dict,
    mode: str,
    oracle: str,
    highlight: str | None,
    framed_with: tuple | None,
):
    values = figure_data(name, tables, filters, oracle)
    if values.empty:
        raise cuts.CutError("no data with these filters")
    if name in LEGACY:
        heading, y_title = TITLES[name]
        subtitle = [""]
        if framed_with is not None:
            heading, subtitle = framed_with
        return charts.chart(
            values,
            heading,
            y_title,
            subtitle,
            KIND.get(name, "grouped"),
            ".1f",
            mode,
            in_card=framed_with is None,
        )
    body = _body(name, values, mode, highlight)
    if framed_with is None:
        return charts.card(body, mode, stretch=name != "iic_diverging")
    heading, subtitle = framed_with
    return charts.framed(body, heading, subtitle, mode)


def card(
    name: str,
    tables: dict,
    filters: dict | None,
    mode: str = "light",
    oracle: str = "corrected",
    highlight: str | None = None,
):
    """The chart of a figure as the dashboard shows it, in a card (title as page text)."""
    return _drawing(name, tables, _clean(filters), mode, oracle, highlight, None)


def chart(
    name: str,
    tables: dict,
    filters: dict | None,
    source: str,
    mode: str = "light",
    oracle: str = "corrected",
    highlight: str | None = None,
):
    """The chart of a figure as a file: the card's drawing with its title and subtitle."""
    filters = _clean(filters)
    heading = title(name, tables, filters, oracle)
    subtitle = [s for s in (heading.subtitle, footer(filters, source)) if s]
    return _drawing(name, tables, filters, mode, oracle, highlight, (heading.text, subtitle))


def _renumber_clips(svg: str) -> str:
    ids: dict[str, int] = {}

    def number(match: re.Match) -> str:
        return f"clip{ids.setdefault(match.group(1), len(ids) + 1)}"

    return re.sub(r"clip(\d+)", number, svg)


def render(
    name: str,
    tables: dict,
    filters: dict | None,
    fmt: str,
    source: str,
    mode: str = "light",
    oracle: str = "corrected",
    highlight: str | None = None,
) -> tuple[str, bytes]:
    """(file name, bytes) of a figure with the filters, drawn as the dashboard shows it."""
    filters = _clean(filters)
    if fmt not in FORMATS:
        raise ValueError(f"unknown format {fmt!r}; choose one of {', '.join(FORMATS)}")
    spec = chart(name, tables, filters, source, mode, oracle, highlight).to_dict()
    if fmt == "png":
        data = vl_convert.vegalite_to_png(spec, scale=PNG_SCALE)
    elif fmt == "svg":
        data = _renumber_clips(vl_convert.vegalite_to_svg(spec)).encode()
    else:
        data = vl_convert.vegalite_to_pdf(spec)
    return file_name(name, filters, fmt, oracle), data


def source_label(run: dict) -> str:
    """Short, stable description of the inputs: the first characters of their manifests' hashes."""
    hashes = "".join(v[:4] for _, v in sorted(run.get("evaluation_manifests", {}).items()))
    return f"data/metrics (avaliação {hashes[:12] or '?'})"
