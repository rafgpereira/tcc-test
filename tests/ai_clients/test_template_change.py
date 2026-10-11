"""Changing the prediction template in the middle of a run (``change-template``, research R27).

The run of the tests reaches the prediction like ``939_C`` black box did: 12 solution attempts that
cannot be read, a 13th that runs into the token ceiling and a 14th that becomes the suite. Then the
template file is edited and the change moves attempts 13 and 14 and the suite aside, to be made
again with the new template and the same seeds.
"""

import json

import pytest

from ai_clients import __main__ as cli
from ai_clients import config, store, template_change
from ai_clients.prompt import load_template
from ai_clients.schemas.common import AttemptKind
from ai_clients.schemas.template_change import TemplateChange
from cli import consistency
from tests.ai_clients.fakes import (
    FakeClock,
    FakeSLMClient,
    completion,
    echo_runner,
    predicted_response,
    record_generation,
    start_run,
)

ONLY = ["--problem", "1_A", "--scenario", "black_box"]
UNREADABLE = completion("I cannot answer with the blocks.")
RUNAWAY = completion(
    "<edge_cases_analysis>\nn\n</edge_cases_analysis>\n<tests>\n<test>\n<input>\n" + "1 " * 50,
    done_reason="length",
)
PREDICTED = completion(predicted_response([("1\n", "1\n"), ("2\n", "2\n")]))
NEW_STEP_2 = "STEP 2 - Test cases: at most 10 numbers per input; never 1 2 3 4 ...\n"


@pytest.fixture()
def env(monkeypatch, repo, tmp_path):
    monkeypatch.chdir(repo)
    monkeypatch.setenv(config.ENV_BASE_URL, "http://gpu.test:11434")
    monkeypatch.setenv(config.ENV_HARDWARE_LABEL, "2x T4 16GB")
    for name in (config.ENV_HTTP_TIMEOUT_S, config.ENV_MAX_INFRA_RETRIES, config.ENV_MODEL):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(cli, "make_clock", FakeClock)
    runner = echo_runner()
    monkeypatch.setattr(cli, "make_runner", lambda: runner)
    monkeypatch.setattr(cli, "cleanup_slot", lambda slot: None)
    start_run(repo)


def use_client(monkeypatch, table):
    client = FakeSLMClient(table, problem_ids=("1_A", "2_B"))
    monkeypatch.setattr(cli, "make_client", lambda base_url, *, timeout_s: client)
    return client


def reach_the_prediction(monkeypatch):
    """1_A black box ends as 939_C black box: accepted_predicted at attempt 14."""
    table = {("1_A", "black_box", n): UNREADABLE for n in range(1, config.SOLUTION_ATTEMPTS + 1)}
    table[("1_A", "black_box", 13)] = RUNAWAY
    table[("1_A", "black_box", 14)] = PREDICTED
    use_client(monkeypatch, table)
    assert cli.main(["generate", "--resume", *ONLY]) == cli.EXIT_OK


def edit_the_template(monkeypatch, tmp_path):
    """The authors edit slm_predict_prompt.txt (here, a copy of it)."""
    old = config.PREDICT_TEMPLATE_PATH.read_text(encoding="utf-8")
    path = tmp_path / "slm_predict_prompt.txt"
    path.write_text(old + NEW_STEP_2, encoding="utf-8")
    monkeypatch.setattr(config, "PREDICT_TEMPLATE_PATH", path)
    return load_template(path)


def names(folder):
    return sorted(p.name for p in folder.iterdir()) if folder.is_dir() else []


def combination(repo):
    return store.combination_dir(repo, "1_A", "black_box")


def test_the_attempts_of_the_old_template_are_moved_aside_and_made_again(
    env, monkeypatch, repo, tmp_path, capsys
):
    reach_the_prediction(monkeypatch)
    assert store.read_suite(repo, "1_A", "black_box").status.value == "accepted_predicted"
    old = store.read_run(repo).predict_template_sha256
    new = edit_the_template(monkeypatch, tmp_path)

    # The run refuses the edited template, and says how to change it on purpose.
    assert cli.main(["generate", "--resume", *ONLY]) == cli.EXIT_USAGE
    assert "change-template --template prediction" in capsys.readouterr().err

    reason = "STEP 2 asked for long sequences (1 2 3 ... 100)"
    assert cli.main(["change-template", "--template", "prediction", "--reason", reason]) == 0
    out = capsys.readouterr().out
    assert "1_A black_box: 3 file(s) superseded" in out
    assert "change 1: prediction template" in out and "next:" in out

    solutions = sorted(config.generation_file_name(n) for n in range(1, 13))
    assert names(combination(repo)) == solutions  # back to pending at attempt 13
    kept = store.superseded_dir(repo, 1, "1_A", "black_box")
    assert names(kept) == sorted(
        [config.SUITE_FILE, config.generation_file_name(13), config.generation_file_name(14)]
    )
    change = store.template_changes(repo)[0]
    assert (change.number, change.template, change.reason) == (1, AttemptKind.PREDICTION, reason)
    assert (change.from_sha256, change.to_sha256) == (old, new.sha256)
    assert [(c.problem_id, c.scenario.value, c.files) for c in change.superseded] == [
        (
            "1_A",
            "black_box",
            [config.SUITE_FILE, config.generation_file_name(14), config.generation_file_name(13)],
        )
    ]
    run = store.read_run(repo)
    assert run.predict_template_sha256 == new.sha256 and run.template_was_changed("prediction")
    assert json.loads(store.run_path(repo).read_text())["predict_template_sha256"] == old  # as is
    assert store.combination_state(repo, "1_A", "black_box", run) == store.State(
        "pending_generation", 13
    )

    # Made again with the new template and the same seed as before (49 for attempt 13).
    client = use_client(monkeypatch, {("1_A", "black_box", 13): PREDICTED})
    assert cli.main(["generate", "--resume", *ONLY]) == cli.EXIT_OK
    assert [(r["key"], r["options"]["seed"]) for r in client.requests] == [
        (("1_A", "black_box", 13), 49)
    ]
    assert NEW_STEP_2.strip() in client.requests[0]["prompt"]
    record = store.read_generation(repo, "1_A", "black_box", 13)
    assert record.template_sha256 == new.sha256
    suite = store.read_suite(repo, "1_A", "black_box")
    assert (suite.status.value, suite.accepted_attempt) == ("accepted_predicted", 13)

    # Kept apart from the metrics, listed in the report and checked by cli check.
    assert cli.main(["report"]) == cli.EXIT_OK
    built = json.loads((repo / config.REPORT_PATH).read_text())
    assert built["predict_template_sha256"] == new.sha256
    assert [(c["number"], c["combinations"], c["files"]) for c in built["template_changes"]] == [
        (1, 1, 3)
    ]
    assert built["attempts"]["total"] == 13  # 12 solutions and the new 13th; 13 and 14 not counted
    assert template_change.superseded_problems(repo, store.template_changes(repo)) == []
    lines = consistency._slm_superseded_lines(repo)
    assert [line.status for line in lines] == [consistency.INFO, consistency.OK]
    assert "combinações refeitas: 1" in lines[0].text

    # The new suite.json and attempt_13 share the names of the moved ones: running the same change
    # again finds nothing to finish and never moves them.
    made_again = names(combination(repo))
    capsys.readouterr()
    assert cli.main(["change-template", "--template", "prediction", "--reason", reason]) == 2
    assert "edit the file first" in capsys.readouterr().err
    assert names(combination(repo)) == made_again and len(store.template_changes(repo)) == 1


def test_a_change_with_nothing_to_make_again_is_recorded_too(
    env, monkeypatch, repo, tmp_path, capsys
):
    record_generation(repo, "1_A", "black_box", 1)  # solutions only: nothing used the template
    edit_the_template(monkeypatch, tmp_path)
    assert cli.main(["change-template", "--template", "prediction", "--reason", "r"]) == 0
    assert store.template_changes(repo)[0].superseded == []
    assert names(combination(repo)) == [config.generation_file_name(1)]  # untouched
    assert "0 combination(s) to make again" in capsys.readouterr().out


def test_the_dry_run_lists_and_moves_nothing(env, monkeypatch, repo, tmp_path, capsys):
    reach_the_prediction(monkeypatch)
    edit_the_template(monkeypatch, tmp_path)
    before = names(combination(repo))
    argv = ["change-template", "--template", "prediction", "--reason", "r", "--dry-run"]
    assert cli.main(argv) == cli.EXIT_OK
    out = capsys.readouterr().out
    assert "1_A black_box: suite.json, attempt_14.generation.json, attempt_13" in out
    assert "dry run: change 1 would make 1 combination(s) again" in out
    assert names(combination(repo)) == before
    assert store.template_changes(repo) == []


def test_an_interrupted_change_is_finished_by_running_it_again(
    env, monkeypatch, repo, tmp_path, capsys
):
    reach_the_prediction(monkeypatch)
    edit_the_template(monkeypatch, tmp_path)
    real_rename, calls = template_change.os.rename, []

    def rename_then_stop(source, target):
        if calls:
            raise KeyboardInterrupt
        calls.append(source)
        real_rename(source, target)

    monkeypatch.setattr(template_change.os, "rename", rename_then_stop)
    argv = ["change-template", "--template", "prediction", "--reason", "r"]
    assert cli.main(argv) == cli.EXIT_INTERRUPTED
    # The change is recorded: what is left of the old template in problems/ is damage, never used.
    run = store.read_run(repo)
    with pytest.raises(store.DamagedCombination, match="change-template again"):
        store.combination_state(repo, "1_A", "black_box", run)
    assert template_change.files_left(repo, store.template_changes(repo)[0]) == 2
    assert consistency._slm_superseded_lines(repo)[1].status == consistency.FAIL

    monkeypatch.setattr(template_change.os, "rename", real_rename)
    capsys.readouterr()
    assert cli.main(argv) == cli.EXIT_OK
    assert "finished the interrupted change 1: 2 file(s) moved" in capsys.readouterr().out
    assert len(store.template_changes(repo)) == 1  # no second change
    assert store.combination_state(repo, "1_A", "black_box", run).kind == "pending_generation"


def test_the_same_template_is_refused(env, repo, capsys):
    argv = ["change-template", "--template", "prediction", "--reason", "r"]
    assert cli.main(argv) == cli.EXIT_USAGE
    assert "edit the file first" in capsys.readouterr().err
    assert not store.template_changes_dir(repo).exists()


def test_a_blank_reason_is_refused(env, monkeypatch, tmp_path, capsys):
    edit_the_template(monkeypatch, tmp_path)
    argv = ["change-template", "--template", "prediction", "--reason", "  "]
    assert cli.main(argv) == cli.EXIT_USAGE


def test_a_damaged_combination_refuses_the_whole_change(env, monkeypatch, repo, tmp_path, capsys):
    reach_the_prediction(monkeypatch)
    edit_the_template(monkeypatch, tmp_path)
    (store.combination_dir(repo, "2_B", "hybrid")).mkdir(parents=True)
    (store.combination_dir(repo, "2_B", "hybrid") / "notes.txt").write_text("x")
    before = names(combination(repo))
    argv = ["change-template", "--template", "prediction", "--reason", "r"]
    assert cli.main(argv) == cli.EXIT_DATA_FAILURE
    assert "nothing was recorded nor moved" in capsys.readouterr().err
    assert names(combination(repo)) == before and store.template_changes(repo) == []


def test_another_command_running_refuses_the_change(env, monkeypatch, repo, tmp_path, capsys):
    edit_the_template(monkeypatch, tmp_path)
    with store.shared_run(repo):  # a generate --resume or an execute
        argv = ["change-template", "--template", "prediction", "--reason", "r"]
        assert cli.main(argv) == cli.EXIT_DATA_FAILURE
    assert "already running" in capsys.readouterr().err


def change_of(run, number=1, frm=None, to="b" * 64):
    return TemplateChange(
        number=number,
        template="prediction",
        from_sha256=frm or run.predict_template_sha256,
        to_sha256=to,
        changed_at="2026-10-07T12:00:00Z",
        reason="r",
        superseded=[],
    )


@pytest.mark.parametrize(
    "template_sha256, damaged",
    [(None, True), ("a" * 64, True), ("b" * 64, False)],
)
def test_an_attempt_of_another_template_is_damage(env, repo, template_sha256, damaged):
    run = store.read_run(repo)
    current = run.with_changes([change_of(run)])
    record = record_generation(repo, "1_A", "black_box", 1).model_copy(
        update={"template": AttemptKind.PREDICTION, "template_sha256": template_sha256}
    )
    assert bool(store._template_problems(record, current)) is damaged


def test_an_attempt_without_hash_is_valid_while_its_template_was_not_changed(env, repo):
    """The attempts written before 2026-10-07 have no hash: the solutions never changed."""
    run = store.read_run(repo)
    current = run.with_changes([change_of(run)])
    record = record_generation(repo, "1_A", "black_box", 1)
    assert record.template_sha256 is None and not store._template_problems(record, current)
    assert store.combination_state(repo, "1_A", "black_box", current).kind == "pending_execution"


@pytest.mark.parametrize("problem", ["from", "number", "name"])
def test_a_broken_chain_of_changes_is_a_damaged_run(env, repo, capsys, problem):
    run = store.read_run(repo)
    change = change_of(run, frm="c" * 64 if problem == "from" else None)
    if problem == "number":
        change = change.model_copy(update={"number": 2})
    folder = store.template_changes_dir(repo)
    folder.mkdir()
    name = "002.json" if problem == "name" else "001.json"
    (folder / name).write_text(change.model_dump_json(), encoding="utf-8")
    with pytest.raises(store.DamagedRunError):
        store.read_run(repo)
    assert cli.main(["report"]) == cli.EXIT_DATA_FAILURE


def test_superseded_files_that_no_change_lists_are_found(env, repo):
    stray = repo / config.SUITES_DIR / config.SUPERSEDED_DIR / "001" / "1_A" / "black_box"
    stray.mkdir(parents=True)
    (stray / "attempt_13.generation.json").write_text("{}")
    assert template_change.superseded_problems(repo, []) == [
        "001/1_A/black_box/attempt_13.generation.json: no template change lists it"
    ]
    lines = consistency._slm_superseded_lines(repo)
    assert lines[1].status == consistency.FAIL
