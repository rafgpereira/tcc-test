"""The readers of both stores can read an archived tree (``--suites-dir``), the default unchanged."""

import shutil
from pathlib import Path

from ai_clients import store
from ai_clients.llm import store as llm_store
from ai_clients.llm.schemas import BarredResponse, LlmAttempt, LlmRunConfig
from tests.ai_clients.fakes import record_generation, start_run
from tests.ai_clients.llm.builders import attempt, call_record, failed, run_config


def test_the_slm_readers_read_an_archived_tree(repo):
    run = start_run(repo)
    record_generation(repo, "1_A", "black_box", 1)
    archived = Path("data/suites/slm-piloto9")
    shutil.copytree(repo / "data/suites/slm", repo / archived)
    shutil.rmtree(repo / "data/suites/slm")

    assert not store.run_exists(repo)
    assert store.run_exists(repo, archived)
    assert store.read_run(repo, archived) == run
    files = store.attempt_files(repo, "1_A", "black_box", run, tree=archived)
    assert [g.attempt for g in files.generations] == [1]
    state = store.combination_state(repo, "1_A", "black_box", run, tree=archived)
    assert (state.kind, state.attempt) == ("pending_execution", 1)
    assert store.read_generation(repo, "1_A", "black_box", 1, archived).attempt == 1
    assert store.combination_dir(repo, "1_A", "black_box") == (
        repo / "data/suites/slm/problems/1_A/black_box"
    )


def test_the_llm_readers_read_an_archived_tree(repo):
    llm_store.write_run(repo, "gpt", LlmRunConfig(**run_config("gpt")))
    llm_store.write_attempt(repo, "gpt", LlmAttempt(**attempt(1, parse=failed())))
    barred = BarredResponse(
        **call_record(
            usage={
                "input_tokens": 1,
                "cached_input_tokens": 0,
                "output_tokens": 1,
                "reasoning_tokens": 0,
            }
        ),
        barred_at="2026-10-20T12:00:00Z",
    )
    llm_store.write_barred(repo, "gpt", barred)
    archived = Path("data/suites/gpt-piloto9")
    shutil.copytree(repo / "data/suites/gpt", repo / archived)
    shutil.rmtree(repo / "data/suites/gpt")

    assert not llm_store.run_exists(repo, "gpt")
    run = llm_store.read_run(repo, "gpt", archived)
    assert run.model_key == "gpt"
    files = llm_store.attempt_files(repo, "gpt", "1_A", "black_box", run, tree=archived)
    assert [a.attempt for a in files.attempts] == [1]
    state = llm_store.combination_state(repo, "gpt", "1_A", "black_box", run, tree=archived)
    assert (state.kind, state.attempt) == ("pending", 2)
    assert [p.name for p in llm_store.barred_files(repo, "gpt", "1_A", "black_box", archived)] == [
        "1.json"
    ]
    assert llm_store.read_attempt(repo, "gpt", "1_A", "black_box", 1, archived).attempt == 1
    assert llm_store.base_dir(repo, "gpt") == repo / "data/suites/gpt"
