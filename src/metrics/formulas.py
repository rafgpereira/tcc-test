"""How each figure is computed: the formula, the same formula in words, and a worked example.

One place for the formulas the dashboard shows next to every chart ("Como se calcula"), so a text
never diverges between two charts. ``example`` recomputes the plotted number from the raw counts
of the cut (problems, WAs, mutants, tests, US$), never from the value already plotted: the tests
check that both agree, which is what makes the formula a statement about the code.
"""

from dataclasses import dataclass

import pandas as pd

from metrics import config, cuts, iic, primary, story


@dataclass(frozen=True)
class Formula:
    latex: tuple[str, ...]  # one equation per line, rendered with st.latex
    words: str  # the same in one or two sentences, for a reader without the notation


_TDF = r"\text{TDF*} = \frac{\text{WAs reprovados pelo gabarito do AC}}{\text{WAs avaliados}} \times 100"
_MS = r"\text{MS*} = \frac{\text{mutantes reprovados pelo gabarito do AC}}{\text{mutantes avaliados}} \times 100"
_TFP = (
    r"\text{TFP} = \frac{\text{problemas em que a suíte reprova o AC}}{\text{problemas}} \times 100"
)
_DELTA = r"\Delta_{\text{oráculo}} = \text{TDF} - \text{TDF*}"
_TC = r"\text{TC} = \frac{\text{combinações com suíte}}{\text{combinações}} \times 100"
_COST = r"\text{custo} = \frac{\text{US\$ gastos}}{\text{WAs reprovados pelo gabarito do AC}} \times 1.000"
_IIC = (
    r"\text{IIC} = \frac{|H \setminus B| - |B \setminus H|}{|B|} \times 100",
    r"H = \text{WAs que o híbrido reprovou};\quad B = \text{WAs que a base reprovou (R ou C)}",
)
_MEAN = (
    "Com mais de um cenário no recorte, o valor é a média dos cenários (cada cenário tem os "
    "mesmos problemas, então é também a conta com as somas)."
)

FORMULAS = {
    "scoreboard": Formula(
        (_TDF, _MS, _TFP, _DELTA, _TC, _COST),
        "Um critério por coluna. TDF* e MS*: quanto mais, melhor; TFP, Δ_oráculo e custo: quanto "
        "menos, melhor; TC: quanto mais, melhor. Uma combinação sem suíte conta 0% em TDF* e MS* "
        "e não reprova o AC. " + _MEAN + " O modelo local não entra no custo (não é cobrado em "
        "dinheiro).",
    ),
    "scoreboard_scenarios": Formula(
        (_TDF, _MS, _TFP, _DELTA, _TC, _COST),
        "As mesmas fórmulas do placar, calculadas em cada cenário separado: a posição compara as "
        "IAs dentro do mesmo cenário (SLM na caixa-preta contra GPT, Gemini e Claude na "
        "caixa-preta), nunca um cenário contra outro. Cada célula usa os 200 problemas daquele "
        "cenário (ou os do recorte). O teste estatístico entre o 1º e o 2º de cada cenário está "
        "no guia de escolha.",
    ),
    "tdf_by_model": Formula(
        (
            _TDF,
            r"\text{TDF} = \frac{\text{WAs reprovados pelo gabarito da IA}}{\text{WAs avaliados}} \times 100",
        ),
        "De cada 100 versões erradas reais do programa (WAs), quantas a suíte reprovou, usando a "
        "saída do AC como resposta certa (TDF*, a barra). O traço é o TDF, com a saída que a IA "
        "escreveu no teste. Cada WA conta uma vez, qualquer que seja o número de testes que o "
        "reprovam. " + _MEAN,
    ),
    "ms_declared_vs_corrected": Formula(
        (
            _MS,
            r"\text{MS} = \frac{\text{mutantes reprovados pelo gabarito da IA}}{\text{mutantes avaliados}} \times 100",
        ),
        "De cada 100 mutantes (defeitos sintéticos inseridos no AC), quantos a suíte reprovou, "
        "com a saída do AC como resposta certa (MS*, a barra) ou com a da IA (MS, o traço). "
        + _MEAN,
    ),
    "tdf_declared_vs_corrected": Formula(
        (_DELTA,),
        "Por cenário, o TDF com o gabarito escrito pela IA ao lado do TDF com a saída do AC. A "
        "diferença (Δ_oráculo) é quanto da detecção vinha de uma saída esperada errada: uma "
        "suíte com gabarito errado reprova também versões que não têm o defeito.",
    ),
    "tradeoff": Formula(
        (_TFP, _TDF),
        "Eixo horizontal: em quantos problemas a suíte reprova o próprio AC (o programa certo), "
        "um falso positivo por problema. Eixo vertical: o TDF*. As linhas tracejadas são as "
        "medianas dos modelos. " + _MEAN,
    ),
    "tfp_by_cause": Formula(
        (
            r"\text{saída errada} = \frac{\text{testes cuja saída esperada difere da do AC}}{\text{testes}} \times 100",
            r"\text{entrada inválida} = \frac{\text{testes em que o próprio AC dá erro}}{\text{testes}} \times 100",
        ),
        "Aqui a conta é por teste, não por problema: de todos os testes das suítes, quantos "
        "reprovam o AC, separados pela causa.",
    ),
    "scenario_shift": Formula(
        (
            _TDF,
            r"\text{variação} = \max_{\text{cenários}} \text{TDF*} - \min_{\text{cenários}} \text{TDF*}",
        ),
        "O TDF* de cada modelo em cada cenário; a variação é a distância entre o melhor e o pior "
        "cenário do modelo, em pontos.",
    ),
    "iic_diverging": Formula(
        _IIC,
        "Quanto o híbrido muda a detecção em relação à base: os WAs que só o híbrido reprovou, "
        "menos os que só a base reprovou, sobre tudo o que a base reprovou. Base caixa-preta (+ "
        "código) ou caixa-branca (+ requisito). Conta só WAs, nunca mutantes. Os pares (problema, "
        "WA) são somados em todos os problemas do recorte; o filtro de cenário não se aplica. "
        "Os conjuntos (R = caixa-preta, C = caixa-branca, H = híbrido), problema a problema e WA "
        'a WA, estão na Rastreabilidade, em "De onde vem o IIC".',
    ),
    "iic_distribution": Formula(
        _IIC,
        "A mesma conta, feita problema a problema. Um problema em que a base não reprovou nenhum "
        "WA não tem IIC (divisão por zero) e fica de fora, contado. Os problemas extremos ficam "
        "fora do desenho da caixa, mas aparecem ao passar o mouse.",
    ),
    "cost_per_detection": Formula(
        (_COST,),
        "Quanto custou, em dólares, cada 1.000 WAs reprovados com a saída do AC como resposta "
        "certa. O custo é o da geração (inclui pedidos repetidos e respostas barradas) somado "
        "nos cenários do recorte; existe só por modelo e cenário, então um filtro de problema não "
        "o muda. O modelo local não entra.",
    ),
    "choice_guide": Formula(
        (_TDF, _MS, _TFP, _DELTA, _TC, _COST),
        "Para cada critério e cenário, o modelo com o melhor valor e o 2º. O estado entre os dois "
        "vem do teste de Wilcoxon pareado por problema, com correção de Holm: diferença ou empate "
        "estatístico. Valores iguais são empate; num recorte parcial, ou sem teste para o "
        "critério (Δ_oráculo, TC, custo), a diferença é dita não testada.",
    ),
}

ORACLE_WORD = {"corrected": "do AC", "declared": "da IA"}


def _cut(tables: dict, recorte: story.Recorte, **extra) -> pd.DataFrame:
    return cuts.apply(tables["per_problem"], **recorte.cut_kwargs(**extra))


def _share(part: int, whole: int) -> float:
    return 100 * part / whole if whole else float("nan")


def _count_line(set_name: str, part: int, whole: int, what: str) -> str:
    return (
        f"{story.name(set_name)}: {story.num(part, 0)} de {story.num(whole, 0)} {what} "
        f"→ {story.pct(_share(part, whole))}"
    )


def example(name: str, tables: dict, filters: dict | None, oracle: str = "corrected") -> list[str]:
    """The worked example of a figure in the cut, from the raw counts; ``[]`` if none applies."""
    recorte = story.Recorte.from_filters(filters)
    try:
        cut = _cut(tables, recorte)
        if cut.empty:
            return []
        return _EXAMPLES[name](tables, recorte, cut, oracle)
    except (cuts.CutError, KeyError, ValueError):
        return []


def _best(cut: pd.DataFrame, column: str, higher: bool = True) -> str:
    """The set the figure ranks first, by the code's own value (the mean of the scenarios)."""
    means = primary.table(cut).groupby("set", sort=False)[column].mean()
    return means.idxmax() if higher else means.idxmin()


def _tdf(tables, recorte, cut, oracle) -> list[str]:
    set_name = _best(cut, "TDF_star")
    mine = cut[cut["set"] == set_name]
    return [
        _count_line(
            set_name, mine["wa_corrected"].sum(), mine["n_wa"].sum(), "WAs (gabarito do AC)"
        ),
        _count_line(
            set_name, mine["wa_declared"].sum(), mine["n_wa"].sum(), "WAs (gabarito da IA)"
        ),
    ]


def _scoreboard_scenarios(tables, recorte, cut, oracle) -> list[str]:
    out = []
    for scenario in story.scenarios_of(tables, recorte):
        mine = cut[cut["scenario"] == scenario]
        if mine.empty:
            continue
        set_name = _best(mine, "TDF_star")
        one = mine[mine["set"] == set_name]
        out.append(
            f"TDF* na {story.SCENARIO_NAME[scenario]}, "
            + _count_line(set_name, one["wa_corrected"].sum(), one["n_wa"].sum(), "WAs")
        )
    return out


def _ms(tables, recorte, cut, oracle) -> list[str]:
    set_name = _best(cut, "MS_star")
    mine = cut[cut["set"] == set_name]
    total = mine["n_mutants"].sum()
    return [
        _count_line(set_name, mine["mutants_corrected"].sum(), total, "mutantes (gabarito do AC)"),
        _count_line(set_name, mine["mutants_declared"].sum(), total, "mutantes (gabarito da IA)"),
    ]


def _tfp_line(cut: pd.DataFrame) -> str:
    set_name = _best(cut, "TFP", higher=False)
    mine = cut[cut["set"] == set_name]
    return _count_line(
        set_name, int(mine["ac_rejected"].sum()), len(mine), "combinações reprovam o AC"
    )


def _delta_line(cut: pd.DataFrame) -> str:
    sums = cut.groupby("set")[["wa_declared", "wa_corrected", "n_wa"]].sum()
    delta = 100 * (sums["wa_declared"] - sums["wa_corrected"]) / sums["n_wa"]
    set_name = _best(cut, "delta_TDF", higher=False)
    r = sums.loc[set_name]
    return (
        f"Δ_oráculo de {story.name(set_name)}: "
        f"{story.pct(_share(r['wa_declared'], r['n_wa']))} − "
        f"{story.pct(_share(r['wa_corrected'], r['n_wa']))} = "
        f"{story.num(delta[set_name], 2)} pontos"
    )


def _scoreboard(tables, recorte, cut, oracle) -> list[str]:
    set_name = _best(cut, "TC", higher=False)
    mine = cut[cut["set"] == set_name]
    return [
        _tfp_line(cut),
        _delta_line(cut),
        "TC de "
        + _count_line(set_name, int(mine["has_suite"].sum()), len(mine), "combinações com suíte"),
    ]


def _tradeoff(tables, recorte, cut, oracle) -> list[str]:
    return [_tfp_line(cut), *_tdf(tables, recorte, cut, oracle)[:1]]


def _tdf_declared_vs_corrected(tables, recorte, cut, oracle) -> list[str]:
    return [_delta_line(cut)]


def _tfp_by_cause(tables, recorte, cut, oracle) -> list[str]:
    sums = cut.groupby("set")[
        ["ac_wrong_output_tests", "ac_runtime_error_tests", "suite_size"]
    ].sum()
    sums = sums[sums["suite_size"] > 0]
    set_name = (sums["ac_wrong_output_tests"] / sums["suite_size"]).idxmax()
    r = sums.loc[set_name]
    return [
        _count_line(
            set_name,
            int(r["ac_wrong_output_tests"]),
            int(r["suite_size"]),
            "testes com saída esperada errada",
        ),
        _count_line(
            set_name,
            int(r["ac_runtime_error_tests"]),
            int(r["suite_size"]),
            "testes com entrada inválida",
        ),
    ]


def _scenario_shift(tables, recorte, cut, oracle) -> list[str]:
    sums = cut.groupby(["set", "scenario"])[["wa_corrected", "n_wa"]].sum()
    tdf = 100 * sums["wa_corrected"] / sums["n_wa"]
    spread = tdf.groupby(level="set").agg(lambda v: v.max() - v.min())
    set_name = story.shift_spread(tables, recorte).idxmax()
    mine = tdf.loc[set_name]
    mine = mine.reindex([s for s in config.SCENARIOS if s in mine.index])
    parts = [f"{story.SCENARIO_NAME[s]} {story.pct(v)}" for s, v in mine.items()]
    return [
        f"{story.name(set_name)}: "
        + ", ".join(parts)
        + f" → variação de {story.num(spread[set_name])} pontos"
    ]


def _iic_cut(tables, recorte):
    kwargs = recorte.cut_kwargs()
    kwargs.pop("scenarios")
    return cuts.apply(tables["per_problem"], detected_wa=tables["detected_wa"], **kwargs)


def _iic_diverging(tables, recorte, cut, oracle) -> list[str]:
    per_problem, detected = _iic_cut(tables, recorte)
    table = iic.table(detected, per_problem)
    mine = table[table["oracle"] == oracle].dropna(subset=["iic_pooled"])
    if mine.empty:
        return []
    r = mine.loc[mine["iic_pooled"].abs().idxmax()]
    gains, losses, base = int(r["gains"]), int(r["losses"]), int(r["base_size"])
    value = 100 * (gains - losses) / base
    return [
        (
            f"{story.name(r['set'])} ({story.DIRECTION_NAME[r['direction']]}, gabarito "
            f"{ORACLE_WORD[oracle]}): ({story.num(gains, 0)} − {story.num(losses, 0)}) ÷ "
            f"{story.num(base, 0)} × 100 = {story.pct(value)}"
        )
    ]


def _iic_distribution(tables, recorte, cut, oracle) -> list[str]:
    per_problem, detected = _iic_cut(tables, recorte)
    table = iic.table(detected, per_problem)
    mine = table[table["oracle"] == oracle].dropna(subset=["per_problem_median"])
    if mine.empty:
        return []
    r = mine.loc[mine["per_problem_median"].abs().idxmax()]
    counted = int(r["positive"] + r["negative"] + r["zero"])
    return [
        (
            f"{story.name(r['set'])} ({story.DIRECTION_NAME[r['direction']]}): mediana de "
            f"{story.pct(r['per_problem_median'])} em {story.num(counted, 0)} problemas "
            f"({story.num(r['positive'], 0)} acima de zero, {story.num(r['negative'], 0)} abaixo, "
            f"{story.num(r['zero'], 0)} em zero); {story.num(r['excluded'], 0)} fora, sem WA "
            "reprovado na base"
        )
    ]


def _cost(tables, recorte, cut, oracle) -> list[str]:
    whole = _cut(tables, recorte, only_sets_and_scenarios=True)
    cost = tables["cost"]
    rows = []
    for set_name, mine in whole.groupby("set", sort=False):
        if set_name in story.LOCAL:
            continue
        spent = cost[(cost["set"] == set_name) & cost["scenario"].isin(set(mine["scenario"]))][
            "cost_usd"
        ]
        killed = int(mine["wa_corrected"].sum())
        if killed and not spent.isna().all():
            rows.append((1000 * spent.sum() / killed, set_name, float(spent.sum()), killed))
    if not rows:
        return []
    value, set_name, spent, killed = min(rows)
    return [
        (
            f"{story.name(set_name)}: US$ {story.num(spent, 2)} ÷ {story.num(killed, 0)} WAs × 1.000 "
            f"= US$ {story.num(value, 3)}"
        )
    ]


def _guide(tables, recorte, cut, oracle) -> list[str]:
    return [_tfp_line(cut), *_tdf(tables, recorte, cut, oracle)[:1]]


_EXAMPLES = {
    "scoreboard": _scoreboard,
    "scoreboard_scenarios": _scoreboard_scenarios,
    "tdf_by_model": _tdf,
    "ms_declared_vs_corrected": _ms,
    "tdf_declared_vs_corrected": _tdf_declared_vs_corrected,
    "tradeoff": _tradeoff,
    "tfp_by_cause": _tfp_by_cause,
    "scenario_shift": _scenario_shift,
    "iic_diverging": _iic_diverging,
    "iic_distribution": _iic_distribution,
    "cost_per_detection": _cost,
    "choice_guide": _guide,
}
