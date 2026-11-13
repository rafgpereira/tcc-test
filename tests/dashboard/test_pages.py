"""Each page runs without error on an evaluated tree and on an empty one; nothing is written."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from dashboard import config


def _page(name):
    def script(page_name: str) -> None:
        from dashboard import app

        app.main(page=page_name)

    return AppTest.from_function(script, args=(name,), default_timeout=30)


@pytest.fixture(autouse=True)
def streamlit_home(tmp_path_factory, monkeypatch):
    # Streamlit keeps settings in ~/.streamlit; keep it away from the tree under test.
    monkeypatch.setenv("HOME", str(tmp_path_factory.mktemp("home")))


@pytest.fixture
def opened(evaluated, monkeypatch):
    root, base = evaluated
    monkeypatch.setenv(config.ENV_EVALUATION_DIR, str(base))
    return root, base


def text_of(at) -> str:
    parts = [e.value for e in at.markdown] + [e.value for e in at.caption]
    parts += [e.value for e in at.info] + [e.value for e in at.warning]
    return "\n".join(str(p) for p in parts)


@pytest.mark.parametrize(
    "page", ["experiment", "metrics", "trace", "evaluation", "overview", "combination", "compare"]
)
def test_every_page_runs_on_an_evaluated_tree(opened, page):
    at = _page(page).run()
    assert not at.exception, at.exception


@pytest.mark.parametrize(
    "page", ["experiment", "metrics", "trace", "evaluation", "overview", "combination", "compare"]
)
def test_every_page_runs_on_an_empty_folder(tmp_path, monkeypatch, page):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(config.ENV_EVALUATION_DIR, str(tmp_path / "data/evaluation"))
    at = _page(page).run()
    assert not at.exception, at.exception
    assert "Nenhum resultado concluído" in text_of(at)


def test_overview_labels_the_preview_and_filters_by_macrocategoria(opened):
    at = _page("overview").run()
    assert config.PREVIEW_LABEL in text_of(at)
    rows_before = len(at.dataframe[1].value)
    at.sidebar.multiselect[3].select("matematica").run()  # macrocategoria
    assert not at.exception
    assert len(at.dataframe[1].value) < rows_before


def test_combination_page_opens_a_target(opened):
    at = _page("combination").run()
    at.selectbox[0].select("gemini").run()
    assert not at.exception
    assert any("Pegos só pelo oráculo declarado" in s.value for s in at.subheader)
    assert any("declarado" in m.value for m in at.markdown)


def test_combination_page_without_a_suite(opened):
    at = _page("combination").run()
    at.selectbox[0].select("claude").run()
    at.selectbox[1].select("2_B").run()
    at.selectbox[2].select("hybrid").run()
    assert not at.exception
    assert "Sem suíte" in text_of(at)


def test_metrics_page_is_a_notice(opened):
    at = _page("metrics").run()
    assert "ainda não calculadas" in text_of(at)


def test_nothing_is_written(opened):
    root, _ = opened
    before = {p: p.stat().st_mtime_ns for p in Path(root).rglob("*") if p.is_file()}
    for page in (
        "experiment",
        "metrics",
        "trace",
        "evaluation",
        "overview",
        "combination",
        "compare",
    ):
        assert not _page(page).run().exception
    after = {p: p.stat().st_mtime_ns for p in Path(root).rglob("*") if p.is_file()}
    assert before == after


# ------------------------------------------------------------ O experimento (feature 012, T021)


def test_the_experiment_is_the_first_page():
    from dashboard import app

    assert app.NAVIGATION[0] == "experiment"


@pytest.fixture
def opened_with_metrics(with_metrics, monkeypatch):
    root, base = with_metrics
    monkeypatch.setenv(config.ENV_EVALUATION_DIR, str(base))
    return root, base


def test_experiment_page_numbers_and_cut(opened_with_metrics):
    at = _page("experiment").run()
    assert not at.exception, at.exception
    headline = " ".join(str(m.value) for m in at.markdown)
    assert "2 problemas, 400 falhas, 4 IAs, 23 suítes" in headline
    assert "Sem filtros · 2 problemas" in text_of(at)
    assert any(m.label == "Gasto" and m.value.startswith("US$") for m in at.metric)
    at.sidebar.multiselect[3].select("matematica").run()  # macrocategoria
    assert not at.exception
    assert "macrocategoria = matematica · 1 problema" in text_of(at)
    assert "1 problema, 200 falhas" in " ".join(str(m.value) for m in at.markdown)


def test_experiment_page_empty_cut(opened_with_metrics):
    at = _page("experiment").run()
    at.sidebar.multiselect[3].select("logica_direta").run()
    at.sidebar.multiselect[4].select(1000).run()  # rating: 2_B is 1600, so nothing is left
    assert not at.exception
    assert "Nenhum problema atende" in " ".join(str(m.value) for m in at.markdown)


def test_experiment_page_without_metrics(opened):
    at = _page("experiment").run()
    assert not at.exception
    assert "métricas ainda não foram calculadas" in text_of(at)
