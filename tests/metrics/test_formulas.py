""" "Como se calcula" (feature 012): every figure has its formula, and the worked example,
recomputed from the raw counts of the cut, gives the number the figure plots."""

import re

import pytest

import metrics.__main__ as cli
from dashboard import config as dashboard_config
from metrics import figures, formulas, story, tables


@pytest.fixture
def loaded(repo, monkeypatch, tmp_path_factory):
    monkeypatch.setenv("HOME", str(tmp_path_factory.mktemp("home")))
    monkeypatch.setenv(dashboard_config.ENV_EVALUATION_DIR, str(repo / "data/evaluation"))
    monkeypatch.setattr(cli, "_run_gate", lambda root: [])
    assert cli.main(["compute"]) == 0
    return tables.read(repo)


# The fake tree gives the Claude hybrid suite of 2_B no suite: that combination counts 100 WAs
# while the others have 2, so a mean of per-problem ratios and a ratio of sums differ there. In
# the real data every problem has 100 WAs and 100 mutants and they are the same number.
UNIFORM = {"sets": ["slm", "gpt", "gemini", "slm-attempt1"]}


def _number(text: str) -> float:
    """The last number of a line, in the Portuguese format (20.000 · 90,1)."""
    found = re.findall(r"-?[\d.]+(?:,\d+)?", text.replace("−", "-"))
    return float(found[-1].replace(".", "").replace(",", "."))


def _who(line: str) -> str:
    return line.split(":")[0].split(" (")[0].replace("TC de ", "").replace("Δ_oráculo de ", "")


def test_every_figure_has_a_formula():
    assert set(formulas.FORMULAS) == set(figures.FIGURES)
    for formula in formulas.FORMULAS.values():
        assert formula.latex and formula.words


@pytest.mark.parametrize("name", figures.FIGURES)
def test_every_figure_has_an_example(loaded, name):
    assert formulas.example(name, loaded, {}), name


@pytest.mark.parametrize(
    ("name", "column"), [("tdf_by_model", "value"), ("ms_declared_vs_corrected", "value")]
)
def test_detection_example_is_the_plotted_bar(loaded, name, column):
    plotted = figures.figure_data(name, loaded, UNIFORM).set_index("y")
    first, second = formulas.example(name, loaded, UNIFORM)
    who = _who(first)
    assert who == plotted.index[0]  # the example is the leader
    assert _number(first) == pytest.approx(plotted.loc[who, column], abs=0.05)
    assert _number(second) == pytest.approx(plotted.loc[who, "before"], abs=0.05)


def test_tfp_delta_and_tc_examples_are_the_scoreboard(loaded):
    board = story.values(loaded, story.Recorte.from_filters(UNIFORM))
    by_name = {story.name(s): s for s in board.index}
    tfp, delta, tc = formulas.example("scoreboard", loaded, UNIFORM)
    assert _number(tfp) == pytest.approx(board.loc[by_name[_who(tfp)], "tfp"], abs=0.05)
    assert _number(delta) == pytest.approx(board.loc[by_name[_who(delta)], "delta_tdf"], abs=0.005)
    assert _number(tc) == pytest.approx(board.loc[by_name[_who(tc)], "tc"], abs=0.05)


def test_tradeoff_example_is_the_plotted_point(loaded):
    plotted = figures.figure_data("tradeoff", loaded, UNIFORM).set_index("label")
    tfp, tdf = formulas.example("tradeoff", loaded, UNIFORM)
    assert _number(tfp) == pytest.approx(plotted.loc[_who(tfp), "x"], abs=0.05)
    assert _number(tdf) == pytest.approx(plotted.loc[_who(tdf), "y"], abs=0.05)


def test_scenario_shift_example_is_the_spread(loaded):
    (line,) = formulas.example("scenario_shift", loaded, UNIFORM)
    spread = story.shift_spread(loaded, story.Recorte.from_filters(UNIFORM))
    assert _number(line) == pytest.approx(spread.max(), abs=0.05)


@pytest.mark.parametrize("oracle", ["corrected", "declared"])
def test_iic_example_is_the_plotted_bar(loaded, oracle):
    lines = formulas.example("iic_diverging", loaded, {}, oracle)
    if not lines:
        pytest.skip("no IIC in the fake tree for this oracle")
    plotted = figures.figure_data("iic_diverging", loaded, {}, oracle)
    assert any(abs(v - _number(lines[0])) < 0.05 for v in plotted["value"])


def test_cost_example_is_the_cheapest_bar(loaded):
    plotted = figures.figure_data("cost_per_detection", loaded, {})
    (line,) = formulas.example("cost_per_detection", loaded, {})
    assert _who(line) == plotted["y"].iloc[0]
    assert _number(line) == pytest.approx(plotted["value"].iloc[0], abs=0.0005)


def test_iic_distribution_follows_the_answer_key(loaded):
    declared = figures.figure_data("iic_distribution", loaded, {}, "declared")
    corrected = figures.figure_data("iic_distribution", loaded, {}, "corrected")
    assert not declared.empty and not corrected.empty
    assert "gabarito-ia" in figures.file_name("iic_distribution", {}, "png", "declared")
    assert "gabarito-ia" not in figures.file_name("iic_distribution", {}, "png", "corrected")


def test_iic_distribution_example_is_a_plotted_median(loaded):
    (line,) = formulas.example("iic_distribution", loaded, {})
    median = float(
        re.search(r"mediana de (-?[\d.,]+)%", line.replace("−", "-")).group(1).replace(",", ".")
    )
    plotted = figures.figure_data("iic_distribution", loaded, {})
    medians = plotted.groupby(["x", "series"])["value"].median()
    assert any(abs(m - median) < 0.05 for m in medians)


@pytest.mark.parametrize("name", ["tdf_by_model", "ms_declared_vs_corrected"])
def test_the_example_names_the_plotted_leader_in_any_cut(loaded, name):
    plotted = figures.figure_data(name, loaded, {})
    assert _who(formulas.example(name, loaded, {})[0]) == plotted["y"].iloc[0]
