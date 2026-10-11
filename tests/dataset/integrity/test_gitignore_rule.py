"""The `.gitignore` rule that lets only the packaged dataset be versioned (T085; FR-029).

Uses a real, temporary git repository with a copy of the project's own `.gitignore` (the same
file that reaches the containers through the `Dockerfile` `COPY` and the dev override mount), so
this test exercises the actual rule shipped with the repository, not a re-typed copy of it.
"""

import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.fixture()
def ignored_repo(tmp_path, repo_root):
    shutil.copy(repo_root / ".gitignore", tmp_path / ".gitignore")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    return tmp_path


def _is_ignored(repo: Path, *paths: str) -> dict[str, bool]:
    result = subprocess.run(
        ["git", "check-ignore", *paths], cwd=repo, capture_output=True, text=True, check=False
    )
    ignored = set(result.stdout.splitlines())
    return {p: p in ignored for p in paths}


def test_data_work_is_ignored(ignored_repo):
    assert _is_ignored(ignored_repo, "data/work/anything")["data/work/anything"] is True


def test_extracted_dataset_folder_is_ignored(ignored_repo):
    assert _is_ignored(ignored_repo, "data/dataset/x")["data/dataset/x"] is True


def test_the_packaged_zip_is_not_ignored(ignored_repo):
    assert _is_ignored(ignored_repo, "data/dataset.zip")["data/dataset.zip"] is False


def test_the_manifest_is_not_ignored(ignored_repo):
    assert (
        _is_ignored(ignored_repo, "manifests/dataset.manifest.json")[
            "manifests/dataset.manifest.json"
        ]
        is False
    )


def test_the_extraction_report_copy_is_not_ignored(ignored_repo):
    assert (
        _is_ignored(ignored_repo, "manifests/extraction_report.json")[
            "manifests/extraction_report.json"
        ]
        is False
    )
