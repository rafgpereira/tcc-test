"""The dashboard's metrics page and the figures behind it (features 010 and 012: T023, T027,
T026, T028, T033).

The evaluated tree of the dashboard tests has two problems (``1_A`` rating 1000 matematica,
``2_B`` rating 1600 logica_direta), so any problem-level filter leaves a single problem: the page
warns and points to the evaluation page. The titles over cuts are tested on richer tables in
``test_story.py``.
"""

import pytest
from streamlit.testing.v1 import AppTest

import metrics.__main__ as cli
from dashboard import config as dashboard_config
from dashboard import glossary
from metrics import charts, cuts, figures, primary, story, tables


@pytest.fixture
def computed(repo, monkeypatch, tmp_path_factory):
    monkeypatch.setenv("HOME", str(tmp_path_factory.mktemp("home")))
    monkeypatch.setenv(dashboard_config.ENV_EVALUATION_DIR, str(repo / "data/evaluation"))
    monkeypatch.setattr(cli, "_run_gate", lambda root: [])
    assert cli.main(["compute"]) == 0
    return repo


def _page():
    def script():
        from dashboard import app

        app.main(page="metrics")

    return AppTest.from_function(script, default_timeout=90)


def _texts(at) -> str:
    parts = [e.value for e in at.markdown] + [e.value for e in at.caption]
    parts += [e.value for e in at.warning] + [e.value for e in at.subheader]
    return "\n".join(str(p) for p in parts)


def test_every_metrics_column_has_an_explanation(computed):
    loaded = tables.read(computed)
    for name in ("metrics", "iic", "stats", "cost"):
        missing = [c for c in loaded[name].columns if glossary.column_help(str(c)) is None]
        assert missing == [], (name, missing)


def test_chart_data_are_the_numbers_of_the_tables(computed):
    loaded = tables.read(computed)
    filters = {"sets": ["gpt", "claude"]}
    values = figures.figure_data("tdf_declared_vs_corrected", loaded, filters)
    official = primary.table(
        loaded["per_problem"][loaded["per_problem"]["set"].isin(["gpt", "claude"])]
    )
    declared = values[values["series"].str.startswith("TDF (")]["value"].tolist()
    corrected = values[values["series"].str.startswith("TDF* (")]["value"].tolist()
    assert declared == official["TDF"].tolist() and corrected == official["TDF_star"].tolist()
    ranked = figures.figure_data("tdf_by_model", loaded, filters).set_index("y")
    means = official.groupby("set")[["TDF", "TDF_star"]].mean()
    for set_name in ("gpt", "claude"):
        row = ranked.loc[story.name(set_name)]
        assert row["value"] == round(means.loc[set_name, "TDF_star"], 2)
        assert row["before"] == round(means.loc[set_name, "TDF"], 2)
    for name in figures.LEGACY:
        data = figures.figure_data(name, loaded, {})
        heading, y_title = figures.TITLES[name]
        spec = charts.chart(
            data, heading, y_title, "filtros: nenhum", figures.KIND.get(name, "grouped")
        )
        as_dict = spec.to_dict()
        assert as_dict["title"]["subtitle"] == ["filtros: nenhum"]
        panels = as_dict.get("vconcat", [as_dict])  # one panel per scenario, or a single one
        for panel in panels:
            marks = [layer["mark"]["type"] for layer in panel["layer"]]
            assert "text" in marks  # value labels (or the median of the IIC boxes)


def test_charts_follow_the_theme():
    import pandas as pd

    data = pd.DataFrame(
        {"x": ["gpt", "gpt"], "series": ["a", "b"], "value": [1.0, 2.0], "panel": ["", ""]}
    )
    for mode in ("light", "dark"):
        spec = charts.chart(data, "t", "y", "s", "grouped", mode=mode).to_dict()
        assert spec["config"]["background"] == charts.INK[mode]["surface"]
        colors = spec["layer"][0]["encoding"]["color"]["scale"]["range"]
        assert colors == charts.PALETTE[mode][:2]  # the series colour of the theme, in slot order
        label = spec["layer"][1]["mark"]
        assert label["color"] == charts.INK[mode]["primary"]  # text in ink, never series colour


def test_problem_filter_needs_two_problems(computed):
    loaded = tables.read(computed)
    two = figures.figure_data("tdf_by_model", loaded, {"problems": ["1_A", "2_B"]})
    assert not two.empty
    with pytest.raises(cuts.CutError):
        figures.figure_data("tdf_by_model", loaded, {"problems": ["1_A"]})


def test_the_download_is_the_chart_on_screen(computed):
    """The file saved from the dashboard is the chart shown, in the theme shown, framed."""
    import vl_convert

    loaded = tables.read(computed)
    filters = {"sets": ["gpt", "claude"]}
    for mode in ("light", "dark"):
        shown = figures.chart("ms_declared_vs_corrected", loaded, filters, "fonte-x", mode)
        _, png = figures.render("ms_declared_vs_corrected", loaded, filters, "png", "fonte-x", mode)
        assert png == vl_convert.vegalite_to_png(shown.to_dict(), scale=figures.PNG_SCALE)
        card = figures.card("ms_declared_vs_corrected", loaded, filters, mode).to_dict()
        assert "title" not in card and card["config"]["background"] == "transparent"
        assert shown.to_dict()["layer"] == card["layer"]  # the same drawing, plus the title


# ------------------------------------------------------------ new and revised figures (T026)

NARRATIVE = [n for n in figures.FIGURES if n not in figures.LEGACY]


@pytest.mark.parametrize("name", NARRATIVE)
def test_new_figures_render_with_and_without_a_rating_filter(computed, name):
    loaded = tables.read(computed)
    full = {}
    with_rating = {"ratings": [1000, 1600]}  # both problems: a filter that keeps a valid cut
    for filters in (full, with_rating):
        for fmt in ("png", "svg"):
            a = figures.render(name, loaded, filters, fmt, "fonte-x")
            b = figures.render(name, loaded, filters, fmt, "fonte-x")
            assert a == b and a[1]
    file_name, _ = figures.render(name, loaded, with_rating, "png", "s")
    assert file_name == f"{name}__rating-1000+1600.png"
    spec = figures.chart(name, loaded, with_rating, "s").to_dict()
    assert spec["title"]["text"] == figures.title(name, loaded, with_rating).text
    assert any("rating = 1000, 1600" in line for line in spec["title"]["subtitle"])


def test_the_title_of_tdf_by_model_names_the_leader_of_the_cut(computed):
    loaded = tables.read(computed)
    for sets in (["gpt", "claude"], ["claude"], ["slm", "gemini"]):
        filters = {"sets": sets}
        leader = story.leader(loaded, story.Recorte.from_filters(filters), "tdf_star")
        assert story.name(leader.leader) in figures.title("tdf_by_model", loaded, filters).text


def test_iic_diverging_takes_the_oracle(computed):
    loaded = tables.read(computed)
    declared = figures.figure_data("iic_diverging", loaded, {}, oracle="declared")
    corrected = figures.figure_data("iic_diverging", loaded, {}, oracle="corrected")
    assert set(declared["panel"]) == {"+ código", "+ requisito"}
    assert len(declared) == len(corrected)
    assert figures.file_name("iic_diverging", {}, "png", "declared") == (
        "iic_diverging__gabarito-ia.png"
    )
    with pytest.raises(ValueError):
        figures.figure_data("iic_diverging", loaded, {}, oracle="other")


def test_figures_command_with_rating(computed):
    assert (
        cli.main(["figures", "--figure", "scoreboard", "--rating", "1000", "--format", "png"]) == 2
    )  # one problem left
    assert cli.main(["figures", "--rating", "9999"]) == 2
    assert (
        cli.main(
            ["figures", "--figure", "scoreboard", "--rating", "1000", "--rating", "1600"]
            + ["--format", "png"]
        )
        == 0
    )
    assert (computed / "data/metrics/figures/scoreboard__rating-1000+1600.png").is_file()


# ------------------------------------------------------------------- the page (T028, T033)


def test_metrics_page_tells_the_story_in_order(computed):
    at = _page().run()
    assert not at.exception, at.exception
    headers = [h.value for h in at.subheader]
    assert headers == [
        "Placar",
        "Falhas reais e mutantes",
        "Falsos positivos",
        "Contexto: requisito, código ou os dois",
        "Custo",
        "Guia de escolha",
    ]
    loaded = tables.read(computed)
    shown = _texts(at)
    for name in ("scoreboard", "tdf_by_model", "tradeoff", "cost_per_detection", "choice_guide"):
        assert figures.title(name, loaded, {}).text in shown
    assert "Sem filtros · 2 problemas" in shown
    assert "Entre o 1º e o 2º" in shown or "não é testada aqui" in shown  # the test state
    assert not [m for m in at.main.multiselect]  # filters only in the sidebar
    assert not [s for s in at.main.selectbox]  # no "Corte das tabelas" any more


def test_metrics_page_titles_follow_the_sidebar(computed):
    at = _page().run()
    at.sidebar.multiselect[0].select("claude").select("slm").run()  # IA (conjunto)
    assert not at.exception, at.exception
    loaded = tables.read(computed)
    filters = {"sets": ["slm", "claude"]}
    assert figures.title("tdf_by_model", loaded, filters).text in _texts(at)
    assert "conjunto = claude, slm" in _texts(at) or "conjunto = slm, claude" in _texts(at)


def test_metrics_page_one_problem_cut_points_to_the_evaluation(computed):
    at = _page().run()
    at.sidebar.multiselect[3].select("matematica").run()  # macrocategoria: only 1_A
    assert not at.exception, at.exception
    assert "Com um problema só não há métrica" in _texts(at)
    assert not at.get("vega_lite_chart")


def test_guide_priority_only_highlights(computed):
    at = _page().run()
    before = _texts(at)
    guide = next(r for r in at.radio if r.label == "Minha prioridade")
    guide.set_value("gastar pouco").run()
    assert not at.exception, at.exception
    assert _texts(at) == before  # no number nor title changes
    at.sidebar.multiselect[1].select("hybrid").run()  # Cenário: one column in the guide
    assert not at.exception, at.exception
    loaded = tables.read(computed)
    columns = set(figures.figure_data("choice_guide", loaded, {"scenarios": ["hybrid"]})["col"])
    assert columns == {"híbrido"}


def test_iic_oracle_control_does_not_change_the_cut(computed):
    at = _page().run()
    radio = next(r for r in at.radio if r.label == "Gabarito do IIC")
    radio.set_value("da IA (declarado)").run()
    assert not at.exception, at.exception
    assert "gabarito da IA" in _texts(at)
    assert "Sem filtros · 2 problemas" in _texts(at)


def test_scoreboard_by_scenario_has_a_row_per_set_and_scenario(computed):
    loaded = tables.read(computed)
    values = figures.figure_data("scoreboard_scenarios", loaded, {})
    sets = loaded["per_problem"]["set"].nunique()
    scenarios = loaded["per_problem"]["scenario"].nunique()
    assert values["row"].nunique() == sets * scenarios
    assert values["row"].iloc[0] == "SLM · caixa-preta"
    for _, group in values.groupby(["scenario", "criterion"]):
        assert group["first"].any() or group["rank"].isna().all()
