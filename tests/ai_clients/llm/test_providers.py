"""The two HTTP clients: the exact request, the reading of the answers, the errors (contracts §1–3)."""

import io
import json
import urllib.error

import pytest

from ai_clients.llm import config, providers
from ai_clients.llm.providers import (
    ProviderFatal,
    ProviderUnavailable,
    answer_from_body,
    classify_http_error,
    request_body,
)
from ai_clients.llm.schemas import FORBIDDEN_PARAMETERS, forbidden_keys, response_schema
from tests.ai_clients.llm.fakes import gemini_body, openai_body

PROMPT = "<system_rules>…</system_rules>\n<context_data>x</context_data>"


def test_the_openai_body_is_exactly_the_contract():
    assert request_body("gpt", PROMPT) == {
        "input": PROMPT,
        "max_output_tokens": 32768,
        "model": "gpt-5.4-mini-2026-03-17",
        "reasoning": {"effort": "medium"},
        "store": False,
        "text": {
            "format": {
                "name": "test_suite",
                "schema": response_schema(),
                "strict": True,
                "type": "json_schema",
            }
        },
    }


def test_the_gemini_body_is_exactly_the_contract():
    assert request_body("gemini", PROMPT) == {
        "contents": [{"parts": [{"text": PROMPT}], "role": "user"}],
        "generationConfig": {
            "maxOutputTokens": 32768,
            "responseFormat": {
                "text": {"mimeType": "APPLICATION_JSON", "schema": response_schema()}
            },
            "thinkingConfig": {"thinkingLevel": "medium"},
        },
    }


@pytest.mark.parametrize("model", config.MODELS)
def test_no_forbidden_parameter_is_ever_sent(model):
    body = request_body(model, PROMPT)
    assert forbidden_keys(body) == set()
    text = json.dumps(body)
    for key in FORBIDDEN_PARAMETERS:
        assert f'"{key}"' not in text


@pytest.mark.parametrize("model", config.MODELS)
def test_the_whole_prompt_is_one_user_message(model):
    body = request_body(model, PROMPT)
    if model == "gpt":
        assert body["input"] == PROMPT  # a string input is one user message
    else:
        assert body["contents"] == [{"parts": [{"text": PROMPT}], "role": "user"}]


def test_the_recorded_parameters_are_the_body_without_the_prompt():
    params = providers.request_parameters("gpt")
    assert params["input"] == "<prompt>" and params["store"] is False


# ------------------------------------------------------------------------------------ answers


def test_reading_an_openai_answer():
    raw = openai_body(reasoning=900, input_tokens=2100, cached=100, output=1500)
    answer = answer_from_body("gpt", raw, 3.0)
    assert (answer.model_returned, answer.response_id) == ("gpt-5.4-mini-2026-03-17", "resp_1")
    assert answer.raw_body == raw and answer.latency_s == 3.0
    assert answer.finish.status == "completed" and answer.refusal is None
    assert answer.usage.model_dump() == {
        "input_tokens": 2100,
        "cached_input_tokens": 100,
        "output_tokens": 1500,
        "reasoning_tokens": 900,
    }
    assert json.loads(answer.text)["tests"] == [{"input": "1\n", "output": "1\n"}]


def test_openai_incomplete_refusal_and_no_reasoning_count():
    cut = answer_from_body("gpt", openai_body(status="incomplete", reason="max_output_tokens"), 1)
    assert (cut.finish.status, cut.finish.reason) == ("incomplete", "max_output_tokens")
    refused = answer_from_body("gpt", openai_body(refusal="I cannot help"), 1)
    assert refused.refusal == "I cannot help" and refused.text is None
    silent = answer_from_body("gpt", openai_body(reasoning=None), 1)
    assert silent.usage.reasoning_tokens is None


def test_reading_a_gemini_answer_bills_thoughts_as_output_and_skips_thought_parts():
    raw = gemini_body(thoughts=700, prompt_tokens=2000, cached=50, candidates=300)
    answer = answer_from_body("gemini", raw, 2.0)
    assert (answer.model_returned, answer.response_id) == ("gemini-3.8-flash", "gem_1")
    assert answer.usage.model_dump() == {
        "input_tokens": 2000,
        "cached_input_tokens": 50,
        "output_tokens": 1000,
        "reasoning_tokens": 700,
    }
    assert "thinking" not in answer.text and json.loads(answer.text)["tests"]


def test_gemini_blocks_and_ceilings():
    blocked = answer_from_body("gemini", gemini_body(block_reason="SAFETY"), 1)
    assert (blocked.finish.status, blocked.finish.reason, blocked.text) == (
        "PROMPT_BLOCKED",
        "SAFETY",
        None,
    )
    unsafe = answer_from_body(
        "gemini", gemini_body(finish="SAFETY", blocked=("HARM_CATEGORY_DANGEROUS_CONTENT",)), 1
    )
    assert unsafe.finish.safety_categories == ["HARM_CATEGORY_DANGEROUS_CONTENT"]
    assert answer_from_body("gemini", gemini_body(finish="MAX_TOKENS"), 1).finish.status == (
        "MAX_TOKENS"
    )
    assert answer_from_body("gemini", gemini_body(thoughts=None), 1).usage.reasoning_tokens is None


@pytest.mark.parametrize("raw", ["", "not json", "[1, 2]"])
def test_a_200_body_that_is_not_a_json_object_is_an_outage(raw):
    with pytest.raises(ProviderUnavailable):
        answer_from_body("gpt", raw, 1)


# ------------------------------------------------------------------------------------- errors


def error(code, payload):
    return json.dumps({"error": payload})


@pytest.mark.parametrize(
    "model, code, payload, kind",
    [
        ("gpt", 429, {"code": "insufficient_quota", "message": "quota"}, ProviderFatal),
        ("gpt", 429, {"code": "rate_limit_exceeded", "message": "slow down"}, ProviderUnavailable),
        ("gpt", 500, {"message": "server"}, ProviderUnavailable),
        ("gpt", 503, {"message": "overloaded"}, ProviderUnavailable),
        ("gpt", 408, {"message": "timeout"}, ProviderUnavailable),
        ("gpt", 400, {"message": "bad schema"}, ProviderFatal),
        ("gpt", 401, {"message": "bad key"}, ProviderFatal),
        ("gpt", 404, {"message": "no model"}, ProviderFatal),
        ("gemini", 429, {"status": "RESOURCE_EXHAUSTED", "message": "rate"}, ProviderUnavailable),
        ("gemini", 503, {"message": "unavailable"}, ProviderUnavailable),
        ("gemini", 400, {"message": "invalid argument"}, ProviderFatal),
        ("gemini", 403, {"message": "permission"}, ProviderFatal),
    ],
)
def test_the_classification_of_http_errors(model, code, payload, kind):
    assert isinstance(classify_http_error(model, code, error(code, payload)), kind)


def test_the_wait_asked_by_the_api_is_read():
    headers = {"Retry-After": "17"}
    assert classify_http_error("gpt", 429, error(429, {}), headers).retry_after_s == 17
    body = error(
        429,
        {"details": [{"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "21s"}]},
    )
    assert classify_http_error("gemini", 429, body).retry_after_s == 21


def test_the_fatal_messages_say_what_to_fix():
    assert "OPENAI_API_KEY was refused" in str(classify_http_error("gpt", 401, "{}"))
    assert "quota or credit" in str(
        classify_http_error("gpt", 429, error(429, {"code": "insufficient_quota"}))
    )


class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.mark.parametrize("model", config.MODELS)
def test_the_key_never_appears_in_an_error(monkeypatch, model):
    key = "sk-very-secret-key"

    def refuse(request, timeout):
        body = json.dumps({"error": {"message": f"Incorrect API key provided: {key}"}})
        raise urllib.error.HTTPError(request.full_url, 401, "no", {}, io.BytesIO(body.encode()))

    monkeypatch.setattr(providers.urllib.request, "urlopen", refuse)
    client = providers.make_provider(model, key, timeout_s=5)
    with pytest.raises(ProviderFatal) as caught:
        client.call(PROMPT)
    assert key not in str(caught.value)


@pytest.mark.parametrize("model", config.MODELS)
def test_a_real_client_sends_the_body_and_reads_the_answer(monkeypatch, model):
    seen = {}
    raw = openai_body() if model == "gpt" else gemini_body()

    def fake_urlopen(request, timeout):
        seen.update(
            url=request.full_url,
            body=json.loads(request.data),
            headers={k.lower(): v for k, v in request.header_items()},
            timeout=timeout,
        )
        return _Response(raw.encode())

    monkeypatch.setattr(providers.urllib.request, "urlopen", fake_urlopen)
    client = providers.make_provider(model, "k", timeout_s=900)
    answer = client.call(PROMPT)
    assert seen["url"] == config.ENDPOINT[model] and seen["timeout"] == 900
    assert seen["body"] == request_body(model, PROMPT)
    if model == "gpt":
        assert seen["headers"]["authorization"] == "Bearer k"
    else:
        assert seen["headers"]["x-goog-api-key"] == "k" and "key=" not in seen["url"]
    assert answer.raw_body == raw


def test_a_timeout_and_a_broken_connection_are_outages(monkeypatch):
    def slow(request, timeout):
        raise TimeoutError

    monkeypatch.setattr(providers.urllib.request, "urlopen", slow)
    with pytest.raises(ProviderUnavailable, match="timed out"):
        providers.make_provider("gpt", "k", timeout_s=1).call(PROMPT)

    def unreachable(request, timeout):
        raise urllib.error.URLError("name resolution failed")

    monkeypatch.setattr(providers.urllib.request, "urlopen", unreachable)
    with pytest.raises(ProviderUnavailable, match="cannot reach"):
        providers.make_provider("gemini", "k", timeout_s=1).call(PROMPT)


def test_a_real_gemini_answer_of_2026_10_16_is_read():
    """The answer of the live API to the request of this module (hello world prompt)."""
    from pathlib import Path

    from ai_clients.llm.interpret import interpret, needs_barrier
    from dataset.schemas.testes import TestCase

    raw = (Path(__file__).parent / "fixtures" / "gemini_hello_world_2026-10-16.json").read_text()
    answer = answer_from_body("gemini", raw, 1.0)
    assert (answer.model_returned, answer.finish.status) == ("gemini-3.8-flash", "STOP")
    assert answer.usage.reasoning_tokens == 309 and answer.usage.output_tokens == 77 + 309
    assert not needs_barrier(answer)
    result = interpret(answer, TestCase(input="1\n", output="1\n"))
    assert result.ok and result.empty_tests == 1
    assert [(t.input, t.output) for t in result.tests] == [
        ("unexpected input text\n", "Hello, World!\n")
    ]
