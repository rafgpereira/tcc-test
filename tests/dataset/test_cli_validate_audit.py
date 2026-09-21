"""The `validate` and `audit` subcommands of the CLI (T068; contracts/cli.md)."""

import pytest

from dataset import __main__ as cli
from dataset.validation import pipeline


def test_validate_and_audit_are_registered_and_listed_in_the_help(capsys):
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(["--help"])
    out = capsys.readouterr().out
    assert "validate" in out and "audit" in out and "selfcheck" in out


def test_validate_options_and_defaults():
    args = cli.build_parser().parse_args(["validate"])
    assert args.target == 200 and args.problem is None
    assert args.workers >= 1
    args = cli.build_parser().parse_args(
        ["validate", "--target", "10", "--workers", "3", "--problem", "1101_A"]
    )
    assert (args.target, args.workers, args.problem) == (10, 3, "1101_A")


def test_the_default_number_of_workers_is_half_of_the_cpus_and_at_least_one(monkeypatch):
    monkeypatch.setattr(cli.os, "cpu_count", lambda: 16)
    assert cli.default_workers() == 8
    monkeypatch.setattr(cli.os, "cpu_count", lambda: 1)
    assert cli.default_workers() == 1
    monkeypatch.setattr(cli.os, "cpu_count", lambda: None)
    assert cli.default_workers() >= 1


@pytest.mark.parametrize("value", ["0", "-2", "abc"])
def test_workers_must_be_a_positive_integer(value):
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(["validate", "--workers", value])


def test_audit_takes_a_repeatable_problem_option():
    args = cli.build_parser().parse_args(["audit", "--problem", "1_A", "--problem", "2_B"])
    assert args.problem == ["1_A", "2_B"]
    assert cli.build_parser().parse_args(["audit"]).problem == []


def test_validate_passes_its_options_to_the_pipeline(monkeypatch):
    seen = {}

    def fake(root, **kw):
        seen.update(kw)
        return 0

    monkeypatch.setattr(pipeline, "run_validate", fake)
    assert cli.main(["validate", "--target", "7", "--workers", "2", "--problem", "1_A"]) == 0
    assert (seen["target"], seen["workers"], seen["problem"]) == (7, 2, "1_A")
    assert seen["selfcheck_fn"] is cli.selfcheck


def test_audit_passes_the_problems_to_the_pipeline(monkeypatch):
    seen = {}
    monkeypatch.setattr(pipeline, "run_audit", lambda root, **kw: seen.update(kw) or 1)
    assert cli.main(["audit", "--problem", "1_A", "--problem", "2_B"]) == 1
    assert seen["problems"] == ["1_A", "2_B"]


def test_a_missing_pool_is_a_data_failure_with_a_hint(monkeypatch, capsys):
    def boom(*a, **k):
        raise pipeline.NoPoolError("no pool found; run `python -m dataset extract` first")

    monkeypatch.setattr(pipeline, "run_validate", boom)
    assert cli.main(["validate"]) == 1
    assert "extract" in capsys.readouterr().err


def test_a_request_that_cannot_be_served_is_a_usage_error(monkeypatch, capsys):
    def boom(*a, **k):
        raise pipeline.UsageError("9_Z is not in the pool")

    monkeypatch.setattr(pipeline, "run_validate", boom)
    assert cli.main(["validate", "--problem", "9_Z"]) == 2
    assert "9_Z" in capsys.readouterr().err


def test_an_infrastructure_failure_exits_with_3(monkeypatch, capsys):
    from sandbox.types import InfraError

    def boom(*a, **k):
        raise InfraError("cannot prepare the workdir")

    monkeypatch.setattr(pipeline, "run_validate", boom)
    assert cli.main(["validate"]) == 3
    assert "infrastructure failure" in capsys.readouterr().err


def test_sigterm_is_a_safe_interruption_like_ctrl_c(monkeypatch, capsys):
    """`docker stop` and the end of a session send SIGTERM: clean up and say it is safe to rerun."""
    import os
    import signal

    cleaned = []

    def killed(*args, **kwargs):
        try:
            os.kill(os.getpid(), signal.SIGTERM)
        finally:
            cleaned.append("finally ran")

    monkeypatch.setattr(pipeline, "run_validate", killed)
    before = signal.getsignal(signal.SIGTERM)
    assert cli.main(["validate"]) == 130
    assert "safe to run the command again" in capsys.readouterr().err
    assert cleaned == ["finally ran"]
    assert signal.getsignal(signal.SIGTERM) == before  # the handler is not left installed
