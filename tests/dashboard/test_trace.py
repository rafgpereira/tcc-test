"""Traceability (feature 012, US5): the data of each case and the page.

The evaluated tree of ``conftest.py`` has two problems; the Gemini black-box suite of ``1_A``
declares a wrong output (the AC is rejected and some WAs are caught only by the AI's answer key);
the Claude hybrid suite of ``2_B`` is ``discarded_manual`` (no suite). ``with_metrics`` also writes
the ``results.csv`` of every set, the per-target table the traceability reads.
"""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from dashboard import config, data, trace
from dashboard.views.trace import CASES


@pytest.fixture(autouse=True)
def streamlit_home(tmp_path_factory, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path_factory.mktemp("home")))


@pytest.fixture
def loaded(with_metrics):
    root, base = with_metrics
    tree = data.combinations(base, root)
    return tree, trace.targets(base)


def test_targets_table(loaded):
    _, frame = loaded
    assert set(frame["set"]) == set(config.SETS)
    assert {"declared", "corrected", "declared_test", "corrected_test"} <= set(frame.columns)
    detected = frame[frame["corrected"]]
    assert (detected["corrected_test"] >= 0).all()
    assert (frame.loc[~frame["corrected"], "corrected_test"] == -1).all()


def test_missing_suites_have_a_reason(loaded):
    tree, _ = loaded
    found = trace.missing_suites(tree.table)
    row = found[(found["set"] == "claude") & (found["problem"] == "2_B")]
    assert list(row["scenario"]) == ["hybrid"]
    assert row["motivo"].iloc[0]


def test_ac_rejections_and_oracle_gap(loaded):
    tree, frame = loaded
    rejected = trace.ac_rejections(tree.table)
    assert ((rejected["set"] == "gemini") & (rejected["problem"] == "1_A")).any()
    by_problem = trace.ac_rejections_by_problem(tree.table)
    assert by_problem.iloc[0]["reprovam"] >= 1
    gap = trace.oracle_only(frame)
    gemini = gap[(gap["set"] == "gemini") & (gap["problem"] == "1_A")]
    assert gemini["só pelo gabarito da IA"].iloc[0] > 0
    only_ia, _ = trace.oracle_only_targets(frame, "gemini", "1_A", "black_box")
    assert len(only_ia) == gemini["só pelo gabarito da IA"].iloc[0]


def test_hard_targets_are_consistent(loaded):
    _, frame = loaded
    final = frame[frame["set"].isin(trace.FINAL_SETS)]
    for _, r in trace.undetected(frame, "wa").iterrows():
        mine = final[(final["problem"] == r["problem"]) & (final["target"] == r["target"])]
        assert not mine["corrected"].any()
    for _, r in trace.exclusive(frame, "wa").iterrows():
        mine = final[(final["problem"] == r["problem"]) & (final["target"] == r["target"])]
        assert set(mine.loc[mine["corrected"], "set"]) == {r["só quem detectou"]}
    survivors = trace.undetected(frame, "mutant")
    assert survivors["target"].str.startswith("Mutant").all()


def test_each_target_is_killed_by_its_first_failing_test(loaded):
    tree, frame = loaded
    detail = data.combination_tests(tree.base, "gpt", "1_A", "black_box")
    killed = set()
    for index in detail.tests["index"]:
        killed |= set(
            trace.killed_by_test(frame, "gpt", "1_A", "black_box", int(index))["corrected"]
        )
    mine = frame[
        (frame["set"] == "gpt") & (frame["problem"] == "1_A") & (frame["scenario"] == "black_box")
    ]
    assert killed == set(mine.loc[mine["corrected"], "target"])


def test_problem_and_target_cards(loaded):
    tree, frame = loaded
    grid = trace.problem_grid(tree.table, "1_A")
    assert len(grid) == len(config.SETS) * len(config.SCENARIOS)
    assert list(grid["set"].drop_duplicates()) == list(config.SETS)
    matrix = trace.target_matrix(frame, "1_A", "WA_1")
    assert len(matrix) == len(config.SETS) * len(config.SCENARIOS)
    info = trace.problem_info(Path("."), "1_A")
    assert info["rating"] == 1000 and info["macrocategoria"] == "matematica"
    row = tree.table[tree.table["set"] == "claude"].iloc[0]
    assert trace.attempts(Path("."), row["tree"], row["problem"], row["scenario"]) is not None


# ------------------------------------------------------------------------------------- page


def _page():
    def script():
        from dashboard import app

        app.main(page="trace")

    return AppTest.from_function(script, default_timeout=60)


def test_page_order():
    from dashboard import app

    assert app.NAVIGATION == ("experiment", "metrics", "trace", "evaluation")


def test_every_case_opens(with_metrics, monkeypatch):
    _, base = with_metrics
    monkeypatch.setenv(config.ENV_EVALUATION_DIR, str(base))
    at = _page().run()
    assert not at.exception, at.exception
    for key in CASES:
        at.selectbox[0].set_value(key).run()
        assert not at.exception, (key, at.exception)
    at.selectbox[0].set_value("missing").run()
    shown = "\n".join(str(m.value) for m in at.markdown)
    assert "combinações sem suíte" in shown and "2_B" in shown


def test_cases_follow_the_sidebar(with_metrics, monkeypatch):
    _, base = with_metrics
    monkeypatch.setenv(config.ENV_EVALUATION_DIR, str(base))
    at = _page().run()
    at.selectbox[0].set_value("missing").run()
    at.sidebar.multiselect[0].select("gpt").run()  # IA: gpt has every suite
    assert not at.exception
    assert "**0 combinações sem suíte**" in "\n".join(str(m.value) for m in at.markdown)


def test_without_results_csv_the_target_cases_explain(evaluated, monkeypatch):
    _, base = evaluated
    monkeypatch.setenv(config.ENV_EVALUATION_DIR, str(base))
    at = _page().run()
    at.selectbox[0].set_value("undetected").run()
    assert not at.exception
    assert any("results.csv" in str(i.value) for i in at.info)


# ------------------------------------------------------------------------------------- IIC


def test_iic_sets_give_the_numbers_of_the_metrics(loaded, with_metrics):
    """The terms of the case are the gains, losses and base of ``iic.csv``, for every set,
    answer key and direction: the sets are the same pairs (problem, WA) the metrics count."""
    from metrics import tables as metric_tables

    root, _ = with_metrics
    official = metric_tables.read(root)["iic"]
    _, frame = loaded
    for _, r in official.iterrows():
        was = trace.iic_wa_table(frame, r["set"], r["oracle"])
        terms = trace.iic_terms(was, r["direction"])
        assert (terms["gains"], terms["losses"], terms["base_size"]) == (
            r["gains"],
            r["losses"],
            r["base_size"],
        ), (r["set"], r["oracle"], r["direction"])
        regions = trace.iic_regions(was).set_index("região")["WAs (pares problema, WA)"]
        assert regions.sum() == len(was)


def test_iic_by_problem_adds_up(loaded):
    _, frame = loaded
    was = trace.iic_wa_table(frame, "gemini", "declared")
    by_problem = trace.iic_by_problem(was, "cod")
    terms = trace.iic_terms(was, "cod")
    assert by_problem["ganhos"].sum() == terms["gains"]
    assert by_problem["perdas"].sum() == terms["losses"]
    roles = trace.iic_role(was, "cod")
    assert (roles == "ganho (só o híbrido)").sum() == terms["gains"]


def test_iic_case_ignores_the_scenario_filter(with_metrics, monkeypatch):
    _, base = with_metrics
    monkeypatch.setenv(config.ENV_EVALUATION_DIR, str(base))
    at = _page().run()
    at.selectbox[0].set_value("iic").run()
    at.sidebar.multiselect[1].select("hybrid").run()  # Cenário: only the hybrid
    assert not at.exception, at.exception
    shown = "\n".join(str(m.value) for m in at.caption)
    assert "|R| = " in shown and "|C| = " in shown


def test_iic_term_regions_add_up_to_the_terms(loaded):
    _, frame = loaded
    was = trace.iic_wa_table(frame, "gemini", "corrected")
    regions = trace.iic_regions(was).set_index("região")["WAs (pares problema, WA)"]
    for direction in ("cod", "req"):
        terms = trace.iic_terms(was, direction)
        for key, labels in trace.iic_term_regions(direction).items():
            assert sum(regions[r] for r in labels) == terms[key], (direction, key)
