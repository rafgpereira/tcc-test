"""Test doubles of the commercial models: a fake provider, a clock and realistic HTTP bodies.

No test calls a real API. ``FakeProvider`` answers from a table and records the exact body of every
request, so the tests check what would have been sent; an unexpected call fails the test.
"""

import json
import threading
from dataclasses import dataclass, field

from ai_clients.llm import config
from ai_clients.llm.providers import ProviderFatal, ProviderUnavailable, answer_from_body

SHA = "a" * 64


# ------------------------------------------------------------------------------- HTTP bodies


def answer_json(tests=(("1\n", "1\n"),), analysis="n = 1 is the smallest case.") -> str:
    """The JSON text a model answers (research R4)."""
    return json.dumps(
        {"edge_cases_analysis": analysis, "tests": [{"input": i, "output": o} for i, o in tests]}
    )


def openai_body(
    text: str | None = None,
    *,
    status: str = "completed",
    reason: str | None = None,
    refusal: str | None = None,
    reasoning: int | None = 1200,
    input_tokens: int = 2000,
    cached: int = 0,
    output: int = 1500,
    model: str = "gpt-5.4-mini-2026-03-17",
    response_id: str = "resp_1",
) -> str:
    """A Responses API body: a reasoning item, then a message with output_text or refusal."""
    text = answer_json() if text is None and refusal is None else text
    content = []
    if text is not None:
        content.append({"type": "output_text", "text": text, "annotations": []})
    if refusal is not None:
        content.append({"type": "refusal", "refusal": refusal})
    details = {} if reasoning is None else {"reasoning_tokens": reasoning}
    return json.dumps(
        {
            "id": response_id,
            "object": "response",
            "model": model,
            "status": status,
            "incomplete_details": None if reason is None else {"reason": reason},
            "output": [
                {"type": "reasoning", "id": "rs_1", "summary": []},
                {"type": "message", "id": "msg_1", "role": "assistant", "content": content},
            ],
            "usage": {
                "input_tokens": input_tokens,
                "input_tokens_details": {"cached_tokens": cached},
                "output_tokens": output,
                "output_tokens_details": details,
                "total_tokens": input_tokens + output,
            },
        }
    )


def gemini_body(
    text: str | None = None,
    *,
    finish: str | None = "STOP",
    block_reason: str | None = None,
    blocked: tuple[str, ...] = (),
    thoughts: int | None = 1200,
    prompt_tokens: int = 2000,
    cached: int | None = None,
    candidates: int = 300,
    model_version: str = "gemini-3.8-flash",
    response_id: str = "gem_1",
    with_thought_part: bool = True,
) -> str:
    """A generateContent body: a thought part (ignored), then the answer part."""
    text = answer_json() if text is None else text
    usage = {"promptTokenCount": prompt_tokens, "candidatesTokenCount": candidates}
    if thoughts is not None:
        usage["thoughtsTokenCount"] = thoughts
    if cached is not None:
        usage["cachedContentTokenCount"] = cached
    body = {"usageMetadata": usage, "modelVersion": model_version, "responseId": response_id}
    if block_reason is not None:
        body["promptFeedback"] = {"blockReason": block_reason}
        return json.dumps(body)
    parts = [{"text": "thinking...", "thought": True}] if with_thought_part else []
    if text != "":
        parts.append({"text": text})
    candidate = {"content": {"role": "model", "parts": parts}, "finishReason": finish}
    if blocked:
        candidate["safetyRatings"] = [
            {"category": c, "probability": "HIGH", "blocked": True} for c in blocked
        ]
    body["candidates"] = [candidate]
    return json.dumps(body)


BODY = {"gpt": openai_body, "gemini": gemini_body}


def body(model: str, *args, reasoning: int | None = 1200, **kwargs) -> str:
    """A well-formed body of ``model`` (reasoning tokens under the right name)."""
    if model == "gpt":
        return openai_body(*args, reasoning=reasoning, **kwargs)
    return gemini_body(*args, thoughts=reasoning, **kwargs)


def answer(model: str, *args, latency_s: float = 2.0, **kwargs):
    """A ``ProviderAnswer`` read from a realistic body (the real reader is used)."""
    return answer_from_body(model, body(model, *args, **kwargs), latency_s)


# ------------------------------------------------------------------------------ the provider


def problem_of(prompt: str) -> str:
    """The synthetic problem a prompt is about (its id is in the statement and the code)."""
    for token in prompt.replace("\n", " ").split():
        if "_" in token and token.split("_")[0].isdigit():
            return token.strip("#.,")
    raise AssertionError("no problem id in the prompt")


def scenario_of(prompt: str) -> str:
    statement = "<problem_statement>" in prompt
    code = "<reference_solution_cpp>" in prompt
    return {(True, False): "black_box", (False, True): "white_box", (True, True): "hybrid"}[
        (statement, code)
    ]


@dataclass
class FakeProvider:
    """``(problem, scenario, n) -> ProviderAnswer | exception``; ``n`` counts the calls of that
    combination (retries included). ``default`` answers anything not in the table."""

    key: str
    table: dict = field(default_factory=dict)
    default: object = None
    requests: list = field(default_factory=list)  # (problem, scenario, body) of every call
    in_flight: set = field(default_factory=set)
    overlaps: list = field(default_factory=list)  # a combination called twice at the same time
    on_call: object = None  # callable(problem, scenario, n), run inside the call (tests of timing)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _counts: dict = field(default_factory=dict)

    def request_body(self, prompt: str) -> dict:
        from ai_clients.llm.providers import request_body

        return request_body(self.key, prompt)

    def call(self, prompt: str):
        problem, scenario = problem_of(prompt), scenario_of(prompt)
        with self._lock:
            n = self._counts.get((problem, scenario), 0) + 1
            self._counts[(problem, scenario)] = n
            self.requests.append((problem, scenario, self.request_body(prompt)))
            if (problem, scenario) in self.in_flight:
                self.overlaps.append((problem, scenario))
            self.in_flight.add((problem, scenario))
        try:
            if self.on_call is not None:
                self.on_call(problem, scenario, n)
            result = self.table.get((problem, scenario, n), self.default)
            if result is None:
                raise AssertionError(f"unexpected call: {problem} {scenario} call {n}")
            if callable(result) and not isinstance(result, Exception):
                result = result()
            if isinstance(result, (ProviderUnavailable, ProviderFatal)):
                raise result
            return result
        finally:
            with self._lock:
                self.in_flight.discard((problem, scenario))

    def calls_of(self, problem: str, scenario: str) -> int:
        return self._counts.get((problem, scenario), 0)


@dataclass
class FakeClock:
    """Waits that only record (and advance the monotonic time); ``today`` fixed (the price row)."""

    sleeps: list = field(default_factory=list)
    now: str = "2026-10-20T12:00:00Z"
    elapsed: float = 0.0
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def sleep(self, seconds: float) -> None:
        with self._lock:
            self.sleeps.append(seconds)
            self.elapsed += seconds

    def wait(self, seconds: float, wake) -> None:
        if not wake.is_set():
            self.sleep(seconds)

    def monotonic(self) -> float:
        with self._lock:
            return self.elapsed

    def utc_now(self) -> str:
        return self.now


def unavailable(reason="HTTP 503 from the API", retry_after=None) -> ProviderUnavailable:
    return ProviderUnavailable(reason, retry_after_s=retry_after)


MODELS = config.MODELS
