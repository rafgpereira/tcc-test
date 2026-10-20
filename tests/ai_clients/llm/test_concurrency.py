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


def test_the_three_models_run_together(repo):
    providers = {m: FakeProvider(m, default=answer(m)) for m in config.MODELS}
    for provider in providers.values():
        provider.on_call = slow()
    threads = [
        threading.Thread(target=run_with, args=(repo, provider, 2, model))
        for model, provider in providers.items()
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert all(len(p.requests) == 6 for p in providers.values())
    assert LlmRunConfig  # both trees are complete and independent
    for model in config.MODELS:
        assert all(store.combination_state(repo, model, p, s).kind == "terminal" for p, s in COMBOS)


def test_barred_answers_with_calls_in_flight(providers, repo, monkeypatch):
    """FR-018a with N = 4: each barred combination is asked again up to 3 times and then takes
    the last readable answer (accepted_barred); every other combination goes on to its suite."""
    monkeypatch.setenv(config.ENV_MAX_CONCURRENCY["gpt"], "4")
    provider = providers["gpt"]
    for n in range(1, config.MAX_BARRED + 1):  # the same attempt, asked again
        provider.table[("1_A", "black_box", n)] = answer("gpt", reasoning=0)
        provider.table[("1_A", "white_box", n)] = answer("gpt", reasoning=0)
    code = cli.main(["generate", "--model", "gpt", "--confirm-spend", "10"])
    assert code == cli.EXIT_OK
    assert len(provider.requests) == 4 + 2 * config.MAX_BARRED
    barred = store.read_barred(repo, "gpt")
    assert sorted({(b.problem_id, b.scenario.value) for b in barred}) == [
        ("1_A", "black_box"),
        ("1_A", "white_box"),
    ]
    statuses = {(p, s): store.read_suite(repo, "gpt", p, s).status.value for p, s in COMBOS}
    assert sorted(k for k, v in statuses.items() if v == "accepted_barred") == [
        ("1_A", "black_box"),
        ("1_A", "white_box"),
    ]
    assert sum(v == "accepted_predicted" for v in statuses.values()) == 4
