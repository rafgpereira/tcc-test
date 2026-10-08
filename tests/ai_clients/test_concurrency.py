"""Commands running together over ``data/suites/slm/`` (two GPUs, research R24).

The commands run in threads of this process: an ``flock`` taken through two different open files
excludes the other one exactly as between two processes, so the locks behave as in production. The
fake model blocks inside a call until the test lets it go, which keeps a command "running".
"""

import threading
import zipfile

import pytest

from ai_clients import __main__ as cli
from ai_clients import config, store
from tests.ai_clients.fakes import (
    FakeClock,
    FakeSLMClient,
    completion,
    echo_runner,
    record_generation,
    start_run,
    well_formed_response,
)

GOOD = completion(well_formed_response(["1\n"]))
PROBLEMS = ("1_A", "2_B")
WAIT_S = 10


class BlockingClient(FakeSLMClient):
    """A fake model whose calls for the keys in ``hold`` wait until ``release`` is set."""

    def __init__(self, hold=(), **kwargs):
        table = {
            (pid, s, n): GOOD
            for pid in PROBLEMS
            for s in config.SCENARIOS
            for n in range(1, config.MAX_ATTEMPTS + 1)
        }
        super().__init__(table, problem_ids=PROBLEMS, **kwargs)
        self.hold = set(hold)
        self.entered = threading.Event()
        self.release = threading.Event()

    def complete(self, model, prompt, options):
        answer = super().complete(model, prompt, options)
        if self.requests[-1]["key"] in self.hold:
            self.entered.set()
            assert self.release.wait(WAIT_S), "the test never released the call"
        return answer


@pytest.fixture()
def env(monkeypatch, repo):
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


def use_clients(monkeypatch, *clients):
    """Each ``generate`` gets the next client, as each GPU has its own Ollama."""
    queue = list(clients)
    lock = threading.Lock()

    def make_client(base_url, *, timeout_s):
        with lock:
            return queue.pop(0)

    monkeypatch.setattr(cli, "make_client", make_client)


def run_command(argv):
    """Run a subcommand as ``main`` does, minus the signal handler (main thread only)."""
    return cli._REGISTRY[argv[0]].run(cli.build_parser().parse_args(argv))


class Background(threading.Thread):
    def __init__(self, argv):
        super().__init__(daemon=True)
        self.argv, self.code, self.error = argv, None, None

    def run(self):
        try:
            self.code = run_command(self.argv)
        except BaseException as exc:  # noqa: BLE001 - reported by finish()
            self.error = exc

    def finish(self):
        self.join(WAIT_S)
        assert not self.is_alive(), f"{self.argv} did not end"
        if self.error is not None:
            raise self.error
        return self.code


def generations(repo):
    base = repo / config.PROBLEMS_DIR
    return sorted(p.relative_to(base).as_posix() for p in base.rglob("*.generation.json"))


def every_first_attempt():
    return sorted(f"{p}/{s}/attempt_1.generation.json" for p in PROBLEMS for s in config.SCENARIOS)


def test_two_generate_on_disjoint_halves_run_at_the_same_time(env, monkeypatch, repo, capsys):
    gpu0 = BlockingClient(hold={("1_A", "black_box", 1)})
    gpu1 = BlockingClient(hold={("2_B", "black_box", 1)})
    use_clients(monkeypatch, gpu0, gpu1)
    first = Background(["generate", "--resume", "--problem", "1_A"])
    second = Background(["generate", "--resume", "--problem", "2_B"])
    first.start()
    assert gpu0.entered.wait(WAIT_S)
    second.start()
    # both are inside a call at once: the second was not refused nor made to wait
    assert gpu1.entered.wait(WAIT_S)
    gpu0.release.set()
    gpu1.release.set()
    assert (first.finish(), second.finish()) == (cli.EXIT_OK, cli.EXIT_OK)
    assert [r["key"][0] for r in gpu0.requests] == ["1_A"] * 3
    assert [r["key"][0] for r in gpu1.requests] == ["2_B"] * 3
    assert generations(repo) == every_first_attempt()
    assert "skipped" not in capsys.readouterr().out


def test_overlapping_halves_skip_the_combination_in_use_and_corrupt_nothing(
    env, monkeypatch, repo, capsys
):
    gpu0 = BlockingClient(hold={("1_A", "black_box", 1)})
    gpu1 = BlockingClient()
    use_clients(monkeypatch, gpu0, gpu1)
    first = Background(["generate", "--resume"])
    first.start()
    assert gpu0.entered.wait(WAIT_S)
    capsys.readouterr()
    assert run_command(["generate", "--resume"]) == cli.EXIT_OK  # the same problems, all of them
    out = capsys.readouterr().out.splitlines()
    assert "1_A black_box: skipped (in use by another command)" in out
    assert out[-1].endswith("; 1 skipped (in use by another command)")
    gpu0.release.set()
    assert first.finish() == cli.EXIT_OK
    keys = [r["key"] for r in gpu0.requests + gpu1.requests]
    assert sorted(keys) == sorted((p, s, 1) for p in PROBLEMS for s in config.SCENARIOS)
    assert [r["key"] for r in gpu0.requests] == [("1_A", "black_box", 1)]
    assert generations(repo) == every_first_attempt()  # each attempt once, none twice
    assert cli.main(["execute"]) == cli.EXIT_OK
    assert cli.main(["report"]) == cli.EXIT_OK  # a sound tree: nothing damaged


def test_two_generate_on_every_problem_share_the_work(env, monkeypatch, repo, capsys):
    """Both get the whole queue (research R26): each skips the combination the other is on and
    takes the next one, so the faster one does more and every attempt is made once."""
    gpu0 = BlockingClient(hold={("1_A", "black_box", 1)})
    gpu1 = BlockingClient(hold={("1_A", "white_box", 1)})
    use_clients(monkeypatch, gpu0, gpu1)
    first = Background(["generate", "--resume"])
    second = Background(["generate", "--resume"])
    first.start()
    assert gpu0.entered.wait(WAIT_S)
    second.start()  # skips 1_A black_box, held by the first, and stops on 1_A white_box
    assert gpu1.entered.wait(WAIT_S)
    gpu0.release.set()  # the first skips 1_A white_box and takes the rest of the queue
    assert first.finish() == cli.EXIT_OK
    gpu1.release.set()
    assert second.finish() == cli.EXIT_OK
    assert [r["key"] for r in gpu0.requests] == [
        ("1_A", "black_box", 1),
        ("1_A", "hybrid", 1),
        ("2_B", "black_box", 1),
        ("2_B", "white_box", 1),
        ("2_B", "hybrid", 1),
    ]
    assert [r["key"] for r in gpu1.requests] == [("1_A", "white_box", 1)]
    assert generations(repo) == every_first_attempt()  # each attempt once, none twice
    out = capsys.readouterr().out.splitlines()
    assert out.count("1_A black_box: skipped (in use by another command)") == 1
    assert out.count("1_A white_box: skipped (in use by another command)") == 1


def test_execute_runs_while_a_generate_is_active(env, monkeypatch, repo, capsys):
    record_generation(repo, "2_B", "black_box")
    record_generation(repo, "2_B", "hybrid")
    gpu0 = BlockingClient(hold={("1_A", "black_box", 1)})
    use_clients(monkeypatch, gpu0)
    first = Background(["generate", "--resume", "--problem", "1_A"])
    first.start()
    assert gpu0.entered.wait(WAIT_S)
    capsys.readouterr()
    assert cli.main(["execute"]) == cli.EXIT_OK
    out = capsys.readouterr().out
    assert "2_B black_box attempt 1: accepted" in out and "2_B hybrid attempt 1: accepted" in out
    assert "done: 2 executed" in out
    gpu0.release.set()
    assert first.finish() == cli.EXIT_OK
    assert store.read_suite(repo, "2_B", "black_box").status.value == "accepted"
    assert not (store.combination_dir(repo, "1_A", "black_box") / "suite.json").exists()


def test_execute_skips_a_combination_another_command_holds(env, repo, capsys):
    record_generation(repo, "1_A", "black_box")
    record_generation(repo, "2_B", "black_box")
    with store.claim(repo, "1_A", "black_box") as mine:
        assert mine
        assert cli.main(["execute"]) == cli.EXIT_OK
    out = capsys.readouterr().out.splitlines()
    assert "1_A black_box: skipped (in use by another command)" in out
    assert "; 1 skipped (in use by another command)" in out[-2]
    assert not (store.combination_dir(repo, "1_A", "black_box") / "suite.json").exists()
    assert cli.main(["execute"]) == cli.EXIT_OK  # free again: executed now
    assert (store.combination_dir(repo, "1_A", "black_box") / "suite.json").exists()


@pytest.mark.parametrize(
    "argv",
    [
        ["package"],
        ["close", "--problem", "1_A", "--scenario", "hybrid", "--reason", "x"],
    ],
)
def test_package_and_close_refuse_while_a_generate_runs(env, monkeypatch, capsys, argv):
    gpu0 = BlockingClient(hold={("1_A", "black_box", 1)})
    use_clients(monkeypatch, gpu0)
    first = Background(["generate", "--resume", "--problem", "1_A"])
    first.start()
    assert gpu0.entered.wait(WAIT_S)
    capsys.readouterr()
    try:
        assert cli.main(argv) == cli.EXIT_DATA_FAILURE
        assert store.ALREADY_RUNNING in capsys.readouterr().err
    finally:
        gpu0.release.set()
        first.finish()


def test_a_second_execute_is_refused(env, repo, capsys):
    record_generation(repo, "1_A", "black_box")
    with store.shared_run(repo), store.single_execute(repo):  # an execute already running
        assert cli.main(["execute"]) == cli.EXIT_DATA_FAILURE
    assert "execute is already running" in capsys.readouterr().err
    assert not (store.combination_dir(repo, "1_A", "black_box") / "suite.json").exists()


def test_generate_and_execute_refuse_while_package_or_close_runs(env, monkeypatch, repo, capsys):
    use_clients(monkeypatch, BlockingClient())
    with store.exclusive_run(repo):
        assert cli.main(["generate", "--resume"]) == cli.EXIT_DATA_FAILURE
        assert cli.main(["execute"]) == cli.EXIT_DATA_FAILURE
    assert capsys.readouterr().err.count(store.ALREADY_RUNNING) == 2


def test_the_locks_stay_out_of_the_package_and_of_cli_check(env, monkeypatch, repo):
    use_clients(monkeypatch, BlockingClient())
    assert run_command(["generate", "--resume"]) == cli.EXIT_OK
    assert (repo / config.SUITES_DIR / config.COMBINATION_LOCKS_DIR).is_dir()
    assert cli.main(["execute"]) == cli.EXIT_OK
    assert cli.main(["package"]) == cli.EXIT_OK
    names = zipfile.ZipFile(repo / config.ZIP_PATH).namelist()
    assert not any("/." in f"/{name}" for name in names)
