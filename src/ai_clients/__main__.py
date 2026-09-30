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

from ai_clients import config, problem, store
from ai_clients.errors import ConfigurationError
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
    except InfraError as exc:
        print(f"infrastructure failure: {exc}", file=sys.stderr)
        return EXIT_INFRA
    finally:
        signal.signal(signal.SIGTERM, previous)


if __name__ == "__main__":
    sys.exit(main())
