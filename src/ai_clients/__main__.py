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

from ai_clients import config, generation, problem, prompt, store
from ai_clients.errors import ConfigurationError, InfrastructureError
from ai_clients.ollama import OllamaClient
from mutation import dataset_gate as gate
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
    for problem_id, scenario in combinations:
        state = store.combination_state(root, problem_id, scenario)
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
    return EXIT_OK


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
        f"{result.discarded} discarded suites; {result.pending_execution} pending execution"
    )
    return EXIT_OK


register(
    "generate",
    "call the local model for every problem x scenario still pending (run it in the app service)",
    _configure_generate,
    _run_generate,
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
