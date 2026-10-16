"""The ``generate`` of a commercial model: N calls at a time, never paying without control.

For every selected problem x scenario still pending, in canonical order, a worker thread claims
the combination and makes its attempts one after the other: the prompt (the text-base with only
``<context_data>`` varying), ONE self-contained call, the raw answer and the attempt recorded, then
the interpretation; a parsed attempt becomes ``suite.json`` (``accepted_predicted``), a format
failure leads to the next attempt, and after 3 the combination awaits the authors (``close``).

A coordinator hands out the combinations and stops handing them out (and every worker stops
before its next call) as soon as one of these happens (research R8):

* the spend cap of the invocation is reached (sum of the cost of every answered call, barred ones
  included; FR-022a): exit code 5;
* an answer reports no reasoning (FR-018a): it is recorded in ``barred/``, never as an attempt:
  exit code 6;
* the API stays unavailable after the retry ceiling (FR-018): exit code 3, nothing recorded for
  that call;
* an error that does not go away (key, quota, model, malformed request): exit code 3;
* an interruption (Ctrl+C, ``docker stop``): exit code 130.

Calls already sent always finish and are recorded (atomic writes), so stopping never leaves a
partial file. An infrastructure failure never consumes an attempt: the same call is made again
after an increasing wait, or the wait the API asks for when it is longer.
"""

import threading
import time
from collections.abc import Callable
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path

from ai_clients import problem as problems
from ai_clients.llm import config, cost, store
from ai_clients.llm.interpret import interpret, needs_barrier
from ai_clients.llm.providers import (
    LLMProvider,
    ProviderAnswer,
    ProviderFatal,
    ProviderUnavailable,
    request_parameters,
)
from ai_clients.llm.schemas import (
    BarredResponse,
    LlmAttempt,
    LlmRunConfig,
    price_table,
    response_schema,
)
from ai_clients.prompt import PromptTemplate, build_prompt, prompt_sha256
from mutation import dataset_gate


class SystemClock:
    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)

    def wait(self, seconds: float, wake: threading.Event) -> None:
        """Wait ``seconds``, or less if ``wake`` is set (the invocation stops: Ctrl+C included)."""
        wake.wait(timeout=seconds)

    def monotonic(self) -> float:
        return time.monotonic()

    def utc_now(self) -> str:
        return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def current_run_config(root: Path, model: str, template: PromptTemplate, now: str) -> LlmRunConfig:
    """The identity of a run of ``model`` with this text-base and this dataset."""
    return LlmRunConfig(
        model_key=model,
        model_requested=config.MODEL_ID[model],
        endpoint=config.ENDPOINT[model],
        request_parameters=request_parameters(model),
        response_schema=response_schema(),
        template_sha256=template.sha256,
        max_attempts=config.MAX_ATTEMPTS,
        dataset_manifest_sha256=dataset_gate.dataset_manifest_sha256(root),
        price_table=price_table(),
        created_at=now,
    )


STOP_CODES = {"interrupted": 130, "infra": 3, "fatal": 3, "barred": 6, "spend_cap": 5}


@dataclass
class GenerateResult:
    calls: int = 0  # answered calls recorded as attempts
    parsed: int = 0
    format_failures: int = 0
    suites: int = 0  # suite.json written by this command
    barred: list[tuple[str, str, Path]] = field(default_factory=list)
    awaiting_manual: list[tuple[str, str]] = field(default_factory=list)
    damaged: list = field(default_factory=list)
    skipped: int = 0
    spent: float = 0.0
    stop: str | None = None  # one of STOP_CODES, the first that happened
    stop_message: str = ""


class _Coordinator:
    """The shared state of one invocation: what was spent and whether to stop."""

    def __init__(self, spend_cap: float | None) -> None:
        self.lock = threading.Lock()
        self.spend_cap = spend_cap
        self.result = GenerateResult()
        self.wake = threading.Event()  # set when the invocation stops: every wait ends at once

    def stopped(self) -> bool:
        with self.lock:
            return self.result.stop is not None

    def stop(self, reason: str, message: str = "") -> None:
        with self.lock:
            if self.result.stop is None:
                self.result.stop, self.result.stop_message = reason, message
        self.wake.set()

    def spend(self, amount: float) -> None:
        with self.lock:
            self.result.spent = round(self.result.spent + amount, 8)
            reached = self.spend_cap is not None and self.result.spent >= self.spend_cap
        if reached:
            self.stop("spend_cap")


class _Pacer:
    """At most ``per_minute`` request starts per minute in this process, retries included: the
    starts are spaced by 60 / ``per_minute`` seconds, whatever the thread (the request limits of
    the APIs, e.g. 5 per minute on the free tier of the Gemini API)."""

    def __init__(self, per_minute: int | None) -> None:
        self.interval = 60.0 / per_minute if per_minute else 0.0
        self.lock = threading.Lock()
        self.next_start: float | None = None

    def delay(self, now: float) -> float:
        """The wait before the next start (and that start booked)."""
        if not self.interval:
            return 0.0
        with self.lock:
            start = now if self.next_start is None else max(now, self.next_start)
            self.next_start = start + self.interval
        return start - now


def _today(clock) -> date:
    return date.fromisoformat(clock.utc_now()[:10])


def _per_call_line(problem_id, scenario, record: LlmAttempt) -> str:
    parse, usage = record.parse, record.usage
    what = (
        f"parsed ({len(parse.tests)} tests)"
        if parse.ok
        else f"{parse.failure.value} ({parse.detail})"
    )
    return (
        f"{problem_id} {scenario} attempt {record.attempt}: {what} — in {usage.input_tokens} "
        f"(cache {usage.cached_input_tokens}) out {usage.output_tokens} (reasoning "
        f"{usage.reasoning_tokens}) tokens, US$ {record.cost_usd:.4f}, {record.latency_s:.1f} s"
    )


@dataclass
class _Context:
    root: Path
    model: str
    provider: LLMProvider
    template: PromptTemplate
    run: LlmRunConfig
    clock: object
    echo: Callable[[str], None]
    max_infra_retries: int
    coordinator: _Coordinator
    pacer: _Pacer


def _call_with_retries(ctx: _Context, prompt: str, what: str) -> ProviderAnswer | None:
    """The answer, or ``None`` if the invocation stops first (nothing is recorded then)."""
    wait_s, retries = config.BACKOFF_START_S, 0
    while True:
        if ctx.coordinator.stopped():
            return None
        delay = ctx.pacer.delay(ctx.clock.monotonic())
        if delay > 0:
            ctx.clock.wait(delay, ctx.coordinator.wake)
            if ctx.coordinator.stopped():
                return None
        try:
            return ctx.provider.call(prompt)
        except ProviderUnavailable as exc:
            if retries >= ctx.max_infra_retries:
                ctx.coordinator.stop(
                    "infra",
                    f"{ctx.model} unavailable after {retries} consecutive retries ({exc.reason}); "
                    f"nothing was recorded for {what}; run generate --model {ctx.model} --resume "
                    "when the service is back",
                )
                return None
            retries += 1
            pause = max(wait_s, exc.retry_after_s or 0)
            ctx.echo(
                f"{ctx.model} unavailable ({exc.reason}); retrying the same call in {pause:g} s "
                f"(retry {retries} of {ctx.max_infra_retries})"
            )
            ctx.clock.wait(pause, ctx.coordinator.wake)
            wait_s = min(wait_s * 2, config.BACKOFF_MAX_S)
        except ProviderFatal as exc:
            ctx.coordinator.stop("fatal", str(exc))
            return None


def _attempt(ctx: _Context, problem, scenario: str, n: int) -> LlmAttempt | None:
    """Make attempt ``n``: one call, the answer recorded; ``None`` if nothing was recorded."""
    prompt = build_prompt(ctx.template, problem, scenario)
    requested_at = ctx.clock.utc_now()
    answer = _call_with_retries(ctx, prompt, f"{problem.problem_id} {scenario} attempt {n}")
    if answer is None:
        return None
    row = cost.price_row_for(ctx.model, date.fromisoformat(requested_at[:10]))
    amount = cost.call_cost(answer.usage, row)
    common = {
        "problem_id": problem.problem_id,
        "scenario": scenario,
        "model_requested": ctx.run.model_requested,
        "model_returned": answer.model_returned,
        "response_id": answer.response_id,
        "prompt_sha256": prompt_sha256(prompt),
        "template_sha256": ctx.template.sha256,
        "request_parameters": ctx.run.request_parameters,
        "requested_at": requested_at,
        "latency_s": round(answer.latency_s, 3),
        "raw_body": answer.raw_body,
        "finish": answer.finish,
        "usage": answer.usage,
        "cost_usd": amount,
        "price_row": row,
    }
    if needs_barrier(answer):
        barred = BarredResponse(**common, barred_at=ctx.clock.utc_now())
        path = store.write_barred(ctx.root, ctx.model, barred)
        with ctx.coordinator.lock:
            ctx.coordinator.result.barred.append((problem.problem_id, scenario, path))
        ctx.coordinator.stop("barred")
        ctx.coordinator.spend(amount)
        count = answer.usage.reasoning_tokens
        reported = "no reasoning token count" if count is None else f"{count} reasoning tokens"
        ctx.echo(
            f"barred: {problem.problem_id} {scenario}: the answer reports {reported} (reasoning effort "
            f'"{config.REASONING_LEVEL}" was sent); saved in {path.relative_to(ctx.root).as_posix()}'
        )
        return None
    parse = interpret(answer, problem.testes.public_tests[0])
    record = LlmAttempt(**common, attempt=n, parse=parse)
    store.write_attempt(ctx.root, ctx.model, record)
    with ctx.coordinator.lock:
        result = ctx.coordinator.result
        result.calls += 1
        result.parsed += parse.ok
        result.format_failures += not parse.ok
    ctx.echo(_per_call_line(problem.problem_id, scenario, record))
    ctx.coordinator.spend(amount)
    return record


def _finalize(ctx: _Context, problem_id: str, scenario: str) -> None:
    suite = store.finalize(ctx.root, ctx.model, problem_id, scenario, ctx.run)
    if suite is not None:
        with ctx.coordinator.lock:
            ctx.coordinator.result.suites += 1
        ctx.echo(f"{problem_id} {scenario}: suite recorded ({suite.status.value})")


def _work(ctx: _Context, problem_id: str, scenario: str, loaded: dict) -> None:
    """Everything this invocation does for one combination, under its claim."""
    with store.claim(ctx.root, ctx.model, problem_id, scenario) as mine:
        if not mine:
            with ctx.coordinator.lock:
                ctx.coordinator.result.skipped += 1
            ctx.echo(f"{problem_id} {scenario}: skipped (in use by another command)")
            return
        try:
            state = store.combination_state(ctx.root, ctx.model, problem_id, scenario, ctx.run)
            while state.kind == "pending" and not ctx.coordinator.stopped():
                problem = loaded[problem_id]
                if _attempt(ctx, problem, scenario, state.attempt) is None:
                    return
                state = store.combination_state(ctx.root, ctx.model, problem_id, scenario, ctx.run)
            if state.kind == "finalizable":
                _finalize(ctx, problem_id, scenario)
        except store.DamagedCombination as exc:
            with ctx.coordinator.lock:
                ctx.coordinator.result.damaged.append(exc)


def generate(
    root: Path,
    model: str,
    combinations: list[tuple[str, str]],
    provider: LLMProvider,
    *,
    template: PromptTemplate,
    run: LlmRunConfig,
    clock,
    echo: Callable[[str], None],
    max_infra_retries: int,
    concurrency: int = 1,
    spend_cap: float | None = None,
    limit: int | None = None,
    requests_per_minute: int | None = None,
) -> GenerateResult:
    """Generate the suites of ``combinations`` (canonical order) with up to ``concurrency``
    calls at a time; ``KeyboardInterrupt`` after the calls in flight are recorded."""
    coordinator = _Coordinator(spend_cap)
    lock = threading.Lock()

    def say(message: str) -> None:
        with lock:
            echo(message)

    ctx = _Context(
        root,
        model,
        provider,
        template,
        run,
        clock,
        say,
        max_infra_retries,
        coordinator,
        _Pacer(requests_per_minute),
    )
    loaded: dict = {}
    handed = 0
    slots = threading.Semaphore(concurrency)
    futures: list[Future] = []
    interrupted = False
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        try:
            for problem_id, scenario in combinations:
                if coordinator.stopped():
                    break
                try:  # a quick look, without the claim, to count pending ones for --limit
                    peek = store.combination_state(root, model, problem_id, scenario, run)
                except store.DamagedCombination:
                    peek = None
                if peek is not None and peek.kind in ("terminal", "awaiting_manual"):
                    continue
                if peek is not None and peek.kind == "pending":
                    if limit is not None and handed >= limit:
                        continue
                    handed += 1
                if problem_id not in loaded:
                    loaded[problem_id] = problems.load_problem(root, problem_id)
                acquired = False
                while not acquired and not coordinator.stopped():
                    acquired = slots.acquire(timeout=0.2)
                if coordinator.stopped():
                    if acquired:
                        slots.release()
                    break
                future = pool.submit(_work, ctx, problem_id, scenario, loaded)
                future.add_done_callback(lambda _f: slots.release())
                futures.append(future)
            pending = [f for f in futures if not f.done()]
            while pending:
                _, pending = wait(pending, timeout=0.2, return_when=FIRST_COMPLETED)
        except KeyboardInterrupt:
            interrupted = True
            coordinator.stop("interrupted")
            say("interrupted: no new call is sent; the calls in flight are being recorded")
            wait(futures)
    for future in futures:
        future.result()  # an unexpected error of a worker surfaces here
    result = coordinator.result
    result.awaiting_manual = store.awaiting_manual(root, model, combinations, run)
    if interrupted:
        raise KeyboardInterrupt
    return result
