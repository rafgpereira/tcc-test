"""The tree of one commercial model: writing, run.json and the states (data-model.md, 1 and 4)."""

import json

import pytest

from ai_clients.llm import config, store
from ai_clients.llm.schemas import BarredResponse, LlmAttempt, LlmRunConfig
from ai_clients.schemas.manual_close import ManualClose
from dataset.persistence import store as files
from tests.ai_clients.llm import builders as b

PID, SC = "1_A", "black_box"


@pytest.fixture()
def run(repo):
    current = LlmRunConfig.model_validate(b.run_config())
    store.write_run(repo, "gpt", current)
    return current


def attempt(repo, n=1, ok=True, **changes):
    parse = b.parsed() if ok else b.failed()
    record = LlmAttempt.model_validate(b.attempt(n, parse=parse, **changes))
    store.write_attempt(repo, "gpt", record)
    return record


def close(repo):
    record = ManualClose(problem_id=PID, scenario=SC, reason="never parsed", closed_at="t")
    store.write_manual_close(repo, "gpt", record)


def state(repo, run):
    return store.combination_state(repo, "gpt", PID, SC, run)


def damaged(repo, run) -> str:
    with pytest.raises(store.DamagedCombination) as caught:
        state(repo, run)
    return str(caught.value)


# --------------------------------------------------------------------------------- writing


def test_the_tree_is_created_level_by_level(repo):
    base = store.ensure_suites_dir(repo, "gemini")
    assert base == repo / "data" / "suites" / "gemini"
    assert (base / "problems").is_dir()


def test_records_are_never_rewritten_and_writes_leave_no_temporary(repo, run, monkeypatch):
    record = attempt(repo)
    with pytest.raises(FileExistsError):
        store.write_attempt(repo, "gpt", record)
    with pytest.raises(FileExistsError):
        store.write_run(repo, "gpt", run)

    def broken(path, data):
        raise OSError("disk full")

    monkeypatch.setattr(files.os, "replace", broken)
    with pytest.raises(OSError):
        attempt(repo, 2, scenario="hybrid")
    folder = store.combination_dir(repo, "gpt", PID, "hybrid")
    assert [p.name for p in folder.iterdir()] == []


def test_barred_answers_are_numbered_and_kept_apart(repo, run):
    data = b.call_record(usage={**b.call_record()["usage"], "reasoning_tokens": 0})
    record = BarredResponse.model_validate({**data, "barred_at": "t"})
    first = store.write_barred(repo, "gpt", record)
    second = store.write_barred(repo, "gpt", record)
    assert (first.name, second.name) == ("1.json", "2.json")
    assert first.parent == repo / "data/suites/gpt/barred/1_A/black_box"
    assert len(store.read_barred(repo, "gpt")) == 2
    assert state(repo, run) == store.State("pending", 1)


def test_read_run_refuses_another_version_or_model(repo):
    path = store.run_path(repo, "gpt")
    store.ensure_suites_dir(repo, "gpt")
    path.write_text(json.dumps(b.run_config(schema_version=2)))
    with pytest.raises(store.IncompatibleRunError, match="mv data/suites/gpt"):
        store.read_run(repo, "gpt")
    path.write_text(json.dumps(b.run_config(model="gemini")))
    with pytest.raises(store.IncompatibleRunError):
        store.read_run(repo, "gpt")


# ---------------------------------------------------------------------------------- states


def test_pending_finalizable_terminal(repo, run):
    assert state(repo, run) == store.State("pending", 1)
    attempt(repo, 1, ok=False)
    assert state(repo, run) == store.State("pending", 2)
    attempt(repo, 2)
    assert state(repo, run) == store.State("finalizable", 2)
    suite = store.finalize(repo, "gpt", PID, SC, run)
    assert suite.status.value == "accepted_predicted" and suite.accepted_attempt == 2
    assert [a.failure for a in suite.attempts] == ["not_json", None]
    assert state(repo, run) == store.State("terminal", 0)
    assert store.finalize(repo, "gpt", PID, SC, run) is None


def test_three_failures_await_the_authors_and_close_finalizes(repo, run):
    for n in (1, 2, 3):
        attempt(repo, n, ok=False)
    assert state(repo, run) == store.State("awaiting_manual", 3)
    assert store.awaiting_manual(repo, "gpt", [(PID, SC)], run) == [(PID, SC)]
    close(repo)
    assert state(repo, run) == store.State("finalizable", 3)
    suite = store.finalize(repo, "gpt", PID, SC, run)
    assert suite.status.value == "discarded_manual" and suite.manual_close.reason == "never parsed"
    assert state(repo, run).kind == "terminal"


def test_leftovers_of_atomic_writes_are_ignored(repo, run):
    attempt(repo, 1, ok=False)
    folder = store.combination_dir(repo, "gpt", PID, SC)
    (folder / ".attempt_2.json.abc.tmp").write_text("partial")
    assert state(repo, run) == store.State("pending", 2)


# ---------------------------------------------------------------------------------- damage


def test_a_gap_in_the_attempts(repo, run):
    attempt(repo, 2, ok=False)
    assert "missing: attempt_1.json" in damaged(repo, run)


def test_an_attempt_beyond_the_third(repo, run):
    store.ensure_suites_dir(repo, "gpt")
    folder = store.combination_dir(repo, "gpt", PID, SC)
    folder.mkdir(parents=True)
    (folder / "attempt_4.json").write_text("{}")
    assert "there are only 3 attempts" in damaged(repo, run)


def test_an_attempt_after_an_accepted_one(repo, run):
    attempt(repo, 1)
    attempt(repo, 2, ok=False)
    assert "attempt 1 was accepted" in damaged(repo, run)


def test_a_file_about_another_combination(repo, run):
    attempt(repo, 1, ok=False)
    folder = store.combination_dir(repo, "gpt", PID, SC)
    other = b.attempt(2, parse=b.failed(), scenario="hybrid")
    (folder / "attempt_2.json").write_text(json.dumps(other))
    assert "it is about 1_A hybrid 2" in damaged(repo, run)


def test_invalid_json_and_a_strange_file(repo, run):
    store.ensure_suites_dir(repo, "gpt")
    folder = store.combination_dir(repo, "gpt", PID, SC)
    folder.mkdir(parents=True)
    (folder / "attempt_1.json").write_text("{not json")
    (folder / "notes.txt").write_text("x")
    text = damaged(repo, run)
    assert "inconsistent: attempt_1.json" in text and "inconsistent: notes.txt" in text


@pytest.mark.parametrize(
    "changes, message",
    [
        ({"model_requested": "gpt-5.4-mini"}, "differs from run.json"),
        ({"template_sha256": b.OTHER_SHA}, "belongs in superseded/"),
        (
            {
                "request_parameters": {
                    **b.run_config()["request_parameters"],
                    "max_output_tokens": 1,
                }
            },
            "request parameters differ",
        ),
    ],
)
def test_an_attempt_that_does_not_match_the_run(repo, run, changes, message):
    attempt(repo, 1, ok=False, **changes)
    assert message in damaged(repo, run)


def test_a_changed_suite_json(repo, run):
    attempt(repo, 1)
    store.finalize(repo, "gpt", PID, SC, run)
    path = store.combination_dir(repo, "gpt", PID, SC) / config.SUITE_FILE
    path.write_text(path.read_text().replace('"suite_size": 1', '"suite_size": 1 '))
    assert "changed: suite.json" in damaged(repo, run)


def test_a_suite_before_the_end_and_a_manual_close_without_three_failures(repo, run):
    attempt(repo, 1, ok=False)
    close(repo)
    assert "does not await manual handling" in damaged(repo, run)


def test_a_suite_json_while_pending(repo, run):
    attempt(repo, 1, ok=False)
    folder = store.combination_dir(repo, "gpt", PID, SC)
    (folder / config.SUITE_FILE).write_text("{}")
    assert "the attempts are not finished" in damaged(repo, run)
