"""Métricas (US4 of the dashboard): the official tables and the charts of the metrics module.

Nothing is computed here. The tables are read from ``data/metrics``; the charts are drawn
interactively by ``metrics.figures.chart`` (the same numbers as the tables), with the filters
chosen, in the viewer's theme; the PNG, SVG and PDF buttons save that same chart
(``metrics.figures.render``), so the picture is what the screen shows.
"""

import json
from pathlib import Path

import streamlit as st

from dashboard import config, data
from dashboard.views.common import download, table, text


@st.cache_data(show_spinner="lendo as métricas...")
def _tables(folder: str, stamp: float) -> dict:
    from metrics import tables

    return tables.read(Path("."), Path(folder))


KILLED = (
    "WA_killed",
    "WA_killed_star",
    "WA_total",
    "TDF",
    "mutants_killed",
    "mutants_killed_star",
    "mutants_total",
    "MS",
)
MIME = {"png": "image/png", "svg": "image/svg+xml", "pdf": "application/pdf"}


@st.cache_data(show_spinner="preparando o arquivo...")
def _file(
    name: str, filters_key: tuple, folder: str, stamp: float, source: str, fmt: str, mode: str
) -> tuple[str, bytes]:
    from metrics import figures

    loaded = _tables(folder, stamp)
    return figures.render(name, loaded, dict(filters_key), fmt, source, mode)


def _mode() -> str:
    """The theme the viewer is using (light or dark); light when it cannot be told."""
    try:
        return "dark" if st.context.theme.type == "dark" else "light"
    except AttributeError:
        return "light"


def _charts_section(loaded: dict, run: dict, folder: str, stamp: float, sidebar: dict) -> None:
    from metrics import cuts, figures

    st.subheader("Gráficos")
    text(
        "Os valores estão escritos em cada barra (e a mediana em cada caixa do IIC); os filtros são "
        "os da **barra lateral**. Os botões **PNG**, **SVG** e **PDF** baixam o gráfico como ele "
        "aparece na tela (no tema claro ou escuro), com os filtros e a fonte no subtítulo; no tema "
        "claro, é a mesma figura do comando `python -m metrics figures` com os mesmos filtros."
    )
    filters = {k: list(sidebar.get(k) or []) for k in figures.FILTER_KEYS}
    source = figures.source_label(run)
    filters_key = tuple((k, tuple(v)) for k, v in filters.items() if v)
    for name in figures.FIGURES:
        title = figures.TITLES[name][0]
        try:
            values = figures.figure_data(name, loaded, filters)
        except cuts.CutError:
            if name in figures.NO_PROBLEM_CUTS:
                reason = (
                    "não tem corte por macrocategoria, status ou problema (o custo é por modelo "
                    "e cenário)"
                )
            else:
                reason = "estes filtros deixam um problema só ou nenhum; amplie os filtros"
            st.caption(f"{title}: {reason}")
            continue
        if values.empty:
            st.caption(f"{title}: sem dados com esses filtros")
            continue
        mode = _mode()
        st.altair_chart(
            figures.chart(name, loaded, filters, source, mode), theme=None, width="content"
        )
        for column, fmt in zip(st.columns(6)[:3], ("png", "svg", "pdf"), strict=True):
            with column:
                st.download_button(
                    fmt.upper(),
                    lambda fmt=fmt, name=name, mode=mode: _file(
                        name, filters_key, folder, stamp, source, fmt, mode
                    )[1],
                    file_name=figures.file_name(name, filters, fmt),
                    mime=MIME[fmt],
                    key=f"{fmt}_{name}",
                    icon=":material/download:",
                    on_click="ignore",
                )


def render(tree: data.LoadedTree, filters: dict) -> None:
    st.title("Métricas oficiais")
    folder = config.METRICS_DIR
    found = data.metrics_files()
    if "metrics.csv" not in found:
        st.info(
            "Métricas oficiais ainda não calculadas. Elas vêm do módulo de métricas "
            "(`docker compose run --rm app python -m metrics compute`), que grava as tabelas em "
            f"`{folder}`; até lá, as outras páginas mostram só a {config.PREVIEW_LABEL}."
        )
        text("Serão: TDF, MS, TFP, IIC, TC e CPD (passe o mouse para ver o nome completo).")
        return
    stamp = (Path(folder) / "metrics.csv").stat().st_mtime
    loaded = _tables(str(folder), stamp)
    run_path = Path(folder) / "run.json"
    run = json.loads(run_path.read_text()) if run_path.is_file() else {}
    text(
        "Números oficiais do experimento (em %), calculados pelo módulo de métricas. Os filtros da "
        "barra lateral valem para os gráficos; as tabelas abaixo são as oficiais, com o corte "
        "escolhido nelas."
    )
    _charts_section(loaded, run, str(folder), stamp, filters)

    metrics = loaded["metrics"]
    cut_labels = ["all"] + sorted(
        {
            f"{c}: {v}"
            for c, v in zip(metrics["cut"], metrics["cut_value"], strict=True)
            if c != "all"
        }
    )
    chosen = st.selectbox(
        "Corte das tabelas",
        cut_labels,
        help="all = os 200 problemas; ou só uma macrocategoria ou um status",
    )
    if chosen == "all":
        shown = metrics[metrics["cut"] == "all"]
    else:
        cut, value = chosen.split(": ", 1)
        shown = metrics[(metrics["cut"] == cut) & (metrics["cut_value"] == value)]
    st.subheader("WAs e mutantes mortos")
    text(
        "Cada WA e cada mutante conta uma vez: **morto** se algum teste da suíte o reprovou. São "
        "100 WAs e 100 mutantes por problema; a TDF é *WAs mortos ÷ WAs no total* e o MS, *mutantes "
        "mortos ÷ mutantes no total*. Com \\* = pelo gabarito do AC."
    )
    killed = shown[["set", "scenario", *KILLED]]
    table(killed)
    download(killed, "mortos")
    st.subheader("TDF, MS, TFP, TC e complementares")
    table(shown)
    download(shown, "metricas")
    st.subheader("IIC (influência do contexto)")
    table(loaded["iic"])
    download(loaded["iic"], "iic")
    st.subheader("Testes estatísticos")
    only_significant = st.checkbox("só as diferenças significativas")
    stats = loaded["stats"]
    if only_significant:
        stats = stats[stats["significant"] == True]
    table(stats)
    download(stats, "estatistica")
    st.subheader("Custo, tokens e tempo")
    table(loaded["cost"])
    download(loaded["cost"], "custo")
