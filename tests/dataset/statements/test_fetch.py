"""The original pages obtained once, at the pace of E2, kept with their hashes (R1)."""

import urllib.request
import zipfile

import pytest

from dataset import config
from dataset.statements import fetch
from tests.dataset.statements.conftest import FakeClock, path_of
from tests.dataset.statements.fixtures import page


def test_the_local_server_answers_inside_a_container_without_network(serving):
    # R7: the sandbox service has no network, but it still has its loopback interface.
    url = config.CODEFORCES_PROBLEM_URL.format(contest=1, index="A")
    with urllib.request.urlopen(url, timeout=5) as response:
        assert response.status == 200


def get(root, ids=("1_A", "2_B"), **kw):
    clock = kw.pop("clock", FakeClock())
    return fetch.ensure_originals(root, list(ids), clock=clock, echo=lambda m: None, **kw), clock


def test_one_request_at_a_time_three_seconds_apart_with_the_user_agent(dataset_root, serving):
    manifest, clock = get(dataset_root)
    assert [p for p, _ in serving.requests] == [
        "/problem/1/A?locale=en",
        "/problem/2/B?locale=en",
    ]
    assert {ua for _, ua in serving.requests} == {config.CODEFORCES_USER_AGENT}
    assert serving.overlaps == 0
    assert clock.sleeps and all(s >= 3.0 - 1e-9 for s in clock.sleeps)
    entry = manifest.entry("1_A")
    body = (dataset_root / "data/statements/originals/1_A.html").read_bytes()
    assert entry.page_sha256 == fetch.sha256(body) and entry.http_status == 200
    block = fetch.statement_block(body.decode())
    assert entry.statement_sha256 == fetch.sha256(block.encode())


def test_a_second_run_asks_nothing(dataset_root, serving):
    get(dataset_root)
    serving.requests.clear()
    get(dataset_root)
    assert serving.requests == []


def test_429_waits_then_succeeds_and_running_out_of_waits_stops(dataset_root, site):
    site.pages[path_of("1_A")] = [(429, b""), (200, page("Hi.").encode())]
    manifest, clock = get(dataset_root, ids=("1_A",))
    assert manifest.entry("1_A").error is None and 30 in clock.sleeps
    site.pages[path_of("2_B")] = [(503, b"")]
    with pytest.raises(fetch.FetchStopped):
        get(dataset_root, ids=("2_B",))
    assert fetch.read_manifest(dataset_root).entry("2_B") is None  # tried again next time


def test_definitive_failures_are_recorded_and_only_retried_with_refetch(dataset_root, site):
    site.pages[path_of("1_A")] = [(200, b"<html>no statement here</html>")]
    manifest, _ = get(dataset_root)  # 2_B: 404 (not served)
    assert manifest.entry("1_A").error == "no_statement_block"
    assert manifest.entry("2_B").error == "http_404"
    site.requests.clear()
    get(dataset_root)
    assert site.requests == []
    get(dataset_root, refetch=True)
    assert len(site.requests) == 2


def test_a_changed_copy_is_refused(dataset_root, serving):
    manifest, _ = get(dataset_root)
    page_file = dataset_root / "data/statements/originals/1_A.html"
    page_file.write_bytes(page_file.read_bytes() + b" ")
    with pytest.raises(fetch.OriginalMismatch, match="1_A"):
        fetch.verify_originals(dataset_root, manifest)


def test_the_package_is_deterministic_and_enough_without_the_pages(dataset_root, serving):
    manifest, _ = get(dataset_root)
    blocks = fetch.read_statement_blocks(dataset_root, manifest)
    assert fetch.package_originals(dataset_root, blocks) is True
    zip_path = dataset_root / config.STATEMENT_ORIGINALS_ZIP
    first = zip_path.read_bytes()
    assert fetch.package_bytes(blocks) == first  # same blocks, same bytes
    assert fetch.package_originals(dataset_root, blocks) is False
    with zipfile.ZipFile(zip_path) as archive:
        assert archive.namelist() == ["statements/1_A.html", "statements/2_B.html"]
        assert {i.date_time for i in archive.infolist()} == {(1980, 1, 1, 0, 0, 0)}
    for f in (dataset_root / "data/statements/originals").iterdir():
        f.unlink()
    assert fetch.read_statement_blocks(dataset_root, manifest) == blocks
    fetch.verify_originals(dataset_root, manifest)  # the block hashes, from the package
    with zipfile.ZipFile(zip_path, "w") as archive:  # a changed block in the package
        archive.writestr("statements/1_A.html", blocks["1_A"] + " ")
        archive.writestr("statements/2_B.html", blocks["2_B"])
    with pytest.raises(fetch.OriginalMismatch, match="packaged block"):
        fetch.verify_originals(dataset_root, manifest)
