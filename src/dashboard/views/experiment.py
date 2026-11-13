"""O experimento (feature 012, US1): the context before any result.

specs/012-dashboard-storytelling/contracts/narrative.md, "Página 1". Every chart sits in a card
whose title is the conclusion of the current cut, computed from the numbers (never a fixed
sentence), with the denominator in the line below it; the numbers of every chart are in one table
view at the end of the page (the relief the palette check asks for).
"""

from pathlib import Path

import pandas as pd
import streamlit as st

from dashboard import config, data
from dashboard.views.common import bridge, cut_banner, theme_mode
from metrics import charts

SET_LABEL = {
    "slm": "SLM",
    "gpt": "GPT",
    "gemini": "Gemini",
    "claude": "Claude",
    "slm-attempt1": "SLM 1ª tentativa",
}
SCENARIO_LABEL = {
    "black_box": "caixa-preta",
    "white_box": "caixa-branca",
    "hybrid": "híbrido",
}
MACRO_LABEL = {
    "logica_direta": "lógica direta",
    "estrutural_otimizacao": "estrutural/otimização",
    "matematica": "matemática",
}
STATUS_ORDER = [
    "aceita (solução conferida)",
    "reserva",
    "saídas escritas pela IA",
    "sem raciocínio",
    "1ª tentativa",
    data.NO_SUITE,
]


def number(value: float, decimals: int = 0) -> str:
    """Portuguese formatting: 24.274 · 19,35."""
    text = f"{value:,.{decimals}f}"
    return text.replace(",", "§").replace(".", ",").replace("§", ".")


def plural(n: int, one: str, many: str) -> str:
    return f"{number(n)} {one if n == 1 else many}"


def percent(value: float, decimals: int = 0) -> str:
    return f"{number(value, decimals)}%"


@st.cache_data(show_spinner=False)
def _cost(path: str, stamp: float) -> pd.DataFrame:
    return pd.read_csv(path)


def _read_cost() -> pd.DataFrame | None:
    path = Path(config.METRICS_DIR) / "cost.csv"
    if not path.is_file():
        return None
    return _cost(str(path), path.stat().st_mtime)


def _card(title: str, subtitle: str):
    """A bordered card with the conclusion as its title and the denominator under it.

    ``height="stretch"`` makes the cards of one row of columns the same height, so they line up.
    """
    box = st.container(border=True, height="stretch")
    box.markdown(f"**{title}**")
    box.caption(subtitle)
    return box


def _kpis(summary: dict) -> None:
    columns = st.columns(6)
    columns[0].metric("Problemas", number(summary["problems"]))
    columns[1].metric(
        "Falhas",
        number(summary["wa"] + summary["mutants"]),
        help="100 WAs + 100 mutantes por problema",
    )
    columns[2].metric("IAs × cenários", f"{len(summary['models'])} × {summary['scenarios']}")
    columns[3].metric(
        "Suítes",
        number(summary["suites"]),
        help=f"de {number(summary['combinations'])} combinações (problema × cenário × IA)",
    )
    columns[4].metric("Testes gerados", number(summary["tests"]))
    spent = summary["spend_total"]
    columns[5].metric("Gasto", f"US$ {number(spent, 2)}" if spent is not None else "—")


def _ratings(rows: pd.DataFrame, n: int, mode: str, tables: dict) -> None:
    counts = data.ratings_count(rows)
    if counts.empty:
        st.caption("Rating: o dataset não está descompactado.")
        return
    most = counts[counts["problems"] == counts["problems"].max()]
    ties = " e ".join(str(int(r)) for r in most["rating"])
    low, high = int(counts["rating"].min()), int(counts["rating"].max())
    title = (
        f"Problemas de rating {low} a {high} do Codeforces"
        if low != high
        else f"Problemas de rating {low} do Codeforces"
    )
    each = " cada" if len(most) > 1 else ""
    label = "faixas mais comuns" if len(most) > 1 else "faixa mais comum"
    subtitle = f"dos {plural(n, 'problema', 'problemas')} · {label}: {ties} ({int(most['problems'].iloc[0])}{each})"
    frame = pd.DataFrame({"x": counts["rating"].astype(str), "value": counts["problems"]})
    with _card(title, subtitle):
        st.altair_chart(charts.bars(frame, "problemas", mode), theme=None, width="stretch")
    tables["Problemas por rating"] = counts.rename(columns={"problems": "problemas"})


def _macro(rows: pd.DataFrame, n: int, mode: str, tables: dict) -> None:
    counts = data.macro_count(rows)
    if counts.empty:
        st.caption("Macrocategoria: o dataset não está descompactado.")
        return
    labels = counts["macrocategoria"].map(lambda m: MACRO_LABEL.get(m, m))
    frame = pd.DataFrame({"label": labels, "value": counts["problems"]})
    biggest = frame.iloc[0]
    title = (
        f"{biggest['label'].capitalize()} é a maior parte "
        f"({percent(100 * biggest['value'] / n)})"
    )
    with _card(title, f"dos {plural(n, 'problema', 'problemas')}, por macrocategoria"):
        st.altair_chart(charts.donut(frame, mode), theme=None, width="stretch")
    tables["Problemas por macrocategoria"] = frame.rename(
        columns={"label": "macrocategoria", "value": "problemas"}
    )


def _suites(rows: pd.DataFrame, mode: str, tables: dict) -> None:
    status = data.suites_by_status(rows)
    totals = status.groupby("set")["total"].first()
    with_suite = (
        status[status["status"] != data.NO_SUITE]
        .groupby("set")["share"]
        .sum()
        .reindex(totals.index)
        .fillna(0)
    )
    worst = with_suite.idxmin()
    title = f"Toda IA entregou suíte em pelo menos {percent(with_suite.min(), 1)} das combinações"
    sizes = sorted(set(totals))
    per = number(sizes[0]) if len(sizes) == 1 else "/".join(number(s) for s in sizes)
    subtitle = (
        f"de {per} combinações por IA, pelo status da suíte · a menor é "
        f"{SET_LABEL.get(worst, worst)}"
    )
    parts = [p for p in STATUS_ORDER if p in set(status["status"])]
    frame = pd.DataFrame(
        {
            "y": status["set"].map(lambda s: SET_LABEL.get(s, s)),
            "part": status["status"],
            "count": status["combinations"],
            "share": status["share"],
        }
    )
    with _card(title, subtitle):
        chart = charts.stacked100(frame, parts, mode, neutral=data.NO_SUITE)
        st.altair_chart(chart, theme=None, width="stretch")
    tables["Suítes por IA e status"] = frame.rename(
        columns={"y": "IA", "part": "status", "count": "combinações", "share": "%"}
    )


def _tests(rows: pd.DataFrame, summary: dict, mode: str, tables: dict) -> None:
    sizes = data.tests_per_suite(rows)
    if sizes.empty:
        return
    final = sizes[sizes["set"].isin(data.FINAL_SETS)]
    per_set = (final if not final.empty else sizes).groupby("set")["mean"].mean()
    leader = per_set.idxmax()
    title = (
        f"{SET_LABEL.get(leader, leader)} escreve as suítes maiores: "
        f"{number(per_set.max(), 1)} testes em média"
    )
    frame = pd.DataFrame(
        {
            "y": sizes["set"].map(lambda s: SET_LABEL.get(s, s)),
            "series": sizes["scenario"].map(lambda c: SCENARIO_LABEL.get(c, c)),
            "value": sizes["mean"],
        }
    )
    subtitle = (
        f"média de testes por suíte, por cenário · {number(summary['tests'])} testes no total"
    )
    with _card(title, subtitle):
        chart = charts.dots(frame, "testes por suíte", mode)
        st.altair_chart(chart, theme=None, width="stretch")
    tables["Testes por suíte"] = frame.rename(
        columns={"y": "IA", "series": "cenário", "value": "testes por suíte"}
    )


def _spend(summary: dict, mode: str, tables: dict) -> None:
    spend = summary["spend"]
    if not spend:
        st.caption("Gasto: as métricas ainda não foram calculadas (`python -m metrics compute`).")
        return
    total = summary["spend_total"]
    frame = pd.DataFrame(
        {"label": [SET_LABEL[s] for s in spend], "value": [round(v, 2) for v in spend.values()]}
    )
    top = frame.sort_values("value", ascending=False).iloc[0]
    title = (
        f"US$ {number(total, 2)} gastos nas APIs; {top['label']} ficou com "
        f"{percent(100 * top['value'] / total)}"
    )
    with _card(title, "gasto dos três modelos comerciais"):
        st.altair_chart(charts.donut(frame, mode, fmt=",.2f"), theme=None, width="stretch")
        if summary["slm_hours"] is not None:
            st.caption(
                f"**SLM (modelo local): {number(summary['slm_hours'])} h de modelo** em GPUs "
                "próprias, sem custo em dinheiro; por isso fica fora da rosca."
            )
        if summary["cost_not_split"]:
            st.caption(
                "O custo não se divide por problema: o valor é o de todos os problemas dos "
                "cenários escolhidos."
            )
    tables["Gasto por IA"] = frame.rename(columns={"label": "IA", "value": "US$"})


def render(tree: data.LoadedTree, filters: dict) -> None:
    st.title("O experimento")
    rows = data.apply_filters(tree.table, **filters)
    n = int(rows["problem"].nunique())
    cut_banner(filters, n)
    if rows.empty:
        st.write("Nenhum problema atende a esses filtros.")
        return
    mode = theme_mode()
    summary = data.experiment_summary(rows, _read_cost(), filters)
    st.markdown(
        f"#### {plural(n, 'problema', 'problemas')}, "
        f"{plural(summary['wa'] + summary['mutants'], 'falha', 'falhas')}, "
        f"{plural(len(summary['models']), 'IA', 'IAs')}, "
        f"{plural(summary['suites'], 'suíte', 'suítes')}"
    )
    st.markdown(
        "Cada problema do Codeforces tem **100 falhas reais** (submissões humanas erradas, os WAs) "
        "e **100 mutantes** (cópias do código correto com um defeito plantado). Cada IA gerou "
        "testes em três cenários: **caixa-preta** (só o requisito), **caixa-branca** (só o código) "
        "e **híbrido** (os dois)."
    )
    _kpis(summary)
    tables: dict[str, pd.DataFrame] = {}
    left, right = st.columns(2)
    with left:
        _ratings(rows, n, mode, tables)
    with right:
        _macro(rows, n, mode, tables)
    _suites(rows, mode, tables)
    left, right = st.columns(2)
    with left:
        _tests(rows, summary, mode, tables)
    with right:
        _spend(summary, mode, tables)
    with st.expander("Ver os números desta página"):
        for name, frame in tables.items():
            st.markdown(f"**{name}**")
            st.dataframe(frame, hide_index=True)
    bridge(
        "Cada suíte foi executada contra o código correto, os WAs e os mutantes. Quem se saiu "
        "melhor? →",
        "metrics",
    )
