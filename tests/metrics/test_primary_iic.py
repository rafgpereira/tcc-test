"""Known cases of every primary and complementary metric and of the IIC (T009–T014)."""

import math

import pandas as pd

from metrics import iic, primary
from tests.metrics.conftest import per_problem_rows, row


def one(table, set_name="gpt", scenario="black_box"):
    return table[(table["set"] == set_name) & (table["scenario"] == scenario)].iloc[0]


def test_ms_with_no_mutant_killed_is_zero():
    t = primary.table(per_problem_rows([row(problem="1_A"), row(problem="2_B")]))
    assert one(t)["MS"] == 0.0  # "MS com DM=0 e M=100 deve retornar 0.0"


def test_tdf_ms_tfp_tc_and_no_suite():
    rows = [
        row(problem="1_A", wa_declared=10, mutants_declared=20),
        row(problem="2_B", wa_declared=50, mutants_declared=40, ac_rejected=True),
        row(problem="3_C", wa_declared=90, mutants_declared=90),
        row(problem="4_D", has_suite=False, suite_size=0, status="discarded_manual"),
    ]
    r = one(primary.table(per_problem_rows(rows)))
    assert r["problems"] == 4
    assert r["TDF"] == (10 + 50 + 90 + 0) / 4  # the combination without a suite counts 0%
    assert r["MS"] == (20 + 40 + 90 + 0) / 4
    assert r["TFP"] == 25.0  # 1 of 4 problems (N = problems)
    assert round(r["TFP_with_suite"], 4) == round(100 / 3, 4)
    assert r["without_suite"] == 1
    assert r["TC"] == 75.0


def test_corrected_oracle_delta_and_causes():
    rows = [
        row(
            problem="1_A",
            wa_declared=60,
            wa_corrected=40,
            mutants_declared=50,
            mutants_corrected=50,
            ac_rejected=True,
            ac_wrong_output_tests=2,
            suite_size=10,
        ),
        row(
            problem="2_B",
            wa_declared=40,
            wa_corrected=40,
            ac_runtime_error_tests=1,
            suite_size=10,
            ac_rejected=True,
        ),
    ]
    r = one(primary.table(per_problem_rows(rows)))
    assert (r["TDF"], r["TDF_star"], r["delta_TDF"]) == (50.0, 40.0, 10.0)
    assert r["delta_MS"] == 0.0
    assert (r["FP_tests_oracle"], r["FP_tests_invalid_input"], r["total_tests"]) == (2, 1, 20)
    assert r["TFP_test"] == 15.0
    assert r["mean_suite_size"] == 10.0 and r["density_TDF"] == 5.0


def test_without_ac_rejection_tdf_equals_tdf_star():
    rows = [row(problem=p, wa_declared=30, wa_corrected=30) for p in ("1_A", "2_B")]
    r = one(primary.table(per_problem_rows(rows)))
    assert r["TDF"] == r["TDF_star"] and r["delta_TDF"] == 0


def detected(rows):
    return pd.DataFrame(rows, columns=["set", "scenario", "problem", "target", "oracle"])


def test_iic_pooled_per_problem_and_exclusions():
    d = []
    # problem 1_A: black box {WA_1, WA_2}, hybrid {WA_2, WA_3, WA_4} -> gains 2, losses 1, base 2
    for t in ("WA_1", "WA_2"):
        d.append(("gpt", "black_box", "1_A", t, "declared"))
    for t in ("WA_2", "WA_3", "WA_4"):
        d.append(("gpt", "hybrid", "1_A", t, "declared"))
    # problem 2_B: black box empty (excluded from the per-problem view), hybrid {WA_1}
    d.append(("gpt", "hybrid", "2_B", "WA_1", "declared"))
    per = pd.DataFrame({"set": ["gpt", "gpt"], "problem": ["1_A", "2_B"]})
    t = iic.table(detected(d), per)
    cod = t[(t["oracle"] == "declared") & (t["direction"] == "cod")].iloc[0]
    # pooled: hybrid {1A:2,3,4, 2B:1}, base {1A:1,2} -> gains 3, losses 1, base 2 -> 100%
    assert (cod["gains"], cod["losses"], cod["base_size"], cod["iic_pooled"]) == (3, 1, 2, 100.0)
    assert cod["excluded"] == 1 and cod["positive"] == 1
    assert cod["per_problem_median"] == 50.0  # problem 1_A alone: (2 - 1) / 2
    req = t[(t["oracle"] == "declared") & (t["direction"] == "req")].iloc[0]
    assert math.isnan(req["iic_pooled"]) and req["excluded"] == 2  # no white box at all


def test_iic_can_exceed_100_percent():
    d = [("gpt", "black_box", "1_A", "WA_1", "declared")] + [
        ("gpt", "hybrid", "1_A", f"WA_{i}", "declared") for i in range(1, 5)
    ]
    per = pd.DataFrame({"set": ["gpt", "gpt"], "problem": ["1_A", "2_B"]})
    cod = iic.table(detected(d), per).iloc[0]
    assert cod["iic_pooled"] == 300.0
