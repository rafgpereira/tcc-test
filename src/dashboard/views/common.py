"""What every page shares: tables with tooltips, text with abbreviations, the CSV download."""

import streamlit as st

from dashboard import glossary


def table(frame, styled=None) -> None:
    """A table whose headers show the full name of each column on hover."""
    config = {}
    for name in frame.columns:
        found = glossary.column_help(str(name))
        if found is not None:
            label, help_text = found
            config[name] = st.column_config.Column(label, help=help_text)
    st.dataframe(styled if styled is not None else frame, hide_index=True, column_config=config)


def text(markdown: str) -> None:
    """Markdown with every known abbreviation explained on hover."""
    st.markdown(glossary.abbr(markdown), unsafe_allow_html=True)


def download(frame, name: str) -> None:
    st.download_button(
        "baixar CSV", frame.to_csv(index=False), file_name=f"{name}.csv", mime="text/csv", key=name
    )


def sidebar_glossary() -> None:
    with st.expander("Glossário (siglas e valores)"):
        for term, meaning in glossary.TERMS.items():
            st.markdown(f"**{term}**: {meaning}")
        for value, meaning in glossary.VALUES.items():
            st.markdown(f"`{value}`: {meaning}")


# ---------------------------------------------------------------- feature 012: cut and bridges

FILTER_LABELS = {  # sidebar key -> label in the banner
    "sets": "conjunto",
    "scenarios": "cenário",
    "macrocategorias": "macrocategoria",
    "ratings": "rating",
    "statuses": "status",
    "problems": "problema",
}
_PAGES: dict = {}  # url key -> st.Page, set by app.main when the navigation exists


def register_pages(pages: dict) -> None:
    _PAGES.clear()
    _PAGES.update(pages)


def cut_description(filters: dict, n_problems: int) -> str:
    """ "filtros: macrocategoria = matematica · 41 problemas" (or "Sem filtros · 200 problemas")."""
    applied = [
        f"{label} = {', '.join(str(v) for v in filters[key])}"
        for key, label in FILTER_LABELS.items()
        if filters.get(key)
    ]
    noun = "problema" if n_problems == 1 else "problemas"
    head = f"filtros: {'; '.join(applied)}" if applied else "Sem filtros"
    return f"{head} · {n_problems} {noun}"


def cut_banner(filters: dict, n_problems: int) -> None:
    """The line at the top of every page with the active cut (FR-004)."""
    st.caption(cut_description(filters, n_problems))


def bridge(sentence: str, page_key: str) -> None:
    """The closing sentence of a page, with a link to the next one when the navigation exists."""
    st.divider()
    page = _PAGES.get(page_key)
    if page is None:
        st.markdown(f"**{sentence}**")
    else:
        st.page_link(page, label=sentence, icon=":material/arrow_forward:")


def theme_mode() -> str:
    """The theme the page is drawn in (light or dark); light when it cannot be told.

    A theme fixed in the configuration (``theme.base``) wins: then ``st.context.theme`` may still
    report the browser's preference, not the page's (seen in the review of 2026-11-12).
    """
    base = st.get_option("theme.base")
    if base in ("light", "dark"):
        return base
    try:
        return "dark" if st.context.theme.type == "dark" else "light"
    except AttributeError:
        return "light"
