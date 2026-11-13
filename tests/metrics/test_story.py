"""The narrative layer of the metrics (feature 012): criteria, values of a cut, test state,
scoreboard and leader (T008, T009, T011, T013).

Fake tables with known values: 4 problems (ratings 1000/1600, two macrocategorias), sets ``gpt``,
``claude`` and ``slm``, scenarios ``black_box`` and ``white_box``. TDF* (AC oracle): gpt 90/80,
claude 70/95, slm 50/60, so the mean leader is gpt (85) and the white-box leader is claude (95).
"""

import math
from pathlib import Path

import pandas as pd
import pytest

from metrics import cuts, story, tables
from tests.metrics.conftest import cost_frame, per_problem_rows, row, stats_frame

PROBLEMS = {
    "1_A": (1000, "matematica"),
    "2_B": (1000, "logica_direta"),
    "3_C": (1600, "matematica"),
    "4_D": (1600, "logica_direta"),
}
TDF_STAR = {
    ("gpt", "black_box"): 90,
    ("gpt", "white_box"): 80,
    ("claude", "black_box"): 70,
    ("claude", "white_box"): 95,
    ("slm", "black_box"): 50,
    ("slm", "white_box"): 60,
}
DELTA = {"gpt": 5, "claude": 1, "slm": 10}  # declared = corrected + delta


def fake_tables() -> dict:
    rows = []
    for (set_name, scenario), corrected in TDF_STAR.items():
        for problem, (rating, macro) in PROBLEMS.items():
            rejected = (set_name == "gpt" and scenario == "black_box" and problem == "1_A") or (
                set_name == "slm" and scenario == "black_box"
            )
            rows.append(
                row(
                    set_name,
                    scenario,
                    problem,
                    macrocategoria=macro,
                    rating=rating,
                    ac_rejected=rejected,
                    wa_corrected=corrected,
                    wa_declared=corrected + DELTA[set_name],
                    mutants_corrected=95,
                    mutants_declared=96,
                )
            )
    stats = stats_frame(
        [
            ("models", "TDF_star", "black_box", "gpt", "claude", True),
            ("models", "TDF_star", "white_box", "gpt", "claude", False),
            ("models", "TFP", "black_box", "gpt", "claude", False),
            ("attempt1", "TDF_star", "black_box", "slm-attempt1", "gpt", True),
        ]
    )
    cost = cost_frame(
        {
            ("gpt", "black_box"): 1.0,
            ("gpt", "white_box"): 1.0,
            ("claude", "black_box"): 0.1,
            ("claude", "white_box"): 0.1,
        }
    )
    return {
        "per_problem": per_problem_rows(rows),
        "detected_wa": pd.DataFrame(columns=["set", "scenario", "problem", "target", "oracle"]),
        "stats": stats,
        "cost": cost,
    }


@pytest.fixture
def t():
    return fake_tables()


# --------------------------------------------------------------------------- criteria and values


def test_criteria_in_scoreboard_order():
    keys = [c.key for c in story.criteria()]
    assert keys == ["tdf_star", "ms_star", "tfp", "delta_tdf", "tc", "cost"]
    by_key = {c.key: c for c in story.criteria()}
    assert by_key["tdf_star"].better == "higher" and by_key["tfp"].better == "lower"
    assert by_key["tdf_star"].stats_metric == "TDF_star" and by_key["tfp"].stats_metric == "TFP"
    assert by_key["delta_tdf"].stats_metric is None and by_key["cost"].stats_metric is None
    assert not by_key["cost"].local_ranked and by_key["tdf_star"].local_ranked


def test_values_are_the_mean_of_the_scenarios(t):
    values = story.values(t, story.Recorte())
    assert list(values.index) == ["slm", "gpt", "claude"]  # the fixed order of the sets
    assert values.loc["gpt", "tdf_star"] == 85.0
    assert values.loc["claude", "tdf_star"] == 82.5
    assert values.loc["slm", "tdf_star"] == 55.0
    assert values.loc["gpt", "delta_tdf"] == 5.0
    assert values.loc["gpt", "tfp"] == 12.5  # 25% in black box, 0% in white box
    assert values.loc["slm", "tfp"] == 50.0
    assert values.loc["gpt", "tc"] == 100.0


def test_cost_is_the_ratio_of_the_sums(t):
    values = story.values(t, story.Recorte())
    assert math.isclose(values.loc["gpt", "cost"], 1000 * 2.0 / (4 * 90 + 4 * 80))
    assert math.isclose(values.loc["claude", "cost"], 1000 * 0.2 / (4 * 70 + 4 * 95))
    assert math.isnan(values.loc["slm", "cost"])  # the local model has no money cost


def test_one_scenario_gives_that_scenario(t):
    values = story.values(t, story.Recorte(scenarios=("white_box",)))
    assert values.loc["claude", "tdf_star"] == 95.0
    assert values.loc["gpt", "tdf_star"] == 80.0
    assert story.values(t, story.Recorte(), scenario="black_box").loc["gpt", "tdf_star"] == 90.0


def test_cost_does_not_split_by_problem(t):
    full = story.values(t, story.Recorte())
    cut = story.values(t, story.Recorte(ratings=(1600,)))
    assert cut.loc["gpt", "cost"] == full.loc["gpt", "cost"]


def test_a_cut_with_one_problem_or_none_has_no_value(t):
    with pytest.raises(cuts.CutError):
        story.values(t, story.Recorte(problems=("1_A",)))
    with pytest.raises(cuts.CutError):
        story.values(t, story.Recorte(ratings=(1300,)))


def test_recorte_completeness():
    assert story.Recorte().complete
    assert story.Recorte(sets=("gpt",), scenarios=("hybrid",)).complete
    for kwargs in ({"problems": ("1_A", "2_B")}, {"ratings": (1000,)}, {"statuses": ("a",)}):
        assert not story.Recorte(**kwargs).complete
    assert not story.Recorte(macrocategorias=("matematica",)).complete
    recorte = story.Recorte.from_filters({"sets": ["gpt"], "ratings": [1000], "other": [1]})
    assert recorte.sets == ("gpt",) and recorte.ratings == (1000,)


# ------------------------------------------------------------------------------------ test state


def test_test_state_reads_the_pair_in_either_order(t):
    full = story.Recorte()
    stats = t["stats"]
    assert story.test_state(stats, "TDF_star", "black_box", "gpt", "claude", full) == "differ"
    assert story.test_state(stats, "TDF_star", "black_box", "claude", "gpt", full) == "differ"
    assert story.test_state(stats, "TDF_star", "white_box", "claude", "gpt", full) == "tie"
    assert story.test_state(stats, "TDF_star", "black_box", "gpt", "slm-attempt1", full) == "differ"


def test_test_state_is_untested_when_there_is_no_test(t):
    stats = t["stats"]
    assert (
        story.test_state(
            stats, "TDF_star", "black_box", "gpt", "claude", story.Recorte(ratings=(1000,))
        )
        == "untested"
    )
    assert story.test_state(stats, None, "black_box", "gpt", "claude", story.Recorte()) == (
        "untested"
    )
    assert story.test_state(stats, "TDF_star", None, "gpt", "claude", story.Recorte()) == (
        "untested"
    )
    assert story.test_state(stats, "MS_star", "black_box", "gpt", "claude", story.Recorte()) == (
        "untested"  # pair not in the table
    )


# ---------------------------------------------------------------------- scoreboard and leader


def test_scoreboard_positions(t):
    board = story.scoreboard(t, story.Recorte()).set_index(["criterion", "set"])
    assert board.loc[("tdf_star", "gpt"), "rank"] == 1
    assert board.loc[("tdf_star", "claude"), "rank"] == 2
    assert board.loc[("tdf_star", "slm"), "rank"] == 3
    assert board.loc[("tfp", "claude"), "rank"] == 1  # lower is better
    assert board.loc[("delta_tdf", "claude"), "rank"] == 1
    assert {board.loc[("tc", s), "rank"] for s in ("gpt", "claude", "slm")} == {1}  # a tie
    assert board.loc[("cost", "claude"), "rank"] == 1
    assert pd.isna(board.loc[("cost", "slm"), "rank"])  # out of the money ranking


def test_leader_of_the_mean_is_untested(t):
    result = story.leader(t, story.Recorte(), "tdf_star")
    assert (result.leader, result.value, result.second, result.second_value) == (
        "gpt",
        85.0,
        "claude",
        82.5,
    )
    assert result.state == "untested" and result.n_problems == 4


def test_leader_per_scenario_uses_the_test(t):
    assert story.leader(t, story.Recorte(), "tdf_star", "black_box").state == "differ"
    white = story.leader(t, story.Recorte(), "tdf_star", "white_box")
    assert (white.leader, white.second, white.state) == ("claude", "gpt", "tie")
    only_white = story.leader(t, story.Recorte(scenarios=("white_box",)), "tdf_star")
    assert (only_white.leader, only_white.state) == ("claude", "tie")


def test_the_local_model_never_leads_the_cost(t):
    result = story.leader(t, story.Recorte(), "cost")
    assert result.leader == "claude" and result.second == "gpt"


CUTS = [
    {},
    {"macrocategorias": ("matematica",)},
    {"macrocategorias": ("logica_direta",)},
    {"ratings": (1000,)},
    {"ratings": (1600,)},
    {"scenarios": ("black_box",)},
    {"scenarios": ("white_box",)},
    {"sets": ("gpt", "slm")},
    {"sets": ("claude", "slm")},
]


@pytest.mark.parametrize("cut", CUTS)
def test_the_leader_has_the_best_value_of_the_cut(t, cut):
    recorte = story.Recorte(**cut)
    values = story.values(t, recorte)
    for criterion in story.criteria():
        column = values[criterion.key].dropna()
        if column.empty:
            continue
        best = column.max() if criterion.better == "higher" else column.min()
        assert story.leader(t, recorte, criterion.key).value == best, (cut, criterion.key)


# ------------------------------------------------------------------ the real numbers (SC-001)

REAL = Path(__file__).resolve().parents[2] / "data/metrics"


@pytest.mark.skipif(
    not (REAL / "per_problem.csv").is_file(), reason="data/metrics is not extracted"
)
def test_real_numbers():
    real = tables.read(Path("/"), REAL)
    values = story.values(real, story.Recorte())
    assert round(values.loc["gemini", "tdf_star"], 1) == 90.1
    assert round(values.loc["gemini", "ms_star"], 1) == 97.0
    assert round(values.loc["claude", "tfp"], 1) == 17.3
    assert round(values.loc["gpt", "delta_tdf"], 1) == 1.9
    assert round(values.loc["slm-attempt1", "tc"], 1) == 91.2
    board = story.scoreboard(real, story.Recorte()).set_index(["criterion", "set"])
    for criterion, winner in (
        ("tdf_star", "gemini"),
        ("ms_star", "gemini"),
        ("tfp", "claude"),
        ("delta_tdf", "gpt"),
        ("cost", "claude"),
    ):
        assert board.loc[(criterion, winner), "rank"] == 1, criterion
    full = story.Recorte()
    white_tfp = story.leader(real, full, "tfp", "white_box")
    assert (white_tfp.leader, white_tfp.value, white_tfp.second) == ("slm", 16.5, "claude")
    assert white_tfp.second_value == 17.5 and white_tfp.state == "tie"
    hybrid_tfp = story.leader(real, full, "tfp", "hybrid")
    assert (hybrid_tfp.leader, hybrid_tfp.value, hybrid_tfp.second) == ("gpt", 15.0, "claude")
    assert hybrid_tfp.state == "tie"
    white_tdf = story.leader(real, full, "tdf_star", "white_box")
    assert (white_tdf.leader, white_tdf.second, white_tdf.state) == ("gemini", "claude", "tie")
    assert round(white_tdf.value, 1) == 89.7 and round(white_tdf.second_value, 1) == 88.0


# ------------------------------------------------------------- conclusion titles (T022, T023)


def test_conclusion_names_the_leader_and_its_value(t):
    title = story.conclusion(t, story.Recorte(), "tdf")
    assert (title.text, title.rule) == ("GPT encontra 85,0% das falhas reais", "tdf")
    assert "de 400 WAs por cenário" in title.subtitle
    assert "média de caixa-preta e caixa-branca" in title.subtitle
    ms = story.conclusion(t, story.Recorte(), "ms")
    assert ms.rule == "ms_tie" and "empatam em mutantes" in ms.text  # MS* = 95% everywhere


def test_conclusion_uses_the_tie_rule(t):
    title = story.conclusion(t, story.Recorte(scenarios=("white_box",)), "tdf")
    assert title.rule == "tdf_tie"
    assert title.text == "Claude e GPT empatam em falhas reais encontradas (95,0% × 80,0%)"
    assert "cenário caixa-branca" in title.subtitle


def test_conclusion_denominator_follows_the_cut(t):
    title = story.conclusion(t, story.Recorte(ratings=(1000,)), "tdf")
    assert "de 200 WAs por cenário" in title.subtitle
    assert "dos 2 problemas" in story.conclusion(t, story.Recorte(ratings=(1000,)), "tfp").subtitle


def test_conclusion_of_the_scoreboard(t):
    split = story.conclusion(t, story.Recorte(), "scoreboard")
    assert (split.text, split.rule) == (
        "Nenhuma IA venceu em todos os critérios",
        "scoreboard_split",
    )
    one = story.conclusion(t, story.Recorte(sets=("gpt",)), "scoreboard")
    assert (one.text, one.rule) == ("GPT venceu em todos os critérios", "scoreboard_one")


def test_conclusion_of_the_false_positives(t):
    tfp = story.conclusion(t, story.Recorte(), "tfp")
    assert tfp.rule == "tfp"  # the TDF* leader (gpt) is not the last in TFP (slm is)
    assert tfp.text == "Claude reprova o código correto em menos problemas: 0,0%"
    tradeoff = story.conclusion(t, story.Recorte(sets=("gpt", "claude")), "tfp")
    assert tradeoff.rule == "tradeoff"  # now gpt leads TDF* and is last in TFP
    assert tradeoff.text == "Quem mais detecta também mais erra o gabarito"


def test_conclusion_of_the_context_and_the_cost(t):
    context = story.conclusion(t, story.Recorte(), "context")
    assert context.rule == "context"
    assert context.text.startswith("O cenário muda a detecção em até 25,0 pontos (Claude)")
    single = story.conclusion(t, story.Recorte(scenarios=("black_box",)), "context")
    assert single.rule == "context_single"
    cost = story.conclusion(t, story.Recorte(), "cost")
    assert cost.rule == "cost" and cost.text.startswith("Claude detecta 1.000 falhas por US$")
    assert "menos que GPT" in cost.text
    cut = story.conclusion(t, story.Recorte(ratings=(1600,)), "cost")
    assert "o custo não se divide por problema" in cut.subtitle
    assert story.conclusion(t, story.Recorte(sets=("slm",)), "cost").rule == "cost_none"


def test_every_section_has_a_template(t):
    for section in (
        "scoreboard",
        "tdf",
        "ms",
        "tfp",
        "tfp_cause",
        "context",
        "iic",
        "cost",
        "guide",
    ):
        title = story.conclusion(t, story.Recorte(), section)
        assert title.rule in story.TEMPLATES and title.text
    with pytest.raises(ValueError):
        story.conclusion(t, story.Recorte(), "nothing")


def test_portuguese_numbers():
    assert story.num(20000, 0) == "20.000"
    assert story.pct(90.14) == "90,1%"
    assert story.num(0.0189, 3) == "0,019"


def test_barred_suites_are_counted_and_their_effect_checked(t):
    assert story.barred_effect(t, story.Recorte()) == (0, [])
    barred = dict(t)
    frame = t["per_problem"].copy()
    rows = (frame["set"] == "claude") & (frame["problem"] == "1_A")
    frame.loc[rows, "status"] = story.BARRED
    barred["per_problem"] = frame
    count, changed = story.barred_effect(barred, story.Recorte())
    assert count == 2 and isinstance(changed, list)


# ------------------------------------------------------------------ the choice guide (T029)


def test_guide_has_one_card_per_criterion_and_scenario(t):
    cards = story.guide(t, story.Recorte())
    criteria = [c.key for c in story.criteria()] + [story.LOCAL_CRITERION]
    assert len(cards) == len(criteria) * 2  # two scenarios in the fake tables
    assert {(c.criterion, c.scenario) for c in cards} == {
        (k, s) for k in criteria for s in ("black_box", "white_box")
    }
    assert {story.SCENARIO_NAME[c.scenario] for c in cards} == {"caixa-preta", "caixa-branca"}
    assert story.SCENARIO_NAME["hybrid"] == "híbrido"
    white_tdf = next(c for c in cards if c.criterion == "tdf_star" and c.scenario == "white_box")
    assert (white_tdf.leader, white_tdf.second, white_tdf.state) == ("claude", "gpt", "tie")
    tc = next(c for c in cards if c.criterion == "tc" and c.scenario == "black_box")
    assert set(tc.tied) == {"slm", "gpt", "claude"}  # everyone delivered a suite


def test_guide_local_card_has_no_number_and_no_overall_winner(t):
    cards = story.guide(t, story.Recorte())
    local = [c for c in cards if c.criterion == story.LOCAL_CRITERION]
    assert local and all(c.leader == "slm" and math.isnan(c.value) for c in local)
    assert all(c.label == story.LOCAL_LABEL for c in local)
    fields = {f for c in cards for f in vars(c)}
    assert not {"overall", "winner", "best"} & fields


def test_guide_follows_the_scenario_filter(t):
    cards = story.guide(t, story.Recorte(scenarios=("white_box",)))
    assert {c.scenario for c in cards} == {"white_box"}


@pytest.mark.skipif(
    not (REAL / "per_problem.csv").is_file(), reason="data/metrics is not extracted"
)
def test_guide_real_numbers():
    real = tables.read(Path("/"), REAL)
    cards = {(c.criterion, c.scenario): c for c in story.guide(real, story.Recorte())}
    white_tfp = cards[("tfp", "white_box")]
    assert (white_tfp.leader, white_tfp.second, white_tfp.state) == ("slm", "claude", "tie")
    white_tdf = cards[("tdf_star", "white_box")]
    assert (white_tdf.leader, white_tdf.second, white_tdf.state) == ("gemini", "claude", "tie")
    hybrid_tfp = cards[("tfp", "hybrid")]
    assert (hybrid_tfp.leader, hybrid_tfp.second, hybrid_tfp.state) == ("gpt", "claude", "tie")
    for scenario in ("black_box", "white_box", "hybrid"):
        cost = cards[("cost", scenario)]
        assert (cost.leader, cost.state) == ("claude", "untested")
    titles = {
        s: story.conclusion(real, story.Recorte(), s).text
        for s in ("scoreboard", "tdf", "tfp", "cost")
    }
    assert titles == {
        "scoreboard": "Nenhuma IA venceu em todos os critérios",
        "tdf": "Gemini encontra 90,1% das falhas reais",
        "tfp": "Quem mais detecta também mais erra o gabarito",
        "cost": "Claude detecta 1.000 falhas por US$ 0,019, 14× menos que GPT",
    }
    assert story.barred_effect(real, story.Recorte()) == (9, [])


def test_scoreboard_by_scenario_ranks_inside_each_scenario():
    t = fake_tables()
    board = story.scoreboard_by_scenario(t, story.Recorte.from_filters({}))
    firsts = board[(board["criterion"] == "tdf_star") & (board["rank"] == 1)]
    assert dict(zip(firsts["scenario"], firsts["set"], strict=True)) == {
        "black_box": "gpt",
        "white_box": "claude",
    }
    one = board[(board["scenario"] == "white_box") & (board["criterion"] == "tdf_star")]
    assert sorted(one["rank"].astype(int)) == [1, 2, 3]  # three sets ranked in the scenario
    assert "tdf_star" in story.scenario_changes(t, story.Recorte.from_filters({}))
    title = story.conclusion(t, story.Recorte.from_filters({}), "scenarios")
    assert title.rule == "scenarios_change"
    single = story.conclusion(
        t, story.Recorte.from_filters({"scenarios": ["white_box"]}), "scenarios"
    )
    assert single.rule == "scenarios_single"
