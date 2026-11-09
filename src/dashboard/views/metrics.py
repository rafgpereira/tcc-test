"""Métricas (US4 of the dashboard): the official tables and figures of the metrics module.

Nothing is computed here: the tables are read from ``data/metrics`` and the figures are drawn by
``metrics.figures.render`` with the filters chosen, so a downloaded figure is byte for byte the one
``python -m metrics figures`` writes with the same filters.
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


def _figure_section(loaded: dict, run: dict) -> None:
    from metrics import cuts, figures

    st.subheader("Figuras")
    text(
        "Desenhadas pelo módulo de métricas, com os filtros abaixo; o arquivo baixado é o mesmo "
        "que `python -m metrics figures` gera com os mesmos filtros (o filtro e a fonte vão no "
        "rodapé e no nome do arquivo)."
    )
    per = loaded["per_problem"]
    name = st.selectbox("Figura", list(figures.FIGURES))
    columns = st.columns(4)
    filters = {
        "macrocategorias": columns[0].multiselect(
            "Macrocategoria", sorted(m for m in set(per["macrocategoria"]) if m), key="f_macro"
        ),
        "statuses": columns[1].multiselect(
            "Status", sorted(s for s in set(per["status"]) if s), key="f_status"
        ),
        "sets": columns[2].multiselect(
            "Conjuntos", [s for s in config.SETS if s in set(per["set"])], key="f_sets"
        ),
        "scenarios": columns[3].multiselect("Cenários", list(config.SCENARIOS), key="f_scen"),
    }
    source = figures.source_label(run)
    try:
        png_name, png = figures.render(name, loaded, filters, "png", source)
        pdf_name, pdf = figures.render(name, loaded, filters, "pdf", source)
    except cuts.CutError as exc:
        st.warning(str(exc))
        return
    st.image(png)
    left, right = st.columns(2)
    left.download_button("baixar PNG", png, file_name=png_name, mime="image/png", key="dl_png")
    right.download_button(
        "baixar PDF", pdf, file_name=pdf_name, mime="application/pdf", key="dl_pdf"
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
        "Números oficiais do experimento (em %), calculados pelo módulo de métricas; os filtros "
        "da barra lateral não se aplicam aqui: use o corte de cada tabela."
    )
    metrics = loaded["metrics"]
    cut_labels = ["all"] + sorted(
        {
            f"{c}: {v}"
            for c, v in zip(metrics["cut"], metrics["cut_value"], strict=True)
            if c != "all"
        }
    )
    chosen = st.selectbox(
        "Corte", cut_labels, help="all = os 200 problemas; ou só uma macrocategoria ou um status"
    )
    if chosen == "all":
        shown = metrics[metrics["cut"] == "all"]
    else:
        cut, value = chosen.split(": ", 1)
        shown = metrics[(metrics["cut"] == cut) & (metrics["cut_value"] == value)]
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
    _figure_section(loaded, run)
