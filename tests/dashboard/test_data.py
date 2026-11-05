"""The data layer: same numbers as the evaluation report, filters, detail, comparisons (T004–T021)."""

from pathlib import Path

import pandas as pd

from dashboard import data
from evaluation import report


def load(root, base):
    return data.combinations(base, root)


# ------------------------------------------------------------------------------ combinations


def test_combinations_one_row_per_closed_combination(evaluated):
    root, base = evaluated
    tree = load(root, base)
    assert list(tree.table.columns) == list(data.COLUMNS)
    assert len(tree.table) == 5 * 2 * 3
    assert tree.closed == {s: 2 for s in ("claude", "gemini", "gpt", "slm", "slm-attempt1")}
    assert tree.invalid == ()
    assert tree.loaded_at is not None
    row = tree.table.query("set == 'slm' and problem == '1_A' and scenario == 'black_box'")
    assert row["tree"].item() == "suites/slm-rev1"
    assert set(tree.table["macrocategoria"]) == {"matematica", "logica_direta"}


def test_combinations_ignore_building_and_list_invalid_files(evaluated):
    root, base = evaluated
    (base / "gpt/building/9_Z").mkdir(parents=True)
    (base / "gpt/building/9_Z/black_box.json").write_text("{}")
    (base / "gpt/problems/1_A/hybrid.json").write_text('{"broken": true}')
    tree = load(root, base)
    assert len(tree.table) == 5 * 2 * 3 - 1
    assert [name for name, _ in tree.invalid] == ["gpt/problems/1_A/hybrid.json"]


def test_macrocategoria_is_empty_without_the_dataset(evaluated):
    root, base = evaluated
    tree = data.combinations(base, root / "elsewhere")
    assert set(tree.table["macrocategoria"]) == {""}


def test_an_absent_folder_is_an_empty_table(tmp_path):
    tree = data.combinations(tmp_path / "nothing")
    assert tree.table.empty and tree.closed == {}


# ------------------------------------------------------------------------- filters, preview


def test_filters(evaluated):
    root, base = evaluated
    table = load(root, base).table
    assert len(data.apply_filters(table)) == len(table)
    only = data.apply_filters(table, sets=["gpt"], macrocategorias=["matematica"])
    assert set(only["set"]) == {"gpt"} and set(only["problem"]) == {"1_A"}
    assert data.apply_filters(table, statuses=["discarded_manual"])["set"].tolist() == ["claude"]


def test_preview_is_the_ratio_of_sums_without_no_suite_combinations(evaluated):
    root, base = evaluated
    table = load(root, base).table
    by_set = data.preview(table, ["set"]).set_index("set")
    claude = table[(table["set"] == "claude") & table["has_suite"]]
    expected = round(100 * claude["wa_corrected"].sum() / claude["n_wa"].sum(), 1)
    assert by_set.loc["claude", "wa_pct_corrected"] == expected
    assert list(by_set.index) == ["slm", "gpt", "gemini", "claude", "slm-attempt1"]


# -------------------------------------------------------------------------- overview (US1)


def test_overview_matches_the_evaluation_report(evaluated):
    root, base = evaluated
    summary = data.overview(load(root, base).table)
    for set_name in ("slm", "gpt", "gemini", "claude", "slm-attempt1"):
        official = report.build_report(root, base, set_name)
        mine = summary[summary["set"] == set_name].sum(numeric_only=True)
        assert mine["ac_approved"] == official.ac_approved
        assert mine["ac_rejected"] == official.ac_rejected
        assert mine["ac_wrong_output_tests"] == official.ac_tests["wrong_output"]
        assert mine["ac_runtime_error_tests"] == official.ac_tests["runtime_error"]
        for key in ("declared_wa", "corrected_wa", "declared_mutants", "corrected_mutants"):
            kind, oracle = (
                ("wa", key.split("_")[0])
                if key.endswith("wa")
                else (
                    "mutants",
                    key.split("_")[0],
                )
            )
            assert mine[f"{kind}_{oracle}"] == official.detected[key]
        assert mine["without_suite"] == sum(official.without_suite.values())


# --------------------------------------------------------------------------- detail (US2)


def test_combination_tests_show_expected_and_real_outputs(evaluated):
    root, base = evaluated
    detail = data.combination_tests(base, "gemini", "1_A", "black_box", root)
    assert detail.suite_available and not detail.suite_changed
    rows = detail.tests
    assert rows["expected"].tolist() == ["2\n", "7\n"]
    assert rows["actual"].tolist() == ["2\n", "6\n"]
    assert rows["ac_verdict"].tolist() == ["passed", "wrong_output"]
    # every target that behaves like the AC is caught by the wrong declared output of test 1
    assert rows.loc[1, "wa_declared_here"] >= 1
    assert data.only_declared(detail.result) == ["WA_2", "Mutant_1", "Mutant_2"]


def test_detail_reads_the_tree_and_the_attempt_of_the_origin(evaluated):
    root, base = evaluated
    rev1 = data.combination_tests(base, "slm", "1_A", "black_box", root)
    assert rev1.suite_available and rev1.tests["input"].tolist() == ["1\n", "3\n"]
    attempt = data.combination_tests(base, "slm-attempt1", "1_A", "hybrid", root)
    assert attempt.suite_available and not attempt.suite_changed
    assert attempt.tests["expected"].tolist() == ["2\n", "6\n"]


def test_detail_warns_when_the_suite_changed_or_is_missing(evaluated):
    root, base = evaluated
    suite = root / "data/suites/gpt/problems/1_A/black_box/suite.json"
    suite.write_text(suite.read_text() + " ")
    assert data.combination_tests(base, "gpt", "1_A", "black_box", root).suite_changed
    suite.unlink()
    missing = data.combination_tests(base, "gpt", "1_A", "black_box", root)
    assert not missing.suite_available and set(missing.tests["input"]) == {""}


def test_combination_without_a_suite_has_no_rows(evaluated):
    root, base = evaluated
    detail = data.combination_tests(base, "claude", "2_B", "hybrid", root)
    assert detail.tests.empty and detail.result.no_suite_reason == "discarded_manual"


def test_target_detail_with_the_code_side_by_side(evaluated):
    root, base = evaluated
    detail = data.target_detail(base, "gpt", "1_A", "black_box", "Mutant_1", root)
    assert detail.source == "prog:Mutant_1" and detail.ac_source == "prog:AC"
    assert "diff_chg" in detail.diff_html or "diff_sub" in detail.diff_html
    (root / "data/mutants/problems/1_A/Mutant_1.cpp").unlink()
    gone = data.target_detail(base, "gpt", "1_A", "black_box", "Mutant_1", root)
    assert gone.source is None and gone.diff_html is None


# ------------------------------------------------------------------------ comparisons (US3)


def test_oracle_gap_and_local_vs_commercial(evaluated):
    root, base = evaluated
    table = load(root, base).table
    gap = data.oracle_gap(table).set_index(["set", "problem", "scenario"])
    assert gap.loc[("gemini", "1_A", "black_box"), "wa_gap"] > 0
    assert gap.loc[("gpt", "1_A", "black_box"), "wa_gap"] == 0
    wide = data.local_vs_commercial(table)
    assert "slm decl" in wide.columns and "claude corr" in wide.columns
    # the final SLM suites here are their first attempts' tests: same values
    hybrid = wide[(wide["problem"] == "2_B") & (wide["scenario"] == "hybrid")]
    assert hybrid["slm corr"].item() == hybrid["slm-attempt1 corr"].item()


def test_metrics_files_absent_and_present(tmp_path):
    assert data.metrics_files(tmp_path) == []
    (tmp_path / "data/metrics").mkdir(parents=True)
    (tmp_path / "data/metrics/tdf.csv").write_text("x")
    assert data.metrics_files(tmp_path) == ["tdf.csv"]


def test_no_function_writes(evaluated):
    root, base = evaluated
    before = {p: p.stat().st_mtime_ns for p in Path(root).rglob("*") if p.is_file()}
    tree = load(root, base)
    data.overview(tree.table)
    data.combination_tests(base, "gemini", "1_A", "black_box", root)
    data.target_detail(base, "gpt", "1_A", "black_box", "WA_1", root)
    data.oracle_gap(tree.table)
    data.local_vs_commercial(tree.table)
    after = {p: p.stat().st_mtime_ns for p in Path(root).rglob("*") if p.is_file()}
    assert before == after
    assert isinstance(tree.table, pd.DataFrame)
