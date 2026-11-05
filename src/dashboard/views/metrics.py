"""Métricas (US4): a notice until the metrics module writes its tables (research R7)."""

import streamlit as st

from dashboard import config, data
from dashboard.views.common import text


def render(tree: data.LoadedTree, filters: dict) -> None:
    st.title("Métricas oficiais")
    found = data.metrics_files()
    if not found:
        st.info(
            "Métricas oficiais ainda não calculadas. Elas vêm do módulo de métricas, que grava as "
            f"tabelas em `{config.METRICS_DIR}`; até lá, as outras páginas mostram só a "
            f"{config.PREVIEW_LABEL}."
        )
        text("Serão: TDF, MS, TFP, IIC, TC e CPD (passe o mouse para ver o nome completo).")
        return
    st.write(f"Tabelas encontradas em `{config.METRICS_DIR}`:")
    for name in found:
        st.write(f"- `{name}`")
