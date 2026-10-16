"""``package`` and ``verify`` of a commercial model (FR-026, A7)."""

import json
import zipfile

import pytest

from ai_clients import __main__ as cli
from ai_clients.llm import config
from ai_clients.llm.schemas import LlmSuitesManifest
from tests.ai_clients.llm.fakes import answer


@pytest.fixture()
def finished_gpt(providers, repo, monkeypatch):
    """Every GPT combination with a suite (one barred answer kept); Gemini left unfinished."""
    monkeypatch.setenv(config.ENV_MAX_CONCURRENCY["gpt"], "1")
    providers["gpt"].table[("2_B", "hybrid", 1)] = answer("gpt", reasoning=0)
    cli.main(["generate", "--model", "gpt", "--confirm-spend", "5"])
    cli.main(["generate", "--model", "gpt", "--resume", "--confirm-spend", "5"])
    providers["gemini"].default = answer("gemini", text="bad")
    cli.main(
        [
            "generate",
            "--model",
            "gemini",
            "--problem",
            "1_A",
            "--scenario",
            "hybrid",
            "--confirm-spend",
            "5",
        ]
    )
    return repo


def test_package_ignores_the_other_model(finished_gpt, repo, capsys):
    capsys.readouterr()
    assert cli.main(["package", "--model", "gpt"]) == cli.EXIT_OK
    out = capsys.readouterr().out
    assert (
        "packaged 6 combinations (6 accepted_predicted, 0 discarded_manual): data/gpt_suites.zip"
        in out
    )
    with zipfile.ZipFile(repo / config.zip_path("gpt")) as archive:
        names = archive.namelist()
    assert "suites/gpt/run.json" in names and "suites/gpt/barred/2_B/hybrid/1.json" in names
    assert not any("/." in name for name in names)
    manifest = LlmSuitesManifest.model_validate_json(
        (repo / config.manifest_path("gpt")).read_text()
    )
    assert manifest.suites_zip.path == "data/gpt_suites.zip"


def test_package_refuses_its_own_pending_combinations(finished_gpt, repo, capsys):
    assert cli.main(["package", "--model", "gemini"]) == cli.EXIT_DATA_FAILURE
    err = capsys.readouterr().err
    assert "6 of 6 combinations of gemini have no suite.json" in err
    assert "1 await manual handling (1_A hybrid)" in err


def test_the_zip_is_deterministic_and_verify_checks_it(finished_gpt, repo, capsys):
    cli.main(["package", "--model", "gpt"])
    first = (repo / config.zip_path("gpt")).read_bytes()
    cli.main(["package", "--model", "gpt"])
    assert (repo / config.zip_path("gpt")).read_bytes() == first
    capsys.readouterr()
    assert cli.main(["verify", "--model", "gpt", "--extracted", "data/suites/gpt"]) == 0
    assert capsys.readouterr().out.strip().endswith("OK")
    suite = repo / "data/suites/gpt/problems/1_A/hybrid/suite.json"
    suite.write_text(suite.read_text() + " ")
    assert cli.main(["verify", "--model", "gpt", "--extracted", "data/suites/gpt"]) == 1
    assert "changed: suites/gpt/problems/1_A/hybrid/suite.json" in capsys.readouterr().out


def test_verify_without_a_manifest_is_a_usage_error(providers, repo):
    assert cli.main(["verify", "--model", "gemini"]) == cli.EXIT_USAGE


def test_the_manifest_accepts_only_files_of_a_run(finished_gpt, repo):
    cli.main(["package", "--model", "gpt"])
    data = json.loads((repo / config.manifest_path("gpt")).read_text())
    data["files"].append({"path": "suites/gpt/notes.txt", "size": 1, "sha256": "a" * 64})
    with pytest.raises(ValueError):
        LlmSuitesManifest.model_validate(data)
    data["files"].pop()
    data["files"][0]["path"] = data["files"][0]["path"].replace("suites/gpt", "suites/slm")
    with pytest.raises(ValueError):
        LlmSuitesManifest.model_validate(data)
