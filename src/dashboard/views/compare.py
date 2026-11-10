"""Comparações (US3): declared × corrected oracle; local model × first attempt × commercial ones."""

import streamlit as st

from dashboard import config, data
from dashboard.views.common import download, table, text
from dashboard.views.overview import PREVIEW_NOTE

REJECTED = "background-color: rgba(227, 73, 72, 0.22)"  # a red wash: legible on light and dark


def _highlight_rejected(row):
    color = REJECTED if row["ac_approved"] is False else ""
    return [color] * len(row)


def render(tree: data.LoadedTree, filters: dict) -> None:
    st.title("Comparações")
    rows = data.apply_filters(tree.table, **filters)
    if rows.empty:
        st.write("Nenhuma combinação com esses filtros.")
        return
    st.subheader("Oráculo declarado (decl) × corrigido (corr)")
    text(
        "Diferença entre o que o gabarito da IA (decl) detecta e o que o gabarito do AC (corr) "
        "detecta; em vermelho, as combinações com o AC reprovado."
    )
    gap = data.oracle_gap(rows)
    table(gap, styled=gap.style.apply(_highlight_rejected, axis=1))
    download(gap, "oraculo")
    st.subheader(f"Modelo local × 1ª tentativa × comerciais (% de WAs, {config.PREVIEW_LABEL})")
    text(PREVIEW_NOTE)
    wide = data.local_vs_commercial(rows)
    table(wide)
    download(wide, "modelos")
