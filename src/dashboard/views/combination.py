"""Combinação (US2): test by test, the targets only the declared oracle caught, one target in detail."""

import streamlit as st

from dashboard import config, data
from dashboard.views.common import download, table, text

DIFF_STYLE = """<style>
table.diff {font-family: monospace; font-size: 12px; border-collapse: collapse;}
.diff_header {background: #eee;} td.diff_header {text-align: right; padding: 0 4px;}
.diff_next {display: none;}
.diff_add {background: #aaffaa;} .diff_chg {background: #ffff77;} .diff_sub {background: #ffaaaa;}
</style>"""


def _short(value: str, width: int = 60) -> str:
    one = value.replace("\n", "⏎")
    return one if len(one) <= width else one[: width - 1] + "…"


def render(tree: data.LoadedTree, filters: dict) -> None:
    st.title("Combinação")
    rows = data.apply_filters(tree.table, **filters)
    if rows.empty:
        st.write("Nenhuma combinação com esses filtros.")
        return
    sets = [s for s in config.SETS if s in set(rows["set"])]
    set_name = st.selectbox("Conjunto", sets, help="slm, gpt, gemini, claude ou slm-attempt1")
    problems = sorted(set(rows.loc[rows["set"] == set_name, "problem"]))
    problem = st.selectbox("Problema", problems)
    here = rows[(rows["set"] == set_name) & (rows["problem"] == problem)]
    scenarios = [s for s in config.SCENARIOS if s in set(here["scenario"])]
    scenario = st.selectbox(
        "Cenário", scenarios, help="black_box: só enunciado · white_box: só código · hybrid: ambos"
    )

    detail = data.combination_tests(tree.base, set_name, problem, scenario)
    r = detail.result
    source = r.suite_source
    origin = source.tree + (f", tentativa {source.attempt}" if source.attempt else "")
    text(
        f"**Status** `{source.status or '—'}` · **origem** `{origin}` · **testes** {r.suite_size}"
        f" · **AC aprovado** {r.ac.approved if r.ac else '—'}"
    )
    if not r.has_suite:
        st.info(f"Sem suíte: `{r.no_suite_reason}`.")
        return
    if not detail.suite_available:
        st.warning("A suíte não está descompactada: entrada e saída esperada não disponíveis.")
    if detail.suite_changed:
        st.warning("A suíte mudou desde a avaliação (o hash não confere).")

    shown = detail.tests.copy()
    for column in ("input", "expected", "actual"):
        shown[column] = shown[column].map(_short)
    table(shown)
    download(detail.tests, f"testes_{set_name}_{problem}_{scenario}")
    with st.expander("Saídas completas"):
        index = st.number_input("Teste", 0, max(0, len(detail.tests) - 1), 0)
        if not detail.tests.empty:
            row = detail.tests.iloc[int(index)]
            st.text("entrada:\n" + row["input"])
            st.text("esperada (IA):\n" + row["expected"])
            st.text("real (AC):\n" + row["actual"])

    only = data.only_declared(r)
    st.subheader(f"Pegos só pelo oráculo declarado ({len(only)})")
    text(
        "WAs e mutantes que só o gabarito da IA (decl) pegou; pelo gabarito do AC (corr) eles "
        "passam: a detecção veio de uma saída esperada errada, não de um bug encontrado."
    )
    st.write(", ".join(only) if only else "nenhum")

    st.subheader("Um alvo")
    target = st.selectbox("Alvo", [t.target for t in r.targets], help="WA_n ou Mutant_n")
    info = data.target_detail(tree.base, set_name, problem, scenario, target)
    t = info.target
    for oracle in ("declared", "corrected"):
        d = getattr(t, oracle)
        label = "declarado (decl)" if oracle == "declared" else "corrigido (corr)"
        text(
            f"**{label}**: "
            + (
                f"detectado no teste {d.test_index} ({d.verdict})"
                if d.detected
                else "não detectado"
            )
        )
    if not t.compiled:
        text("Não compilou (CE).")
    if info.diff_html is None:
        st.warning("Código não disponível (dataset ou mutantes não descompactados).")
    else:
        st.html(DIFF_STYLE + info.diff_html)
