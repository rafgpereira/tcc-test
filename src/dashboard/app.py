"""The Streamlit entry point: sidebar (folder, reload, filters) and the three pages.

Feature 012: O experimento (default) → As métricas → Rastreabilidade → A avaliação, with the filters only in the
sidebar. The keys of the pages of feature 011 (overview, combination, compare) can still be opened
by ``main(page=...)`` until the evaluation page replaces them (specs/012, T034–T037).

Run by ``python -m dashboard serve``; the tests call ``main(page=...)`` through ``AppTest``. The
data are read once and kept (``st.cache_data``) until "recarregar dados" changes the cache key
(FR-001a). Nothing is ever written.
"""

import os
from pathlib import Path

import streamlit as st

from dashboard import config, data, glossary
from dashboard.views import (
    combination,
    common,
    compare,
    evaluation,
    experiment,
    metrics,
    overview,
    trace,
)
from dashboard.views.common import sidebar_glossary
from dashboard.views.experiment import SCENARIO_LABEL, SET_LABEL

PAGES = {
    "experiment": ("O experimento", experiment.render),
    "metrics": ("As métricas", metrics.render),
    "trace": ("Rastreabilidade", trace.render),
    "evaluation": ("A avaliação", evaluation.render),
    # pages of feature 011, out of the navigation; kept for the tests until T037
    "overview": ("Visão geral", overview.render),
    "combination": ("Combinação", combination.render),
    "compare": ("Comparações", compare.render),
}
NAVIGATION = ("experiment", "metrics", "trace", "evaluation")


@st.cache_data(show_spinner="lendo os resultados...")
def _load(base: str, root: str, reload_count: int) -> data.LoadedTree:
    return data.combinations(Path(base), Path(root))


def _sidebar() -> tuple[data.LoadedTree, dict]:
    default = os.environ.get(config.ENV_EVALUATION_DIR, str(config.DEFAULT_EVALUATION_DIR))
    with st.sidebar:
        st.markdown("**Filtros**")
        st.caption("Valem para todas as páginas; vazio = tudo.")
        filter_box = st.container()  # drawn first, filled once the data are read
        st.divider()
        with st.expander("Fonte dos dados"):
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
            "sets": filter_box.multiselect(
                "IA (conjunto)",
                [s for s in config.SETS if s in set(table["set"])],
                format_func=lambda s: SET_LABEL.get(s, s),
                placeholder="todas",
                help="A suíte final de cada modelo, ou a 1ª tentativa do modelo local",
            ),
            "scenarios": filter_box.multiselect(
                "Cenário",
                list(config.SCENARIOS),
                format_func=lambda c: SCENARIO_LABEL.get(c, c),
                placeholder="todos",
                help="caixa-preta: só o requisito · caixa-branca: só o código · híbrido: os dois",
            ),
            "problems": filter_box.multiselect(
                "Problema", sorted(set(table["problem"])), placeholder="todos"
            ),
            "macrocategorias": filter_box.multiselect(
                "Macrocategoria",
                sorted(m for m in set(table["macrocategoria"]) if m),
                placeholder="todas",
                format_func=explain,
                help="Categoria algorítmica do problema",
            ),
            "ratings": filter_box.multiselect(
                "Rating",
                sorted(int(r) for r in set(table["rating"].dropna())),
                placeholder="todos",
                help="Dificuldade do problema no Codeforces (de 1000 a 1600)",
            ),
            "statuses": filter_box.multiselect(
                "Status da suíte",
                sorted(s for s in set(table["status"]) if s),
                placeholder="todos",
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
    pages = {
        key: st.Page(lambda f=PAGES[key][1]: f(tree, filters), title=PAGES[key][0], url_path=key)
        for key in NAVIGATION
    }
    common.register_pages(pages)
    st.navigation(list(pages.values())).run()


if __name__ == "__main__":
    main()
