"""Tests for the command line of ``python -m cli`` (the layers are tested in test_consistency)."""

import pytest

import cli.__main__ as entry


def test_no_command_is_a_usage_error(capsys):
    assert entry.main([]) == entry.EXIT_USAGE
    assert "check" in capsys.readouterr().err


def test_help_lists_the_check_command_and_exits_zero(capsys):
    assert entry.main(["--help"]) == 0
    assert "check" in capsys.readouterr().out


def test_check_help_lists_only_and_deep(capsys):
    assert entry.main(["check", "--help"]) == 0
    out = capsys.readouterr().out
    assert "--only" in out and "--deep" in out


def test_an_unknown_command_is_a_usage_error():
    assert entry.main(["frobnicate"]) == 2


def test_an_unknown_layer_is_a_usage_error(tmp_path, capsys):
    assert entry.main(["--root", str(tmp_path), "check", "--only", "ia"]) == entry.EXIT_USAGE
    assert "unknown layer" in capsys.readouterr().err


def test_a_missing_dataset_manifest_is_a_usage_error(tmp_path, capsys):
    assert entry.main(["--root", str(tmp_path), "check"]) == entry.EXIT_USAGE
    assert "manifest not found: manifests/dataset.manifest.json" in capsys.readouterr().err


@pytest.mark.parametrize("flag", ["--only", "--deep"])
def test_the_hidden_root_option_is_not_in_the_help(flag, capsys):
    entry.main(["--help"])
    assert "--root" not in capsys.readouterr().out
    assert flag  # parametrized only to keep the two flags visible in the test report
