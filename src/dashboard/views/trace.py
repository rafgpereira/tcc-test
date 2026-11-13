"""Rastreabilidade (feature 012, US5): from a number back to the problem, the suite and the test.

The reader chooses what to trace; each case lists the items of the sidebar cut and opens one of
them: a combination (status, why it has no suite, the generation attempts, the tests with the
AC's output), a target (who detected it, with which test, and its code beside the AC) or a
problem (statement, AC and its 15 combinations). Everything comes from ``dashboard.trace`` and
``dashboard.data``; nothing is computed beyond counting and nothing is written.
"""

from pathlib import Path

import pandas as pd
import streamlit as st

from dashboard import data, trace
from dashboard.views.combination import DIFF_STYLE
from dashboard.views.common import bridge, cut_banner, download, table, text
from dashboard.views.experiment import SCENARIO_LABEL, SET_LABEL, number

CASES = {
    "missing": "Combinações sem suíte, com o motivo",
    "barred": 'Suítes "sem raciocínio"',
    "slm_origin": "De onde veio a suíte do modelo local",
    "test_of_target": "Qual teste reprovou um WA ou mutante",
    "targets_of_test": "O que um teste derrubou",
    "ac_rejected": "Por que o código correto (AC) foi reprovado",
    "oracle_only": "Detecções que só existem por um dos gabaritos",
    "undetected": "WAs que nenhuma IA detectou",
    "exclusive": "WAs que só uma IA detectou",
    "surviving": "Mutantes que sobreviveram a todas as suítes",
    "iic": "De onde vem o IIC: os conjuntos de WAs de cada cenário",
    "problem": "Ficha de um problema",
}
NEEDS_TARGETS = {
    "iic",
    "test_of_target",
    "targets_of_test",
    "oracle_only",
    "undetected",
    "exclusive",
    "surviving",
}


@st.cache_data(show_spinner="lendo os alvos de cada combinação...")
def _targets(base: str, stamp: tuple) -> pd.DataFrame:
    return trace.targets(Path(base))


def _stamp(base: Path) -> tuple:
    return tuple(
        (p.parent.name, p.stat().st_mtime) for p in sorted(Path(base).glob("*/results.csv"))
    )


def _set(name: str) -> str:
    return SET_LABEL.get(name, name)


def _scenario(name: str) -> str:
    return SCENARIO_LABEL.get(name, name)


def _pretty(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    if "set" in out:
        out["set"] = out["set"].map(_set)
    if "scenario" in out:
        out["scenario"] = out["scenario"].map(_scenario)
    if "só quem detectou" in out:
        out["só quem detectou"] = out["só quem detectou"].map(_set)
    return out.rename(columns={"set": "IA", "scenario": "cenário", "problem": "problema"})


def _combo(r) -> str:
    return f"{_set(r['set'])} · {r['problem']} · {_scenario(r['scenario'])}"


def _pick(label: str, frame: pd.DataFrame, describe, key: str):
    """A choice among the rows of ``frame``; the chosen row, or None when the list is empty."""
    if frame.empty:
        return None
    index = st.selectbox(
        label, list(frame.index), format_func=lambda i: describe(frame.loc[i]), key=key
    )
    return frame.loc[index]


def _short(value: str, width: int = 50) -> str:
    one = str(value).replace("\n", "⏎")
    return one if len(one) <= width else one[: width - 1] + "…"


def _row_of(tree: data.LoadedTree, set_name: str, problem: str, scenario: str) -> pd.Series:
    t = tree.table
    return t[(t["set"] == set_name) & (t["problem"] == problem) & (t["scenario"] == scenario)].iloc[
        0
    ]


# ------------------------------------------------------------------------------------ cards


def _attempts(tree: data.LoadedTree, row: pd.Series) -> None:
    found = trace.attempts(Path("."), row["tree"], row["problem"], row["scenario"])
    if found.empty:
        st.caption("Tentativas: os arquivos das suítes não estão descompactados.")
        return
    st.markdown(f"**Tentativas de geração ({len(found)})**")
    table(found)
    barred = trace.barred_responses(Path("."), row["set"], row["problem"], row["scenario"])
    if not barred.empty:
        st.markdown(f"**Respostas sem raciocínio ({len(barred)})**")
        table(barred)


def _combination_card(
    tree: data.LoadedTree,
    set_name: str,
    problem: str,
    scenario: str,
    *,
    only_failing_ac: bool = False,
    with_attempts: bool = False,
) -> data.CombinationDetail | None:
    row = _row_of(tree, set_name, problem, scenario)
    with st.container(border=True):
        st.markdown(f"**{_set(set_name)} · {problem} · {_scenario(scenario)}**")
        status = (
            data.STATUS_LABEL.get(row["status"], row["status"])
            if row["has_suite"]
            else data.NO_SUITE
        )
        attempt = row["attempt"] if pd.notna(row["attempt"]) and row["attempt"] else None
        origin = row["tree"] + (f", tentativa {int(attempt)}" if attempt else "")
        st.caption(
            f"status: {status} · origem: {origin or '—'} · testes: {int(row['suite_size'])}"
            + (
                f" · AC {'aprovado' if row['ac_approved'] else 'reprovado'}"
                if row["has_suite"]
                else ""
            )
        )
        if not row["has_suite"]:
            st.markdown(f"Sem suíte: {trace.no_suite_reason(Path('.'), row)}.")
        if with_attempts or not row["has_suite"]:
            _attempts(tree, row)
        if not row["has_suite"]:
            return None
        detail = data.combination_tests(tree.base, set_name, problem, scenario)
        if not detail.suite_available:
            st.caption("A suíte não está descompactada: entrada e saída esperada indisponíveis.")
        tests = detail.tests
        if only_failing_ac:
            tests = tests[tests["ac_verdict"] != "passed"]
            st.markdown(f"**Testes que reprovam o AC ({len(tests)} de {len(detail.tests)})**")
        else:
            st.markdown(f"**Testes ({len(tests)})**")
        shown = tests.rename(
            columns={
                "index": "teste",
                "input": "entrada",
                "expected": "esperada (IA)",
                "actual": "saída do AC",
                "ac_verdict": "AC",
                "error_kind": "erro",
                "wa_declared_here": "WAs (IA)",
                "wa_corrected_here": "WAs (AC)",
                "mut_declared_here": "mutantes (IA)",
                "mut_corrected_here": "mutantes (AC)",
            }
        )
        for column in ("entrada", "esperada (IA)", "saída do AC"):
            shown[column] = shown[column].map(_short)
        table(shown.drop(columns=["unstable"]))
        download(tests, f"testes_{set_name}_{problem}_{scenario}")
        st.caption(
            "WAs e mutantes por teste: os que esse teste derrubou primeiro (cada alvo para no "
            "primeiro teste que o reprova)."
        )
    return detail


def _test_text(detail: data.CombinationDetail, index: int) -> None:
    found = detail.tests[detail.tests["index"] == index]
    if found.empty:
        return
    test = found.iloc[0]
    left, middle, right = st.columns(3)
    left.markdown("**entrada**")
    left.code(test["input"] or "(vazia)", language=None)
    middle.markdown("**saída esperada (escrita pela IA)**")
    middle.code(test["expected"] or "(vazia)", language=None)
    right.markdown(f"**saída do AC** ({test['ac_verdict']})")
    right.code(test["actual"] or "(vazia)", language=None)


def _code_diff(tree: data.LoadedTree, frame: pd.DataFrame, problem: str, target: str) -> None:
    mine = frame[(frame["problem"] == problem) & (frame["target"] == target)]
    if mine.empty:
        return
    first = mine.iloc[0]
    info = data.target_detail(tree.base, first["set"], problem, first["scenario"], target)
    with st.expander(f"Código de {target} ao lado do AC", expanded=False):
        if info.diff_html is None:
            st.caption("Código não disponível (dataset ou mutantes não descompactados).")
        else:
            st.html(DIFF_STYLE + info.diff_html)


def _target_card(tree: data.LoadedTree, frame: pd.DataFrame, problem: str, target: str) -> None:
    with st.container(border=True):
        kind = "WA" if target.startswith("WA") else "mutante"
        st.markdown(f"**{problem} · {target}** ({kind})")
        matrix = trace.target_matrix(frame, problem, target)
        detected = matrix[matrix["gabarito do AC"] != "—"] if not matrix.empty else matrix
        st.caption(
            f"Detectado pelo gabarito do AC em {len(detected)} das {len(matrix)} combinações do "
            "recorte; o número é o primeiro teste que o reprovou."
        )
        table(_pretty(matrix))
        _code_diff(tree, frame, problem, target)


def _problem_card(tree: data.LoadedTree, rows: pd.DataFrame, problem: str) -> None:
    info = trace.problem_info(Path("."), problem)
    with st.container(border=True):
        st.markdown(f"**{info['name']}**")
        details = [
            f"rating {info['rating']}" if info["rating"] else "",
            info["macrocategoria"],
            ", ".join(info["tags"]),
            f"limite de tempo {info['time_limit_seconds']} s" if info["time_limit_seconds"] else "",
        ]
        st.caption(" · ".join(d for d in details if d))
        if info["url"]:
            st.markdown(f"[Abrir no Codeforces]({info['url']})")
        grid = trace.problem_grid(rows, problem)
        table(_pretty(grid))
        with st.expander("Enunciado"):
            st.markdown(info["statement"] or "O dataset não está descompactado.")
        with st.expander("Código correto (AC_ref.cpp)"):
            st.code(info["ac"] or "O dataset não está descompactado.", language="cpp")


def _choose_combination(rows: pd.DataFrame, key: str):
    with_suite = rows[rows["has_suite"]]
    if with_suite.empty:
        st.write("Nenhuma combinação com suíte neste recorte.")
        return None
    columns = st.columns(3)
    sets = [s for s in data.config.SETS if s in set(with_suite["set"])]
    set_name = columns[0].selectbox("IA", sets, format_func=_set, key=f"{key}_set")
    mine = with_suite[with_suite["set"] == set_name]
    problem = columns[1].selectbox("Problema", sorted(set(mine["problem"])), key=f"{key}_problem")
    here = mine[mine["problem"] == problem]
    scenarios = [s for s in data.config.SCENARIOS if s in set(here["scenario"])]
    scenario = columns[2].selectbox("Cenário", scenarios, format_func=_scenario, key=f"{key}_sc")
    return set_name, problem, scenario


# ------------------------------------------------------------------------------------ cases


def _missing(tree, rows, frame) -> None:
    found = trace.missing_suites(rows)
    counts = found["set"].map(_set).value_counts()
    text(
        f"**{number(len(found))} combinações sem suíte** neste recorte"
        + (": " + ", ".join(f"{s} {n}" for s, n in counts.items()) if len(found) else "")
        + ". Elas contam como 0% de detecção nas métricas."
    )
    table(_pretty(found))
    chosen = _pick("Abrir", found, _combo, "missing_pick")
    if chosen is not None:
        _combination_card(tree, chosen["set"], chosen["problem"], chosen["scenario"])


def _barred(tree, rows, frame) -> None:
    found = trace.barred_suites(rows)
    rejected = int((~found["ac_approved"].astype(bool)).sum()) if len(found) else 0
    text(
        f"**{len(found)} suítes vieram de respostas sem raciocínio** (o modelo respondeu sem "
        f"raciocinar três vezes; a suíte é a da última resposta legível). **{rejected} delas "
        "reprovam o AC.** Elas ficam nas métricas, como suítes que a ferramenta entregou."
    )
    table(_pretty(found))
    chosen = _pick("Abrir", found, _combo, "barred_pick")
    if chosen is not None:
        _combination_card(
            tree, chosen["set"], chosen["problem"], chosen["scenario"], with_attempts=True
        )


def _slm_origin(tree, rows, frame) -> None:
    found = trace.slm_origin(rows)
    if found.empty:
        st.write("O modelo local não está no recorte.")
        return
    counts = found["origem"].value_counts()
    text(
        "O modelo local escreve uma **solução** e as saídas vêm de executá-la (aceita); se a "
        "solução falha nos testes públicos, ele **prediz** as saídas (reserva). "
        + " · ".join(f"**{n}** {o}" for o, n in counts.items())
        + "."
    )
    table(_pretty(found.drop(columns=["status"])))
    chosen = _pick("Abrir", found.assign(set="slm"), _combo, "slm_pick")
    if chosen is not None:
        _combination_card(tree, "slm", chosen["problem"], chosen["scenario"], with_attempts=True)


def _test_of_target(tree, rows, frame) -> None:
    text(
        "Escolha a combinação e o alvo: aparece o teste que o reprovou em cada gabarito, a "
        "entrada e as duas saídas esperadas (a da IA e a do AC), e o código do alvo ao lado do AC."
    )
    chosen = _choose_combination(rows, "tt")
    if chosen is None:
        return
    set_name, problem, scenario = chosen
    mine = frame[
        (frame["set"] == set_name) & (frame["problem"] == problem) & (frame["scenario"] == scenario)
    ]
    mine = trace._target_order(mine).reset_index(drop=True)

    def describe(r) -> str:
        ia = f"teste {r['declared_test']}" if r["declared"] else "não"
        ac = f"teste {r['corrected_test']}" if r["corrected"] else "não"
        return f"{r['target']} · gabarito da IA: {ia} · do AC: {ac}"

    target = _pick("Alvo", mine, describe, "tt_target")
    if target is None:
        return
    detail = data.combination_tests(tree.base, set_name, problem, scenario)
    for oracle, label in (("declared", "gabarito da IA"), ("corrected", "gabarito do AC")):
        if target[oracle]:
            st.markdown(f"**Pelo {label}: reprovado no teste {target[f'{oracle}_test']}**")
            _test_text(detail, int(target[f"{oracle}_test"]))
        else:
            st.markdown(f"**Pelo {label}: nenhum teste reprovou {target['target']}.**")
    if not target["compiled"]:
        st.caption("Este alvo não compilou.")
    _code_diff(tree, frame, problem, target["target"])


def _targets_of_test(tree, rows, frame) -> None:
    text(
        "Escolha a combinação e um teste: aparecem a entrada, as saídas e os alvos que esse "
        "teste derrubou. Cada alvo para no **primeiro** teste que o reprova, então um alvo "
        "derrubado por um teste anterior não aparece de novo aqui."
    )
    chosen = _choose_combination(rows, "kt")
    if chosen is None:
        return
    set_name, problem, scenario = chosen
    detail = data.combination_tests(tree.base, set_name, problem, scenario)
    if detail.tests.empty:
        st.write("Esta suíte não tem testes executados.")
        return
    tests = detail.tests.set_index("index", drop=False)
    index = st.selectbox(
        "Teste",
        list(tests.index),
        format_func=lambda i: f"teste {i} · AC {tests.loc[i, 'ac_verdict']}",
        key="kt_test",
    )
    _test_text(detail, int(index))
    killed = trace.killed_by_test(frame, set_name, problem, scenario, int(index))
    for oracle, label in (("declared", "gabarito da IA"), ("corrected", "gabarito do AC")):
        names = killed[oracle]
        st.markdown(f"**Pelo {label}: {len(names)} alvos**")
        st.write(", ".join(names) if names else "nenhum")


def _ac_rejected(tree, rows, frame) -> None:
    by_problem = trace.ac_rejections_by_problem(rows)
    found = trace.ac_rejections(rows)
    text(
        f"**{number(len(found))} suítes reprovam o código correto** neste recorte, em "
        f"{len(by_problem)} problemas. Um teste reprova o AC quando a saída esperada que a IA "
        "escreveu está errada, ou quando a entrada é inválida e o AC falha ao rodar."
    )
    left, right = st.columns([1, 2])
    with left:
        st.markdown("**Problemas que mais reprovam o AC**")
        table(by_problem.rename(columns={"problem": "problema", "suites": "suítes"}))
    with right:
        st.markdown("**Suítes que reprovam o AC**")
        table(_pretty(found))
    chosen = _pick("Abrir", found, _combo, "ac_pick")
    if chosen is not None:
        _combination_card(
            tree, chosen["set"], chosen["problem"], chosen["scenario"], only_failing_ac=True
        )


def _oracle_only(tree, rows, frame) -> None:
    found = trace.oracle_only(frame)
    declared = int(found["só pelo gabarito da IA"].sum()) if len(found) else 0
    corrected = int(found["só pelo gabarito do AC"].sum()) if len(found) else 0
    text(
        f"**{number(declared)} detecções só existem pelo gabarito da IA**: o teste reprovou o alvo porque "
        "a saída esperada estava errada, não porque achou o defeito. **"
        f"{number(corrected)} só existem pelo gabarito do AC**: com a saída certa, um teste passa a "
        "pegar um alvo que a saída errada deixava passar."
    )
    table(_pretty(found))
    chosen = _pick("Abrir", found, _combo, "oo_pick")
    if chosen is None:
        return
    only_ia, only_ac = trace.oracle_only_targets(
        frame, chosen["set"], chosen["problem"], chosen["scenario"]
    )
    st.markdown(f"**Só pelo gabarito da IA ({len(only_ia)})**")
    st.write(", ".join(only_ia) if only_ia else "nenhum")
    st.markdown(f"**Só pelo gabarito do AC ({len(only_ac)})**")
    st.write(", ".join(only_ac) if only_ac else "nenhum")
    _combination_card(
        tree, chosen["set"], chosen["problem"], chosen["scenario"], only_failing_ac=True
    )
    st.caption('Para ver um alvo teste a teste, use "Qual teste reprovou um WA ou mutante".')


def _hard_targets(tree, rows, frame, case: str) -> None:
    if case == "undetected":
        found = trace.undetected(frame, "wa")
        intro = "WAs que **nenhuma das IAs do recorte** detectou, em nenhum cenário"
    elif case == "exclusive":
        found = trace.exclusive(frame, "wa")
        intro = "WAs que **só uma IA** detectou (em algum cenário)"
    else:
        found = trace.undetected(frame, "mutant")
        intro = (
            "Mutantes que **nenhuma suíte do recorte** reprovou; alguns podem ser equivalentes "
            "ao AC (mesmo comportamento com outro código)"
        )
    problems = found["problem"].nunique() if len(found) else 0
    text(f"{intro}, pelo gabarito do AC: **{number(len(found))}**, em **{problems}** problemas.")
    if case == "exclusive" and len(found):
        counts = found["só quem detectou"].map(_set).value_counts()
        st.caption(" · ".join(f"{s}: {n}" for s, n in counts.items()))
    table(_pretty(found))
    chosen = _pick("Abrir", found, lambda r: f"{r['problem']} · {r['target']}", f"{case}_pick")
    if chosen is not None:
        _target_card(tree, frame, chosen["problem"], chosen["target"])


IIC_ORACLE = {"do AC (corrigido)": "corrected", "da IA (declarado)": "declared"}
IIC_DIRECTION = {
    "cod": "+ código: híbrido (H) sobre caixa-preta (R)",
    "req": "+ requisito: híbrido (H) sobre caixa-branca (C)",
}


def _signed(value: float) -> str:
    return f"{value:+.1f}%".replace(".", ",").replace("-", "−")


def _mark(flag: bool) -> str:
    return "✓" if flag else "—"


def _iic(tree, rows, frame) -> None:
    text(
        "O IIC compara os WAs que a mesma IA pegou em cada cenário: **R** = caixa-preta (só o "
        "requisito), **C** = caixa-branca (só o código), **H** = híbrido (os dois). Cada elemento "
        "é um par (problema, WA), somado em todos os problemas do recorte; o filtro de cenário "
        "não vale aqui, porque o IIC compara os cenários."
    )
    columns = st.columns(3)
    sets = [s for s in data.config.SETS if s in set(frame["set"])]
    if not sets:
        st.write("Nenhuma IA neste recorte.")
        return
    set_name = columns[0].selectbox("IA", sets, format_func=_set, key="iic_set")
    direction = columns[1].selectbox(
        "Direção", list(IIC_DIRECTION), format_func=IIC_DIRECTION.get, key="iic_dir"
    )
    oracle = IIC_ORACLE[columns[2].radio("Gabarito", list(IIC_ORACLE), key="iic_oracle")]
    was = trace.iic_wa_table(frame, set_name, oracle)
    if was.empty:
        st.write("Nenhum WA desta IA no recorte.")
        return
    terms = trace.iic_terms(was, direction)
    base = terms["base"]

    st.markdown("**1. Os conjuntos**")
    sizes = " · ".join(f"|{x}| = {number(int(was[x].sum()))}" for x in ("R", "C", "H"))
    st.caption(
        f"{number(len(was))} pares (problema, WA) no recorte, {was['problem'].nunique()} "
        f"problemas. {sizes}."
    )
    table(trace.iic_regions(was))

    st.markdown("**2. A conta**")
    st.latex(
        rf"\text{{IIC}} = \frac{{|H \setminus {base}| - |{base} \setminus H|}}{{|{base}|}} "
        rf"\times 100 = \frac{{{terms['gains']} - {terms['losses']}}}{{{terms['base_size']}}} "
        rf"\times 100"
    )
    if terms["base_size"]:
        st.markdown(
            f"= **{_signed(terms['iic'])}**. Ganhos ({number(terms['gains'])}): WAs que o "
            f"híbrido pegou e a base ({base}) não; perdas ({number(terms['losses'])}): WAs que a "
            f"base pegou e o híbrido não. Os ganhos e as perdas são somas de regiões da tabela "
            f"acima."
        )
    else:
        st.markdown("A base não pegou nenhum WA: o IIC não se calcula neste recorte.")
    regions = trace.iic_regions(was).set_index("região")["WAs (pares problema, WA)"]
    parts = trace.iic_term_regions(direction)
    names = {
        "gains": f"|H ∖ {base}| (ganhos)",
        "losses": f"|{base} ∖ H| (perdas)",
        "base_size": f"|{base}| (base)",
    }
    lines = []
    for key, label in names.items():
        summed = " + ".join(f"{r} ({number(int(regions[r]))})" for r in parts[key])
        lines.append(f"- {label} = {summed} = **{number(terms[key])}**")
    st.markdown("Para conferir à mão, com as regiões da tabela:\n\n" + "\n".join(lines))

    st.markdown("**3. Problema a problema**")
    st.caption(
        "Ordenados pelo que mais pesa no saldo (ganhos − perdas). Sem WA na base, o problema "
        "fica fora do IIC por problema (o gráfico de caixas)."
    )
    by_problem = trace.iic_by_problem(was, direction)
    table(_pretty(by_problem))
    chosen = _pick("Abrir o problema", by_problem, lambda r: r["problem"], "iic_problem")
    if chosen is None:
        return
    mine = was[was["problem"] == chosen["problem"]].copy()
    mine["papel no IIC"] = trace.iic_role(mine, direction)
    shown = pd.DataFrame(
        {
            "WA": mine["target"],
            "R (caixa-preta)": mine["R"].map(_mark),
            "C (caixa-branca)": mine["C"].map(_mark),
            "H (híbrido)": mine["H"].map(_mark),
            "papel no IIC": mine["papel no IIC"],
        }
    )
    st.markdown(f"**{chosen['problem']}: os {len(mine)} WAs**")
    table(shown)
    target = st.selectbox(
        "Abrir um WA (que teste o reprovou em cada cenário)",
        list(mine["target"]),
        format_func=lambda t: f"{t} · {mine.loc[mine['target'] == t, 'papel no IIC'].iloc[0]}",
        key="iic_target",
    )
    _target_card(tree, frame, chosen["problem"], target)


def _problem(tree, rows, frame) -> None:
    problems = sorted(set(rows["problem"]))
    problem = st.selectbox("Problema", problems, key="problem_pick")
    _problem_card(tree, rows, problem)


HANDLERS = {
    "missing": _missing,
    "barred": _barred,
    "slm_origin": _slm_origin,
    "test_of_target": _test_of_target,
    "targets_of_test": _targets_of_test,
    "ac_rejected": _ac_rejected,
    "oracle_only": _oracle_only,
    "iic": _iic,
    "problem": _problem,
}


def render(tree: data.LoadedTree, filters: dict) -> None:
    st.title("Rastreabilidade")
    rows = data.apply_filters(tree.table, **filters)
    cut_banner(filters, int(rows["problem"].nunique()))
    if rows.empty:
        st.write("Nenhuma combinação com esses filtros.")
        return
    text(
        "De onde vem cada número: escolha o que rastrear e abra o problema, a suíte, o teste ou "
        "o WA. As listas seguem os filtros da barra lateral."
    )
    case = st.selectbox("O que você quer rastrear?", list(CASES), format_func=CASES.get)
    frame = pd.DataFrame()
    if case in NEEDS_TARGETS:
        everything = _targets(str(tree.base), _stamp(tree.base))
        if everything.empty:
            st.info(
                "Falta a tabela de alvos da avaliação (`results.csv` de cada conjunto). Ela vem "
                "de `docker compose run --rm app python -m evaluation report` ou do pacote da "
                "avaliação descompactado."
            )
            return
        cut = rows
        if case == "iic":  # the IIC compares the scenarios: every scenario of the cut stays
            cut = data.apply_filters(
                tree.table, **{k: v for k, v in filters.items() if k != "scenarios"}
            )
        frame = trace.cut_targets(everything, cut)
    if case in ("undetected", "exclusive", "surviving"):
        _hard_targets(tree, rows, frame, case)
    else:
        HANDLERS[case](tree, rows, frame)
    bridge("Veja todas as combinações e as comparações entre os gabaritos →", "evaluation")
