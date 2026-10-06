"""The generation phase: one stateless call per attempt; nothing is executed here.

For each problem × scenario pending a generation: build the prompt, make ONE call with the seed of
the attempt (``42 + n``), and record the raw answer and how it was read. An answer that cannot be
read is a failed attempt and the next seed is called at once (there is nothing to execute), unless
the combination got a suite without one (``config.py``: a fallback after the 8th, a low-confidence
suite after the 20th) or awaits manual handling (the 23rd). Attempts 21 to 23 ask for a prediction
with the second template; a parsed one is the suite at once (``accepted_predicted``), since there
is no solution to execute. A call the model itself fails (Ollama's ``token repeat
limit reached``) is recorded the same way, with the reason ``repetition``: the same seed would
loop again, so it is never repeated. An outage never consumes an attempt: the same call, with the
same seed, is repeated after a wait that doubles from 5 s up to 60 s, until the retry ceiling (then
the command stops and nothing of that attempt is recorded).
"""

import time
from collections import Counter
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
from ai_clients.parser import parse_prediction, parse_response
from ai_clients.problem import ProblemInput, load_problem
from ai_clients.prompt import PromptTemplate, build_prompt, load_template, prompt_sha256
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
    predict_template: PromptTemplate | None = None,
) -> RunConfig:
    """The identity of a run with this model, these options, these templates and this dataset.

    ``model`` defaults to ``config.MODEL``, the model of the design; ``predict_template`` to the
    template of the prediction attempts (``config.PREDICT_TEMPLATE_PATH``).
    """
    model = model or config.MODEL
    predict_template = predict_template or load_template(config.PREDICT_TEMPLATE_PATH)
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
        strict_attempts=config.STRICT_ATTEMPTS,
        solution_attempts=config.SOLUTION_ATTEMPTS,
        predict_attempts=config.PREDICT_ATTEMPTS,
        max_attempts=config.MAX_ATTEMPTS,
        prompt_template_sha256=template.sha256,
        predict_template_sha256=predict_template.sha256,
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
    # suites this run recorded without an execution, by status (accepted_fallback,
    # accepted_low_confidence after an interruption, accepted_predicted)
    suites: Counter = field(default_factory=Counter)
    pending_execution: int = 0  # combinations of the selection waiting for `execute` at the end
    awaiting_manual: list[tuple[str, str]] = field(default_factory=list)  # selection, at the end
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


def _record_suite(root, problem_id, scenario, run, result: GenerateResult, echo) -> None:
    """Write the ``suite.json`` of a finalizable combination (no call is needed for it)."""
    suite = store.finalize(root, problem_id, scenario, run)
    echo(f"{problem_id} {scenario}: suite recorded ({suite.status.value})")
    result.suites[suite.status.value] += 1


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
    predict_template: PromptTemplate | None = None,
) -> GenerateResult:
    """Call the model for every combination pending a generation, in the order given.

    Attempts 1..SOLUTION_ATTEMPTS use ``template`` and ask for a solution; the last ones use
    ``predict_template`` (default: ``config.PREDICT_TEMPLATE_PATH``) and ask for a prediction,
    whose parsed answer is the suite at once (nothing to execute).
    """
    templates = {
        "solution": (template, parse_response),
        "prediction": (
            predict_template or load_template(config.PREDICT_TEMPLATE_PATH),
            parse_prediction,
        ),
    }
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
            _record_suite(root, problem_id, scenario, run, result, echo)
            continue
        if state.kind != "pending_generation":
            continue
        if limit is not None and handled >= limit:
            break
        handled += 1
        if problem_id not in problems:
            problems[problem_id] = load_problem(root, problem_id)
        attempt = state.attempt
        while True:
            what = f"{problem_id} {scenario} attempt {attempt}"
            kind = config.attempt_kind(attempt)
            chosen, parse_answer = templates[kind]
            prompt = build_prompt(chosen, problems[problem_id], scenario)
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
                failure, parse = None, parse_answer(completion.content)
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
                if not parse.ok:
                    outcome = f"unparseable ({parse.error})"
                elif kind == "prediction":
                    outcome = f"parsed ({len(parse.tests)} tests)"
                else:
                    outcome = f"parsed ({len(parse.inputs)} inputs)"
                echo(
                    f"{what} seed {options.seed}: {outcome} — {completion.prompt_eval_count}+"
                    f"{completion.eval_count} tokens, {completion.done_reason}, "
                    f"{completion.total_duration_ns / 1e9:.1f} s"
                )
            if parse.ok:
                result.parsed += 1
            elif completion is None:
                result.repetition += 1
            else:
                result.unparseable += 1
            if parse.ok and kind == "solution":
                break  # the solution runs in `execute`
            state = store.combination_state(root, problem_id, scenario, run)
            if state.kind == "finalizable":  # a prediction, a fallback or a low-confidence suite
                _record_suite(root, problem_id, scenario, run, result, echo)
                break
            if state.kind == "awaiting_manual":
                echo(f"{problem_id} {scenario}: awaiting manual handling")
                break
            attempt = state.attempt
    result.pending_execution = store.count_in_state(root, combinations, "pending_execution", run)
    result.awaiting_manual = store.awaiting_manual(root, combinations, run)
    return result
