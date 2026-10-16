"""The commands of ``python -m ai_clients ... --model gpt|gemini`` (contracts/cli.md).

``ai_clients.__main__`` registers the subcommands and hands them here when ``--model`` names a
commercial model; without it, every command does exactly what it did for the SLM. Exit codes: the
SLM ones plus 5 (spend cap reached) and 6 (an answer without reasoning was barred), with the
precedence 130 > 3 > 6 > 1 > 5 > 4 > 0.
"""

import os
import sys
from datetime import date
from pathlib import Path

from ai_clients import prompt
from ai_clients.errors import UsageError
from ai_clients.llm import closing, config, cost, generation, store
from ai_clients.llm.providers import make_provider
from dataset.persistence import store as files

EXIT_OK, EXIT_DATA_FAILURE, EXIT_USAGE, EXIT_INFRA, EXIT_MANUAL = 0, 1, 2, 3, 4
EXIT_SPEND_CAP, EXIT_NO_REASONING, EXIT_INTERRUPTED = 5, 6, 130
PRECEDENCE = (
    EXIT_INTERRUPTED,
    EXIT_INFRA,
    EXIT_NO_REASONING,
    EXIT_DATA_FAILURE,
    EXIT_SPEND_CAP,
    EXIT_MANUAL,
)

# Replaced by the tests (a fake provider, a clock that does not wait).
make_client = make_provider
make_clock = generation.SystemClock


def combine(codes) -> int:
    """The exit code of a command that met several of these situations."""
    for code in PRECEDENCE:
        if code in codes:
            return code
    return EXIT_OK


def _main():  # the helpers shared with the SLM commands (imported late: no import cycle)
    from ai_clients import __main__ as main

    return main


def _tree(model: str) -> str:
    return config.suites_dir(model).as_posix()


def _env_positive_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        value = 0
    if value <= 0:
        raise UsageError(f"{name} must be a positive integer, got {raw!r}")
    return value


def _api_key(model: str) -> str:
    name = config.ENV_API_KEY[model]
    value = os.environ.get(name, "").strip()
    if not value:
        raise UsageError(f"{name} is not set in .env (see .env.example); {model} cannot run")
    return value


def _read_run_if_any(root: Path, model: str):
    return store.read_run(root, model) if store.run_exists(root, model) else None


def report_damage(model: str, damaged: list) -> int:
    for exc in damaged:
        print(f"damaged: {exc}", file=sys.stderr)
    if damaged:
        print(
            f"error: {len(damaged)} damaged combination(s) in {_tree(model)} were left as they "
            "are; nothing was repaired",
            file=sys.stderr,
        )
        return EXIT_DATA_FAILURE
    return EXIT_OK


def close_command(model: str, problem_id: str, scenario: str) -> str:
    return (
        f"docker compose run --rm app python -m ai_clients close --model {model} "
        f'--problem {problem_id} --scenario {scenario} --reason "<reason>"'
    )


def manual_lines(model: str, awaiting) -> None:
    for problem_id, scenario in awaiting:
        print(
            f"manual: {problem_id} {scenario}: {config.MAX_ATTEMPTS} attempts failed by format; "
            f"close it with: {close_command(model, problem_id, scenario)}",
            file=sys.stderr,
        )


# ------------------------------------------------------------------------------ the estimate


def _estimate(root: Path, model: str, combinations, template, limit, today: date):
    """Print the estimate of the pending combinations (nothing is called); the totals."""
    run = _read_run_if_any(root, model)
    loaded, damaged = {}, []
    per_scenario = {s: cost.Estimate() for s in config.SCENARIOS}
    calls_left = {s: 0 for s in config.SCENARIOS}
    taken = 0
    for problem_id, scenario in combinations:
        try:
            state = store.combination_state(root, model, problem_id, scenario, run)
        except store.DamagedCombination as exc:
            damaged.append(exc)
            continue
        if state.kind != "pending":
            continue
        if limit is not None and taken >= limit:
            break
        taken += 1
        if problem_id not in loaded:
            from ai_clients import problem as problems

            loaded[problem_id] = problems.load_problem(root, problem_id)
        size = len(prompt.build_prompt(template, loaded[problem_id], scenario))
        per_scenario[scenario].add(problem_id, size)
        calls_left[scenario] += config.MAX_ATTEMPTS - state.attempt + 1
    total = cost.Estimate()
    ratio, origin = config.CHARS_PER_TOKEN[model], config.CHARS_PER_TOKEN_ORIGIN[model]
    mean = config.MEASURED_MEAN_OUTPUT_TOKENS[model]
    output = f"output {config.MAX_OUTPUT_TOKENS} max" + (f" / {mean} measured" if mean else "")

    def line(label: str, estimate: cost.Estimate, up_to: int) -> tuple[float, float]:
        low, high = cost.cost_range(model, estimate, today)
        tokens = cost.estimated_input_tokens(model, estimate.prompt_chars)
        print(
            f"{model} {label}: {estimate.combinations} combinations, {estimate.combinations} "
            f"calls (up to {up_to}), ~{tokens} input tokens (CHARS_PER_TOKEN={ratio:g} {origin}), "
            f"{output}; US$ {low:.2f}–{high:.2f}"
        )
        return low, high

    for scenario in config.SCENARIOS:
        estimate = per_scenario[scenario]
        if estimate.combinations:
            line(scenario, estimate, calls_left[scenario])
            size, problem_id = estimate.largest_prompt
            print(f"largest prompt: {scenario} {size} chars ({problem_id})")
        total.merge(estimate)
    low, high = line("total", total, sum(calls_left.values()))
    return total, sum(calls_left.values()), low, high, damaged


# ----------------------------------------------------------------------------------- generate


def run_generate(args) -> int:
    main = _main()
    root, model = Path("."), args.model
    failed = main.dataset_gate(root)
    if failed is not None:
        return failed
    combinations = main.selected_combinations(root, args)
    template = prompt.load_template(config.LLM_TEMPLATE_PATH)
    clock = make_clock()
    today = date.fromisoformat(clock.utc_now()[:10])
    if args.dry_run or args.confirm_spend is None:
        _, calls, low, high, damaged = _estimate(
            root, model, combinations, template, args.limit, today
        )
        if args.dry_run:
            print("dry run: nothing was called nor recorded")
            return report_damage(model, damaged)
        raise UsageError(
            f"this would make up to {calls} paid calls (estimated US$ {low:.2f} to {high:.2f}); "
            "to confirm, run again with --confirm-spend <max US$ for this run>"
        )
    key = _api_key(model)
    concurrency = _env_positive_int(
        config.ENV_MAX_CONCURRENCY[model], config.DEFAULT_MAX_CONCURRENCY
    )
    retries = _env_positive_int(
        config.ENV_MAX_INFRA_RETRIES[model], config.DEFAULT_MAX_INFRA_RETRIES
    )
    timeout_s = _env_positive_int(config.ENV_HTTP_TIMEOUT_S, config.DEFAULT_HTTP_TIMEOUT_S)
    per_minute_name = config.ENV_MAX_REQUESTS_PER_MINUTE[model]
    per_minute = _env_positive_int(per_minute_name, 1) if os.environ.get(per_minute_name) else None
    exists = store.run_exists(root, model)
    if exists and not args.resume:
        raise UsageError(f"a run already exists in {_tree(model)}; use --resume to continue it")
    if args.resume and not exists:
        raise UsageError(
            f"nothing to resume: {_tree(model)}/run.json does not exist; run generate without "
            "--resume to start a run"
        )
    provider = make_client(model, key, timeout_s=timeout_s)

    def echo(message: str) -> None:
        print(message, flush=True)

    lock = store.shared_run if args.resume else store.exclusive_run
    with lock(root, model):
        current = generation.current_run_config(root, model, template, clock.utc_now())
        if args.resume:
            run = store.read_run(root, model)
            differences = run.differences(current)
            if differences:
                lines = "\n".join(
                    f"  {name}: recorded {recorded!r}, current {now!r}"
                    for name, recorded, now in differences
                )
                hint = ""
                if "template_sha256" in {d[0] for d in differences}:
                    hint = (
                        "; or, if the text-base was changed on purpose: docker compose run --rm "
                        f"app python -m ai_clients change-template --model {model} --template llm "
                        '--reason "<reason>"'
                    )
                raise UsageError(
                    f"the configuration differs from {_tree(model)}/run.json, and a run never "
                    f"mixes configurations:\n{lines}\nrestore the recorded configuration, or move "
                    f"{_tree(model)} away to start a new run{hint}"
                )
        else:
            store.write_run(root, model, current)
            run = current
        try:
            result = generation.generate(
                root,
                model,
                combinations,
                provider,
                template=template,
                run=run,
                clock=clock,
                echo=echo,
                max_infra_retries=retries,
                concurrency=concurrency,
                spend_cap=args.confirm_spend,
                limit=args.limit,
                requests_per_minute=per_minute,
            )
        except KeyboardInterrupt:
            print(
                f"interrupted; it is safe to run the command again with --model {model} --resume",
                file=sys.stderr,
            )
            return EXIT_INTERRUPTED
    skipped = main.skipped_note(result.skipped)
    print(
        f"done: {result.calls} calls, {result.parsed} parsed, {result.format_failures} format "
        f"failures; suites: {result.suites} accepted_predicted; {len(result.awaiting_manual)} "
        f"awaiting manual handling; spent US$ {result.spent:.4f} (cap US$ "
        f"{args.confirm_spend:g}){skipped}"
    )
    codes = {report_damage(model, result.damaged)}
    manual_lines(model, result.awaiting_manual)
    if result.awaiting_manual:
        codes.add(EXIT_MANUAL)
    if result.stop in ("infra", "fatal"):
        print(f"error: {result.stop_message}", file=sys.stderr)
        codes.add(EXIT_INFRA)
    if result.barred:
        print(
            "barred: nothing new was sent; investigate before resuming (the answer is in "
            f"{_tree(model)}/{config.BARRED_DIR}/)",
            file=sys.stderr,
        )
        codes.add(EXIT_NO_REASONING)
    if result.stop == "spend_cap" or (
        result.spent >= args.confirm_spend and result.stop is not None
    ):
        over = max(result.spent - args.confirm_spend, 0)
        print(
            f"spend cap reached: spent US$ {result.spent:.4f} of US$ {args.confirm_spend:g} "
            f"(US$ {over:.4f} over the cap by the calls already in flight); nothing new was "
            f"sent; continue with: docker compose run --rm app python -m ai_clients generate "
            f"--model {model} --resume --confirm-spend <new cap>",
            file=sys.stderr,
        )
        codes.add(EXIT_SPEND_CAP)
    return combine(codes)


# -------------------------------------------------------------------------------------- close


def run_close(args) -> int:
    main = _main()
    root, model = Path("."), args.model
    failed = main.dataset_gate(root)
    if failed is not None:
        return failed
    from ai_clients import problem as problems

    if args.problem not in problems.list_problem_ids(root):
        raise UsageError(f"not in data/dataset: {args.problem}")
    if not store.run_exists(root, model):
        raise UsageError(f"{_tree(model)}/run.json does not exist; run generate first")
    run = store.read_run(root, model)
    clock = make_clock()
    try:
        record = closing.manual_close_record(
            args.problem, args.scenario, args.reason, now=clock.utc_now
        )
    except ValueError as exc:
        raise UsageError("--reason must not be empty") from exc
    try:
        if args.dry_run:
            closing.check_awaiting(root, model, args.problem, args.scenario, run)
            print(files.dumps_json(record), end="")
            print("dry run: nothing was recorded")
            return EXIT_OK
        with store.exclusive_run(root, model):
            suite = closing.close(
                root,
                model,
                args.problem,
                args.scenario,
                args.reason,
                run=run,
                now=lambda: record.closed_at,
            )
    except closing.NotAwaitingManual as exc:
        raise UsageError(str(exc)) from exc
    except store.DamagedCombination as exc:
        return report_damage(model, [exc])
    print(f"{args.problem} {args.scenario}: suite recorded ({suite.status.value})")
    return EXIT_OK


# ---------------------------------------------------------------------------- change-template


def run_change_template(args) -> int:
    from ai_clients.llm import template_change
    from ai_clients.report import DamagedTreeError

    main = _main()
    root, model = Path("."), args.model
    failed = main.dataset_gate(root)
    if failed is not None:
        return failed
    if not store.run_exists(root, model):
        raise UsageError(f"{_tree(model)}/run.json does not exist; run generate first")
    if not args.reason.strip():
        raise UsageError("--reason must not be empty")
    template = prompt.load_template(config.LLM_TEMPLATE_PATH)
    clock = make_clock()
    try:
        if args.dry_run:
            changes = store.template_changes(root, model)
            if changes and template_change.files_left(root, model, changes[-1]):
                left = template_change.files_left(root, model, changes[-1])
                print(
                    f"dry run: change {changes[-1].number} was interrupted with {left} file(s) "
                    "still to move; run the command without --dry-run to finish it"
                )
                return EXIT_OK
            number = len(changes) + 1
            planned = template_change.plan_change(
                root,
                model,
                template,
                args.reason,
                run=store.read_run(root, model),
                number=number,
                now=clock.utc_now,
            )
            for item in planned.superseded:
                print(f"{item.problem_id} {item.scenario.value}: {', '.join(item.files)}")
            print(
                f"dry run: change {number} would make {len(planned.superseded)} combination(s) "
                "again; nothing was recorded"
            )
            return EXIT_OK
        with store.exclusive_run(root, model):
            result = template_change.change_template(
                root, model, template, args.reason, now=clock.utc_now
            )
    except template_change.NothingToChange as exc:
        raise UsageError(str(exc)) from exc
    except DamagedTreeError as exc:
        code = report_damage(model, exc.damaged)
        print("error: nothing was recorded nor moved", file=sys.stderr)
        return code
    except template_change.BrokenChangeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_DATA_FAILURE
    change = result.change
    if result.finished_earlier:
        print(f"finished the interrupted change {change.number}: {result.moved} file(s) moved")
    for item in change.superseded:
        print(f"{item.problem_id} {item.scenario.value}: {len(item.files)} file(s) superseded")
    print(
        f"change {change.number}: llm template {change.from_sha256[:12]} -> "
        f"{change.to_sha256[:12]}; {len(change.superseded)} combination(s) to make again, "
        f"{result.moved} file(s) moved to {_tree(model)}/{config.SUPERSEDED_DIR}/"
    )
    print(
        f"next: docker compose run --rm app python -m ai_clients generate --model {model} "
        "--resume --confirm-spend <max US$>"
    )
    return EXIT_OK


# ------------------------------------------------------------------- report, package, verify


def run_report(args) -> int:
    from ai_clients.llm import report
    from ai_clients.report import DamagedTreeError

    root, model = Path("."), args.model
    if not store.run_exists(root, model):
        raise UsageError(f"{_tree(model)}/run.json does not exist; run generate first")
    try:
        built = report.build_report(root, model)
    except DamagedTreeError as exc:
        return report_damage(model, exc.damaged)
    report.write_report(root, model, built)
    total = built.combinations["total"]
    print(f"report: {config.report_path(model).as_posix()}")
    print(
        f"{total.total} combinations: {total.accepted_predicted} accepted_predicted, "
        f"{total.discarded_manual} discarded_manual, {total.awaiting_manual} awaiting_manual, "
        f"{total.pending} pending; US$ {built.cost_usd.total:.4f} spent"
    )
    return EXIT_OK


def run_package(args) -> int:
    from ai_clients.llm import packaging, report
    from ai_clients.report import DamagedTreeError

    main = _main()
    root, model = Path("."), args.model
    failed = main.dataset_gate(root)
    if failed is not None:
        return failed
    if not store.run_exists(root, model):
        raise UsageError(f"{_tree(model)}/run.json does not exist; run generate first")
    with store.exclusive_run(root, model):
        try:
            result = packaging.build_zip(root, model)
        except DamagedTreeError as exc:
            return report_damage(model, exc.damaged)
        except packaging.UnfinishedRunError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return EXIT_DATA_FAILURE
        packaging.write_manifest(root, model, packaging.build_manifest(model, result.zip_path))
        report.write_report(root, model, report.build_report(root, model))
    statuses = ", ".join(f"{count} {status}" for status, count in result.statuses.items())
    zip_name = config.zip_path(model).as_posix()
    print(
        f"packaged {result.combinations} combinations ({statuses}): {zip_name} ({result.size} bytes)"
    )
    if result.over_size_warning:
        print(
            f"warning: {zip_name} is {result.size} bytes, above the 95 MB warning threshold "
            "(GitHub refuses pushes above 100 MB)",
            file=sys.stderr,
        )
    print(f"manifest: {config.manifest_path(model).as_posix()}")
    print(f"report: {config.report_path(model).as_posix()}")
    return EXIT_OK


def run_verify(args) -> int:
    from ai_clients.llm import packaging

    root, model = Path("."), args.model
    if not (root / config.manifest_path(model)).is_file():
        print(
            f"error: manifest not found: {config.manifest_path(model).as_posix()}", file=sys.stderr
        )
        return EXIT_USAGE
    extracted = Path(args.extracted) if args.extracted else None
    result = packaging.verify(root, model, extracted)
    for path in result.changed:
        print(f"changed: {path}")
    for path in result.missing:
        print(f"missing: {path}")
    for path in result.extra:
        print(f"extra: {path}")
    print("OK" if result.ok else "FAIL")
    return EXIT_OK if result.ok else EXIT_DATA_FAILURE
