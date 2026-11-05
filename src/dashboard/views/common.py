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
