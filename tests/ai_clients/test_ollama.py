"""The Ollama client against a real HTTP server on 127.0.0.1 (no model, no network outside)."""

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from ai_clients.errors import ConfigurationError
from ai_clients.ollama import (
    GenerationOptions,
    OllamaClient,
    OllamaConfigError,
    OllamaUnavailable,
)

OPTIONS = GenerationOptions(
    temperature=0.7,
    top_p=0.8,
    top_k=20,
    repeat_penalty=1.05,
    num_ctx=8192,
    num_predict=4096,
    seed=43,
)

CHAT_OK = {
    "model": "qwen2.5-coder:7b",
    "created_at": "2026-10-01T12:00:00.000Z",
    "message": {"role": "assistant", "content": "<edge_cases_analysis>x</edge_cases_analysis>"},
    "done": True,
    "done_reason": "stop",
    "total_duration": 5,
    "load_duration": 1,
    "prompt_eval_count": 1570,
    "prompt_eval_duration": 2,
    "eval_count": 812,
    "eval_duration": 3,
}
TAGS = {
    "models": [
        {"name": "llama3:8b", "digest": "0" * 64, "details": {"quantization_level": "Q4_0"}},
        {
            "name": "qwen2.5-coder:7b",
            "digest": "f" * 64,
            "details": {"quantization_level": "Q4_K_M"},
        },
    ]
}


class FakeOllama:
    """What the server answers: ``routes[(method, path)] = (status, body)`` or a delay."""

    def __init__(self):
        self.routes = {
            ("POST", "/api/chat"): (200, CHAT_OK),
            ("GET", "/api/tags"): (200, TAGS),
            ("GET", "/api/version"): (200, {"version": "0.12.0"}),
        }
        self.delay = 0.0
        self.received = []


@pytest.fixture()
def server():
    fake = FakeOllama()

    class Handler(BaseHTTPRequestHandler):
        def _answer(self, method):
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length) if length else b""
            fake.received.append((method, self.path, json.loads(body) if body else None))
            time.sleep(fake.delay)
            status, payload = fake.routes.get((method, self.path), (404, {"error": "not found"}))
            data = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            self._answer("GET")

        def do_POST(self):
            self._answer("POST")

        def log_message(self, *args):
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    fake.url = f"http://127.0.0.1:{httpd.server_address[1]}"
    yield fake
    httpd.shutdown()
    httpd.server_close()


def client(server, timeout_s=5.0):
    return OllamaClient(server.url, timeout_s=timeout_s)


def test_the_request_is_one_stateless_message_with_every_option(server):
    client(server).complete("qwen2.5-coder:7b", "the prompt", OPTIONS)
    [(method, path, body)] = server.received
    assert (method, path) == ("POST", "/api/chat")
    assert body["model"] == "qwen2.5-coder:7b" and body["stream"] is False
    assert body["messages"] == [{"role": "user", "content": "the prompt"}]
    for forbidden in ("context", "system", "format", "template"):
        assert forbidden not in body
    assert body["options"] == {
        "temperature": 0.7,
        "top_p": 0.8,
        "top_k": 20,
        "repeat_penalty": 1.05,
        "num_ctx": 8192,
        "num_predict": 4096,
        "seed": 43,
    }


def test_the_completion_carries_content_tokens_reason_and_durations(server):
    got = client(server).complete("qwen2.5-coder:7b", "p", OPTIONS)
    assert got.content == CHAT_OK["message"]["content"]
    assert (got.done_reason, got.prompt_eval_count, got.eval_count) == ("stop", 1570, 812)
    assert (got.total_duration_ns, got.load_duration_ns) == (5, 1)
    assert (got.prompt_eval_duration_ns, got.eval_duration_ns) == (2, 3)
    assert got.model == "qwen2.5-coder:7b" and got.created_at == CHAT_OK["created_at"]


def test_nothing_is_kept_between_two_calls(server):
    c = client(server)
    before = dict(vars(c))
    c.complete("qwen2.5-coder:7b", "first", OPTIONS)
    c.complete("qwen2.5-coder:7b", "second", OPTIONS)
    assert vars(c) == before
    assert [body["messages"] for _, _, body in server.received] == [
        [{"role": "user", "content": "first"}],
        [{"role": "user", "content": "second"}],
    ]


def test_a_refused_connection_is_unavailable():
    with pytest.raises(OllamaUnavailable):
        OllamaClient("http://127.0.0.1:9", timeout_s=2).complete("m", "p", OPTIONS)


def test_an_unresolvable_host_is_unavailable():
    with pytest.raises(OllamaUnavailable):
        OllamaClient("http://ollama.invalid:11434", timeout_s=2).complete("m", "p", OPTIONS)


def test_the_timeout_given_is_the_one_used(server):
    server.delay = 1.5
    with pytest.raises(OllamaUnavailable, match="timed out|timeout"):
        client(server, timeout_s=0.5).complete("qwen2.5-coder:7b", "p", OPTIONS)
    client(server, timeout_s=5).complete("qwen2.5-coder:7b", "p", OPTIONS)  # long enough


def test_a_server_error_is_unavailable(server):
    server.routes[("POST", "/api/chat")] = (500, {"error": "out of memory"})
    with pytest.raises(OllamaUnavailable, match="500"):
        client(server).complete("qwen2.5-coder:7b", "p", OPTIONS)


def test_a_body_that_is_not_json_is_unavailable(server):
    server.routes[("POST", "/api/chat")] = (200, b"<html>proxy</html>")
    with pytest.raises(OllamaUnavailable):
        client(server).complete("qwen2.5-coder:7b", "p", OPTIONS)


@pytest.mark.parametrize("status", [400, 404])
def test_a_client_error_is_a_configuration_error(server, status):
    server.routes[("POST", "/api/chat")] = (status, {"error": "model 'x' not found"})
    with pytest.raises(OllamaConfigError, match="not found"):
        client(server).complete("qwen2.5-coder:7b", "p", OPTIONS)
    assert issubclass(OllamaConfigError, ConfigurationError)


def test_model_info_reads_digest_quantization_and_version(server):
    info = client(server).model_info("qwen2.5-coder:7b")
    assert info.digest == "f" * 64
    assert info.quantization_level == "Q4_K_M"
    assert info.ollama_version == "0.12.0"


def test_a_model_that_is_not_installed_is_a_configuration_error(server):
    with pytest.raises(OllamaConfigError, match="ollama pull qwen2.5-coder:14b"):
        client(server).model_info("qwen2.5-coder:14b")


def test_model_info_while_ollama_is_down_is_unavailable():
    with pytest.raises(OllamaUnavailable):
        OllamaClient("http://127.0.0.1:9", timeout_s=2).model_info("qwen2.5-coder:7b")
