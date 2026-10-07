"""The Ollama client against a real HTTP server on 127.0.0.1 (no model, no network outside)."""

import dataclasses
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from ai_clients.errors import ConfigurationError
from ai_clients.ollama import (
    GenerationOptions,
    ModelRepetition,
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


def stream_of(answer: dict, pieces: int = 3) -> list[bytes]:
    """The lines Ollama streams for ``answer`` (its non-streamed form): the content in pieces, each
    with its own ``created_at``, then a last piece with no content and every metric."""
    content = answer["message"]["content"]
    size = -(-len(content) // pieces)
    lines = [
        {
            "model": answer["model"],
            "created_at": f"2026-10-01T11:59:5{n}.000Z",
            "message": {"role": "assistant", "content": content[n * size : (n + 1) * size]},
            "done": False,
        }
        for n in range(pieces)
    ]
    last = {key: value for key, value in answer.items() if key != "message"}
    lines.append({**last, "message": {"role": "assistant", "content": ""}})
    return [json.dumps(line).encode() + b"\n" for line in lines]


class FakeOllama:
    """What the server answers: ``routes[(method, path)] = (status, body)`` or a delay.

    A 200 dict answer of ``/api/chat`` asked with ``stream: true`` is streamed (``stream_of``);
    ``stream`` replaces those lines, ``chunk_delay`` waits before each one, and ``declared``
    announces a Content-Length (a body cut short when it is larger than what is sent).
    """

    def __init__(self):
        self.routes = {
            ("POST", "/api/chat"): (200, CHAT_OK),
            ("GET", "/api/tags"): (200, TAGS),
            ("GET", "/api/version"): (200, {"version": "0.12.0"}),
        }
        self.delay = 0.0
        self.chunk_delay = 0.0
        self.stream = None
        self.declared = None
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
            streamed = (body and json.loads(body).get("stream")) and status == 200
            if streamed and (fake.stream is not None or isinstance(payload, dict)):
                lines = fake.stream if fake.stream is not None else stream_of(payload)
                self.send_response(200)
                self.send_header("Content-Type", "application/x-ndjson")
                if fake.declared is not None:
                    self.send_header("Content-Length", str(fake.declared))
                self.end_headers()  # no length: the end of the body is the closed connection
                for line in lines:
                    time.sleep(fake.chunk_delay)
                    self.wfile.write(line)
                    self.wfile.flush()
                return
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
    assert body["model"] == "qwen2.5-coder:7b" and body["stream"] is True
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


def test_the_streamed_completion_is_the_one_without_streaming(server):
    """Joined pieces, and model, created_at, done_reason, counts and durations of the last piece:
    the same Completion Ollama gives for the call without streaming (its answer is CHAT_OK)."""
    server.stream = stream_of(CHAT_OK, pieces=7)
    got = client(server).complete("qwen2.5-coder:7b", "p", OPTIONS)
    assert dataclasses.asdict(got) == {
        "content": CHAT_OK["message"]["content"],
        "model": CHAT_OK["model"],
        "created_at": CHAT_OK["created_at"],  # of the last piece, as without streaming
        "done_reason": "stop",
        "prompt_eval_count": 1570,
        "eval_count": 812,
        "total_duration_ns": 5,
        "load_duration_ns": 1,
        "prompt_eval_duration_ns": 2,
        "eval_duration_ns": 3,
    }


def test_the_metrics_come_only_from_the_last_piece(server):
    lines = stream_of({**CHAT_OK, "done_reason": "length", "eval_count": 4096}, pieces=2)
    first = json.loads(lines[0])
    lines[0] = json.dumps({**first, "eval_count": 1, "done_reason": "stop"}).encode() + b"\n"
    server.stream = lines
    got = client(server).complete("qwen2.5-coder:7b", "p", OPTIONS)
    assert (got.done_reason, got.eval_count) == ("length", 4096)


def test_an_answer_that_keeps_streaming_is_not_cut_by_the_timeout(server):
    """The timeout is the longest silence, not the whole answer (what a proxy closes on)."""
    server.stream = stream_of(CHAT_OK, pieces=5)
    server.chunk_delay = 0.3  # 6 pieces: about 1.8 s in all, never 1 s without a byte
    got = client(server, timeout_s=1.0).complete("qwen2.5-coder:7b", "p", OPTIONS)
    assert got.content == CHAT_OK["message"]["content"]


def test_a_silence_longer_than_the_timeout_is_unavailable(server):
    server.chunk_delay = 1.5
    with pytest.raises(OllamaUnavailable, match="timed out"):
        client(server, timeout_s=0.5).complete("qwen2.5-coder:7b", "p", OPTIONS)


@pytest.mark.parametrize("kept", [0, 1, 3])
def test_a_stream_that_ends_before_its_last_piece_is_unavailable(server, kept):
    """The connection closes after ``kept`` pieces of 4, without ``done``: an outage, so the same
    call is made again, and nothing of the partial answer is returned."""
    server.stream = stream_of(CHAT_OK)[:kept]
    with pytest.raises(OllamaUnavailable, match="ended before its last piece"):
        client(server).complete("qwen2.5-coder:7b", "p", OPTIONS)


def test_a_stream_cut_in_the_middle_of_a_line_is_unavailable(server):
    lines = stream_of(CHAT_OK)
    server.stream = lines[:2] + [lines[2][:10]]  # the connection breaks inside a piece
    with pytest.raises(OllamaUnavailable):
        client(server).complete("qwen2.5-coder:7b", "p", OPTIONS)


def test_a_body_shorter_than_its_content_length_is_unavailable(server):
    lines = stream_of(CHAT_OK)
    server.stream = lines[:2]
    server.declared = sum(len(line) for line in lines)  # announces the whole answer
    with pytest.raises(OllamaUnavailable):
        client(server).complete("qwen2.5-coder:7b", "p", OPTIONS)


def test_the_token_repeat_limit_inside_the_stream_is_a_failure_of_the_model(server):
    """After the 200 is sent, Ollama reports an error as a line of the stream."""
    error = json.dumps({"error": "prediction aborted, token repeat limit reached"}).encode()
    server.stream = stream_of(CHAT_OK)[:2] + [error + b"\n"]
    with pytest.raises(ModelRepetition, match="token repeat limit reached"):
        client(server).complete("qwen2.5-coder:7b", "p", OPTIONS)


def test_another_error_inside_the_stream_is_unavailable(server):
    server.stream = stream_of(CHAT_OK)[:1] + [
        b'{"error":"model runner has unexpectedly stopped"}\n'
    ]
    with pytest.raises(OllamaUnavailable, match="unexpectedly stopped"):
        client(server).complete("qwen2.5-coder:7b", "p", OPTIONS)


def test_a_line_that_is_not_json_is_unavailable(server):
    server.stream = stream_of(CHAT_OK)[:1] + [b"<html>proxy</html>\n"]
    with pytest.raises(OllamaUnavailable, match="not JSON"):
        client(server).complete("qwen2.5-coder:7b", "p", OPTIONS)


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


def test_the_token_repeat_limit_is_a_failure_of_the_model_not_an_outage(server):
    server.routes[("POST", "/api/chat")] = (500, {"error": "token repeat limit reached"})
    with pytest.raises(ModelRepetition, match="token repeat limit reached") as caught:
        client(server).complete("qwen2.5-coder:7b", "p", OPTIONS)
    assert not isinstance(caught.value, OllamaUnavailable)


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


@pytest.mark.parametrize("path", [("POST", "/api/chat"), ("GET", "/api/version")])
def test_a_tunnel_that_is_offline_is_unavailable_not_a_configuration_error(server, path):
    """ngrok answers 404 with ERR_NGROK_3200 while the tunnel is down: an outage, to wait out."""
    page = b"The endpoint robin.ngrok-free.dev is offline.\n\nERR_NGROK_3200\n"
    server.routes[path] = (404, page)
    with pytest.raises(OllamaUnavailable, match="ERR_NGROK_3200"):
        if path[0] == "POST":
            client(server).complete("qwen2.5-coder:7b", "p", OPTIONS)
        else:
            client(server).model_info("qwen2.5-coder:7b")


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
