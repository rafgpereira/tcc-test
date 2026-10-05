"""Command line entry point of the ai_clients module: ``python -m ai_clients <command>``.

Commands are registered by their stories (generate, execute, report, package, verify), with the
registration pattern of ``python -m mutation``. Exit codes (specs/003-slm-test-generation/
contracts/cli.md): 0 success, 1 data failure, 2 usage error, 3 infrastructure or Ollama
configuration failure, 130 interrupted.
"""

import argparse
import os
import signal
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from ai_clients import (
    config,
    execution,
    generation,
    oracle,
    packaging,
    problem,
    prompt,
    report,
    store,
)
from ai_clients.errors import ConfigurationError, InfrastructureError
from ai_clients.ollama import OllamaClient
from mutation import dataset_gate as gate
from sandbox import isolation
from sandbox.types import InfraError

EXIT_OK = 0
EXIT_DATA_FAILURE = 1
EXIT_USAGE = 2
EXIT_INFRA = 3
EXIT_INTERRUPTED = 130


class UsageError(Exception):
    """A wrong option or environment variable: exit code 2."""


@dataclass(frozen=True)
class Subcommand:
    name: str
    help: str
    configure: Callable[[argparse.ArgumentParser], None]
    run: Callable[[argparse.Namespace], int]


_REGISTRY: dict[str, Subcommand] = {}


def register(
    name: str,
    help: str,
    configure: Callable[[argparse.ArgumentParser], None],
    run: Callable[[argparse.Namespace], int],
) -> None:
    """Register a subcommand; a name can be registered only once."""
    if name in _REGISTRY:
        raise ValueError(f"subcommand {name!r} is already registered")
    _REGISTRY[name] = Subcommand(name, help, configure, run)


# ------------------------------------------------------------------------------ common options


def _positive_int(text: str) -> int:
    try:
        value = int(text)
    except ValueError:
        value = 0
    if value <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return value


def add_common_options(parser: argparse.ArgumentParser) -> None:
    """``--problem``, ``--scenario``, ``--limit`` and ``--dry-run`` (generate and execute)."""
    parser.add_argument(
        "--problem",
        action="append",
        default=[],
        metavar="ID",
        help="only this problem (repeatable; default: every problem of data/dataset)",
    )
    parser.add_argument(
        "--scenario",
        action="append",
        default=[],
        choices=config.SCENARIOS,
        help="only this scenario (repeatable; default: all three)",
    )
    parser.add_argument(
        "--limit",
        type=_positive_int,
        metavar="N",
        help="process at most N pending problem x scenario combinations",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="only list what would be done; calls nothing, runs nothing, writes nothing",
    )


def selected_combinations(root: Path, args: argparse.Namespace) -> list[tuple[str, str]]:
    """The (problem, scenario) pairs chosen, in canonical order: problem, then scenario order."""
    available = problem.list_problem_ids(root)
    unknown = [pid for pid in args.problem if pid not in available]
    if unknown:
        raise UsageError(f"not in data/dataset: {', '.join(unknown)}")
    problems = sorted(set(args.problem)) if args.problem else available
    scenarios = [s for s in config.SCENARIOS if not args.scenario or s in args.scenario]
    return [(pid, scenario) for pid in problems for scenario in scenarios]


def selection_options(args: argparse.Namespace) -> str:
    """The ``--problem``/``--scenario`` options of ``args``, as typed again in a ``next:`` line."""
    options = [f"--problem {pid}" for pid in sorted(set(args.problem))]
    options += [f"--scenario {s}" for s in config.SCENARIOS if s in args.scenario]
    return "".join(f" {option}" for option in options)


def dataset_gate(root: Path) -> int | None:
    """``None`` if ``data/dataset`` matches its manifest; otherwise print why and return 1."""
    try:
        gate.verify_dataset(root)
    except gate.DatasetMismatchError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_DATA_FAILURE
    except FileNotFoundError as exc:
        print(
            f"error: {exc.filename or exc} not found; restore the versioned dataset with: "
            "unzip data/dataset.zip -d data/",
            file=sys.stderr,
        )
        return EXIT_DATA_FAILURE
    return None


def read_run_if_any(root: Path):
    """``run.json`` if a run was started (so damage can be checked against it), else ``None``."""
    return store.read_run(root) if store.run_exists(root) else None


def report_damage(damaged: list[store.DamagedCombination]) -> int:
    """Print every damaged combination; 1 if there is any (nothing was repaired), else 0."""
    for exc in damaged:
        print(f"damaged: {exc}", file=sys.stderr)
    if damaged:
        print(
            f"error: {len(damaged)} damaged combination(s) in data/suites/slm were left as they "
            "are; nothing was repaired",
            file=sys.stderr,
        )
        return EXIT_DATA_FAILURE
    return EXIT_OK


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


def http_timeout_s() -> int:
    """Seconds to wait for one answer of Ollama (``OLLAMA_HTTP_TIMEOUT_S``, default 900)."""
    return _env_positive_int(config.ENV_HTTP_TIMEOUT_S, config.DEFAULT_HTTP_TIMEOUT_S)


def max_infra_retries() -> int:
    """Consecutive retries of one call before stopping (``OLLAMA_MAX_INFRA_RETRIES``, default 30)."""
    return _env_positive_int(config.ENV_MAX_INFRA_RETRIES, config.DEFAULT_MAX_INFRA_RETRIES)


# ----------------------------------------------------------------------------------- generate

# Replaced by the tests (a fake client, a clock that does not wait).
make_client = OllamaClient
make_clock = generation.SystemClock


def _required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise UsageError(f"{name} is not set in .env (see .env.example)")
    return value


def _configure_generate(parser: argparse.ArgumentParser) -> None:
    add_common_options(parser)
    parser.add_argument(
        "--resume",
        action="store_true",
        help="continue the run already started in data/suites/slm (required once run.json exists)",
    )


def _dry_run_generate(root: Path, combinations, template, limit: int | None) -> int:
    planned = 0
    largest: dict[str, tuple[int, str]] = {}
    problems: dict[str, problem.ProblemInput] = {}
    run, damaged = read_run_if_any(root), []
    for problem_id, scenario in combinations:
        try:
            state = store.combination_state(root, problem_id, scenario, run)
        except store.DamagedCombination as exc:
            damaged.append(exc)
            continue
        if state.kind != "pending_generation":
            continue
        if limit is not None and planned >= limit:
            break
        if problem_id not in problems:
            problems[problem_id] = problem.load_problem(root, problem_id)
        size = len(prompt.build_prompt(template, problems[problem_id], scenario))
        print(
            f"{problem_id} {scenario} attempt {state.attempt} seed "
            f"{config.seed_for(state.attempt)}: prompt {size} chars"
        )
        planned += 1
        if size > largest.get(scenario, (0, ""))[0]:
            largest[scenario] = (size, problem_id)
    print(f"dry run: {planned} calls planned")
    for scenario in config.SCENARIOS:
        if scenario in largest:
            size, problem_id = largest[scenario]
            print(f"largest prompt: {scenario} {size} chars ({problem_id})")
    return report_damage(damaged)


def _run_generate(args: argparse.Namespace) -> int:
    root = Path(".")
    failed = dataset_gate(root)
    if failed is not None:
        return failed
    combinations = selected_combinations(root, args)
    template = prompt.load_template()
    if args.dry_run:
        return _dry_run_generate(root, combinations, template, args.limit)
    base_url = _required_env(config.ENV_BASE_URL)
    _required_env(config.ENV_HARDWARE_LABEL)
    timeout_s, retries = http_timeout_s(), max_infra_retries()
    if store.run_exists(root) and not args.resume:
        raise UsageError("a run already exists in data/suites/slm; use --resume to continue it")
    if args.resume and not store.run_exists(root):
        raise UsageError(
            "nothing to resume: data/suites/slm/run.json does not exist; "
            "run generate without --resume to start a run"
        )
    client = make_client(base_url, timeout_s=timeout_s)
    clock = make_clock()

    def echo(message: str) -> None:
        print(message, flush=True)

    with store.exclusive_run(root):
        current = generation.current_run_config(
            client, template, root, clock=clock, max_infra_retries=retries, echo=echo
        )
        if args.resume:
            run = store.read_run(root)
            differences = run.differences(current)
            if differences:
                lines = "\n".join(
                    f"  {name}: recorded {recorded!r}, current {now!r}"
                    for name, recorded, now in differences
                )
                raise UsageError(
                    "the configuration differs from data/suites/slm/run.json, and a run never "
                    f"mixes configurations:\n{lines}\n"
                    "restore the recorded configuration, or move data/suites/slm away to start a "
                    "new run"
                )
        else:
            store.write_run(root, current)
            run = current
        result = generation.generate(
            root,
            combinations,
            client,
            template=template,
            run=run,
            hardware_label=lambda: _required_env(config.ENV_HARDWARE_LABEL),
            max_infra_retries=retries,
            clock=clock,
            echo=echo,
            limit=args.limit,
        )
    print(
        f"done: {result.calls} calls, {result.parsed} parsed, {result.unparseable} unparseable, "
        f"{result.repetition} repetition, {result.discarded} discarded suites; "
        f"{result.pending_execution} pending execution"
    )
    return report_damage(result.damaged)


register(
    "generate",
    "call the local model for every problem x scenario still pending (run it in the app service)",
    _configure_generate,
    _run_generate,
)


# ------------------------------------------------------------------------------------ execute

SLOT = 0  # one worker: every Python run uses the engine slot 0 (uid 10000)
MIB = 1024 * 1024

# Replaced by the tests (a fake runner; no real slot to clean).
make_runner = lambda: oracle.run_python
cleanup_slot = isolation.kill_slot_processes


def _dry_run_execute(root: Path, combinations, limit: int | None) -> int:
    planned = 0
    run, damaged = store.read_run(root), []
    for problem_id, scenario in combinations:
        try:
            state = store.combination_state(root, problem_id, scenario, run)
        except store.DamagedCombination as exc:
            damaged.append(exc)
            continue
        if state.kind != "pending_execution":
            continue
        if limit is not None and planned >= limit:
            break
        record = store.read_generation(root, problem_id, scenario, state.attempt)
        judged = problem.load_judge_input(root, problem_id)
        limits = oracle.python_limits(judged.metadata)
        print(
            f"{problem_id} {scenario} attempt {state.attempt}: {len(record.parse.inputs)} inputs, "
            f"{len(judged.testes.public_tests)} public tests, limits "
            f"{limits.time_limit_seconds:g} s and {limits.memory_limit_bytes / MIB:.0f} MiB"
        )
        planned += 1
    print(f"dry run: {planned} attempts to execute")
    return report_damage(damaged)


def _run_execute(args: argparse.Namespace) -> int:
    root = Path(".")
    failed = dataset_gate(root)
    if failed is not None:
        return failed
    combinations = selected_combinations(root, args)
    if not store.run_exists(root):
        raise UsageError("data/suites/slm/run.json does not exist; run generate first")
    if args.dry_run:
        return _dry_run_execute(root, combinations, args.limit)
    run = store.read_run(root)

    def echo(message: str) -> None:
        print(message, flush=True)

    with store.exclusive_run(root):
        cleanup_slot(SLOT)  # leftovers of a run that was killed
        try:
            result = execution.execute(
                root,
                combinations,
                run=run,
                runner=make_runner(),
                echo=echo,
                limit=args.limit,
                slot=SLOT,
            )
        finally:
            cleanup_slot(SLOT)
    print(
        f"done: {result.executed} executed, {result.accepted} accepted, {result.failed} failed "
        f"({result.need_generation} need a new generation), {result.discarded} discarded suites"
    )
    if result.pending_generation:
        print(
            "next: docker compose run --rm app python -m ai_clients generate --resume"
            + selection_options(args)
        )
    return report_damage(result.damaged)


def _run_report(args: argparse.Namespace) -> int:
    root = Path(".")
    if not store.run_exists(root):
        raise UsageError("data/suites/slm/run.json does not exist; run generate first")
    try:
        built = report.build_report(root)
    except report.DamagedTreeError as exc:
        return report_damage(exc.damaged)
    report.write_report(root, built)
    print(f"report: {config.REPORT_PATH.as_posix()}")
    total = built.combinations["total"]
    print(
        f"{total.total} combinations: {total.accepted} accepted, {total.discarded} discarded, "
        f"{total.pending_generation} pending generation, {total.pending_execution} pending "
        f"execution; discard rate {built.discard_rate['total']:.1%}"
    )
    return EXIT_OK


def _run_package(args: argparse.Namespace) -> int:
    root = Path(".")
    failed = dataset_gate(root)
    if failed is not None:
        return failed
    if not store.run_exists(root):
        raise UsageError("data/suites/slm/run.json does not exist; run generate first")
    with store.exclusive_run(root):
        try:
            result = packaging.build_zip(root, root / config.ZIP_PATH)
        except report.DamagedTreeError as exc:
            return report_damage(exc.damaged)
        except packaging.UnfinishedRunError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return EXIT_DATA_FAILURE
        packaging.write_manifest(root, packaging.build_manifest(result.zip_path))
        # The report is rebuilt from what was just packaged, so it always describes exactly that.
        report.write_report(root, report.build_report(root))
    print(
        f"packaged {result.combinations} combinations ({result.accepted} accepted, "
        f"{result.discarded} discarded): {config.ZIP_PATH.as_posix()} ({result.size} bytes)"
    )
    if result.over_size_warning:
        print(
            f"warning: {config.ZIP_PATH.as_posix()} is {result.size} bytes, above the 95 MB "
            "warning threshold (GitHub refuses pushes above 100 MB)",
            file=sys.stderr,
        )
    print(f"manifest: {config.MANIFEST_PATH.as_posix()}")
    print(f"report: {config.REPORT_PATH.as_posix()}")
    return EXIT_OK


def _configure_verify(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--extracted",
        default=None,
        metavar="DIR",
        help="also check the extracted tree (data/suites/slm after unzip data/slm_suites.zip -d data/)",
    )


def _run_verify(args: argparse.Namespace) -> int:
    root = Path(".")
    manifest_path = root / config.MANIFEST_PATH
    if not manifest_path.is_file():
        print(f"error: manifest not found: {config.MANIFEST_PATH.as_posix()}", file=sys.stderr)
        return EXIT_USAGE
    extracted = Path(args.extracted) if args.extracted else None
    result = packaging.verify(root / config.ZIP_PATH, manifest_path, extracted)
    for path in result.changed:
        print(f"changed: {path}")
    for path in result.missing:
        print(f"missing: {path}")
    for path in result.extra:
        print(f"extra: {path}")
    print("OK" if result.ok else "FAIL")
    return EXIT_OK if result.ok else EXIT_DATA_FAILURE


register(
    "package",
    "zip a finished run into data/slm_suites.zip with its manifest and report (app service)",
    lambda parser: None,
    _run_package,
)

register(
    "verify",
    "check data/slm_suites.zip (and, with --extracted, data/suites/slm) against the manifest",
    _configure_verify,
    _run_verify,
)

register(
    "report",
    "write manifests/slm_generation_report.json from data/suites/slm (any time; reads only)",
    lambda parser: None,
    _run_report,
)


register(
    "execute",
    "run the Python solution of every attempt pending execution (run it in the sandbox service)",
    add_common_options,
    _run_execute,
)


# ------------------------------------------------------------------------------------- parser


def _raise_interrupt(signum: int, frame: object) -> None:
    raise KeyboardInterrupt


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m ai_clients",
        description="Test suites generated by the local model (Qwen2.5-Coder-7B via Ollama).",
    )
    subparsers = parser.add_subparsers(dest="command")
    for name in sorted(_REGISTRY):
        sub = _REGISTRY[name]
        sub.configure(subparsers.add_parser(name, help=sub.help, description=sub.help))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:  # argparse exits with 0 for --help and 2 for usage errors
        return int(exc.code or 0)
    if args.command is None:
        parser.print_help(sys.stderr)
        return EXIT_USAGE
    # `docker stop` and the end of a session send SIGTERM: treat it like Ctrl+C, so `finally`
    # blocks run and the run can resume.
    previous = signal.signal(signal.SIGTERM, _raise_interrupt)
    try:
        return _REGISTRY[args.command].run(args)
    except KeyboardInterrupt:
        print("interrupted; it is safe to run the command again", file=sys.stderr)
        return EXIT_INTERRUPTED
    except UsageError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_USAGE
    except store.AlreadyRunningError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_DATA_FAILURE
    except ConfigurationError as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return EXIT_INFRA
    except (InfraError, InfrastructureError) as exc:
        print(f"infrastructure failure: {exc}", file=sys.stderr)
        return EXIT_INFRA
    finally:
        signal.signal(signal.SIGTERM, previous)


if __name__ == "__main__":
    sys.exit(main())
