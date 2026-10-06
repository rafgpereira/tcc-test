"""``package`` and ``verify``: the deterministic zip of a finished run and its integrity manifest."""

import json
import shutil
import zipfile

import pytest

from ai_clients import __main__ as cli
from ai_clients import closing, config, execution, store
from tests.ai_clients.fakes import echo_runner, record_generation, start_run

COMBOS = [(pid, s) for pid in ("1_A", "2_B") for s in config.SCENARIOS]


def unparseable_to_the_end(repo, pid="2_B", scenario="hybrid"):
    """23 unparseable answers: the combination awaits manual handling."""
    for n in range(1, config.MAX_ATTEMPTS + 1):
        record_generation(repo, pid, scenario, n, parsed=False)


def finish(repo, run, combos=COMBOS):
    """Every combination accepted at attempt 1 (the hybrid of 2_B: 23 unparseable answers,
    closed by hand as discarded_manual)."""
    for pid, scenario in combos:
        if (pid, scenario) == ("2_B", "hybrid"):
            unparseable_to_the_end(repo, pid, scenario)
            closing.close(repo, pid, scenario, "never parsed", run=run, now=lambda: "2026-10-07")
        else:
            record_generation(repo, pid, scenario)
    execution.execute(repo, combos, run=run, runner=echo_runner(), echo=lambda line: None)


@pytest.fixture()
def finished(repo, monkeypatch):
    monkeypatch.chdir(repo)
    run = start_run(repo)
    finish(repo, run)
    with store.exclusive_run(repo):  # leaves data/suites/slm/.lock behind, as the commands do
        pass
    return run


def tree_files(base):
    return {
        p.relative_to(base).as_posix(): p.read_bytes()
        for p in sorted(base.rglob("*"))
        if p.is_file() and p.name != config.LOCK_FILE
    }


def test_package_writes_the_zip_the_manifest_and_the_report(finished, repo, capsys):
    assert cli.main(["package"]) == cli.EXIT_OK
    out = capsys.readouterr().out
    assert (
        "packaged 6 combinations (5 accepted, 0 accepted_fallback, 0 accepted_predicted, "
        "1 discarded_manual)"
    ) in out
    with zipfile.ZipFile(repo / config.ZIP_PATH) as archive:
        names = archive.namelist()
    assert "suites/slm/run.json" in names
    assert "suites/slm/problems/1_A/black_box/suite.json" in names
    assert "suites/slm/problems/2_B/hybrid/attempt_15.generation.json" in names
    assert "suites/slm/problems/2_B/hybrid/manual_close.json" in names
    assert not any(name.endswith(config.LOCK_FILE) for name in names)
    assert names == sorted(names)
    manifest = json.loads((repo / config.MANIFEST_PATH).read_text(encoding="utf-8"))
    files = [item["path"] for item in manifest["files"]]
    assert files == sorted(n for n in names if not n.endswith("/"))
    assert manifest["slm_suites_zip"]["path"] == "data/slm_suites.zip"
    assert (repo / config.REPORT_PATH).is_file()


def test_the_same_tree_gives_the_same_zip_bytes(finished, repo):
    assert cli.main(["package"]) == cli.EXIT_OK
    first = (repo / config.ZIP_PATH).read_bytes()
    assert cli.main(["package"]) == cli.EXIT_OK
    assert (repo / config.ZIP_PATH).read_bytes() == first


def test_the_zip_has_fixed_dates_and_modes(finished, repo):
    cli.main(["package"])
    with zipfile.ZipFile(repo / config.ZIP_PATH) as archive:
        for info in archive.infolist():
            assert info.date_time == (1980, 1, 1, 0, 0, 0)
            mode = (info.external_attr >> 16) & 0o777
            assert mode == (0o755 if info.is_dir() else 0o644)


def test_unzip_recreates_the_tree_byte_for_byte(finished, repo, tmp_path):
    cli.main(["package"])
    target = tmp_path / "elsewhere"
    with zipfile.ZipFile(repo / config.ZIP_PATH) as archive:
        archive.extractall(target)
    assert tree_files(target / config.ZIP_ROOT) == tree_files(repo / config.SUITES_DIR)


def test_package_refuses_an_unfinished_run(repo, monkeypatch, capsys):
    monkeypatch.chdir(repo)
    run = start_run(repo)
    finish(repo, run, COMBOS[:-1])
    assert cli.main(["package"]) == cli.EXIT_DATA_FAILURE
    assert "1 of 6 combinations have no suite.json" in capsys.readouterr().err
    assert not (repo / config.ZIP_PATH).exists()


def test_package_refuses_a_damaged_run(finished, repo, capsys):
    path = store.combination_dir(repo, "1_A", "black_box") / config.SUITE_FILE
    data = json.loads(path.read_text(encoding="utf-8"))
    data["tests"][0]["output"] = "42\n"
    path.write_text(json.dumps(data), encoding="utf-8")
    assert cli.main(["package"]) == cli.EXIT_DATA_FAILURE
    assert "damaged: 1_A black_box: changed: suite.json" in capsys.readouterr().err
    assert not (repo / config.ZIP_PATH).exists()


def test_package_has_no_problem_or_scenario_option(finished):
    assert cli.main(["package", "--problem", "1_A"]) == cli.EXIT_USAGE
    assert cli.main(["package", "--scenario", "hybrid"]) == cli.EXIT_USAGE


def test_verify_checks_the_zip_and_the_extracted_tree(finished, repo, capsys):
    cli.main(["package"])
    capsys.readouterr()
    assert cli.main(["verify"]) == cli.EXIT_OK
    assert cli.main(["verify", "--extracted", "data/suites/slm"]) == cli.EXIT_OK
    assert capsys.readouterr().out.splitlines()[-1] == "OK"


def test_verify_finds_a_changed_a_missing_and_an_extra_file(finished, repo, capsys):
    cli.main(["package"])
    folder = store.combination_dir(repo, "1_A", "black_box")
    (folder / config.SUITE_FILE).write_text("{}\n", encoding="utf-8")
    (store.combination_dir(repo, "1_A", "white_box") / config.SUITE_FILE).unlink()
    (folder / "notes.txt").write_text("x", encoding="utf-8")
    capsys.readouterr()
    assert cli.main(["verify", "--extracted", "data/suites/slm"]) == cli.EXIT_DATA_FAILURE
    out = capsys.readouterr().out
    assert "changed: suites/slm/problems/1_A/black_box/suite.json" in out
    assert "missing: suites/slm/problems/1_A/white_box/suite.json" in out
    assert "extra: suites/slm/problems/1_A/black_box/notes.txt" in out
    assert out.splitlines()[-1] == "FAIL"


def test_verify_finds_a_changed_zip(finished, repo, capsys):
    cli.main(["package"])
    with (repo / config.ZIP_PATH).open("ab") as handle:
        handle.write(b"x")
    assert cli.main(["verify"]) == cli.EXIT_DATA_FAILURE
    assert "changed: data/slm_suites.zip" in capsys.readouterr().out


def test_verify_without_a_manifest_is_a_usage_error(repo, monkeypatch, capsys):
    monkeypatch.chdir(repo)
    assert cli.main(["verify"]) == cli.EXIT_USAGE
    assert "manifest not found" in capsys.readouterr().err


def test_verify_after_unzip_in_a_fresh_clone(finished, repo):
    cli.main(["package"])
    shutil.rmtree(repo / config.SUITES_DIR)
    with zipfile.ZipFile(repo / config.ZIP_PATH) as archive:
        archive.extractall(repo / "data")
    assert cli.main(["verify", "--extracted", "data/suites/slm"]) == cli.EXIT_OK


def test_package_refuses_while_a_combination_awaits_manual_handling(repo, monkeypatch, capsys):
    monkeypatch.chdir(repo)
    run = start_run(repo)
    for pid, scenario in COMBOS:
        if (pid, scenario) == ("2_B", "hybrid"):
            unparseable_to_the_end(repo)
        else:
            record_generation(repo, pid, scenario)
    execution.execute(repo, COMBOS, run=run, runner=echo_runner(), echo=lambda line: None)
    assert cli.main(["package"]) == cli.EXIT_DATA_FAILURE
    err = capsys.readouterr().err
    assert "1 await manual handling (2_B hybrid)" in err
    assert "python -m ai_clients close --problem ID --scenario S" in err
    assert not (repo / config.ZIP_PATH).exists()
