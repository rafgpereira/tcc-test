"""``manifests/slm_generation_report.json``: the numbers of the run, from the files only."""

import json

import pytest
from pydantic import ValidationError

from ai_clients import __main__ as cli
from ai_clients import closing, config, execution, report, store
from ai_clients.schemas.report import SlmGenerationReport
from sandbox.types import RunStatus
from tests.ai_clients.fakes import (
    ECHO_PY,
    FakePythonRunner,
    echo_runner,
    record_generation,
    run_result,
    start_run,
)

WRONG_PY = "print(0)\n"


def runner():
    """Echo; the wrong solution prints 0; the input 9 times out."""

    def answer(code, stdin):
        if code == WRONG_PY:
            return run_result(b"0\n")
        if stdin == b"9\n":
            return run_result(status=RunStatus.TIMEOUT, cpu_time_s=11.0)
        return run_result(stdin)

    return FakePythonRunner(default=answer)


def run_execute(repo, run):
    combos = [(pid, s) for pid in ("1_A", "2_B") for s in config.SCENARIOS]
    execution.execute(repo, combos, run=run, runner=runner(), echo=lambda line: None)


@pytest.fixture()
def tree(repo, monkeypatch):
    """A run in the middle: 2 accepted, 1 awaiting manual handling, 1 pending execution, 2 pending
    generation.

    1_A black_box  accepted at attempt 1 (inputs 5, 6, 5: one duplicate)
    1_A white_box  accepted at attempt 2 (attempt 1 failed a public test; input 9 timed out)
    1_A hybrid     awaiting manual handling (23 unparseable answers, the 3rd and 4th on another
                   machine)
    2_B black_box  pending execution
    2_B white_box  pending generation 2 (attempt 1 unparseable)
    2_B hybrid     pending generation 1
    """
    monkeypatch.chdir(repo)
    run = start_run(repo)
    record_generation(repo, "1_A", "black_box", inputs=["5\n", "6\n", "5\n"])
    record_generation(repo, "1_A", "white_box", code=WRONG_PY)
    run_execute(repo, run)
    record_generation(repo, "1_A", "white_box", 2, inputs=["7\n", "9\n"])
    for n in range(1, config.MAX_ATTEMPTS + 1):
        label = "CPU only" if n in (3, 4) else "RTX 3060 12GB"
        record_generation(repo, "1_A", "hybrid", n, parsed=False, hardware_label=label)
    run_execute(repo, run)
    record_generation(repo, "2_B", "black_box")
    record_generation(repo, "2_B", "white_box", parsed=False)
    return run


@pytest.fixture()
def built(tree, repo):
    return report.build_report(repo)


def counts(**nonzero):
    states = (
        "accepted",
        "accepted_fallback",
        "accepted_low_confidence",
        "accepted_predicted",
        "discarded_manual",
        "awaiting_manual",
        "pending_generation",
        "pending_execution",
    )
    return {"total": sum(nonzero.values())} | {state: nonzero.get(state, 0) for state in states}


def test_the_combinations_add_up_per_scenario_and_in_total(built):
    assert built.combinations["total"].model_dump() == counts(
        accepted=2, awaiting_manual=1, pending_generation=2, pending_execution=1
    )
    assert built.combinations["black_box"].model_dump() == counts(accepted=1, pending_execution=1)
    assert built.combinations["hybrid"].model_dump() == counts(
        awaiting_manual=1, pending_generation=1
    )


def test_the_share_of_each_status_is_over_every_combination_never_a_reduced_n(built):
    assert built.status_rate["accepted"] == {
        "total": 2 / 6,
        "black_box": 0.5,
        "white_box": 0.5,
        "hybrid": 0.0,
    }
    for status in ("accepted_fallback", "accepted_low_confidence", "accepted_predicted"):
        assert set(built.status_rate[status].values()) == {0.0}
    assert set(built.status_rate["discarded_manual"].values()) == {0.0}


def test_a_combination_closed_by_hand_is_counted_apart(tree, repo):
    closing.close(repo, "1_A", "hybrid", "never parsed", run=tree, now=lambda: "2026-10-07")
    built = report.build_report(repo)
    assert built.combinations["hybrid"].model_dump() == counts(
        discarded_manual=1, pending_generation=1
    )
    assert built.status_rate["discarded_manual"]["hybrid"] == 0.5
    assert "discarded_manual" not in built.suite_size  # it has no tests


def test_the_suite_size_is_per_status(built):
    total = built.suite_size["accepted"]["total"]
    assert (total.count, total.min, total.max) == (2, 1, 3)
    assert (total.p25, total.median, total.p75) == (1.5, 2.0, 2.5)
    assert total.histogram == {"1": 1, "3": 1}
    hybrid = built.suite_size["accepted"]["hybrid"]
    assert hybrid.count == 0 and hybrid.min is None
    assert built.suite_size["accepted_predicted"]["total"].count == 0


def test_the_attempt_funnel_by_reason_and_attempt_number(built):
    failures = built.attempt_failures
    assert failures["unparseable_response"] == {"1": 2} | {str(n): 1 for n in range(2, 24)}
    assert failures["public_test_failed"]["1"] == 1
    assert sum(failures["all_inputs_failed"].values()) == 0
    assert built.attempts.model_dump() == {"total": 28, "failed": 25}


def test_inputs_duplicates_tokens_and_reasons(built):
    assert built.input_discards == {"timeout": 1, "runtime_error": 0, "non_utf8_output": 0}
    assert built.duplicate_inputs == 0  # the fake generations declare no duplicate
    zero = {"total": 0, "black_box": 0, "white_box": 0, "hybrid": 0}
    assert built.done_reason_length == built.markdown_fences_removed == built.empty_inputs == zero
    assert built.empty_tests == zero
    assert built.tokens.model_dump() == {
        "prompt_total": 28 * 1000,
        "eval_total": 28 * 500,
        "prompt_max": 1000,
    }
    assert built.duration_s_total == pytest.approx(28 * 1e-9)


def test_hardware_and_seeds(built):
    assert built.hardware == {"CPU only": 2, "RTX 3060 12GB": 26}
    assert built.seeds["1_A/hybrid"] == list(range(43, 66))
    assert built.seeds["1_A/white_box"] == [43, 44]
    assert "2_B/hybrid" not in built.seeds


def test_the_provenance_comes_from_run_json(built, tree):
    assert (built.model, built.model_digest, built.ollama_version) == (
        tree.model,
        tree.model_digest,
        tree.ollama_version,
    )
    assert built.options == tree.options and built.seed_base == 42
    assert built.prompt_template_sha256 == tree.prompt_template_sha256
    assert built.predict_template_sha256 == tree.predict_template_sha256
    assert built.dataset_manifest_sha256 == tree.dataset_manifest_sha256


def test_the_same_tree_gives_the_same_bytes(tree, repo, capsys):
    assert cli.main(["report"]) == cli.EXIT_OK
    path = repo / config.REPORT_PATH
    first = path.read_bytes()
    assert cli.main(["report"]) == cli.EXIT_OK
    assert path.read_bytes() == first
    assert json.loads(first)["schema_version"] == 1
    assert f"report: {config.REPORT_PATH.as_posix()}" in capsys.readouterr().out


def test_a_damaged_combination_stops_the_report_with_1(tree, repo, capsys):
    path = store.combination_dir(repo, "1_A", "black_box") / "attempt_1.generation.json"
    path.write_text("{", encoding="utf-8")
    assert cli.main(["report"]) == cli.EXIT_DATA_FAILURE
    assert "damaged: 1_A black_box" in capsys.readouterr().err
    assert not (repo / config.REPORT_PATH).exists()


def test_without_a_run_it_asks_for_generate_first(repo, monkeypatch, capsys):
    monkeypatch.chdir(repo)
    assert cli.main(["report"]) == cli.EXIT_USAGE
    assert "run generate first" in capsys.readouterr().err


def test_the_control_sums_are_validated(built):
    data = built.model_dump(mode="json")
    data["combinations"]["total"]["accepted"] += 1
    with pytest.raises(ValidationError, match="add up"):
        SlmGenerationReport.model_validate(data)
    data = built.model_dump(mode="json")
    data["attempt_failures"]["unparseable_response"]["1"] += 1
    with pytest.raises(ValidationError, match="failed attempts"):
        SlmGenerationReport.model_validate(data)


def test_a_fallback_suite_is_counted_apart_with_its_own_sizes(tree, repo):
    for n in range(1, config.STRICT_ATTEMPTS + 1):  # 2_B hybrid: 8 times a WA
        record_generation(repo, "2_B", "hybrid", n, code=WRONG_PY, inputs=["4\n"])
        run_execute(repo, tree)
    assert store.read_suite(repo, "2_B", "hybrid").status == "accepted_fallback"
    built = report.build_report(repo)
    counts = built.combinations
    # 2_B black_box, pending execution in the tree, was accepted on the way
    assert (counts["total"].accepted, counts["total"].accepted_fallback) == (3, 1)
    assert (counts["hybrid"].accepted_fallback, counts["hybrid"].pending_generation) == (1, 0)
    assert built.status_rate["accepted_fallback"] == {
        "total": 1 / 6,
        "black_box": 0.0,
        "white_box": 0.0,
        "hybrid": 0.5,
    }
    assert built.suite_size["accepted"]["total"].count == 3
    assert built.suite_size["accepted_fallback"]["total"].count == 1
    assert built.attempt_failures["public_test_failed"]["8"] == 1


def test_a_full_scope_always_counts_every_problem_and_scenario(repo, monkeypatch):
    monkeypatch.chdir(repo)
    start_run(repo)
    built = report.build_report(repo)
    assert built.combinations["total"].total == 6
    assert built.combinations["total"].pending_generation == 6
    assert built.status_rate["accepted"]["total"] == 0.0


def test_an_accepted_suite_counts_its_duplicates(repo, monkeypatch):
    monkeypatch.chdir(repo)
    run = start_run(repo)
    from ai_clients.schemas.generation import GenerationRecord
    from tests.ai_clients.test_schemas import generation, parsed

    record = GenerationRecord(
        **generation(
            model_digest=run.model_digest,
            parse=parsed(inputs=["5\n", "5\n"], reference_py=ECHO_PY, duplicate_inputs=1),
        )
    )
    store.write_generation(repo, record)
    execution.execute(
        repo, [("1_A", "black_box")], run=run, runner=echo_runner(), echo=lambda line: None
    )
    assert report.build_report(repo).duplicate_inputs == 1


def test_cut_answers_fences_empty_inputs_and_repetitions_per_scenario(repo, monkeypatch):
    monkeypatch.chdir(repo)
    run = start_run(repo)
    from ai_clients.schemas.generation import GenerationRecord
    from tests.ai_clients.test_schemas import generation, ollama_meta, parsed

    def write(scenario, attempt, **fields):
        record = generation(
            scenario=scenario, attempt=attempt, seed=42 + attempt, model_digest=run.model_digest
        )
        store.write_generation(repo, GenerationRecord(**(record | fields)))

    cut = ollama_meta() | {"done_reason": "length"}
    write("black_box", 1, ollama=cut, parse={"ok": False, "error": "unclosed_block:inputs"})
    write("black_box", 2, parse=parsed(markdown_fence_removed=True, empty_inputs=2))
    write("hybrid", 1, ollama=cut, parse={"ok": False, "error": "unclosed_block:inputs"})
    write(
        "hybrid",
        2,
        raw_response="",
        ollama=None,
        parse={"ok": False, "error": "repetition"},
        model_failure={"reason": "repetition", "detail": "token repeat limit reached"},
    )
    write("hybrid", 3, parse=parsed(markdown_fence_removed=True))
    built = report.build_report(repo)
    assert built.done_reason_length == {"total": 2, "black_box": 1, "white_box": 0, "hybrid": 1}
    assert built.markdown_fences_removed == {
        "total": 2,
        "black_box": 1,
        "white_box": 0,
        "hybrid": 1,
    }
    assert built.empty_inputs == {"total": 2, "black_box": 2, "white_box": 0, "hybrid": 0}
    assert built.attempt_failures["repetition"]["2"] == 1
    assert built.attempt_failures["unparseable_response"]["1"] == 2
    assert built.attempts.model_dump() == {"total": 5, "failed": 3}
    assert built.tokens.prompt_total == 4 * 1000  # the failed call answered nothing


def test_a_predicted_suite_and_its_dropped_tests_are_counted_apart(repo, monkeypatch):
    monkeypatch.chdir(repo)
    run = start_run(repo)
    from ai_clients.schemas.generation import GenerationRecord
    from tests.ai_clients.test_schemas import generation, prediction

    for n in range(1, config.SOLUTION_ATTEMPTS + 1):
        record_generation(repo, "1_A", "white_box", n, parsed=False)
    tests = [{"input": "3\n", "output": "3\n"}, {"input": "4\n", "output": "4\n"}]
    record = generation(
        scenario="white_box",
        attempt=21,
        seed=63,
        model_digest=run.model_digest,
        parse=prediction(tests=tests, empty_tests=1),
    )
    store.write_generation(repo, GenerationRecord(**record))
    built = report.build_report(repo)
    assert built.combinations["white_box"].accepted_predicted == 1
    assert built.suite_size["accepted_predicted"]["white_box"].histogram == {"2": 1}
    assert built.empty_tests == {"total": 1, "black_box": 0, "white_box": 1, "hybrid": 0}
    assert built.attempts.model_dump() == {"total": 21, "failed": 20}
