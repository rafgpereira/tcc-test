"""A combination whose files are not what the commands write is damage: reported, never repaired."""

import json

import pytest

from ai_clients import __main__ as cli
from ai_clients import config, execution, store
from tests.ai_clients.fakes import (
    FakeClock,
    FakeSLMClient,
    completion,
    echo_runner,
    record_generation,
    start_run,
    well_formed_response,
)


@pytest.fixture()
def setup(monkeypatch, repo):
    """A run with 1_A black_box executed and accepted, and 2_B black_box pending execution."""
    monkeypatch.chdir(repo)
    monkeypatch.setattr(cli, "make_runner", echo_runner)
    monkeypatch.setattr(cli, "cleanup_slot", lambda slot: None)
    run = start_run(repo)
    record_generation(repo, "1_A", "black_box")
    execution.execute(repo, [("1_A", "black_box")], run=run, runner=echo_runner(), echo=print)
    record_generation(repo, "2_B", "black_box")
    return run


def folder(repo, pid="1_A", scenario="black_box"):
    return store.combination_dir(repo, pid, scenario)


def edit_json(path, **changes):
    data = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(json.dumps(data | changes), encoding="utf-8")


def gap(repo):
    record_generation(repo, "1_A", "white_box", parsed=False)
    record_generation(repo, "1_A", "white_box", 2, parsed=False)
    (folder(repo, scenario="white_box") / "attempt_1.generation.json").unlink()
    return "white_box", "missing: attempt_1.generation.json"


def execution_without_generation(repo):
    (folder(repo) / "attempt_1.generation.json").unlink()
    return "black_box", "missing: attempt_1.generation.json"


def wrong_seed(repo):
    edit_json(folder(repo) / "attempt_1.generation.json", seed=99)
    return "black_box", "inconsistent: attempt_1.generation.json"


def another_digest(repo):
    edit_json(folder(repo) / "attempt_1.generation.json", model_digest="sha256:" + "e" * 64)
    return "black_box", "inconsistent: attempt_1.generation.json: model_digest"


def edited_suite(repo):
    path = folder(repo) / config.SUITE_FILE
    data = json.loads(path.read_text(encoding="utf-8"))
    data["tests"][0]["output"] = "42\n"
    path.write_text(json.dumps(data), encoding="utf-8")
    return "black_box", "changed: suite.json"


def invalid_json(repo):
    (folder(repo) / "attempt_1.execution.json").write_text("{", encoding="utf-8")
    return "black_box", "inconsistent: attempt_1.execution.json"


def execution_of_an_unparsed_attempt(repo):
    record_generation(repo, "1_A", "hybrid", parsed=False)
    source = folder(repo) / "attempt_1.execution.json"
    target = folder(repo, scenario="hybrid") / "attempt_1.execution.json"
    data = json.loads(source.read_text(encoding="utf-8")) | {"scenario": "hybrid"}
    target.write_text(json.dumps(data), encoding="utf-8")
    return "hybrid", "inconsistent: attempt_1.execution.json"


def a_7th_attempt(repo):
    path = folder(repo) / "attempt_7.generation.json"
    path.write_text("{}", encoding="utf-8")
    return "black_box", "inconsistent: attempt_7.generation.json"


DAMAGES = [
    gap,
    execution_without_generation,
    wrong_seed,
    another_digest,
    edited_suite,
    invalid_json,
    execution_of_an_unparsed_attempt,
    a_7th_attempt,
]


def snapshot(repo):
    base = repo / config.PROBLEMS_DIR / "1_A"
    return {p: p.read_bytes() for p in base.rglob("*") if p.is_file()}


@pytest.mark.parametrize("damage", DAMAGES, ids=lambda d: d.__name__)
def test_execute_reports_the_damage_repairs_nothing_and_goes_on(setup, repo, capsys, damage):
    scenario, reason = damage(repo)
    before = snapshot(repo)
    capsys.readouterr()
    assert cli.main(["execute"]) == cli.EXIT_DATA_FAILURE
    captured = capsys.readouterr()
    damaged = [line for line in captured.err.splitlines() if line.startswith("damaged: ")]
    assert len(damaged) == 1 and damaged[0].startswith(f"damaged: 1_A {scenario}: ")
    assert reason in damaged[0]
    assert snapshot(repo) == before  # nothing repaired
    # the other combinations went on
    assert "2_B black_box attempt 1: accepted" in captured.out
    assert store.read_suite(repo, "2_B", "black_box") is not None


def test_generate_reports_the_damage_too(setup, repo, monkeypatch, capsys):
    monkeypatch.setenv(config.ENV_BASE_URL, "http://ollama.test:11434")
    monkeypatch.setenv(config.ENV_HARDWARE_LABEL, "RTX 3060 12GB")
    good = completion(well_formed_response(["1\n"]))
    table = {("1_A", "white_box", 1): good, ("2_B", "white_box", 1): good}
    client = FakeSLMClient(table, problem_ids=["1_A", "2_B"])
    monkeypatch.setattr(cli, "make_client", lambda base_url, *, timeout_s: client)
    monkeypatch.setattr(cli, "make_clock", FakeClock)
    _, reason = wrong_seed(repo)
    capsys.readouterr()
    assert (
        cli.main(
            [
                "generate",
                "--resume",
                "--problem",
                "2_B",
                "--problem",
                "1_A",
                "--scenario",
                "black_box",
                "--scenario",
                "white_box",
            ]
        )
        == cli.EXIT_DATA_FAILURE
    )
    err = capsys.readouterr().err
    assert f"damaged: 1_A black_box: {reason}" in err
    assert [r["key"] for r in client.requests] == [
        ("1_A", "white_box", 1),
        ("2_B", "white_box", 1),
    ]


def test_a_damaged_combination_has_its_state_refused(setup, repo):
    wrong_seed(repo)
    with pytest.raises(store.DamagedCombination) as caught:
        store.combination_state(repo, "1_A", "black_box", run=setup)
    assert caught.value.problems[0].startswith("inconsistent: attempt_1.generation.json")


def test_a_leftover_temporary_file_is_not_damage(setup, repo):
    (folder(repo) / ".attempt_2.generation.json.abc123.tmp").write_text("{", encoding="utf-8")
    assert store.combination_state(repo, "1_A", "black_box", run=setup).kind == "terminal"


# ------------------------------------------------------- damage of the rules of 2026-10-06


def test_an_execution_of_a_prediction_attempt_is_damage(setup, repo):
    for n in range(1, config.SOLUTION_ATTEMPTS + 2):
        record_generation(repo, "1_A", "hybrid", n, parsed=False)
    (folder(repo, scenario="hybrid") / "attempt_13.execution.json").write_text("{}")
    with pytest.raises(store.DamagedCombination, match="a prediction attempt is never executed"):
        store.combination_state(repo, "1_A", "hybrid", setup)


def test_a_prediction_after_a_possible_fallback_is_damage(setup, repo):
    """A WA among the 12 is the fallback: a 13th attempt (a prediction) should not exist."""

    def runner(code, stdin, limits, slot):
        from tests.ai_clients.fakes import run_result

        return run_result(b"0\n" if code == "print(0)\n" else stdin)  # print(0): WA, inputs kept

    record_generation(repo, "1_A", "hybrid", 1, code="print(0)\n", inputs=["5\n"])
    execution.execute(repo, [("1_A", "hybrid")], run=setup, runner=runner, echo=print)
    for n in range(2, config.SOLUTION_ATTEMPTS + 2):  # 2..12, then a 13th it should not have
        record_generation(repo, "1_A", "hybrid", n, parsed=False)
    with pytest.raises(store.DamagedCombination, match="could already be the fallback"):
        store.combination_state(repo, "1_A", "hybrid", setup)


@pytest.mark.parametrize(
    "field_name, value",
    [("seed", 43), ("temperature", 0.6), ("phase", 2), ("template", "prediction")],
)
def test_an_attempt_that_is_not_its_row_of_the_policy_is_damage(setup, repo, field_name, value):
    path = folder(repo) / "attempt_1.generation.json"
    if field_name == "template":
        edit_json(path, template=value, parse={"ok": False, "error": "x"})
    else:
        edit_json(path, **{field_name: value})
    with pytest.raises(store.DamagedCombination, match="but attempt 1 is"):
        store.combination_state(repo, "1_A", "black_box", setup)
