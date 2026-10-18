"""The original pages, obtained once and kept with their hashes (research R1, decision E2).

One request at a time, at least ``CODEFORCES_MIN_INTERVAL_S`` apart, with the project's
``User-Agent``. HTTP 429, 5xx and network errors wait (``CODEFORCES_RETRY_WAITS_S``) and repeat;
when the waits run out the command stops (``FetchStopped``), keeping what it got. A definitive
failure (404, a page without the statement block) is recorded and only tried again with
``refetch``. Each page goes to ``data/statements/originals/<id>.html`` atomically and the manifest
is rewritten after every page, so an interruption loses nothing.

The package ``data/statement_originals.zip`` keeps only the statement blocks, deterministically
(sorted entries, fixed date): the same blocks always give the same bytes.
"""

import hashlib
import io
import json
import time
import urllib.error
import urllib.request
import zipfile
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from dataset import config
from dataset.integrity.packaging import COMPRESS_LEVEL, FILE_MODE, FIXED_DATE_TIME
from dataset.persistence import store
from dataset.schemas.statements import OriginalEntry, OriginalsManifest
from dataset.statements.extract import statement_block

ZIP_ROOT = "statements"
TEMPORARY = {429, 500, 502, 503, 504}


class FetchStopped(Exception):
    """The site kept refusing (or was unreachable) after every wait; what was got is kept."""


class OriginalMismatch(Exception):
    """A kept copy differs from its hash in the manifest."""


class Clock(Protocol):
    def monotonic(self) -> float: ...

    def sleep(self, seconds: float) -> None: ...


class SystemClock:
    def monotonic(self) -> float:
        return time.monotonic()

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def manifest_path(root: Path) -> Path:
    return Path(root) / config.STATEMENT_ORIGINALS_MANIFEST


def page_path(root: Path, problem_id: str) -> Path:
    return Path(root) / config.STATEMENT_ORIGINALS_DIR / f"{problem_id}.html"


def dataset_manifest_sha256(root: Path) -> str:
    return sha256((Path(root) / config.MANIFEST_PATH).read_bytes())


def read_manifest(root: Path) -> OriginalsManifest | None:
    path = manifest_path(root)
    if not path.is_file():
        return None
    return OriginalsManifest.model_validate_json(path.read_bytes())


def _write_manifest(root: Path, entries: dict[str, OriginalEntry]) -> OriginalsManifest:
    manifest = OriginalsManifest(
        dataset_manifest_sha256=dataset_manifest_sha256(root),
        user_agent=config.CODEFORCES_USER_AGENT,
        min_interval_s=config.CODEFORCES_MIN_INTERVAL_S,
        originals=[entries[k] for k in sorted(entries)],
    )
    store.atomic_write_json(manifest_path(root), manifest)
    return manifest


def problem_url(root: Path, problem_id: str) -> str:
    folder = Path(root) / config.EXTRACTED_PROBLEMS_DIR / problem_id
    meta = json.loads((folder / "metadata.json").read_text(encoding="utf-8"))
    return config.CODEFORCES_PROBLEM_URL.format(
        contest=meta["cf_contest_id"], index=meta["cf_index"]
    )


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class _Pacer:
    def __init__(self, clock: Clock) -> None:
        self.clock, self.last = clock, None

    def wait(self) -> None:
        if self.last is not None:
            left = config.CODEFORCES_MIN_INTERVAL_S - (self.clock.monotonic() - self.last)
            if left > 0:
                self.clock.sleep(left)

    def done(self) -> None:
        self.last = self.clock.monotonic()


def _get(url: str, pacer: _Pacer, opener: Callable, echo) -> tuple[int, bytes]:
    """``(status, body)``; repeats temporary failures, then ``FetchStopped``."""
    waits = list(config.CODEFORCES_RETRY_WAITS_S)
    while True:
        pacer.wait()
        request = urllib.request.Request(url, headers={"User-Agent": config.CODEFORCES_USER_AGENT})
        try:
            with opener(request, timeout=config.CODEFORCES_TIMEOUT_S) as response:
                status, body = response.status, response.read()
            pacer.done()
            return status, body
        except urllib.error.HTTPError as exc:
            pacer.done()
            if exc.code not in TEMPORARY:
                return exc.code, b""
            reason = f"HTTP {exc.code}"
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as exc:
            pacer.done()
            reason = f"network: {getattr(exc, 'reason', exc)}"
        if not waits:
            raise FetchStopped(f"{url}: {reason}; stopped asking the site")
        wait = waits.pop(0)
        echo(f"fetch: {reason}; waiting {wait} s before asking again")
        pacer.clock.sleep(wait)


def ensure_originals(
    root: Path,
    problem_ids: list[str],
    *,
    refetch: bool = False,
    clock: Clock | None = None,
    opener: Callable = urllib.request.urlopen,
    echo: Callable[[str], None] = print,
) -> OriginalsManifest:
    """Get the pages missing (or, with ``refetch``, all of ``problem_ids``); the manifest."""
    root = Path(root)
    current = read_manifest(root)
    entries = {e.problem_id: e for e in current.originals} if current is not None else {}
    wanted = [
        pid
        for pid in problem_ids
        if refetch or pid not in entries or not _has_copy(root, entries[pid])
    ]
    if not wanted:
        return current if current is not None else _write_manifest(root, entries)
    pacer = _Pacer(clock or SystemClock())
    folder = root / config.STATEMENT_ORIGINALS_DIR
    for level in (root / config.STATEMENTS_DIR, folder):
        store.make_private_dir(level)
    for pid in wanted:
        url = problem_url(root, pid)
        status, body = _get(url, pacer, opener, echo)
        if status != 200:
            entries[pid] = OriginalEntry(
                problem_id=pid,
                url=url,
                fetched_at=_now(),
                http_status=status,
                error=f"http_{status}",
            )
            echo(f"fetch: {pid} http_{status}")
        else:
            block = statement_block(body.decode("utf-8", errors="replace"))
            store._atomic_write_bytes(page_path(root, pid), body)
            if block is None:
                entries[pid] = OriginalEntry(
                    problem_id=pid,
                    url=url,
                    fetched_at=_now(),
                    http_status=None,
                    page_bytes=len(body),
                    error="no_statement_block",
                )
                echo(f"fetch: {pid} no_statement_block")
            else:
                entries[pid] = OriginalEntry(
                    problem_id=pid,
                    url=url,
                    fetched_at=_now(),
                    http_status=200,
                    page_bytes=len(body),
                    page_sha256=sha256(body),
                    statement_sha256=sha256(block.encode("utf-8")),
                )
                echo(f"fetch: {pid} ok ({len(body)} bytes)")
        _write_manifest(root, entries)
    return read_manifest(root)


def _has_copy(root: Path, entry: OriginalEntry) -> bool:
    """A definitive failure counts as done (only ``refetch`` asks again)."""
    if entry.error is not None:
        return True
    return page_path(root, entry.problem_id).is_file() or _zip_names(root).__contains__(
        f"{ZIP_ROOT}/{entry.problem_id}.html"
    )


def _zip_names(root: Path) -> set[str]:
    path = Path(root) / config.STATEMENT_ORIGINALS_ZIP
    if not path.is_file():
        return set()
    with zipfile.ZipFile(path) as archive:
        return set(archive.namelist())


def read_statement_blocks(root: Path, manifest: OriginalsManifest) -> dict[str, str]:
    """``problem_id -> statement block``: from the kept page, or from the package without it."""
    root = Path(root)
    blocks: dict[str, str] = {}
    zip_path = root / config.STATEMENT_ORIGINALS_ZIP
    archive = zipfile.ZipFile(zip_path) if zip_path.is_file() else None
    try:
        for entry in manifest.originals:
            if entry.error is not None:
                continue
            page = page_path(root, entry.problem_id)
            if page.is_file():
                block = statement_block(page.read_bytes().decode("utf-8", errors="replace"))
            elif (
                archive is not None and f"{ZIP_ROOT}/{entry.problem_id}.html" in archive.namelist()
            ):
                block = archive.read(f"{ZIP_ROOT}/{entry.problem_id}.html").decode("utf-8")
            else:
                continue
            if block is not None:
                blocks[entry.problem_id] = block
    finally:
        if archive is not None:
            archive.close()
    return blocks


def verify_originals(root: Path, manifest: OriginalsManifest) -> None:
    """``OriginalMismatch`` unless every kept copy has its hashes: the page and its block with the
    page kept; only the block when there is just the package."""
    root = Path(root)
    wrong = []
    zip_path = root / config.STATEMENT_ORIGINALS_ZIP
    archive = zipfile.ZipFile(zip_path) if zip_path.is_file() else None
    try:
        for entry in manifest.originals:
            if entry.error is not None:
                continue
            page = page_path(root, entry.problem_id)
            name = f"{ZIP_ROOT}/{entry.problem_id}.html"
            if page.is_file():
                body = page.read_bytes()
                block = statement_block(body.decode("utf-8", errors="replace")) or ""
                if sha256(body) != entry.page_sha256:
                    wrong.append(f"{entry.problem_id}: the page differs from page_sha256")
                elif sha256(block.encode("utf-8")) != entry.statement_sha256:
                    wrong.append(f"{entry.problem_id}: the block differs from statement_sha256")
            elif archive is not None and name in archive.namelist():
                if sha256(archive.read(name)) != entry.statement_sha256:
                    wrong.append(
                        f"{entry.problem_id}: the packaged block differs from statement_sha256"
                    )
    finally:
        if archive is not None:
            archive.close()
    if wrong:
        raise OriginalMismatch("; ".join(wrong))


def package_bytes(blocks: dict[str, str]) -> bytes:
    """The package of the blocks: sorted entries, fixed date and mode, fixed compression level."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED, compresslevel=COMPRESS_LEVEL) as zf:
        for pid in sorted(blocks):
            info = zipfile.ZipInfo(f"{ZIP_ROOT}/{pid}.html", FIXED_DATE_TIME)
            info.external_attr = (0o100000 | FILE_MODE) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3  # unix, whatever the machine
            zf.writestr(info, blocks[pid].encode("utf-8"), compresslevel=COMPRESS_LEVEL)
    return buffer.getvalue()


def package_originals(root: Path, blocks: dict[str, str]) -> bool:
    """Write ``data/statement_originals.zip`` if its bytes would change; whether it changed."""
    path = Path(root) / config.STATEMENT_ORIGINALS_ZIP
    data = package_bytes(blocks)
    if path.is_file() and path.read_bytes() == data:
        return False
    store._atomic_write_bytes(path, data)
    return True
