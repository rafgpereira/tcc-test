"""As métricas (feature 012, US2 and US3): who won each criterion, and a guide to choose.

specs/012-dashboard-storytelling/contracts/narrative.md, "Página 3". Nothing is computed here:
the tables are read from ``data/metrics``; the titles come from ``metrics.story.conclusion`` (the
conclusion of the sidebar cut, so they change with the filters); the charts from
``metrics.figures.card``, the same numbers as the tables. Each card has a "Baixar figura" button
that saves the same drawing with its title, cut and source (``metrics.figures.render``).
"""

import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import streamlit as st

from dashboard import config, data
from dashboard.views.common import bridge, cut_banner, download, table, text, theme_mode

KILLED = (
    "WA_killed",
    "WA_killed_star",
    "WA_total",
    "TDF",
    "mutants_killed",
    "mutants_killed_star",
    "mutants_total",
    "MS",
)
MIME = {"png": "image/png", "svg": "image/svg+xml", "pdf": "application/pdf"}
ORACLE_CHOICE = {"do AC (corrigido)": "corrected", "da IA (declarado)": "declared"}
STATE_NOTE = {
    "differ": "Entre o 1º e o 2º: diferença significativa (Wilcoxon pareado, com Holm).",
    "tie": "Entre o 1º e o 2º: empate estatístico (Wilcoxon pareado, com Holm).",
    "untested": (
        "Valor médio dos cenários do recorte: a diferença não é testada aqui. O teste é feito "
        "por cenário, com todos os problemas; o resultado está no guia de escolha, no fim."
    ),
}


@dataclass(frozen=True)
class _Ctx:
    loaded: dict
    filters: dict
    key: tuple
    folder: str
    stamp: float
    source: str
    mode: str


@st.cache_data(show_spinner="lendo as métricas...")
def _tables(folder: str, stamp: float) -> dict:
    from metrics import tables

    return tables.read(Path("."), Path(folder))


def _key(filters: dict) -> tuple:
    return tuple((k, tuple(v)) for k, v in sorted(filters.items()) if v)


@st.cache_data(show_spinner=False)
def _title(name: str, key: tuple, folder: str, stamp: float, oracle: str) -> tuple:
    from metrics import figures

    found = figures.title(name, _tables(folder, stamp), dict(key), oracle)
    return found.text, found.subtitle, found.rule


@st.cache_data(show_spinner="preparando o arquivo...")
def _file(
    name: str,
    key: tuple,
    folder: str,
    stamp: float,
    source: str,
    fmt: str,
    mode: str,
    oracle: str,
    highlight: str | None,
) -> bytes:
    from metrics import figures

    loaded = _tables(folder, stamp)
    return figures.render(name, loaded, dict(key), fmt, source, mode, oracle, highlight)[1]


def _downloads(ctx: _Ctx, name: str, oracle: str = "corrected", highlight: str | None = None):
    from metrics import figures

    with st.popover("Baixar figura", icon=":material/download:"):
        st.caption(
            "Com o título, o recorte e a fonte. Sem filtros e no tema claro, PNG e SVG são os "
            "mesmos de `python -m metrics figures`."
        )
        for fmt in figures.FORMATS:
            st.download_button(
                fmt.upper(),
                lambda fmt=fmt: _file(
                    name,
                    ctx.key,
                    ctx.folder,
                    ctx.stamp,
                    ctx.source,
                    fmt,
                    ctx.mode,
                    oracle,
                    highlight,
                ),
                file_name=figures.file_name(name, ctx.filters, fmt, oracle),
                mime=MIME[fmt],
                key=f"{fmt}_{name}_{oracle}",
                on_click="ignore",
            )


def _card(
    ctx: _Ctx,
    name: str,
    notes: list[str] = (),
    oracle: str = "corrected",
    highlight: str | None = None,
):
    """A bordered card: the conclusion, the subtitle, the chart, the notes and the download."""
    from metrics import cuts, figures

    heading, subtitle, _ = _title(name, ctx.key, ctx.folder, ctx.stamp, oracle)
    box = st.container(border=True, height="stretch")
    with box:
        st.markdown(f"**{heading}**")
        if subtitle:
            st.caption(subtitle)
        try:
            chart = figures.card(name, ctx.loaded, ctx.filters, ctx.mode, oracle, highlight)
        except cuts.CutError:
            st.caption("Sem dados para este gráfico neste recorte.")
            return box
        fixed = name in figures.LEGACY or name == "iic_diverging"
        st.altair_chart(chart, theme=None, width="content" if fixed else "stretch")
        for note in notes:
            st.caption(note)
        _downloads(ctx, name, oracle, highlight)
    return box


def _no_metrics(folder) -> None:
    st.info(
        "Métricas oficiais ainda não calculadas. Elas vêm do módulo de métricas "
        "(`docker compose run --rm app python -m metrics compute`), que grava as tabelas em "
        f"`{folder}`; até lá, as outras páginas mostram só a {config.PREVIEW_LABEL}."
    )
    text("Serão: TDF, MS, TFP, IIC, TC e CPD (passe o mouse para ver o nome completo).")


def _scoreboard(ctx: _Ctx, recorte) -> None:
    from metrics import cuts, story

    st.subheader("Placar")
    cut = cuts.apply(ctx.loaded["per_problem"], **recorte.cut_kwargs())
    notes = []
    sets = set(cut["set"])
    if sets & set(story.LOCAL):
        notes.append("O modelo local (SLM) roda em GPUs próprias: fica fora do ranking de custo.")
    attempt = cut[cut["set"] == "slm-attempt1"]
    missing = int((~attempt["has_suite"].astype(bool)).sum())
    if missing:
        notes.append(
            f"SLM 1ª tentativa: {missing} combinações sem suíte contam como 0% de detecção."
        )
    barred, changed = story.barred_effect(ctx.loaded, recorte)
    if barred:
        effect = (
            "sem elas, nenhum 1º lugar muda"
            if not changed
            else "sem elas, muda o 1º lugar em: " + ", ".join(changed)
        )
        notes.append(
            f'{barred} suítes "sem raciocínio" (o modelo respondeu sem raciocinar nas três '
            f"tentativas) estão incluídas; {effect}."
        )
    notes.append(
        "Cada valor é a média dos cenários do recorte, sem teste estatístico; o teste por "
        "cenário está no guia de escolha."
    )
    _card(ctx, "scoreboard", notes)


def _detection(ctx: _Ctx, recorte) -> None:
    from metrics import story

    st.subheader("Falhas reais e mutantes")
    text(
        "A **TDF\\*** é a parte dos WAs (submissões humanas erradas) que a suíte reprova; o "
        "**MS\\***, a parte dos mutantes. O \\* indica o gabarito do AC: a saída esperada de cada "
        "teste é a do código correto, não a que a IA escreveu."
    )
    left, right = st.columns(2)
    for column, name, key in (
        (left, "tdf_by_model", "tdf_star"),
        (right, "ms_declared_vs_corrected", "ms_star"),
    ):
        with column:
            from metrics import figures

            state = story.leader(ctx.loaded, recorte, key).state
            ranked = figures.figure_data(name, ctx.loaded, ctx.filters)
            notes = [n for n in ranked["note"] if n] + [STATE_NOTE[state]]
            _card(ctx, name, notes)
    with st.expander("Ver por cenário: gabarito da IA × gabarito do AC"):
        _card(ctx, "tdf_declared_vs_corrected")


def _false_positives(ctx: _Ctx, recorte) -> None:
    from metrics import story

    st.subheader("Falsos positivos")
    text(
        "Um falso positivo é um teste que reprova o **código correto** (o AC): a suíte acusa um "
        "erro que não existe. A **TFP** é a parte dos problemas em que isso acontece."
    )
    vals = story.values(ctx.loaded, recorte)
    tdf_first = vals["tdf_star"].idxmax()
    tfp_first = vals["tfp"].idxmin()
    best = vals.loc[tdf_first]
    notes = [
        (
            f"Em azul, quem mais detecta ({story.name(tdf_first)}: TDF\\* "
            f"{story.pct(best['tdf_star'])}, TFP {story.pct(best['tfp'])})."
        )
    ]
    if tfp_first != tdf_first:
        notes.append(
            f"Em laranja, quem menos reprova o código correto ({story.name(tfp_first)}: TFP "
            f"{story.pct(vals.loc[tfp_first, 'tfp'])})."
        )
    notes.append(
        "Região ideal: TFP abaixo da mediana e TDF\\* acima da mediana das IAs do recorte."
    )
    notes.append(STATE_NOTE[story.leader(ctx.loaded, recorte, "tfp").state])
    _card(ctx, "tradeoff", notes)
    with st.expander("Por que o código correto foi reprovado"):
        _card(ctx, "tfp_by_cause")


def _context(ctx: _Ctx, recorte) -> None:
    from metrics import story

    st.subheader("Contexto: requisito, código ou os dois")
    text(
        "O mesmo modelo, com contextos diferentes: **caixa-preta** (só o requisito), "
        "**caixa-branca** (só o código) e **híbrido** (os dois). O **IIC** mede quanto o híbrido "
        "ganha (ou perde) sobre cada cenário de base."
    )
    if len(story.scenarios_of(ctx.loaded, recorte)) > 1:
        spread = story.shift_spread(ctx.loaded, recorte)
        notes = [
            (
                f"Em azul, quem mais muda ({story.name(spread.idxmax())}); em laranja, quem menos "
                f"muda ({story.name(spread.idxmin())})."
            )
        ]
        _card(ctx, "scenario_shift", notes)
    else:
        st.caption(
            "Com um cenário só no recorte, não há o que comparar entre cenários; o IIC abaixo "
            "usa sempre os três."
        )
    choice = st.radio(
        "Gabarito do IIC",
        list(ORACLE_CHOICE),
        horizontal=True,
        help="Não muda o recorte: só o gabarito usado para dizer que um WA foi detectado.",
    )
    oracle = ORACLE_CHOICE[choice]
    _card(ctx, "iic_diverging", story.iic_sign_changes(ctx.loaded, recorte), oracle=oracle)
    with st.expander("Ver o IIC problema a problema (diagnóstico)"):
        _card(ctx, "iic_distribution")


def _cost(ctx: _Ctx, recorte) -> None:
    from metrics import story

    st.subheader("Custo")
    left, right = st.columns([3, 2])
    with left:
        _card(ctx, "cost_per_detection")
    cost = ctx.loaded["cost"]
    local = cost[cost["set"].isin(story.LOCAL)]
    with right, st.container(border=True, height="stretch"):
        st.markdown("**O modelo local não custa dinheiro, mas custa tempo**")
        if local.empty:
            st.caption("Sem o modelo local nas tabelas.")
        for set_name, rows in local.groupby("set", sort=False):
            hours = rows["duration_s"].sum() / 3600
            st.caption(
                f"{story.name(set_name)}: {story.num(hours, 0)} h de modelo em GPUs próprias, "
                "sem custo de API. Fica fora do ranking de custo."
            )


PRIORITY_HELP = "Só realça uma linha do guia; nenhum número muda."


def _guide(ctx: _Ctx, recorte) -> None:
    from metrics import story

    st.subheader("Guia de escolha")
    text(
        "Não há uma IA melhor em tudo. Escolha o que mais importa para você: o guia mostra, em "
        "cada cenário, a melhor IA nesse critério, o 2º colocado e se a diferença entre os dois "
        "é **significativa**, um **empate** estatístico ou **não testada**."
    )
    options = [c.label for c in story.criteria()] + [story.LOCAL_LABEL]
    highlight = st.radio(
        "Minha prioridade", options, index=None, horizontal=True, help=PRIORITY_HELP
    )
    _card(ctx, "choice_guide", highlight=highlight)
    st.markdown("**Limites do experimento**")
    st.markdown(
        "- Uma execução por modelo: outra execução pode dar números um pouco diferentes.\n"
        "- O gabarito que a IA escreve não foi conferido por ela; por isso os números com \\* "
        "usam o gabarito do AC.\n"
        "- Combinações sem suíte contam como 0% de detecção.\n"
        "- Problemas do Codeforces de rating 1000 a 1600.\n"
        "- O modelo local não tem custo em dinheiro comparável ao das APIs."
    )


def _official_tables(ctx: _Ctx, recorte) -> None:
    from metrics import cuts, iic, primary

    with st.expander("Tabelas oficiais (os números de todos os gráficos)"):
        metrics = ctx.loaded["metrics"]
        sets, scenarios = recorte.sets, recorte.scenarios
        if recorte.complete:
            shown = metrics[metrics["cut"] == "all"]
            if sets:
                shown = shown[shown["set"].isin(sets)]
            if scenarios:
                shown = shown[shown["scenario"].isin(scenarios)]
            st.caption("Linhas oficiais de `metrics.csv` (todos os problemas).")
        else:
            cut = cuts.apply(ctx.loaded["per_problem"], **recorte.cut_kwargs())
            shown = primary.table(cut)
            st.caption(
                "Calculadas para este recorte com as mesmas funções das tabelas oficiais; não são "
                "linhas de `metrics.csv`."
            )
        st.markdown("**WAs e mutantes mortos**")
        killed = shown[["set", "scenario", *KILLED]]
        table(killed)
        download(killed, "mortos")
        st.markdown("**TDF, MS, TFP, TC e complementares**")
        table(shown)
        download(shown, "metricas")
        st.markdown("**IIC (influência do contexto)**")
        if recorte.complete:
            iic_rows = ctx.loaded["iic"]
            if sets:
                iic_rows = iic_rows[iic_rows["set"].isin(sets)]
        else:
            kwargs = recorte.cut_kwargs()
            kwargs.pop("scenarios")
            per_problem, detected = cuts.apply(
                ctx.loaded["per_problem"], detected_wa=ctx.loaded["detected_wa"], **kwargs
            )
            iic_rows = iic.table(detected, per_problem)
        table(iic_rows)
        download(iic_rows, "iic")
        st.markdown("**Testes estatísticos**")
        if recorte.complete:
            only_significant = st.checkbox("só as diferenças significativas")
            stats = ctx.loaded["stats"]
            if only_significant:
                stats = stats[stats["significant"] == True]
            table(stats)
            download(stats, "estatistica")
        else:
            st.caption(
                "Os testes estatísticos existem só para todos os problemas (pareados por "
                "problema); este recorte não tem teste."
            )
        st.markdown("**Custo, tokens e tempo**")
        cost = ctx.loaded["cost"]
        if sets:
            cost = cost[cost["set"].isin(sets)]
        if scenarios:
            cost = cost[cost["scenario"].isin(scenarios)]
        table(cost)
        download(cost, "custo")


def render(tree: data.LoadedTree, filters: dict) -> None:
    from metrics import cuts, figures, story

    st.title("As métricas")
    folder = config.METRICS_DIR
    if "metrics.csv" not in data.metrics_files():
        rows = data.apply_filters(tree.table, **filters)
        cut_banner(filters, int(rows["problem"].nunique()))
        _no_metrics(folder)
        return
    stamp = (Path(folder) / "metrics.csv").stat().st_mtime
    loaded = _tables(str(folder), stamp)
    clean = {k: list(v) for k, v in filters.items() if v}
    recorte = story.Recorte.from_filters(clean)
    per_problem = loaded["per_problem"]
    mask = pd.Series(True, index=per_problem.index)
    for column, key in (
        ("set", "sets"),
        ("scenario", "scenarios"),
        ("macrocategoria", "macrocategorias"),
        ("rating", "ratings"),
        ("status", "statuses"),
        ("problem", "problems"),
    ):
        if clean.get(key):
            mask &= per_problem[column].isin(clean[key])
    n = int(per_problem[mask]["problem"].nunique())
    cut_banner(filters, n)
    if n == 0:
        st.write("Nenhum problema atende a esses filtros.")
        return
    if n < 2:
        st.warning(
            "Com um problema só não há métrica: TDF, MS e TFP são médias sobre problemas. Veja "
            "esse problema na página **Rastreabilidade** (ficha do problema, suítes e testes)."
        )
        bridge("Abrir a ficha do problema na Rastreabilidade →", "trace")
        return
    run_path = Path(folder) / "run.json"
    run = json.loads(run_path.read_text()) if run_path.is_file() else {}
    ctx = _Ctx(
        loaded, clean, _key(clean), str(folder), stamp, figures.source_label(run), theme_mode()
    )
    text(
        "Somando todas as combinações do recorte: quem se saiu melhor em cada critério. Os "
        "títulos são a conclusão dos números e mudam com os filtros da barra lateral."
    )
    try:
        _scoreboard(ctx, recorte)
        _detection(ctx, recorte)
        _false_positives(ctx, recorte)
        _context(ctx, recorte)
        _cost(ctx, recorte)
        _guide(ctx, recorte)
    except cuts.CutError as exc:
        st.warning(f"Este recorte não tem dados suficientes para as métricas ({exc}).")
    _official_tables(ctx, recorte)
    bridge("De onde vem cada número? Rastreie o problema, a suíte e o teste →", "trace")
