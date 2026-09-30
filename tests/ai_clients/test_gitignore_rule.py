"""The `.gitignore` rule: the SLM suites are versioned only as the packaged final run."""

import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.fixture()
def ignored_repo(tmp_path, repo_root):
    shutil.copy(repo_root / ".gitignore", tmp_path / ".gitignore")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    return tmp_path


def _is_ignored(repo: Path, path: str) -> bool:
    result = subprocess.run(
        ["git", "check-ignore", path], cwd=repo, capture_output=True, text=True, check=False
    )
    return path in result.stdout.splitlines()


def test_the_loose_suites_are_ignored(ignored_repo):
    assert _is_ignored(ignored_repo, "data/suites/slm/problems/1_A/hybrid/suite.json")
    assert _is_ignored(ignored_repo, "data/suites/slm/run.json")


def test_the_packaged_suites_are_not_ignored(ignored_repo):
    assert not _is_ignored(ignored_repo, "data/slm_suites.zip")


def test_the_manifest_and_the_report_are_not_ignored(ignored_repo):
    assert not _is_ignored(ignored_repo, "manifests/slm_suites.manifest.json")
    assert not _is_ignored(ignored_repo, "manifests/slm_generation_report.json")
