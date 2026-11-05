"""The Streamlit entry point: sidebar (folder, reload, filters) and the four pages.

Run by ``python -m dashboard serve``; the tests call ``main(page=...)`` through ``AppTest``. The
data are read once and kept (``st.cache_data``) until "recarregar dados" changes the cache key
(FR-001a). Nothing is ever written.
"""

import os
from pathlib import Path

import streamlit as st

from dashboard import config, data, glossary
from dashboard.views import combination, compare, metrics, overview
from dashboard.views.common import sidebar_glossary

PAGES = {
    "overview": ("Visão geral", overview.render),
    "combination": ("Combinação", combination.render),
    "compare": ("Comparações", compare.render),
    "metrics": ("Métricas", metrics.render),
}


@st.cache_data(show_spinner="lendo os resultados...")
def _load(base: str, root: str, reload_count: int) -> data.LoadedTree:
    return data.combinations(Path(base), Path(root))


def _sidebar() -> tuple[data.LoadedTree, dict]:
    default = os.environ.get(config.ENV_EVALUATION_DIR, str(config.DEFAULT_EVALUATION_DIR))
    with st.sidebar:
        base = st.text_input("Pasta de avaliação", value=default)
        if st.button("recarregar dados"):
            st.session_state["reload"] = st.session_state.get("reload", 0) + 1
        tree = _load(base, ".", st.session_state.get("reload", 0))
        st.caption(f"lido em {tree.loaded_at:%Y-%m-%d %H:%M:%S} UTC")
        if tree.closed:
            st.caption(
                "problemas concluídos: "
                + ", ".join(f"{s} {n}" for s, n in sorted(tree.closed.items()))
            )
        if tree.invalid:
            st.warning(f"{len(tree.invalid)} arquivo(s) inválido(s)")
            for name, reason in tree.invalid[:20]:
                st.caption(f"{name}: {reason}")
        table = tree.table

        def explain(value: str) -> str:
            meaning = glossary.VALUES.get(value)
            return f"{value} — {meaning}" if meaning else value

        filters = {
            "sets": st.multiselect(
                "Conjunto",
                [s for s in config.SETS if s in set(table["set"])],
                format_func=explain,
                help="Qual suíte avaliar: a final de cada modelo ou a 1ª tentativa do SLM",
            ),
            "scenarios": st.multiselect(
                "Cenário", list(config.SCENARIOS), format_func=explain, help="O que a IA recebeu"
            ),
            "problems": st.multiselect("Problema", sorted(set(table["problem"]))),
            "macrocategorias": st.multiselect(
                "Macrocategoria",
                sorted(m for m in set(table["macrocategoria"]) if m),
                format_func=explain,
                help="Categoria algorítmica do problema",
            ),
            "statuses": st.multiselect(
                "Status da suíte",
                sorted(s for s in set(table["status"]) if s),
                format_func=explain,
                help="Como a suíte foi obtida",
            ),
        }
        sidebar_glossary()
    return tree, filters


def main(page: str | None = None) -> None:
    st.set_page_config(page_title="Resultados da avaliação", layout="wide")
    tree, filters = _sidebar()
    if tree.table.empty:
        st.info(
            f"Nenhum resultado concluído em `{tree.base}` ainda. Para avaliar: "
            "`docker compose run --rm sandbox python -m evaluation run`"
        )
    if page is not None:  # the tests open one page directly
        PAGES[page][1](tree, filters)
        return
    navigation = st.navigation(
        [
            st.Page(lambda f=fn: f(tree, filters), title=title, url_path=key)
            for key, (title, fn) in PAGES.items()
        ]
    )
    navigation.run()


if __name__ == "__main__":
    main()
