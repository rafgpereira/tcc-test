"""The dashboard's metrics page: official tables and interactive charts with filters (T023, T027)."""

import pytest
from streamlit.testing.v1 import AppTest

import metrics.__main__ as cli
from dashboard import config as dashboard_config
from dashboard import glossary
from metrics import charts, figures, primary, tables


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

    return AppTest.from_function(script, default_timeout=60)


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
    for name in figures.FIGURES:
        data = figures.figure_data(name, loaded, {})
        title, y_title = figures.TITLES[name]
        spec = charts.chart(
            data, title, y_title, "filtros: nenhum", figures.KIND.get(name, "grouped")
        )
        assert spec.to_dict()["title"]["subtitle"] == ["filtros: nenhum"]
        as_dict = spec.to_dict()
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
    import pytest as _pytest

    from metrics import cuts

    loaded = tables.read(computed)
    two = figures.figure_data("tdf_by_model", loaded, {"problems": ["1_A", "2_B"]})
    assert not two.empty
    with _pytest.raises(cuts.CutError):
        figures.figure_data("tdf_by_model", loaded, {"problems": ["1_A"]})
    with _pytest.raises(cuts.CutError):
        figures.figure_data("cost_per_detection", loaded, {"problems": ["1_A", "2_B"]})


def test_the_download_is_the_chart_on_screen(computed):
    """The file saved from the dashboard is the chart shown, in the theme shown."""
    import vl_convert

    loaded = tables.read(computed)
    filters = {"sets": ["gpt", "claude"]}
    for mode in ("light", "dark"):
        shown = figures.chart("ms_declared_vs_corrected", loaded, filters, "fonte-x", mode)
        _, png = figures.render("ms_declared_vs_corrected", loaded, filters, "png", "fonte-x", mode)
        assert png == vl_convert.vegalite_to_png(shown.to_dict(), scale=figures.PNG_SCALE)


def test_metrics_page_draws_the_six_charts_with_the_filter_in_the_subtitle(computed):
    at = _page().run()
    assert not at.exception, at.exception
    charts_shown = at.get("vega_lite_chart")
    assert len(charts_shown) == len(figures.FIGURES)
    assert len(at.dataframe) == 5  # killed targets, metrics, IIC, statistics, cost
    killed = at.dataframe[0].value
    assert list(killed.columns[:3]) == ["set", "scenario", "WA_killed"]
    assert not [m for m in at.main.multiselect]  # filters only in the sidebar
    at.sidebar.multiselect[0].select("gpt").select("claude").run()  # "Conjunto"
    assert not at.exception
    spec = at.get("vega_lite_chart")[0].proto.spec
    assert "set = claude, gpt" in spec
    assert '"text"' in spec  # the values are written on the bars


def test_metrics_page_cut_selector(computed):
    at = _page().run()
    labels = at.selectbox[0].options
    assert labels[0] == "all"
    at.selectbox[0].select(labels[-1]).run()
    assert not at.exception
