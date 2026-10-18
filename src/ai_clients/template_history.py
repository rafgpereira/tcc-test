"""The prompt template a recorded attempt was built from, found by its hash.

An attempt records the SHA-256 of its template, not the template itself. When that hash is the one
of the file in ``src/prompt_templates/`` today, that file is used. When it is not (the template was
changed after the attempt), every version the file ever had in the Git history is read and the one
with the recorded hash is used. Only ``git log`` and ``git cat-file`` are run: they read the
history and never change it, so they work with ``.git`` mounted read only (the ``app`` service).

A version that is not found (edited and never committed, or no Git here) is never replaced by
another one: ``TemplateNotFound`` is raised, with both hashes.
"""

import hashlib
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from ai_clients.prompt import MARKERS, PromptTemplate, load_template

Reason = Literal["not_in_history", "git_unavailable", "no_repository"]


@dataclass(frozen=True)
class TemplateSource:
    path: str  # relative to the repository root, e.g. src/prompt_templates/llm_prompt.txt
    expected_sha256: str
    origin: Literal["current", "git"]
    commit: str | None  # with origin "git": the latest commit holding that version (full id)
    template: PromptTemplate


class TemplateNotFound(Exception):
    def __init__(self, path: str, expected_sha256: str, current_sha256: str, reason: Reason):
        self.path, self.expected_sha256 = path, expected_sha256
        self.current_sha256, self.reason = current_sha256, reason
        where = {
            "not_in_history": "was not found in the Git history",
            "git_unavailable": "the Git history is not available here (run it in the app service)",
            "no_repository": "the Git history is not available here (run it in the app service)",
        }[reason]
        super().__init__(
            f"the template of this attempt (sha256 {expected_sha256}) is not the current one "
            f"({current_sha256}) and {where}"
        )


def _normalized(data: bytes) -> str | None:
    """The text ``load_template`` would read from these bytes, or ``None`` if not a template."""
    try:
        text = data.decode("utf-8").replace("\r\n", "\n")
    except UnicodeDecodeError:
        return None
    return text if all(text.count(marker) == 1 for marker in MARKERS) else None


def _git(repo: Path, *args: str, stdin: bytes | None = None) -> bytes:
    return subprocess.run(
        ["git", "-c", "safe.directory=*", "-C", str(repo), *args],
        input=stdin,
        capture_output=True,
        check=True,
    ).stdout


def _versions(repo: Path, rel_path: str) -> dict[str, str]:
    """``blob id -> latest commit holding it``, for every version the file ever had."""
    out = _git(repo, "log", "--all", "--format=commit %H", "--raw", "--no-abbrev", "--", rel_path)
    introduced: dict[str, str] = {}  # the version a commit wrote: that commit holds it
    replaced: dict[str, str] = {}  # a version only seen being replaced: its replacer's parent
    commit = ""
    for line in out.decode("utf-8", errors="replace").splitlines():
        if line.startswith("commit "):
            commit = line.split()[1]
        elif line.startswith(":"):  # :old_mode new_mode old_blob new_blob status<TAB>path
            old, new = line.split("\t")[0].split()[2:4]
            if set(new) != {"0"}:  # a blob of zeros: the file does not exist on that side
                introduced.setdefault(new, commit)  # log goes newest first
            if set(old) != {"0"}:
                replaced.setdefault(old, f"{commit}^")
    return {**{b: c for b, c in replaced.items() if b not in introduced}, **introduced}


def _read_blobs(repo: Path, blobs: list[str]) -> dict[str, bytes]:
    """The contents of ``blobs`` in one ``git cat-file --batch``."""
    out = _git(repo, "cat-file", "--batch", stdin="".join(f"{b}\n" for b in blobs).encode())
    found, at = {}, 0
    while at < len(out):
        header_end = out.index(b"\n", at)
        name, kind, size = out[at:header_end].decode().split()
        start = header_end + 1
        found[name] = out[start : start + int(size)] if kind == "blob" else b""
        at = start + int(size) + 1  # the content is followed by a newline
    return found


def resolve(repo: Path, rel_path: str, expected_sha256: str) -> TemplateSource:
    """The template of ``rel_path`` whose hash is ``expected_sha256``: the file, else Git."""
    repo = Path(repo)
    current = load_template(repo / rel_path)
    if current.sha256 == expected_sha256:
        return TemplateSource(rel_path, expected_sha256, "current", None, current)

    def missing(reason: Reason) -> TemplateNotFound:
        return TemplateNotFound(rel_path, expected_sha256, current.sha256, reason)

    if not (repo / ".git").exists():
        raise missing("no_repository")
    try:
        versions = _versions(repo, rel_path)
        contents = _read_blobs(repo, list(versions)) if versions else {}
    except OSError:  # no git executable (or a PATH without it)
        raise missing("git_unavailable") from None
    except subprocess.CalledProcessError:  # not a repository git can read
        raise missing("no_repository") from None
    for blob, commit in versions.items():
        text = _normalized(contents.get(blob, b""))
        if text is not None:
            sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
            if sha == expected_sha256:
                return TemplateSource(
                    rel_path, expected_sha256, "git", commit, PromptTemplate(text, sha)
                )
    raise missing("not_in_history")
