"""The dashboard's metrics page shows the official tables and the same figures (T023, T027)."""

import json

import pytest
from streamlit.testing.v1 import AppTest

import metrics.__main__ as cli
from dashboard import config as dashboard_config
from dashboard import glossary
from metrics import figures, tables


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


def test_metrics_page_shows_tables_and_the_same_figure_bytes(computed):
    at = _page().run()
    assert not at.exception, at.exception
    assert len(at.dataframe) == 4
    loaded = tables.read(computed)
    run = json.loads((computed / "data/metrics/run.json").read_text())
    _, png = figures.render("tdf_by_model", loaded, {}, "png", figures.source_label(run))
    assert at.get("download_button")  # PNG and PDF offered
    assert at.image[0].proto.imgs[0].url  # the figure is shown
    expected_name, _ = figures.render("tdf_by_model", loaded, {}, "pdf", figures.source_label(run))
    assert expected_name == "tdf_by_model.pdf"
    assert png[:8] == b"\x89PNG\r\n\x1a\n"


def test_metrics_page_cut_selector(computed):
    at = _page().run()
    labels = at.selectbox[0].options
    assert labels[0] == "all"
    at.selectbox[0].select(labels[-1]).run()
    assert not at.exception
