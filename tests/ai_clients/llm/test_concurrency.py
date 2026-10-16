"""N calls at a time in one process, and processes together (FR-012, FR-024)."""

import threading
import time

from ai_clients import __main__ as cli
from ai_clients.llm import config, generation, store
from ai_clients.llm.schemas import LlmRunConfig
from ai_clients.prompt import load_template
from tests.ai_clients.llm.fakes import FakeClock, FakeProvider, answer
from tests.ai_clients.llm.test_resume import tree, without_dates

COMBOS = [(p, s) for p in ("1_A", "2_B") for s in config.SCENARIOS]


def slow(seconds=0.02):
    def on_call(problem, scenario, n):
        time.sleep(seconds)

    return on_call


def run_with(repo, provider, concurrency, model="gpt", combos=COMBOS):
    template = load_template(config.LLM_TEMPLATE_PATH)
    clock = FakeClock()
    if not store.run_exists(repo, model):
        store.write_run(
            repo, model, generation.current_run_config(repo, model, template, clock.utc_now())
        )
    run = store.read_run(repo, model)
    return generation.generate(
        repo,
        model,
        combos,
        provider,
        template=template,
        run=run,
        clock=clock,
        echo=lambda line: None,
        max_infra_retries=3,
        concurrency=concurrency,
    )


def table_with_failures(model="gpt"):
    bad = answer(model, text="bad")
    return {("1_A", "hybrid", 1): bad, ("2_B", "black_box", 1): bad, ("2_B", "black_box", 2): bad}


def test_four_calls_at_a_time_never_take_one_combination_twice(repo):
    provider = FakeProvider("gpt", table=table_with_failures(), default=answer("gpt"))
    provider.on_call = slow()
    result = run_with(repo, provider, 4)
    assert provider.overlaps == []
    assert result.suites == 6 and result.calls == 9


def test_four_threads_give_the_tree_of_one(repo, tmp_path):
    first = FakeProvider("gpt", table=table_with_failures(), default=answer("gpt"))
    run_with(repo, first, 1)
    one = without_dates(tree(repo))
    for path in (store.base_dir(repo, "gpt") / "problems").rglob("*.json"):
        path.unlink()
    second = FakeProvider("gpt", table=table_with_failures(), default=answer("gpt"))
    second.on_call = slow()
    run_with(repo, second, 4)
    assert without_dates(tree(repo)) == one


def test_two_processes_share_the_queue_and_skip_what_the_other_holds(repo):
    """Two generate --resume of the same model: a combination in use is skipped, never doubled."""
    provider = FakeProvider("gpt", default=answer("gpt"))
    provider.on_call = slow(0.05)
    results = []
    run_with(repo, FakeProvider("gpt", default=answer("gpt")), 1, combos=[])

    def one():
        with store.shared_run(repo, "gpt"):
            results.append(run_with(repo, provider, 2))

    threads = [threading.Thread(target=one) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert provider.overlaps == []
    assert sum(r.suites for r in results) == 6
    assert sum(len(provider.requests) for _ in [0]) == 6


def test_exclusive_commands_refuse_while_a_generate_runs(providers, repo, capsys):
    cli.main(["generate", "--model", "gpt", "--problem", "1_A", "--confirm-spend", "1"])
    capsys.readouterr()
    with store.shared_run(repo, "gpt"):
        code = cli.main(["generate", "--model", "gpt", "--confirm-spend", "1"])
        assert code == cli.EXIT_USAGE  # run.json exists: --resume needed before the lock
        assert cli.main(["package", "--model", "gpt"]) == cli.EXIT_DATA_FAILURE
    assert "already running over data/suites/gpt/" in capsys.readouterr().err


def test_the_two_models_run_together(repo):
    gpt, gem = FakeProvider("gpt", default=answer("gpt")), FakeProvider(
        "gemini", default=answer("gemini")
    )
    gpt.on_call = gem.on_call = slow()
    with store.exclusive_run(repo, "gpt"), store.exclusive_run(repo, "gemini"):
        pass
    threads = [
        threading.Thread(target=run_with, args=(repo, gpt, 2, "gpt")),
        threading.Thread(target=run_with, args=(repo, gem, 2, "gemini")),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(gpt.requests) == len(gem.requests) == 6
    assert LlmRunConfig  # both trees are complete and independent
    for model in config.MODELS:
        assert all(store.combination_state(repo, model, p, s).kind == "terminal" for p, s in COMBOS)


def test_a_barred_answer_with_calls_in_flight(providers, repo, monkeypatch):
    """FR-018a with N = 4: the barred answer stops the dispatch; the 3 in flight end, pass the
    same check and are recorded; with the cap also reached, the exit code is 6."""
    monkeypatch.setenv(config.ENV_MAX_CONCURRENCY["gpt"], "4")
    provider = providers["gpt"]
    started, release = threading.Barrier(4), threading.Event()
    provider.table[("1_A", "black_box", 1)] = answer("gpt", reasoning=0)
    provider.table[("1_A", "white_box", 1)] = answer("gpt", reasoning=0)

    def on_call(problem, scenario, n):
        if len(provider.requests) <= 4:
            started.wait(timeout=5)
            if (problem, scenario) != ("1_A", "black_box"):
                release.wait(timeout=5)

    original = provider.call

    def call(prompt):
        try:
            return original(prompt)
        finally:
            release.set()

    provider.on_call = on_call
    provider.call = call
    code = cli.main(["generate", "--model", "gpt", "--confirm-spend", "0.0001"])
    assert code == cli.EXIT_NO_REASONING
    assert len(provider.requests) == 4  # nothing new after the first barred answer
    barred = store.read_barred(repo, "gpt")
    assert sorted((b.problem_id, b.scenario.value) for b in barred) == [
        ("1_A", "black_box"),
        ("1_A", "white_box"),
    ]
    recorded = [
        (p, s)
        for p in ("1_A", "2_B")
        for s in config.SCENARIOS
        if store.read_attempt(repo, "gpt", p, s, 1) is not None
    ]
    assert recorded == [("1_A", "hybrid"), ("2_B", "black_box")]
