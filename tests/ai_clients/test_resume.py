"""Interrupting ``generate`` or ``execute`` anywhere and running again gives the same final tree."""

import json

import pytest

from ai_clients import __main__ as cli
from ai_clients import config, store
from tests.ai_clients.conftest import build_dataset, problem
from tests.ai_clients.fakes import (
    ECHO_PY,
    FakeClock,
    FakePythonRunner,
    FakeSLMClient,
    completion,
    predicted_response,
    run_result,
    well_formed_response,
)

PROBLEMS = ("1_A", "2_B")
COMBOS = [(pid, s) for pid in PROBLEMS for s in config.SCENARIOS]
WRONG_PY = "print(0)\n"
GOOD = completion(well_formed_response(["5\n", "6\n"], code=ECHO_PY))
WRONG = completion(well_formed_response(["5\n"], code=WRONG_PY))
BAD = completion("no blocks")
PREDICTED = completion(predicted_response([("7\n", "7\n")]))


def table():
    """Every combination: accepted at attempt 1, except 1_A black_box (unparseable, then a wrong
    solution, then accepted at attempt 3), 2_B black_box (failures through phase 1 into phase
    2, accepted at attempt 9) and 2_B hybrid (12 unparseable answers, an unparseable prediction,
    then a parsed one at attempt 14: accepted_predicted)."""
    answers = {(pid, s, 1): GOOD for pid, s in COMBOS}
    answers[("1_A", "black_box", 1)] = BAD
    answers[("1_A", "black_box", 2)] = WRONG
    answers[("1_A", "black_box", 3)] = GOOD
    for n in range(1, 9):
        answers[("2_B", "black_box", n)] = BAD if n % 2 else WRONG
    answers[("2_B", "black_box", 9)] = GOOD
    for n in range(1, config.SOLUTION_ATTEMPTS + 2):
        answers[("2_B", "hybrid", n)] = BAD
    answers[("2_B", "hybrid", config.SOLUTION_ATTEMPTS + 2)] = PREDICTED
    return answers


def python_runner():
    return FakePythonRunner(
        default=lambda code, stdin: run_result(b"0\n" if code == WRONG_PY else stdin)
    )


class Once:
    """Raise ``KeyboardInterrupt`` the first time ``hit`` is true; afterwards, never again."""

    def __init__(self):
        self.fired = False

    def __call__(self, hit: bool) -> None:
        if hit and not self.fired:
            self.fired = True
            raise KeyboardInterrupt


@pytest.fixture()
def world(tmp_path, monkeypatch):
    """Two repositories with the same dataset: one runs straight, the other is interrupted."""
    monkeypatch.setenv(config.ENV_BASE_URL, "http://ollama.test:11434")
    monkeypatch.setenv(config.ENV_HARDWARE_LABEL, "RTX 3060 12GB")
    monkeypatch.setattr(cli, "make_clock", FakeClock)
    monkeypatch.setattr(cli, "cleanup_slot", lambda slot: None)
    files = {pid: problem(pid) for pid in PROBLEMS}
    return build_dataset(tmp_path / "straight", files), build_dataset(tmp_path / "broken", files)


def drive(root, monkeypatch, client, runner, max_rounds=20):
    """Alternate generate and execute, as the operator does, until nothing is pending.

    Returns the exit codes, in order (130 where an interruption happened).
    """
    monkeypatch.chdir(root)
    monkeypatch.setattr(cli, "make_client", lambda base_url, *, timeout_s: client)
    monkeypatch.setattr(cli, "make_runner", lambda: runner)
    codes = []
    for _ in range(max_rounds):
        resume = ["--resume"] if store.run_exists(root) else []
        codes.append(cli.main(["generate", *resume]))
        codes.append(cli.main(["execute"]))
        if all(store.combination_state(root, pid, s).kind == "terminal" for pid, s in COMBOS):
            return codes
    pytest.fail(f"still pending after {max_rounds} rounds: {codes}")


def tree(root):
    """Every file under data/suites/slm (but the locks), with the informative timestamps removed."""
    base = root / config.SUITES_DIR
    out = {}
    for path in sorted(base.rglob("*")):
        if path.is_dir() or any(part.startswith(".") for part in path.relative_to(base).parts):
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        data.pop("created_at", None)
        data.pop("requested_at", None)
        out[str(path.relative_to(base))] = data
    return out


def leftovers(root):
    return [p for p in (root / config.SUITES_DIR).rglob("*") if p.name.endswith(".tmp")]


def straight_tree(straight, monkeypatch):
    codes = drive(straight, monkeypatch, FakeSLMClient(table(), PROBLEMS), python_runner())
    assert set(codes) == {cli.EXIT_OK}
    return tree(straight)


def keys(client):
    return [r["key"] for r in client.requests]


def test_an_interruption_during_a_call_redoes_that_call_with_the_same_seed(world, monkeypatch):
    straight, broken = world
    expected = straight_tree(straight, monkeypatch)
    client = FakeSLMClient(table(), PROBLEMS)
    once, complete = Once(), client.complete

    def interrupted(model, prompt, options):
        result = complete(model, prompt, options)
        once(client.requests[-1]["key"] == ("1_A", "white_box", 1))  # answer lost in flight
        return result

    client.complete = interrupted
    codes = drive(broken, monkeypatch, client, python_runner())
    assert cli.EXIT_INTERRUPTED in codes
    assert tree(broken) == expected and leftovers(broken) == []
    calls = keys(client)
    assert calls.count(("1_A", "white_box", 1)) == 2  # the same seed again
    assert len(calls) == len(set(calls)) + 1  # no other call was repeated


@pytest.mark.parametrize(
    "where",
    [("1_A", "black_box", 3), ("2_B", "black_box", 9), ("2_B", "hybrid", 14)],
    ids=["phase_1", "phase_2", "phase_4_prediction"],
)
def test_an_interruption_after_a_generation_record_in_each_phase(world, monkeypatch, where):
    straight, broken = world
    expected = straight_tree(straight, monkeypatch)
    client = FakeSLMClient(table(), PROBLEMS)
    once, write = Once(), store.write_generation

    def interrupted(root, record):
        path = write(root, record)
        once((record.problem_id, record.scenario, record.attempt) == where)
        return path

    monkeypatch.setattr(store, "write_generation", interrupted)
    codes = drive(broken, monkeypatch, client, python_runner())
    assert cli.EXIT_INTERRUPTED in codes
    assert tree(broken) == expected and leftovers(broken) == []
    assert len(keys(client)) == len(set(keys(client)))  # no recorded attempt was asked again


def test_an_interruption_during_the_evaluation_of_an_attempt(world, monkeypatch):
    straight, broken = world
    expected = straight_tree(straight, monkeypatch)
    once, runner = Once(), python_runner()
    answer = runner.default

    def interrupted(code, stdin):
        once(stdin == b"6\n")  # in the middle of the generated inputs of the first attempt
        return answer(code, stdin)

    runner.default = interrupted
    codes = drive(broken, monkeypatch, FakeSLMClient(table(), PROBLEMS), runner)
    assert cli.EXIT_INTERRUPTED in codes
    assert tree(broken) == expected and leftovers(broken) == []


def test_an_interruption_between_the_execution_record_and_the_suite(world, monkeypatch):
    straight, broken = world
    expected = straight_tree(straight, monkeypatch)
    once, write = Once(), store.write_execution

    def interrupted(root, record):
        path = write(root, record)
        once(record.outcome == "accepted")
        return path

    monkeypatch.setattr(store, "write_execution", interrupted)
    runner = python_runner()
    codes = drive(broken, monkeypatch, FakeSLMClient(table(), PROBLEMS), runner)
    assert cli.EXIT_INTERRUPTED in codes
    assert tree(broken) == expected and leftovers(broken) == []


def test_a_terminal_combination_is_never_touched_again(world, monkeypatch):
    straight, _ = world
    straight_tree(straight, monkeypatch)
    before = {p: p.read_bytes() for p in (straight / config.SUITES_DIR).rglob("*.json")}
    client, runner = FakeSLMClient({}, PROBLEMS), FakePythonRunner()
    monkeypatch.setattr(cli, "make_client", lambda base_url, *, timeout_s: client)
    monkeypatch.setattr(cli, "make_runner", lambda: runner)
    assert cli.main(["generate", "--resume"]) == cli.EXIT_OK
    assert cli.main(["execute"]) == cli.EXIT_OK
    assert client.requests == [] and runner.calls == []
    assert {p: p.read_bytes() for p in before} == before
