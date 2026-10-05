"""The generation phase: one stateless call per attempt; nothing is executed here.

For each problem × scenario pending a generation: build the prompt, make ONE call with the seed of
the attempt (``42 + n``), and record the raw answer and how it was read. An answer that cannot be
read is a failed attempt and the next seed is called at once (there is nothing to execute); after
the 6th failure the suite is discarded. A call the model itself fails (Ollama's ``token repeat
limit reached``) is recorded the same way, with the reason ``repetition``: the same seed would
loop again, so it is never repeated. An outage never consumes an attempt: the same call, with the
same seed, is repeated after a wait that doubles from 5 s up to 60 s, until the retry ceiling (then
the command stops and nothing of that attempt is recorded).
"""

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from ai_clients import config, store
from ai_clients.errors import InfrastructureError
from ai_clients.ollama import (
    Completion,
    GenerationOptions,
    ModelRepetition,
    OllamaConfigError,
    OllamaUnavailable,
    SLMClient,
)
from ai_clients.parser import parse_response
from ai_clients.problem import ProblemInput, load_problem
from ai_clients.prompt import PromptTemplate, build_prompt, prompt_sha256
from ai_clients.schemas.generation import (
    GenerationRecord,
    ModelFailure,
    OllamaMeta,
    UnparsedResponse,
)
from ai_clients.schemas.run import RunConfig, SamplingOptions
from mutation import dataset_gate


class Clock(Protocol):
    def sleep(self, seconds: float) -> None: ...


class SystemClock:
    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)


def utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def sampling_options() -> SamplingOptions:
    return SamplingOptions(
        temperature=config.TEMPERATURE,
        top_p=config.TOP_P,
        top_k=config.TOP_K,
        repeat_penalty=config.REPEAT_PENALTY,
        num_ctx=config.NUM_CTX,
        num_predict=config.NUM_PREDICT,
    )


def generation_options(run: RunConfig, attempt: int) -> GenerationOptions:
    return GenerationOptions(**run.options.model_dump(), seed=run.seed_base + attempt)


def _with_retries(call: Callable, *, what: str, seed: int | None, max_retries, clock, echo):
    """Run ``call`` until it answers, waiting after each outage; stop at the retry ceiling."""
    wait, retries = config.BACKOFF_START_S, 0
    while True:
        try:
            return call()
        except OllamaUnavailable as exc:
            if retries >= max_retries:
                raise InfrastructureError(
                    f"ollama unavailable after {retries} consecutive retries ({exc}); "
                    f"nothing was recorded for {what}; run generate --resume when the service "
                    "is back"
                ) from exc
            retries += 1
            same = f"the same call (seed {seed})" if seed is not None else "the same call"
            echo(
                f"ollama unavailable ({exc}); retrying {same} in {wait} s "
                f"(retry {retries} of {max_retries})"
            )
            clock.sleep(wait)
            wait = min(wait * 2, config.BACKOFF_MAX_S)


def current_run_config(
    client: SLMClient,
    template: PromptTemplate,
    root: Path,
    *,
    now: Callable[[], str] = utc_now,
    clock: Clock,
    max_infra_retries: int,
    echo: Callable[[str], None],
    model: str | None = None,
) -> RunConfig:
    """The identity of a run with this model, these options, this template and this dataset.

    ``model`` defaults to ``config.MODEL``, the model of the design.
    """
    model = model or config.MODEL
    info = _with_retries(
        lambda: client.model_info(model),
        what="the model information",
        seed=None,
        max_retries=max_infra_retries,
        clock=clock,
        echo=echo,
    )
    return RunConfig(
        model=model,
        model_digest=info.digest,
        model_quantization=info.quantization_level,
        ollama_version=info.ollama_version,
        options=sampling_options(),
        seed_base=config.SEED_BASE,
        max_attempts=config.MAX_ATTEMPTS,
        prompt_template_sha256=template.sha256,
        dataset_manifest_sha256=dataset_gate.dataset_manifest_sha256(root),
        py_time_factor=config.PY_TIME_FACTOR,
        py_memory_factor=config.PY_MEMORY_FACTOR,
        created_at=now(),
    )


@dataclass
class GenerateResult:
    calls: int = 0
    parsed: int = 0
    unparseable: int = 0
    repetition: int = 0  # calls the model failed itself (token repeat limit reached)
    discarded: int = 0  # suites discarded by this run (6 failed attempts)
    pending_execution: int = 0  # combinations of the selection waiting for `execute` at the end
    damaged: list[store.DamagedCombination] = field(default_factory=list)  # reported, not repaired


def _check_context_window(completion: Completion, run: RunConfig, what: str) -> None:
    """The prompt may have been truncated by Ollama if it plus the answer budget exceed num_ctx."""
    if completion.prompt_eval_count + run.options.num_predict > run.options.num_ctx:
        raise OllamaConfigError(
            f"{what}: prompt_eval_count {completion.prompt_eval_count} + num_predict "
            f"{run.options.num_predict} > num_ctx {run.options.num_ctx}; the prompt may have been "
            "truncated, so nothing was recorded (raise num_ctx in the design and start a new run)"
        )


def _ollama_meta(completion: Completion) -> OllamaMeta:
    return OllamaMeta(
        model=completion.model,
        created_at=completion.created_at,
        done_reason=completion.done_reason,
        prompt_eval_count=completion.prompt_eval_count,
        eval_count=completion.eval_count,
        total_duration_ns=completion.total_duration_ns,
        load_duration_ns=completion.load_duration_ns,
        prompt_eval_duration_ns=completion.prompt_eval_duration_ns,
        eval_duration_ns=completion.eval_duration_ns,
    )


def generate(
    root: Path,
    combinations: Sequence[tuple[str, str]],
    client: SLMClient,
    *,
    template: PromptTemplate,
    run: RunConfig,
    hardware_label: Callable[[], str],
    max_infra_retries: int,
    clock: Clock,
    echo: Callable[[str], None],
    limit: int | None = None,
    now: Callable[[], str] = utc_now,
) -> GenerateResult:
    """Call the model for every combination pending a generation, in the order given."""
    result = GenerateResult()
    problems: dict[str, ProblemInput] = {}
    handled = 0
    for problem_id, scenario in combinations:
        try:
            state = store.combination_state(root, problem_id, scenario, run)
        except store.DamagedCombination as exc:
            result.damaged.append(exc)
            continue
        if state.kind == "finalizable":  # interrupted before its suite.json: no call needed
            suite = store.finalize(root, problem_id, scenario, run)
            result.discarded += suite.status == "discarded"
            continue
        if state.kind != "pending_generation":
            continue
        if limit is not None and handled >= limit:
            break
        handled += 1
        if problem_id not in problems:
            problems[problem_id] = load_problem(root, problem_id)
        prompt = build_prompt(template, problems[problem_id], scenario)
        attempt = state.attempt
        while True:
            what = f"{problem_id} {scenario} attempt {attempt}"
            options = generation_options(run, attempt)
            try:
                completion = _with_retries(
                    lambda options=options, prompt=prompt: client.complete(
                        run.model, prompt, options
                    ),
                    what=what,
                    seed=options.seed,
                    max_retries=max_infra_retries,
                    clock=clock,
                    echo=echo,
                )
            except ModelRepetition as exc:
                completion, failure = None, ModelFailure(reason="repetition", detail=exc.detail)
                parse = UnparsedResponse(ok=False, error=failure.reason)
            else:
                _check_context_window(completion, run, what)
                failure, parse = None, parse_response(completion.content)
            record = GenerationRecord(
                problem_id=problem_id,
                scenario=scenario,
                attempt=attempt,
                seed=options.seed,
                model_digest=run.model_digest,
                prompt_sha256=prompt_sha256(prompt),
                raw_response="" if completion is None else completion.content,
                ollama=None if completion is None else _ollama_meta(completion),
                hardware_label=hardware_label(),
                requested_at=now(),
                parse=parse,
                model_failure=failure,
            )
            store.write_generation(root, record)
            result.calls += 1
            if completion is None:
                echo(f"{what} seed {options.seed}: model failure (repetition) — {failure.detail}")
            else:
                outcome = (
                    f"parsed ({len(parse.inputs)} inputs)"
                    if parse.ok
                    else f"unparseable ({parse.error})"
                )
                echo(
                    f"{what} seed {options.seed}: {outcome} — {completion.prompt_eval_count}+"
                    f"{completion.eval_count} tokens, {completion.done_reason}, "
                    f"{completion.total_duration_ns / 1e9:.1f} s"
                )
            if parse.ok:
                result.parsed += 1
                break
            if completion is None:
                result.repetition += 1
            else:
                result.unparseable += 1
            if attempt == run.max_attempts:
                store.finalize(root, problem_id, scenario, run)
                result.discarded += 1
                break
            attempt += 1
    result.pending_execution = store.count_in_state(root, combinations, "pending_execution", run)
    return result
