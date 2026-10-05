"""A stateless client of Ollama: ``POST /api/chat`` with ONE message, nothing kept between calls.

Every request is self-contained: ``messages`` has exactly one item (the whole prompt, as ``user``),
and ``context``, ``system``, ``format`` or ``template`` are never sent, so no call can inherit
anything from another. Every option is sent explicitly. A new HTTP connection is opened per request
(standard library ``urllib``, no dependency). Errors are split in three: ``OllamaUnavailable`` is an
outage (retry the same call later, never consumes an attempt); ``OllamaConfigError`` means the run
cannot go on as configured (stop, code 3); ``ModelRepetition`` is a failure of the model itself
(Ollama stopped the generation with ``token repeat limit reached``): the same seed would fail
again, so it consumes the attempt.
"""

import dataclasses
import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Protocol

from ai_clients.errors import ConfigurationError


@dataclass(frozen=True)
class GenerationOptions:
    temperature: float
    top_p: float
    top_k: int
    repeat_penalty: float
    num_ctx: int
    num_predict: int
    seed: int


@dataclass(frozen=True)
class Completion:
    content: str  # message.content, whole
    model: str
    created_at: str
    done_reason: str
    prompt_eval_count: int
    eval_count: int
    total_duration_ns: int
    load_duration_ns: int
    prompt_eval_duration_ns: int
    eval_duration_ns: int


@dataclass(frozen=True)
class ModelInfo:
    digest: str
    quantization_level: str
    ollama_version: str


# The code an ngrok tunnel puts in its error page (ERR_NGROK_3200: the tunnel is offline).
TUNNEL_ERROR = "ERR_NGROK_"
# What Ollama answers (HTTP 500) when the model loops on the same tokens and it stops the generation.
REPETITION_ERROR = "token repeat limit reached"


class OllamaUnavailable(Exception):
    """An outage (refused connection, DNS, timeout, HTTP 5xx, a tunnel that is down, a body that
    is not JSON)."""


class ModelRepetition(Exception):
    """The model looped on the same tokens and Ollama stopped it: a failed attempt, not an outage."""

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


class OllamaConfigError(ConfigurationError):
    """HTTP 4xx, a model that is not installed: nothing will work until the operator acts."""


class SLMClient(Protocol):
    def model_info(self, model: str) -> ModelInfo: ...

    def complete(self, model: str, prompt: str, options: GenerationOptions) -> Completion: ...


def request_body(model: str, prompt: str, options: GenerationOptions) -> dict[str, Any]:
    """The whole body of one request: one message, every option, no streaming."""
    return {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": dataclasses.asdict(options),
    }


class OllamaClient:
    """The real client. Holds only its configuration; never a prompt or an answer."""

    def __init__(self, base_url: str, *, timeout_s: float) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s

    def _request(self, method: str, path: str, body: dict | None = None) -> dict:
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = urllib.request.Request(
            self.base_url + path,
            data=data,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            if REPETITION_ERROR in detail:
                raise ModelRepetition(f"HTTP {exc.code} from {path}: {detail}") from exc
            # A tunnel in front of Ollama (ngrok) answers 4xx with an `ERR_NGROK_<n>` code while
            # it is down: that is an outage of the service, not a wrong configuration.
            if exc.code >= 500 or TUNNEL_ERROR in detail:
                raise OllamaUnavailable(f"HTTP {exc.code} from {path}: {detail}") from exc
            raise OllamaConfigError(f"HTTP {exc.code} from {path}: {detail}") from exc
        except TimeoutError as exc:
            raise OllamaUnavailable(
                f"timed out after {self.timeout_s} s waiting for {path}"
            ) from exc
        except (urllib.error.URLError, ConnectionError, OSError) as exc:
            reason = getattr(exc, "reason", exc)
            if isinstance(reason, TimeoutError):
                raise OllamaUnavailable(
                    f"timed out after {self.timeout_s} s waiting for {path}"
                ) from exc
            raise OllamaUnavailable(f"cannot reach {self.base_url}: {reason}") from exc
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise OllamaUnavailable(f"the answer of {path} is not JSON") from exc

    def model_info(self, model: str) -> ModelInfo:
        version = self._request("GET", "/api/version").get("version", "")
        for entry in self._request("GET", "/api/tags").get("models", []):
            if model in (entry.get("name"), entry.get("model")):
                return ModelInfo(
                    digest=entry.get("digest", ""),
                    quantization_level=(entry.get("details") or {}).get("quantization_level", ""),
                    ollama_version=version,
                )
        raise OllamaConfigError(
            f"model {model} is not installed on {self.base_url}; run: ollama pull {model}"
        )

    def complete(self, model: str, prompt: str, options: GenerationOptions) -> Completion:
        answer = self._request("POST", "/api/chat", request_body(model, prompt, options))
        message = answer.get("message")
        if not isinstance(message, dict) or not isinstance(message.get("content"), str):
            raise OllamaUnavailable("the answer of /api/chat has no message content")
        return Completion(
            content=message["content"],
            model=answer.get("model", model),
            created_at=answer.get("created_at", ""),
            done_reason=answer.get("done_reason", ""),
            prompt_eval_count=int(answer.get("prompt_eval_count", 0)),
            eval_count=int(answer.get("eval_count", 0)),
            total_duration_ns=int(answer.get("total_duration", 0)),
            load_duration_ns=int(answer.get("load_duration", 0)),
            prompt_eval_duration_ns=int(answer.get("prompt_eval_duration", 0)),
            eval_duration_ns=int(answer.get("eval_duration", 0)),
        )
