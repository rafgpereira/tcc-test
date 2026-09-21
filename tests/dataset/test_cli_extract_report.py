"""Tests for the `extract` and `report` subcommands (T033)."""

import json
import re

import pytest

from dataset import __main__ as cli
from dataset import config
from dataset.extraction import stream
from dataset.persistence import store


class FakeSplit:
    def __init__(self, shards, fail=False):
        self.shards, self.fail = shards, fail

    @property
    def n_shards(self):
        return len(self.shards)

    def shard_rows(self, index):
        if self.fail:
            raise ConnectionError("connection reset by peer")
        return iter(self.shards[index])


@pytest.fixture
def in_tmp(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture
def install(monkeypatch, row_factory):
    def _install(n=4, fail=False):
        rows = [
            row_factory(cf_contest_id=3000 + i, cf_index="A", name=f"{3000 + i}_A. P")
            for i in range(n)
        ]
        data = {"train": [rows], "valid": [[]], "test": [[]]}
        monkeypatch.setattr(stream, "open_split", lambda split: FakeSplit(data[split], fail))

    return _install


def test_the_help_lists_both_subcommands_in_the_argparse_usage_group(capsys):
    assert cli.main(["--help"]) == 0
    usage = capsys.readouterr().out
    group = re.search(r"\{([^{}]*)\}", usage).group(1).split(",")
    assert {"extract", "report"} <= set(group)


def test_extract_writes_the_pool_and_the_report_and_exits_zero(in_tmp, install, capsys):
    install(4)
    assert cli.main(["extract"]) == 0
    out = capsys.readouterr().out
    assert "4 eligible problems" in out and "estrutural_otimizacao: 4" in out
    assert (in_tmp / config.STAGING_DIR / "pool.json").is_file()
    assert (in_tmp / config.REPORTS_DIR / "extraction_report.md").is_file()
    report = json.loads((in_tmp / config.REPORTS_DIR / "extraction_report.json").read_text())
    assert report["funnel"]["read"] == 4 and report["funnel"]["included"] == 0


def test_extract_accepts_seed_splits_and_limit_rows(in_tmp, install):
    install(4)
    assert cli.main(["extract", "--seed", "7", "--splits", "train", "--limit-rows", "2"]) == 0
    pool = json.loads((in_tmp / config.STAGING_DIR / "pool.json").read_text())
    assert pool["seed"] == 7 and len(pool["problems"]) == 2


@pytest.mark.parametrize("splits", ["dev", "train,dev", ","])
def test_extract_rejects_unknown_splits_with_a_usage_error(in_tmp, install, splits, capsys):
    install(1)
    assert cli.main(["extract", "--splits", splits]) == cli.EXIT_USAGE
    assert "--splits" in capsys.readouterr().err


def test_a_network_failure_exits_3_and_the_command_can_be_run_again(in_tmp, install, capsys):
    install(2, fail=True)
    assert cli.main(["extract"]) == cli.EXIT_INFRA
    assert "run the same command again" in capsys.readouterr().err
    install(2)
    assert cli.main(["extract"]) == 0


def test_a_programming_error_is_not_swallowed(in_tmp, monkeypatch):
    def broken(split):
        raise ValueError("bug")

    monkeypatch.setattr(stream, "open_split", broken)
    with pytest.raises(ValueError):
        cli.main(["extract"])


def test_extract_creates_the_private_work_dir(in_tmp, install):
    install(1)
    cli.main(["extract"])
    assert oct((in_tmp / config.WORK_DIR).stat().st_mode & 0o777) == "0o700"


def test_report_without_a_pool_exits_1(in_tmp, capsys):
    assert cli.main(["report"]) == cli.EXIT_DATA_FAILURE
    assert "extract" in capsys.readouterr().err


def test_report_reads_the_pool_and_the_validated_problems(in_tmp, install, capsys):
    install(3)
    cli.main(["extract"])
    ids = sorted(json.loads((in_tmp / config.STAGING_DIR / "pool.json").read_text())["problems"])
    folder = in_tmp / config.PROBLEMS_DIR / ids[0]
    folder.mkdir(parents=True)
    store.atomic_write_json(folder / "validacao.json", {"problem_id": ids[0], "status": "complete"})
    pending = in_tmp / config.PROBLEMS_DIR / ids[1]
    pending.mkdir()
    store.atomic_write_json(
        pending / "validacao.json",
        {
            "problem_id": ids[1],
            "status": "pending_triage",
            "triage": {"stage": "selection", "reason": "AC diverged"},
        },
    )
    capsys.readouterr()

    assert cli.main(["report"]) == 0

    out = capsys.readouterr().out
    assert "included 1 of 200 (deficit 199)" in out
    assert f"PENDING TRIAGE: {ids[1]} (selection): AC diverged" in out
    text = (in_tmp / config.REPORTS_DIR / "extraction_report.md").read_text(encoding="utf-8")
    assert "Triagem adiada" in text  # D17: the pool still has open problems, so it is deferred


def test_report_alerts_when_the_pool_is_exhausted_with_a_deficit(in_tmp, install, capsys):
    """The selection is final once every pool problem is closed, even below the target."""
    install(2)
    cli.main(["extract"])
    ids = sorted(json.loads((in_tmp / config.STAGING_DIR / "pool.json").read_text())["problems"])
    for i, pid in enumerate(ids):
        folder = in_tmp / config.PROBLEMS_DIR / pid
        folder.mkdir(parents=True)
        status = (
            {"status": "complete"}
            if i == 0
            else {"status": "discarded", "discard_reason": "insufficient_wa"}
        )
        store.atomic_write_json(folder / "validacao.json", {"problem_id": pid, **status})
    capsys.readouterr()

    assert cli.main(["report"]) == 0

    out = capsys.readouterr().out
    assert "included 1 of 200 (deficit 199)" in out
    assert out.count("ALERT:") == 3, "all three categories are below 30"
