"""Stateless clients of the two commercial APIs (contracts/providers.md; research R2, R3, R6).

Standard library HTTP (``urllib.request``), one connection per request, no streaming, and never a
retry: waiting and retrying belong to the coordinator (``generation``), so every infrastructure
failure is visible and never consumes an attempt. A client holds only its configuration (key, URL,
timeout), never a prompt or an answer.

Each request is self-contained (FR-002): the whole prompt as ONE user message, the reasoning effort
``medium`` sent explicitly, the strict JSON schema of the answer, and nothing else; no sampling
parameter, no system instruction, no stored state, no safety settings (A3, A11, A13). The body is
built by ``request_body``, a pure function checked key by key by the tests.

Errors are split in two: ``ProviderUnavailable`` (network, timeout, 5xx, rate limit: retry the same
call later) and ``ProviderFatal`` (the run cannot go on as configured: wrong key, exhausted quota,
unknown model, request refused as malformed). The API key never appears in a message.
"""

import email.utils
import http.client
import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from ai_clients.errors import ConfigurationError
from ai_clients.llm import config
from ai_clients.llm.schemas import Finish, Usage, response_schema

PROMPT_PLACEHOLDER = "<prompt>"  # where the prompt goes, in the recorded request parameters


class ProviderUnavailable(Exception):
    """An outage of the API: the same call is made again later; nothing is recorded."""

    def __init__(self, reason: str, retry_after_s: float | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.retry_after_s = retry_after_s


class ProviderFatal(ConfigurationError):
    """The run cannot go on as configured: stop at once, never retry, no attempt consumed."""


@dataclass(frozen=True)
class ProviderAnswer:
    http_status: int
    raw_body: str
    latency_s: float
    model_returned: str
    response_id: str
    finish: Finish
    usage: Usage
    text: str | None  # the answer text, without reasoning parts; None if there is none
    refusal: str | None  # the `refusal` item of the OpenAI answer


class LLMProvider(Protocol):
    key: str

    def request_body(self, prompt: str) -> dict: ...

    def call(self, prompt: str) -> ProviderAnswer: ...


# ----------------------------------------------------------------------------------- requests


def request_body(model: str, prompt: str) -> dict[str, Any]:
    """The exact body of one request (contracts/providers.md, sections 2 and 3)."""
    schema = response_schema()
    if model == "gpt":
        return {
            "input": prompt,
            "max_output_tokens": config.MAX_OUTPUT_TOKENS,
            "model": config.MODEL_ID["gpt"],
            "reasoning": {"effort": config.REASONING_LEVEL},
            "store": False,
            "text": {
                "format": {
                    "name": "test_suite",
                    "schema": schema,
                    "strict": True,
                    "type": "json_schema",
                }
            },
        }
    if model == "gemini":
        return {
            "contents": [{"parts": [{"text": prompt}], "role": "user"}],
            "generationConfig": {
                "maxOutputTokens": config.MAX_OUTPUT_TOKENS,
                # Checked against the live API on 2026-10-16: `mimeType` is an enum
                # (TextResponseFormat.MimeType): "application/json" is refused (HTTP 400),
                # "APPLICATION_JSON" is accepted.
                "responseFormat": {"text": {"mimeType": "APPLICATION_JSON", "schema": schema}},
                "thinkingConfig": {"thinkingLevel": config.REASONING_LEVEL},
            },
        }
    raise ValueError(f"unknown model {model!r}")


def request_parameters(model: str) -> dict[str, Any]:
    """Every parameter sent, as recorded in run.json and in every attempt: the body with the prompt
    replaced by ``<prompt>`` (the prompt itself is recorded by its hash)."""
    return request_body(model, PROMPT_PLACEHOLDER)


# ---------------------------------------------------------------------------------- answers


def _int(value: Any) -> int:
    return int(value) if isinstance(value, (int, float)) and value >= 0 else 0


def _openai_answer(data: dict, raw: str, latency_s: float) -> ProviderAnswer:
    details = data.get("incomplete_details") or {}
    texts, refusal = [], None
    for item in data.get("output") or []:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        for part in item.get("content") or []:
            if part.get("type") == "output_text" and isinstance(part.get("text"), str):
                texts.append(part["text"])
            elif part.get("type") == "refusal" and refusal is None:
                refusal = str(part.get("refusal", ""))
    usage = data.get("usage") or {}
    reasoning = (usage.get("output_tokens_details") or {}).get("reasoning_tokens")
    return ProviderAnswer(
        http_status=200,
        raw_body=raw,
        latency_s=latency_s,
        model_returned=str(data.get("model", "")),
        response_id=str(data.get("id", "")),
        finish=Finish(status=str(data.get("status", "")), reason=details.get("reason")),
        usage=Usage(
            input_tokens=_int(usage.get("input_tokens")),
            cached_input_tokens=_int(
                (usage.get("input_tokens_details") or {}).get("cached_tokens")
            ),
            output_tokens=_int(usage.get("output_tokens")),
            reasoning_tokens=None if reasoning is None else _int(reasoning),
        ),
        text="".join(texts) if texts else None,
        refusal=refusal,
    )


def _gemini_answer(data: dict, raw: str, latency_s: float) -> ProviderAnswer:
    usage = data.get("usageMetadata") or {}
    thoughts = usage.get("thoughtsTokenCount")
    meta = {
        "http_status": 200,
        "raw_body": raw,
        "latency_s": latency_s,
        "model_returned": str(data.get("modelVersion", "")),
        "response_id": str(data.get("responseId", "")),
        "usage": Usage(
            input_tokens=_int(usage.get("promptTokenCount")),
            cached_input_tokens=_int(usage.get("cachedContentTokenCount")),
            output_tokens=_int(usage.get("candidatesTokenCount")) + _int(thoughts),
            reasoning_tokens=None if thoughts is None else _int(thoughts),
        ),
        "refusal": None,
    }
    blocked = (data.get("promptFeedback") or {}).get("blockReason")
    candidates = data.get("candidates") or []
    if blocked or not candidates:
        status = "PROMPT_BLOCKED" if blocked else "NO_CANDIDATE"
        return ProviderAnswer(finish=Finish(status=status, reason=blocked), text=None, **meta)
    candidate = candidates[0]
    parts = (candidate.get("content") or {}).get("parts") or []
    texts = [p["text"] for p in parts if isinstance(p.get("text"), str) and not p.get("thought")]
    categories = [
        str(r.get("category"))
        for r in candidate.get("safetyRatings") or []
        if isinstance(r, dict) and r.get("blocked")
    ]
    finish = Finish(
        status=str(candidate.get("finishReason", "")), reason=None, safety_categories=categories
    )
    return ProviderAnswer(finish=finish, text="".join(texts) if texts else None, **meta)


def answer_from_body(model: str, raw: str, latency_s: float) -> ProviderAnswer:
    """Read an HTTP 200 body; a body that is not a JSON object is an outage (cut transfer)."""
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ProviderUnavailable("the body of an HTTP 200 answer is not JSON") from exc
    if not isinstance(data, dict):
        raise ProviderUnavailable("the body of an HTTP 200 answer is not a JSON object")
    if model == "gpt":
        return _openai_answer(data, raw, latency_s)
    return _gemini_answer(data, raw, latency_s)


# ------------------------------------------------------------------------------------ errors


def _retry_after(headers, body: dict) -> float | None:
    """Seconds the API asks to wait: ``Retry-After`` (seconds or HTTP date) or the Gemini
    ``google.rpc.RetryInfo`` ``retryDelay`` (``"12s"``)."""
    value = headers.get("Retry-After") if headers is not None else None
    if value:
        try:
            return max(0.0, float(value))
        except ValueError:
            when = email.utils.parsedate_to_datetime(value) if value else None
            if when is not None:
                return max(0.0, (when - datetime.now(UTC)).total_seconds())
    for detail in (body.get("error") or {}).get("details") or []:
        if isinstance(detail, dict) and str(detail.get("@type", "")).endswith("RetryInfo"):
            delay = str(detail.get("retryDelay", "")).rstrip("s")
            try:
                return max(0.0, float(delay))
            except ValueError:
                return None
    return None


def _daily_quota(body: dict) -> str | None:
    """The quota id of an exhausted DAILY quota in a Gemini 429 (``google.rpc.QuotaFailure``
    with ``PerDay`` in a ``quotaId``), or ``None``: retrying it before the quota resets is useless.
    """
    for detail in (body.get("error") or {}).get("details") or []:
        if not isinstance(detail, dict) or not str(detail.get("@type", "")).endswith(
            "QuotaFailure"
        ):
            continue
        for violation in detail.get("violations") or []:
            quota = str((violation or {}).get("quotaId", ""))
            if "PerDay" in quota:
                limit = (violation or {}).get("quotaValue")
                return f"{quota}, limit {limit}" if limit else quota
    return None


def classify_http_error(model: str, code: int, text: str, headers=None) -> Exception:
    """The exception for an HTTP error of ``model`` (contracts/providers.md, the error tables)."""
    try:
        body = json.loads(text)
        body = body if isinstance(body, dict) else {}
    except (json.JSONDecodeError, ValueError):
        body = {}
    error = body.get("error") if isinstance(body.get("error"), dict) else {}
    message = str(error.get("message") or text)[:300]
    detail = f"HTTP {code}: {message}"
    retry_after = _retry_after(headers, body)
    key_name = config.ENV_API_KEY[model]
    if model == "gpt" and code == 429 and error.get("code") == "insufficient_quota":
        return ProviderFatal(f"{model}: the quota or credit of the account is exhausted ({detail})")
    daily = _daily_quota(body) if code == 429 else None
    if daily:
        return ProviderFatal(
            f"{model}: the daily request quota of the API is exhausted ({daily}); nothing was "
            f"recorded; run generate --model {model} --resume after the quota resets"
        )
    if code in (408, 409, 429) or code >= 500:
        return ProviderUnavailable(detail, retry_after_s=retry_after)
    if code in (401, 403):
        return ProviderFatal(f"{model}: the API key in {key_name} was refused ({detail})")
    if code == 404:
        return ProviderFatal(f"{model}: model {config.MODEL_ID[model]} not found ({detail})")
    return ProviderFatal(f"{model}: the request was refused as malformed ({detail})")


# ----------------------------------------------------------------------------------- clients


class _Client:
    key = ""

    def __init__(self, api_key: str, *, timeout_s: float) -> None:
        self._api_key = api_key
        self.timeout_s = timeout_s

    def request_body(self, prompt: str) -> dict:
        return request_body(self.key, prompt)

    def _headers(self) -> dict[str, str]:  # pragma: no cover - replaced in each client
        raise NotImplementedError

    def _scrub(self, text: str) -> str:
        return text.replace(self._api_key, "***") if self._api_key else text

    def call(self, prompt: str) -> ProviderAnswer:
        data = json.dumps(self.request_body(prompt)).encode("utf-8")
        request = urllib.request.Request(
            config.ENDPOINT[self.key], data=data, method="POST", headers=self._headers()
        )
        started = time.monotonic()
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            text = exc.read().decode("utf-8", errors="replace")
            error = classify_http_error(self.key, exc.code, self._scrub(text), exc.headers)
            raise error from None
        except TimeoutError:
            raise ProviderUnavailable(f"timed out after {self.timeout_s} s") from None
        except http.client.HTTPException as exc:  # a body cut short, and alike
            raise ProviderUnavailable(f"the connection broke: {type(exc).__name__}") from None
        except (urllib.error.URLError, ConnectionError, OSError) as exc:
            reason = getattr(exc, "reason", exc)
            if isinstance(reason, TimeoutError):
                raise ProviderUnavailable(f"timed out after {self.timeout_s} s") from None
            raise ProviderUnavailable(f"cannot reach the API: {self._scrub(str(reason))}") from None
        return answer_from_body(self.key, raw, time.monotonic() - started)


class OpenAIClient(_Client):
    key = "gpt"

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}


class GeminiClient(_Client):
    key = "gemini"

    def _headers(self) -> dict[str, str]:
        return {"x-goog-api-key": self._api_key, "Content-Type": "application/json"}


CLIENTS = {"gpt": OpenAIClient, "gemini": GeminiClient}


def make_provider(model: str, api_key: str, *, timeout_s: float) -> LLMProvider:
    return CLIENTS[model](api_key, timeout_s=timeout_s)


__all__ = [
    "PROMPT_PLACEHOLDER",
    "LLMProvider",
    "ProviderAnswer",
    "ProviderFatal",
    "ProviderUnavailable",
    "answer_from_body",
    "classify_http_error",
    "make_provider",
    "request_body",
    "request_parameters",
]
