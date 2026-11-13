"""A avaliação (feature 012, US4): Comparações and Combinação in one page, in tabs.

Provisional (T016): the two pages of feature 011 drawn as they are; T034–T035 remove their titles
and add the evaluation numbers on top.
"""

import streamlit as st

from dashboard import data
from dashboard.views import combination, compare
from dashboard.views.common import cut_banner


def render(tree: data.LoadedTree, filters: dict) -> None:
    st.title("A avaliação")
    rows = data.apply_filters(tree.table, **filters)
    cut_banner(filters, rows["problem"].nunique())
    tab_compare, tab_combination = st.tabs(["Comparações", "Combinação"])
    with tab_compare:
        compare.render(tree, filters)
    with tab_combination:
        combination.render(tree, filters)
