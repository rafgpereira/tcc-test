"""The entry point of ``python -m ai_clients`` and the options every command shares."""

import argparse

import pytest

from ai_clients import __main__ as cli
from ai_clients import config
from tests.ai_clients.conftest import build_dataset, problem


def parse(argv, root):
    parser = argparse.ArgumentParser()
    cli.add_common_options(parser)
    args = parser.parse_args(argv)
    return cli.selected_combinations(root, args)


def test_no_command_prints_the_help_and_is_a_usage_error(capsys):
    assert cli.main([]) == cli.EXIT_USAGE
    assert "python -m ai_clients" in capsys.readouterr().err


def test_help_exits_with_0():
    assert cli.main(["--help"]) == cli.EXIT_OK


def test_a_subcommand_is_registered_only_once():
    cli.register("dummy-once", "help", lambda p: None, lambda a: 0)
    try:
        with pytest.raises(ValueError, match="already registered"):
            cli.register("dummy-once", "help", lambda p: None, lambda a: 0)
    finally:
        del cli._REGISTRY["dummy-once"]


def test_by_default_every_problem_and_every_scenario_in_canonical_order(repo):
    assert parse([], repo) == [
        ("1_A", "black_box"),
        ("1_A", "white_box"),
        ("1_A", "hybrid"),
        ("2_B", "black_box"),
        ("2_B", "white_box"),
        ("2_B", "hybrid"),
    ]


def test_problem_and_scenario_filter_and_can_be_repeated(repo):
    assert parse(["--problem", "2_B", "--scenario", "hybrid", "--scenario", "black_box"], repo) == [
        ("2_B", "black_box"),
        ("2_B", "hybrid"),
    ]


def test_an_unknown_problem_is_a_usage_error(repo):
    with pytest.raises(cli.UsageError, match="not in data/dataset: 9_Z"):
        parse(["--problem", "9_Z"], repo)


def test_an_unknown_scenario_is_rejected_by_the_parser(repo):
    with pytest.raises(SystemExit):
        parse(["--scenario", "grey_box"], repo)


@pytest.mark.parametrize("value", ["0", "-1", "x"])
def test_limit_must_be_a_positive_integer(repo, value):
    with pytest.raises(SystemExit):
        parse(["--limit", value], repo)


def test_limit_and_dry_run_are_parsed(repo):
    parser = argparse.ArgumentParser()
    cli.add_common_options(parser)
    args = parser.parse_args(["--limit", "2", "--dry-run"])
    assert args.limit == 2 and args.dry_run is True


def test_an_intact_dataset_passes_the_gate(repo):
    assert cli.dataset_gate(repo) is None


def test_a_changed_dataset_fails_the_gate_with_code_1(repo, capsys):
    path = repo / "data" / "dataset" / "problems" / "1_A" / "enunciado.md"
    path.write_text("changed\n", encoding="utf-8")
    assert cli.dataset_gate(repo) == cli.EXIT_DATA_FAILURE
    err = capsys.readouterr().err
    assert "changed: " in err and "unzip data/dataset.zip -d data/" in err


def test_a_missing_dataset_manifest_fails_the_gate_with_code_1(repo, capsys):
    (repo / config.DATASET_MANIFEST_PATH).unlink()
    assert cli.dataset_gate(repo) == cli.EXIT_DATA_FAILURE
    assert "unzip data/dataset.zip -d data/" in capsys.readouterr().err


def test_a_missing_extracted_dataset_fails_the_gate(tmp_path):
    root = build_dataset(tmp_path, {"1_A": problem("1_A")})
    import shutil

    shutil.rmtree(root / "data" / "dataset")
    assert cli.dataset_gate(root) == cli.EXIT_DATA_FAILURE


def test_the_optional_variables_fall_back_to_their_defaults(monkeypatch):
    monkeypatch.delenv(config.ENV_HTTP_TIMEOUT_S, raising=False)
    monkeypatch.delenv(config.ENV_MAX_INFRA_RETRIES, raising=False)
    assert cli.http_timeout_s() == config.DEFAULT_HTTP_TIMEOUT_S
    assert cli.max_infra_retries() == config.DEFAULT_MAX_INFRA_RETRIES


def test_the_optional_variables_are_read_from_the_environment(monkeypatch):
    monkeypatch.setenv(config.ENV_HTTP_TIMEOUT_S, "1800")
    monkeypatch.setenv(config.ENV_MAX_INFRA_RETRIES, "5")
    assert cli.http_timeout_s() == 1800
    assert cli.max_infra_retries() == 5


@pytest.mark.parametrize("value", ["0", "-3", "abc", "1.5", ""])
def test_an_optional_variable_that_is_not_a_positive_integer_is_a_usage_error(monkeypatch, value):
    monkeypatch.setenv(config.ENV_MAX_INFRA_RETRIES, value)
    with pytest.raises(cli.UsageError, match=config.ENV_MAX_INFRA_RETRIES):
        cli.max_infra_retries()


def test_errors_map_to_their_exit_codes(monkeypatch):
    from ai_clients.errors import ConfigurationError
    from sandbox.types import InfraError

    def raising(exc):
        def run(args):
            raise exc

        return run

    cases = {
        "dummy-usage": (cli.UsageError("bad"), cli.EXIT_USAGE),
        "dummy-config": (ConfigurationError("model missing"), cli.EXIT_INFRA),
        "dummy-infra": (InfraError("no slot"), cli.EXIT_INFRA),
        "dummy-busy": (cli.store.AlreadyRunningError("busy"), cli.EXIT_DATA_FAILURE),
        "dummy-stop": (KeyboardInterrupt(), cli.EXIT_INTERRUPTED),
    }
    try:
        for name, (exc, _) in cases.items():
            cli.register(name, "help", lambda p: None, raising(exc))
        for name, (_, code) in cases.items():
            assert cli.main([name]) == code, name
    finally:
        for name in cases:
            cli._REGISTRY.pop(name, None)
