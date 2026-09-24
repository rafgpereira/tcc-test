"""Command line entry point of the mutation module: ``python -m mutation <command>``.

Commands are registered by their stories (generate; package and verify; report). Exit codes
(specs/002-mutant-generation/contracts/cli.md): 0 success, 1 data failure, 2 usage error,
3 infrastructure failure, 130 interrupted.
"""

import argparse
import signal
import sys
import time
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from dataset.schemas.metadata import Metadata
from dataset.schemas.testes import Testes
from dataset.validation.engine import Engine
from dataset.validation.suite import suite_from_testes
from mutation import config, dataset_gate, orchestrator, persistence
from sandbox.types import ExecutionLimits, InfraError

EXIT_OK = 0
EXIT_DATA_FAILURE = 1
EXIT_USAGE = 2
EXIT_INFRA = 3
EXIT_INTERRUPTED = 130


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


# ---------------------------------------------------------------------------------- generate


@dataclass
class GenerateResult:
    generated: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)  # already closed by an earlier run
    excluded: list[str] = field(default_factory=list)  # closed with an exclusion alert
    failed: list[str] = field(default_factory=list)  # could not be completed (nothing written)


def _problem_ids(root: Path) -> list[str]:
    folder = root / config.DATASET_PROBLEMS_DIR
    return sorted(p.name for p in folder.iterdir() if p.is_dir()) if folder.is_dir() else []


def _configure_generate(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--problem",
        action="append",
        default=[],
        metavar="ID",
        help="process only this problem (repeatable); default: every problem of the dataset",
    )


def generate(
    root: Path, problems: list[str], engine: Engine, echo: Callable[[str], None]
) -> GenerateResult:
    """Generate and persist the mutants of each problem that is not closed yet."""
    result = GenerateResult()
    persistence.reset_building(root)  # partial problems of an interrupted run start over
    for position, problem_id in enumerate(problems, start=1):
        if persistence.is_closed(root, problem_id):
            result.skipped.append(problem_id)
            echo(f"[{position}/{len(problems)}] {problem_id}: already generated, skipped")
            continue
        folder = root / config.DATASET_PROBLEMS_DIR / problem_id
        source = (folder / "AC_ref.cpp").read_text(encoding="utf-8")
        metadata = Metadata.from_folder(
            folder
        )  # the limits come from the problem, never a constant
        limits = ExecutionLimits(metadata.time_limit_seconds, metadata.memory_limit_bytes)
        suite = suite_from_testes(Testes.from_folder(folder))
        echo(f"[{position}/{len(problems)}] {problem_id}: generating")
        started = time.monotonic()
        try:
            selection = orchestrator.select_mutants(
                problem_id, source, suite, limits, engine=engine, slot=0
            )
        except orchestrator.HigherOrderNotAvailable as exc:
            result.failed.append(problem_id)
            echo(f"  FAILED: {exc}")
            continue
        persistence.write_selection(root, problem_id, selection)
        seconds = time.monotonic() - started
        by_order = Counter(m.order for m in selection.mutants)
        reasons = Counter(d.reason.value for d in selection.discards)
        (result.excluded if selection.alert else result.generated).append(problem_id)
        echo(
            f"  {len(selection.mutants)} mutants (by order: {dict(sorted(by_order.items()))}); "
            f"discarded: {dict(sorted(reasons.items())) or 'none'}; {seconds:.0f} s"
        )
        if selection.alert is not None:
            echo(
                f"  ALERT: {problem_id} reached only {selection.alert.mutants_reached} of "
                f"{config.MUTANTS_PER_PROBLEM} mutants (highest order tried: "
                f"{selection.alert.highest_order_attempted}); the problem is left out of the "
                "mutation score"
            )
    return result


def _run_generate(args: argparse.Namespace) -> int:
    from dataset.validation.engine import real_engine
    from sandbox import isolation

    root = Path(".")
    try:
        dataset_gate.verify_dataset(root)
    except (dataset_gate.DatasetMismatchError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_DATA_FAILURE
    available = _problem_ids(root)
    unknown = [p for p in args.problem if p not in available]
    if unknown:
        print(f"error: not in data/dataset: {', '.join(unknown)}", file=sys.stderr)
        return EXIT_USAGE
    problems = sorted(set(args.problem)) if args.problem else available
    isolation.kill_slot_processes(0)  # leftovers of a run that was killed
    engine = real_engine()
    result = generate(root, problems, engine, lambda message: print(message, flush=True))
    print(
        f"done: {len(result.generated)} generated, {len(result.skipped)} skipped, "
        f"{len(result.excluded)} excluded, {len(result.failed)} failed"
    )
    return EXIT_DATA_FAILURE if result.failed else EXIT_OK


register(
    "generate",
    "generate up to 100 mutants per problem from AC_ref.cpp (run it in the sandbox service)",
    _configure_generate,
    _run_generate,
)


def _raise_interrupt(signum: int, frame: object) -> None:
    raise KeyboardInterrupt


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m mutation",
        description="Mutant generation from the reference solutions (feature 002-mutant-generation).",
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
    # blocks run and the run can resume (research R5).
    previous = signal.signal(signal.SIGTERM, _raise_interrupt)
    try:
        return _REGISTRY[args.command].run(args)
    except KeyboardInterrupt:
        print("interrupted; it is safe to run the command again", file=sys.stderr)
        return EXIT_INTERRUPTED
    except InfraError as exc:
        print(f"infrastructure failure: {exc}", file=sys.stderr)
        return EXIT_INFRA
    finally:
        signal.signal(signal.SIGTERM, previous)


if __name__ == "__main__":
    sys.exit(main())
