"""Who won each criterion in a cut: the narrative layer of the metrics (feature 012).

specs/012-dashboard-storytelling (research R1, R3, R4; data-model.md; contracts/api.md). Pure
functions over the tables of ``metrics.tables.read``: no Streamlit, no file read or written. The
values come from the same functions as the official tables (``cuts.apply``, ``primary.table``) and
from ``cost.csv``; no statistical test is run here: the state of a difference is read from
``stats.csv`` and is "untested" whenever the test does not exist for what is shown.
"""

from dataclasses import dataclass, fields

import numpy as np
import pandas as pd

from metrics import config, cuts, primary

LOCAL = ("slm", "slm-attempt1")  # run locally: no money cost, never ranked on cost
DIFFER, TIE, UNTESTED = "differ", "tie", "untested"


@dataclass(frozen=True)
class Recorte:
    """The active filters; an empty tuple filters nothing."""

    sets: tuple = ()
    scenarios: tuple = ()
    macrocategorias: tuple = ()
    ratings: tuple = ()
    statuses: tuple = ()
    problems: tuple = ()

    @property
    def complete(self) -> bool:
        """True when every problem is in: only then the paired tests of ``stats.csv`` apply."""
        return not (self.problems or self.macrocategorias or self.ratings or self.statuses)

    @classmethod
    def from_filters(cls, filters: dict | None) -> "Recorte":
        """From the filter dict of the dashboard and of ``metrics.figures`` (unknown keys ignored)."""
        filters = filters or {}
        names = {f.name for f in fields(cls)}
        return cls(**{k: tuple(v or ()) for k, v in filters.items() if k in names})

    def cut_kwargs(self, only_sets_and_scenarios: bool = False) -> dict:
        keys = ("sets", "scenarios")
        if not only_sets_and_scenarios:
            keys += ("macrocategorias", "ratings", "statuses", "problems")
        return {k: getattr(self, k) for k in keys}


@dataclass(frozen=True)
class Criterio:
    key: str
    label: str  # plain language, for the guide
    column: str  # column of ``primary.table`` (cost: computed from ``cost.csv``)
    better: str  # "higher" or "lower"
    stats_metric: str | None  # metric of ``stats.csv``, None when there is no test
    unit: str
    local_ranked: bool = True


CRITERIA = (
    Criterio(
        "tdf_star", "encontrar o máximo de falhas reais", "TDF_star", "higher", "TDF_star", "%"
    ),
    Criterio("ms_star", "pegar defeitos sintéticos", "MS_star", "higher", "MS_star", "%"),
    Criterio("tfp", "não reprovar o código correto", "TFP", "lower", "TFP", "%"),
    Criterio(
        "delta_tdf", "confiar no gabarito que a IA escreve", "delta_TDF", "lower", None, "pontos"
    ),
    Criterio("tc", "sempre entregar uma suíte", "TC", "higher", None, "%"),
    Criterio(
        "cost",
        "gastar pouco",
        "cpd_wa_corrected",
        "lower",
        None,
        "US$ por 1.000 WAs",
        local_ranked=False,
    ),
)


@dataclass(frozen=True)
class Resultado:
    criterion: str
    scenario: str | None
    leader: str | None
    value: float
    second: str | None
    second_value: float
    state: str
    n_problems: int


def criteria() -> tuple[Criterio, ...]:
    return CRITERIA


def _criterion(key: str) -> Criterio:
    for criterion in CRITERIA:
        if criterion.key == key:
            return criterion
    raise KeyError(key)


def _sets_in(frame: pd.DataFrame) -> list[str]:
    present = set(frame["set"])
    return [s for s in config.SETS if s in present]


def values(tables: dict, recorte: Recorte, scenario: str | None = None) -> pd.DataFrame:
    """Set × criterion: the value of each criterion in the cut (research R4).

    TDF*, MS*, TFP, Δ and TC are the mean of the per-scenario values of ``primary.table`` (every
    scenario has the same problems, so this is also the pooled value). The cost is
    1000 × Σ cost ÷ Σ WAs killed by the AC oracle over the scenarios; it exists per set ×
    scenario only, so a problem-level filter does not change it (the dashboard says so).
    """
    per_problem = tables["per_problem"]
    cut = cuts.apply(per_problem, **recorte.cut_kwargs())
    if scenario is not None:
        cut = cut[cut["scenario"] == scenario]
    if cut.empty:
        raise cuts.CutError("no combination with these filters")
    table = primary.table(cut)
    out = table.groupby("set", sort=False)[[c.column for c in CRITERIA[:-1]]].mean()
    out.columns = [c.key for c in CRITERIA[:-1]]
    out["cost"] = _cost(tables, recorte, scenario, out.index)
    return out.reindex(_sets_in(cut))


def _cost(tables: dict, recorte: Recorte, scenario: str | None, sets) -> list[float]:
    whole = cuts.apply(tables["per_problem"], **recorte.cut_kwargs(only_sets_and_scenarios=True))
    if scenario is not None:
        whole = whole[whole["scenario"] == scenario]
    cost = tables["cost"]
    out = []
    for set_name in sets:
        mine = whole[whole["set"] == set_name]
        scenarios = set(mine["scenario"])
        spent = cost[(cost["set"] == set_name) & cost["scenario"].isin(scenarios)]["cost_usd"]
        killed = mine["wa_corrected"].sum()
        if set_name in LOCAL or spent.isna().all() or spent.empty or not killed:
            out.append(float("nan"))
        else:
            out.append(float(1000 * spent.sum() / killed))
    return out


def _significant(value) -> bool:
    return str(value).strip().lower() == "true"


def test_state(
    stats: pd.DataFrame, metric: str | None, scenario: str | None, a: str, b: str, recorte: Recorte
) -> str:
    """Do ``a`` and ``b`` differ in ``metric`` in ``scenario``? From ``stats.csv`` only (R3)."""
    if metric is None or scenario is None or not recorte.complete:
        return UNTESTED
    family = "attempt1" if "slm-attempt1" in (a, b) else "models"
    pair = ((stats["group_a"] == a) & (stats["group_b"] == b)) | (
        (stats["group_a"] == b) & (stats["group_b"] == a)
    )
    found = stats[
        (stats["family"] == family)
        & (stats["metric"] == metric)
        & (stats["scope"] == scenario)
        & pair
    ]
    if found.empty:
        return UNTESTED
    return DIFFER if _significant(found["significant"].iloc[0]) else TIE


def _ranked(column: pd.Series, criterion: Criterio) -> pd.Series:
    """The values of the column in the order of the ranking (best first, stable on set order)."""
    present = column.dropna()
    if not criterion.local_ranked:
        present = present[[s not in LOCAL for s in present.index]]
    order = np.argsort(
        -present.to_numpy() if criterion.better == "higher" else present.to_numpy(), kind="stable"
    )
    return present.iloc[order]


def scoreboard(tables: dict, recorte: Recorte) -> pd.DataFrame:
    """Long form ``set, criterion, value, rank``; ties share the rank; no rank = not ranked."""
    vals = values(tables, recorte)
    rows = []
    for criterion in CRITERIA:
        column = vals[criterion.key]
        ranked = _ranked(column, criterion)
        signed = ranked if criterion.better == "lower" else -ranked
        ranks = signed.rank(method="min").astype(int)
        for set_name in vals.index:
            rows.append(
                {
                    "set": set_name,
                    "criterion": criterion.key,
                    "value": column.loc[set_name],
                    "rank": ranks.get(set_name, pd.NA),
                }
            )
    frame = pd.DataFrame(rows, columns=["set", "criterion", "value", "rank"])
    frame["rank"] = frame["rank"].astype("Int64")
    return frame


def leader(
    tables: dict, recorte: Recorte, criterion: str, scenario: str | None = None
) -> Resultado:
    """The best set of a criterion in the cut, the second one and the state of the difference.

    With ``scenario`` None the value is the mean of the scenarios of the cut, untested unless the
    cut has a single scenario.
    """
    spec = _criterion(criterion)
    vals = values(tables, recorte, scenario)
    ranked = _ranked(vals[spec.key], spec)
    n_problems = cuts.apply(tables["per_problem"], **recorte.cut_kwargs())["problem"].nunique()
    effective = scenario
    if effective is None and len(recorte.scenarios) == 1:
        effective = recorte.scenarios[0]
    if ranked.empty:
        return Resultado(
            spec.key, effective, None, float("nan"), None, float("nan"), UNTESTED, n_problems
        )
    first, value = ranked.index[0], float(ranked.iloc[0])
    if len(ranked) < 2:
        return Resultado(
            spec.key, effective, first, value, None, float("nan"), UNTESTED, n_problems
        )
    second, second_value = ranked.index[1], float(ranked.iloc[1])
    if value == second_value:
        state = TIE
    else:
        state = test_state(tables["stats"], spec.stats_metric, effective, first, second, recorte)
    return Resultado(spec.key, effective, first, value, second, second_value, state, n_problems)


# ------------------------------------------------------------------ titles of the sections (R5)
# The sentence templates of every section, in one table for the authors to edit. ``{...}`` are
# filled from the cut; the key is the ``rule`` a ``Titulo`` carries, so a test can tell which
# template a title used (contracts/narrative.md, page 3).

TEMPLATES = {
    "scoreboard_split": "Nenhuma IA venceu em todos os critérios",
    "scoreboard_one": "{leader} venceu em todos os critérios",
    "tdf": "{leader} encontra {value} das falhas reais",
    "tdf_tie": "{leader} e {second} empatam em falhas reais encontradas ({value} × {second_value})",
    "ms": "{leader} detecta {value} dos mutantes",
    "ms_tie": "{leader} e {second} empatam em mutantes detectados ({value} × {second_value})",
    "tradeoff": "Quem mais detecta também mais erra o gabarito",
    "tfp": "{leader} reprova o código correto em menos problemas: {value}",
    "tfp_tie": (
        "{leader} e {second} empatam em código correto reprovado ({value} × {second_value})"
    ),
    "tfp_cause": "{value} dos testes de {leader} esperam a saída errada",
    "context": "O cenário muda a detecção em até {dmax} pontos ({max_set}); {min_set} quase não muda",
    "context_single": "Com um cenário só no recorte, não há efeito de contexto para comparar",
    "iic": "Juntar requisito e código muda a detecção em no máximo {value} ({leader})",
    "iic_none": "Nenhum WA detectado no cenário de base: o IIC não se calcula neste recorte",
    "cost": "{leader} detecta 1.000 falhas por US$ {value}, {ratio}× menos que {last}",
    "cost_single": "{leader} detecta 1.000 falhas por US$ {value}",
    "cost_none": "Sem modelo comercial no recorte: não há custo em dinheiro",
    "guide": "Qual IA escolher depende do que importa para você",
}
SET_NAME = {
    "slm": "SLM",
    "gpt": "GPT",
    "gemini": "Gemini",
    "claude": "Claude",
    "slm-attempt1": "SLM 1ª tentativa",
}
SCENARIO_NAME = {"black_box": "caixa-preta", "white_box": "caixa-branca", "hybrid": "híbrido"}
DIRECTION_NAME = {"cod": "+ código", "req": "+ requisito"}  # what the hybrid adds to the base
STATE_NAME = {
    DIFFER: "diferença significativa",
    TIE: "empate estatístico",
    UNTESTED: "não testado",
}
BARRED = "accepted_barred"


@dataclass(frozen=True)
class Titulo:
    text: str
    subtitle: str
    rule: str


def num(value: float, decimals: int = 1) -> str:
    """Portuguese number: 20.000 · 90,1."""
    text = f"{value:,.{decimals}f}"
    return text.replace(",", "§").replace(".", ",").replace("§", ".")


def pct(value: float, decimals: int = 1) -> str:
    return f"{num(value, decimals)}%"


def name(set_name: str | None) -> str:
    return SET_NAME.get(set_name, set_name or "—")


def scenarios_of(tables: dict, recorte: Recorte) -> list[str]:
    """The scenarios of the cut, in the fixed order."""
    chosen = recorte.scenarios or config.SCENARIOS
    present = set(tables["per_problem"]["scenario"])
    return [s for s in config.SCENARIOS if s in chosen and s in present]


def _scenario_words(scenarios: list[str]) -> str:
    names = [SCENARIO_NAME[s] for s in scenarios]
    if len(names) == 1:
        return f"cenário {names[0]}"
    return "média de " + ", ".join(names[:-1]) + " e " + names[-1]


def n_problems(tables: dict, recorte: Recorte) -> int:
    return int(cuts.apply(tables["per_problem"], **recorte.cut_kwargs())["problem"].nunique())


def _fill(rule: str, **values) -> str:
    return TEMPLATES[rule].format(**values)


def _leader_title(tables: dict, recorte: Recorte, key: str, rule: str, unit: str) -> Titulo:
    result = leader(tables, recorte, key)
    rule = f"{rule}_tie" if result.state == TIE else rule
    text = _fill(
        rule,
        leader=name(result.leader),
        value=pct(result.value),
        second=name(result.second),
        second_value=pct(result.second_value),
    )
    n = n_problems(tables, recorte)
    words = _scenario_words(scenarios_of(tables, recorte))
    return Titulo(
        text,
        f"{words} · de {num(100 * n, 0)} {unit} por cenário · barra: gabarito do AC; "
        "traço: gabarito da IA",
        rule,
    )


def conclusion(tables: dict, recorte: Recorte, section: str, oracle: str = "corrected") -> Titulo:
    """The conclusion title of a section of page 3 for the cut (contracts/narrative.md)."""
    n = n_problems(tables, recorte)
    scenarios = scenarios_of(tables, recorte)
    words = _scenario_words(scenarios)
    if section == "scoreboard":
        board = scoreboard(tables, recorte)
        ranked = board.dropna(subset=["rank"])
        firsts = ranked[ranked["rank"] == 1]
        criteria_ranked = set(ranked["criterion"])
        winners = [
            s
            for s in _sets_in(board)
            if set(firsts.loc[firsts["set"] == s, "criterion"]) == criteria_ranked
        ]
        rule = "scoreboard_one" if len(winners) == 1 else "scoreboard_split"
        return Titulo(
            _fill(rule, leader=name(winners[0]) if winners else ""),
            f"Posição em cada critério ({words}); 1º = melhor; gabarito do AC; {n} problemas",
            rule,
        )
    if section == "tdf":
        return _leader_title(tables, recorte, "tdf_star", "tdf", "WAs")
    if section == "ms":
        return _leader_title(tables, recorte, "ms_star", "ms", "mutantes")
    if section == "tfp":
        vals = values(tables, recorte)
        tdf_first = _ranked(vals["tdf_star"], _criterion("tdf_star")).index[0]
        tfp_order = _ranked(vals["tfp"], _criterion("tfp"))
        subtitle = (
            f"{words} · TFP: % dos {n} problemas em que a suíte reprova o código correto "
            f"(menor é melhor) · TDF*: de {num(100 * n, 0)} WAs por cenário"
        )
        if len(tfp_order) > 1 and tfp_order.index[-1] == tdf_first:
            return Titulo(_fill("tradeoff"), subtitle, "tradeoff")
        result = leader(tables, recorte, "tfp")
        rule = "tfp_tie" if result.state == TIE else "tfp"
        text = _fill(
            rule,
            leader=name(result.leader),
            value=pct(result.value),
            second=name(result.second),
            second_value=pct(result.second_value),
        )
        return Titulo(text, subtitle, rule)
    if section == "tfp_cause":
        causes = tfp_causes(tables, recorte)
        top = causes.sort_values("oracle_share", ascending=False, kind="stable").iloc[0]
        listed = words.removeprefix("média de ")
        return Titulo(
            _fill("tfp_cause", value=pct(top["oracle_share"]), leader=name(top["set"])),
            f"{listed} somados · % dos testes de cada IA que reprovam o código correto, por causa · "
            f"dos {num(top['total_tests'], 0)} testes de {name(top['set'])}",
            "tfp_cause",
        )
    if section == "context":
        subtitle = f"TDF* (gabarito do AC) em cada cenário · de {num(100 * n, 0)} WAs por cenário"
        if len(scenarios) < 2:
            return Titulo(_fill("context_single"), subtitle, "context_single")
        spread = shift_spread(tables, recorte)
        text = _fill(
            "context",
            dmax=num(spread.max()),
            max_set=name(spread.idxmax()),
            min_set=name(spread.idxmin()),
        )
        return Titulo(text, subtitle, "context")
    if section == "iic":
        frame = iic_values(tables, recorte, oracle).dropna(subset=["iic"])
        which = "do AC" if oracle == "corrected" else "da IA"
        subtitle = (
            "IIC: WAs que o híbrido ganha menos os que perde, em % dos detectados no cenário "
            f"de base · gabarito {which} · {n} problemas"
        )
        if frame.empty:
            return Titulo(_fill("iic_none"), subtitle, "iic_none")
        top = frame.loc[frame["iic"].abs().idxmax()]
        text = _fill(
            "iic",
            value=pct(abs(top["iic"])),
            leader=f"{name(top['set'])}, {DIRECTION_NAME[top['direction']]}",
        )
        return Titulo(text, subtitle, "iic")
    if section == "cost":
        vals = values(tables, recorte)
        ranked = _ranked(vals["cost"], _criterion("cost"))
        subtitle = f"US$ por 1.000 WAs detectados pelo gabarito do AC · {words}"
        if not recorte.complete:
            subtitle += " · o custo não se divide por problema: valor de todos os problemas"
        if ranked.empty:
            return Titulo(_fill("cost_none"), subtitle, "cost_none")
        first, value = ranked.index[0], float(ranked.iloc[0])
        if len(ranked) == 1:
            return Titulo(
                _fill("cost_single", leader=name(first), value=num(value, 3)),
                subtitle,
                "cost_single",
            )
        last, worst = ranked.index[-1], float(ranked.iloc[-1])
        ratio = worst / value
        text = _fill(
            "cost",
            leader=name(first),
            value=num(value, 3),
            ratio=num(ratio, 0 if ratio >= 10 else 1),
            last=name(last),
        )
        return Titulo(text, subtitle, "cost")
    if section == "guide":
        return Titulo(
            _fill("guide"), f"Melhor IA de cada critério em cada cenário · {n} problemas", "guide"
        )
    raise ValueError(f"unknown section {section!r}")


# ------------------------------------------------------------------- data of the new figures


def tfp_causes(tables: dict, recorte: Recorte) -> pd.DataFrame:
    """Per set: tests that reject the AC by a wrong expected output, over all tests of the cut."""
    table = primary.table(cuts.apply(tables["per_problem"], **recorte.cut_kwargs()))
    sums = table.groupby("set", sort=False)[
        ["FP_tests_oracle", "FP_tests_invalid_input", "total_tests"]
    ].sum()
    out = sums[sums["total_tests"] > 0].reset_index()
    out["oracle_share"] = 100 * out["FP_tests_oracle"] / out["total_tests"]
    out["invalid_share"] = 100 * out["FP_tests_invalid_input"] / out["total_tests"]
    return out


def scenario_shift(tables: dict, recorte: Recorte) -> pd.DataFrame:
    """``set, scenario, value``: the TDF* of each set in each scenario of the cut."""
    rows = []
    for scenario in scenarios_of(tables, recorte):
        column = values(tables, recorte, scenario)["tdf_star"]
        rows += [{"set": s, "scenario": scenario, "value": float(v)} for s, v in column.items()]
    return pd.DataFrame(rows, columns=["set", "scenario", "value"])


def shift_spread(tables: dict, recorte: Recorte) -> pd.Series:
    """Per set: the highest minus the lowest TDF* over the scenarios of the cut."""
    shift = scenario_shift(tables, recorte)
    spread = shift.groupby("set")["value"].agg(lambda v: v.max() - v.min())
    return spread.reindex(_sets_in(shift))


def iic_values(tables: dict, recorte: Recorte, oracle: str = "corrected") -> pd.DataFrame:
    """``set, direction, iic``: the pooled IIC over the problems of the cut.

    The IIC compares scenarios, so the scenario filter does not apply to it.
    """
    from metrics import iic

    kwargs = recorte.cut_kwargs()
    kwargs.pop("scenarios")
    per_problem, detected = cuts.apply(
        tables["per_problem"], detected_wa=tables["detected_wa"], **kwargs
    )
    if per_problem.empty:
        raise cuts.CutError("no combination with these filters")
    table = iic.table(detected, per_problem)
    mine = table[table["oracle"] == oracle]
    return pd.DataFrame(
        {"set": mine["set"], "direction": mine["direction"], "iic": mine["iic_pooled"]}
    ).reset_index(drop=True)


def iic_sign_changes(tables: dict, recorte: Recorte) -> list[str]:
    """Sentences for the sets whose IIC changes sign from the AI's answer key to the AC's."""
    declared = iic_values(tables, recorte, "declared").set_index(["set", "direction"])["iic"]
    corrected = iic_values(tables, recorte, "corrected").set_index(["set", "direction"])["iic"]
    out = []
    for key, before in declared.items():
        after = corrected.get(key, float("nan"))
        if before and after and np.sign(before) != np.sign(after):
            set_name, direction = key
            word = "positivo" if after > 0 else "negativo"
            out.append(
                f"Com o gabarito do AC, o efeito de {name(set_name)} "
                f"({DIRECTION_NAME[direction]}) vira {word}: de {pct(before)} para {pct(after)}."
            )
    return out


def barred_effect(tables: dict, recorte: Recorte) -> tuple[int, list[str]]:
    """How many suites without reasoning (``accepted_barred``) are in the cut, and the criteria
    whose 1st place would change without them (decision of 2026-11-12: they stay included)."""
    cut = cuts.apply(tables["per_problem"], **recorte.cut_kwargs())
    count = int((cut["status"] == BARRED).sum())
    if not count:
        return 0, []
    without = dict(tables)
    without["per_problem"] = tables["per_problem"][tables["per_problem"]["status"] != BARRED]
    before = scoreboard(tables, recorte)
    after = scoreboard(without, recorte)
    changed = []
    for criterion in CRITERIA:
        first = [
            set(b[(b["criterion"] == criterion.key) & (b["rank"] == 1)]["set"])
            for b in (before, after)
        ]
        if first[0] != first[1]:
            changed.append(criterion.key)
    return count, changed


# --------------------------------------------------------------------------- the choice guide

LOCAL_CRITERION = "local"
LOCAL_LABEL = "rodar sem custo de API"


@dataclass(frozen=True)
class Cartao:
    """One cell of the guide: the best set of a criterion in one scenario of the cut."""

    criterion: str
    label: str
    scenario: str
    leader: str | None
    value: float
    second: str | None
    second_value: float
    state: str
    tied: tuple = ()  # every set with exactly the leader's value (e.g. TC = 100%)


def guide(tables: dict, recorte: Recorte) -> list[Cartao]:
    """One card per criterion × scenario of the cut, plus "rodar sem custo de API"; never an
    overall winner (spec US3)."""
    cards = []
    scenarios = scenarios_of(tables, recorte)
    for scenario in scenarios:
        vals = values(tables, recorte, scenario)
        for criterion in CRITERIA:
            result = leader(tables, recorte, criterion.key, scenario)
            column = _ranked(vals[criterion.key], criterion)
            tied = tuple(s for s, v in column.items() if v == result.value)
            cards.append(
                Cartao(
                    criterion.key,
                    criterion.label,
                    scenario,
                    result.leader,
                    result.value,
                    result.second,
                    result.second_value,
                    result.state,
                    tied if len(tied) > 1 else (),
                )
            )
    sets_in_cut = set(cuts.apply(tables["per_problem"], **recorte.cut_kwargs())["set"])
    local = "slm" if "slm" in sets_in_cut else None
    for scenario in scenarios:
        cards.append(
            Cartao(
                LOCAL_CRITERION,
                LOCAL_LABEL,
                scenario,
                local,
                float("nan"),
                None,
                float("nan"),
                UNTESTED,
            )
        )
    order = [c.key for c in CRITERIA] + [LOCAL_CRITERION]
    return sorted(cards, key=lambda c: (order.index(c.criterion), scenarios.index(c.scenario)))
