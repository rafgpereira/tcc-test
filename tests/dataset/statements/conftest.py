"""A local HTTP server in place of Codeforces (no internet), a clock that does not wait, and a
dataset whose statements match the hand-written pages of ``fixtures.py``."""

import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from dataset import config
from tests.ai_clients.conftest import build_dataset, problem
from tests.dataset.statements.fixtures import (
    NEW_LEGEND_HTML,
    NEW_LEGEND_OURS,
    OLD_LEGEND_HTML,
    OLD_LEGEND_OURS,
    enunciado,
    page,
)

# problem id -> (legend html, legend as the dataset has it)
LEGENDS = {"1_A": (OLD_LEGEND_HTML, OLD_LEGEND_OURS), "2_B": (NEW_LEGEND_HTML, NEW_LEGEND_OURS)}


@dataclass
class FakeClock:
    now: float = 1000.0
    sleeps: list = field(default_factory=list)

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


@dataclass
class Site:
    pages: dict  # path -> list of (status, body) served in order (the last one repeats)
    requests: list = field(default_factory=list)  # (path, user agent)
    in_flight: int = 0
    overlaps: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock)

    def answer(self, path):
        with self.lock:
            self.in_flight += 1
            self.overlaps += self.in_flight > 1
        try:
            served = self.pages.get(path, [(404, b"not found")])
            return served.pop(0) if len(served) > 1 else served[0]
        finally:
            with self.lock:
                self.in_flight -= 1


@pytest.fixture()
def site(monkeypatch):
    state = Site(pages={})

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # the name http.server calls
            state.requests.append((self.path, self.headers.get("User-Agent")))
            status, body = state.answer(self.path.split("?")[0])
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    monkeypatch.setattr(
        config,
        "CODEFORCES_PROBLEM_URL",
        f"http://127.0.0.1:{port}/problem/{{contest}}/{{index}}?locale=en",
    )
    yield state
    server.shutdown()


def path_of(problem_id: str) -> str:
    contest, index = problem_id.split("_")
    return f"/problem/{contest}/{index}"


@pytest.fixture()
def dataset_root(tmp_path, monkeypatch):
    """A packaged, manifested and extracted dataset whose statements match the fixture pages."""
    files = {}
    for pid, (_, ours) in LEGENDS.items():
        files[pid] = problem(pid)
        files[pid]["enunciado.md"] = enunciado(ours)
    root = build_dataset(tmp_path, files)
    monkeypatch.chdir(root)
    return root


@pytest.fixture()
def serving(site):
    """The fixture pages served by the local site."""
    for pid, (legend, _) in LEGENDS.items():
        site.pages[path_of(pid)] = [(200, page(legend).encode("utf-8"))]
    return site
