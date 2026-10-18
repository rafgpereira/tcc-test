"""A stateless client of Ollama: ``POST /api/chat`` with ONE message, nothing kept between calls.

Every request is self-contained: ``messages`` has exactly one item (the whole prompt, as ``user``),
and ``context``, ``system``, ``format`` or ``template`` are never sent, so no call can inherit
anything from another. Every option is sent explicitly. A new HTTP connection is opened per request
(standard library ``urllib``, no dependency). The answer is streamed (``"stream": true``, research
R25): a proxy in front of Ollama (Cloudflare closes a request with HTTP 524 after ~100 s without a
byte) sees bytes flowing during the whole generation; the pieces are joined and the metrics read
from the last one, which gives exactly the ``Completion`` of the same call without streaming. A
stream that ends before its last piece is an outage, and nothing of it is kept. The timeout is the
longest wait for the next bytes, not for the whole answer. Errors are split in three: ``OllamaUnavailable`` is an
outage (retry the same call later, never consumes an attempt); ``OllamaConfigError`` means the run
cannot go on as configured (stop, code 3); ``ModelRepetition`` is a failure of the model itself
(Ollama stopped the generation with ``token repeat limit reached``): the same seed would fail
again, so it consumes the attempt.
"""

import dataclasses
import http.client
import json
import urllib.error
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Protocol

from ai_clients.errors import ConfigurationError
from ai_clients.prompt import wire_bytes


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
    """The whole body of one request: one message, every option, the answer streamed (R25)."""
    return {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": True,
        "options": dataclasses.asdict(options),
    }


class OllamaClient:
    """The real client. Holds only its configuration; never a prompt or an answer."""

    def __init__(self, base_url: str, *, timeout_s: float) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s

    def _open(self, method: str, path: str, body: dict | None = None):
        data = wire_bytes(body) if body is not None else None
        request = urllib.request.Request(
            self.base_url + path,
            data=data,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        return urllib.request.urlopen(request, timeout=self.timeout_s)

    @contextmanager
    def _translated(self, path: str) -> Iterator[None]:
        """Turn what the network or the server raise, while sending or reading, into our errors."""
        try:
            yield
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
        except http.client.HTTPException as exc:  # a body cut short (IncompleteRead), and alike
            raise OllamaUnavailable(f"the connection to {path} broke: {exc!r}") from exc
        except (urllib.error.URLError, ConnectionError, OSError) as exc:
            reason = getattr(exc, "reason", exc)
            if isinstance(reason, TimeoutError):
                raise OllamaUnavailable(
                    f"timed out after {self.timeout_s} s waiting for {path}"
                ) from exc
            raise OllamaUnavailable(f"cannot reach {self.base_url}: {reason}") from exc

    def _request(self, method: str, path: str, body: dict | None = None) -> dict:
        with self._translated(path), self._open(method, path, body) as response:
            raw = response.read()
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise OllamaUnavailable(f"the answer of {path} is not JSON") from exc

    def _stream_chat(self, body: dict) -> tuple[str, dict]:
        """The joined content and the last piece (``done: true``) of a streamed ``/api/chat``."""
        path = "/api/chat"
        pieces: list[str] = []
        with self._translated(path), self._open("POST", path, body) as response:
            for line in response:  # one JSON object per line
                if not line.strip():
                    continue
                try:
                    chunk = json.loads(line)
                except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                    raise OllamaUnavailable(f"a line of the answer of {path} is not JSON") from exc
                if not isinstance(chunk, dict):
                    raise OllamaUnavailable(f"a line of the answer of {path} is not an object")
                if "error" in chunk:  # an error after the 200 was sent arrives in the stream
                    detail = line.decode("utf-8", errors="replace").strip()[:500]
                    if REPETITION_ERROR in detail:
                        raise ModelRepetition(f"error in the stream of {path}: {detail}")
                    raise OllamaUnavailable(f"error in the stream of {path}: {detail}")
                message = chunk.get("message")
                if not isinstance(message, dict) or not isinstance(message.get("content"), str):
                    raise OllamaUnavailable(
                        f"a line of the answer of {path} has no message content"
                    )
                pieces.append(message["content"])
                if chunk.get("done") is True:
                    return "".join(pieces), chunk
        # The connection closed cleanly but without the last piece: never keep a partial answer.
        raise OllamaUnavailable(f"the answer of {path} ended before its last piece (done)")

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
        content, answer = self._stream_chat(request_body(model, prompt, options))
        return Completion(
            content=content,
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
