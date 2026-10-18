"""The template of an attempt found by its hash: the current file, else the Git history (R2)."""

import hashlib
import os
import subprocess

import pytest

from ai_clients import template_history
from ai_clients.prompt import MARKERS
from ai_clients.template_history import TemplateNotFound, resolve

REL = "src/prompt_templates/llm_prompt.txt"


def template_text(words: str) -> str:
    return f"{words}\n<context_data>\n{MARKERS[0]}\n</context_data>\n{MARKERS[1]} {MARKERS[2]}\n"


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def git(repo, *args):
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def commit(repo, data: bytes, message: str) -> str:
    path = repo / REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    git(repo, "add", REL)
    git(repo, "commit", "-q", "-m", message)
    return git(repo, "rev-parse", "HEAD")


@pytest.fixture()
def repo(tmp_path):
    git(tmp_path, "init", "-q")
    return tmp_path


def snapshot(folder):
    return sorted(
        (str(p.relative_to(folder)), p.stat().st_mtime_ns) for p in folder.rglob("*") if p.is_file()
    )


def test_the_current_file_is_used_when_its_hash_is_the_recorded_one(repo):
    text = template_text("v1")
    commit(repo, text.encode(), "v1")
    found = resolve(repo, REL, sha(text))
    assert (found.origin, found.commit, found.template.text) == ("current", None, text)


def test_an_older_version_is_found_in_the_history_with_its_commit(repo):
    old, new = template_text("v1"), template_text("v2")
    first = commit(repo, old.encode(), "v1")
    commit(repo, new.encode(), "v2")
    before = snapshot(repo / ".git")
    found = resolve(repo, REL, sha(old))
    assert (found.origin, found.commit, found.template.text) == ("git", first, old)
    assert found.template.sha256 == sha(old)
    assert snapshot(repo / ".git") == before  # only read


def test_a_version_committed_with_crlf_is_found_by_the_hash_of_its_lf_text(repo):
    old = template_text("v1")
    commit(repo, old.replace("\n", "\r\n").encode(), "v1 crlf")
    commit(repo, template_text("v2").encode(), "v2")
    assert resolve(repo, REL, sha(old)).origin == "git"


def test_a_hash_that_is_not_in_the_history_is_refused_with_both_hashes(repo):
    current = template_text("v1")
    commit(repo, current.encode(), "v1")
    with pytest.raises(TemplateNotFound) as caught:
        resolve(repo, REL, "c" * 64)
    error = caught.value
    assert (error.reason, error.expected_sha256, error.current_sha256) == (
        "not_in_history",
        "c" * 64,
        sha(current),
    )
    assert str(error) == (
        f"the template of this attempt (sha256 {'c' * 64}) is not the current one "
        f"({sha(current)}) and was not found in the Git history"
    )


def test_an_uncommitted_edit_is_not_in_the_history(repo):
    commit(repo, template_text("v1").encode(), "v1")
    edited = template_text("edited, never committed")
    (repo / REL).write_text(template_text("v3"))
    with pytest.raises(TemplateNotFound) as caught:
        resolve(repo, REL, sha(edited))
    assert caught.value.reason == "not_in_history"


def test_without_a_repository_it_is_refused(tmp_path):
    path = tmp_path / REL
    path.parent.mkdir(parents=True)
    path.write_text(template_text("v1"))
    with pytest.raises(TemplateNotFound) as caught:
        resolve(tmp_path, REL, "c" * 64)
    assert caught.value.reason == "no_repository"
    assert "run it in the app service" in str(caught.value)


def test_without_git_it_is_refused(repo, monkeypatch):
    commit(repo, template_text("v1").encode(), "v1")
    monkeypatch.setenv("PATH", os.devnull)
    with pytest.raises(TemplateNotFound) as caught:
        resolve(repo, REL, "c" * 64)
    assert caught.value.reason == "git_unavailable"


def test_only_reading_commands_are_run(repo, monkeypatch):
    commit(repo, template_text("v1").encode(), "v1")
    commit(repo, template_text("v2").encode(), "v2")
    seen = []
    real = template_history._git

    def spy(repo_, *args, **kwargs):
        seen.append(args[0])
        return real(repo_, *args, **kwargs)

    monkeypatch.setattr(template_history, "_git", spy)
    resolve(repo, REL, sha(template_text("v1")))
    assert set(seen) == {"log", "cat-file"}
