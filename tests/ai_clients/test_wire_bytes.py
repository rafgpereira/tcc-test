"""One serialization of the request body: what the two clients send is ``wire_bytes(body)``."""

import io
import json

import pytest

from ai_clients import ollama
from ai_clients.llm import providers
from ai_clients.ollama import GenerationOptions, OllamaClient
from ai_clients.prompt import wire_bytes

PROMPT = "Read n (1 ≤ n ≤ 105) and print it.\n"


def test_wire_bytes_is_the_compact_json_with_non_ascii_escaped():
    body = {"input": PROMPT, "store": False}
    assert wire_bytes(body) == json.dumps(body).encode("utf-8")
    assert b"\\u2264" in wire_bytes(body) and "≤".encode() not in wire_bytes(body)


@pytest.mark.parametrize("model", ["gpt", "gemini"])
def test_the_commercial_clients_send_wire_bytes(monkeypatch, model):
    sent = {}

    def fake_urlopen(request, timeout):
        sent["data"] = request.data
        raise providers.urllib.error.URLError("stop here")

    monkeypatch.setattr(providers.urllib.request, "urlopen", fake_urlopen)
    client = providers.make_provider(model, "key", timeout_s=5)
    with pytest.raises(providers.ProviderUnavailable):
        client.call(PROMPT)
    assert sent["data"] == wire_bytes(providers.request_body(model, PROMPT))


def test_the_ollama_client_sends_wire_bytes(monkeypatch):
    sent = {}

    def fake_urlopen(request, timeout):
        sent["data"] = request.data
        return io.BytesIO(b"")

    monkeypatch.setattr(ollama.urllib.request, "urlopen", fake_urlopen)
    options = GenerationOptions(
        temperature=0.7,
        top_p=0.9,
        top_k=40,
        repeat_penalty=1.1,
        num_ctx=8192,
        num_predict=5120,
        seed=42,
    )
    client = OllamaClient("http://ollama.test:11434", timeout_s=5)
    with pytest.raises(ollama.OllamaUnavailable):  # the empty stream, after the request is sent
        client.complete("qwen", PROMPT, options)
    assert sent["data"] == wire_bytes(ollama.request_body("qwen", PROMPT, options))
