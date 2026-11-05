"""Visão geral (US1): what was evaluated, per set × scenario, with the filters."""

import streamlit as st

from dashboard import config, data
from dashboard.views.common import download, table, text

PREVIEW_NOTE = (
    f"As porcentagens são uma **{config.PREVIEW_LABEL}** da detecção (Σ detectados ÷ Σ total, só "
    "combinações com suíte); as métricas oficiais (TDF, MS) vêm do módulo de métricas. Passe o "
    "mouse sobre o nome de uma coluna ou de uma sigla para ver o que significa."
)


def render(tree: data.LoadedTree, filters: dict) -> None:
    st.title("Visão geral")
    rows = data.apply_filters(tree.table, **filters)
    if rows.empty:
        st.write("Nenhuma combinação com esses filtros.")
        return
    text(PREVIEW_NOTE)
    summary = data.overview(rows)
    st.subheader(f"Por conjunto e cenário ({config.PREVIEW_LABEL} nas colunas %)")
    table(summary)
    download(summary, "visao_geral")
    st.subheader(f"Por combinação ({config.PREVIEW_LABEL})")
    per = data.per_problem(rows)
    table(per)
    download(per, "por_combinacao")
