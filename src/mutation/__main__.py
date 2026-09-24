"""Command line entry point of the mutation module: ``python -m mutation <command>``.

Commands are registered by their stories (generate; package and verify; report). Exit codes
(specs/002-mutant-generation/contracts/cli.md): 0 success, 1 data failure, 2 usage error,
3 infrastructure failure, 130 interrupted.
"""

import argparse
import os
import signal
import sys
import time
from collections import Counter
from collections.abc import Callable, Sequence
from concurrent.futures import FIRST_COMPLETED, Future, wait
from dataclasses import dataclass, field
from pathlib import Path

from dataset.schemas.metadata import Metadata
from dataset.schemas.testes import Testes
from dataset.validation.suite import suite_from_testes
from mutation import config, dataset_gate, orchestrator, persistence
from mutation import runtime as runtime_module
from mutation.types import Selection
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


def default_workers() -> int:
    return max(1, (os.cpu_count() or 2) // 2)


def _positive_int(text: str) -> int:
    value = int(text)
    if value < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return value


def _configure_generate(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--problem",
        action="append",
        default=[],
        metavar="ID",
        help="process only this problem (repeatable); default: every problem of the dataset",
    )
    parser.add_argument(
        "--workers",
        type=_positive_int,
        default=default_workers(),
        help="problems processed in parallel, default half of the CPUs; never changes the result",
    )


def _prepare(root: Path, problem_id: str) -> runtime_module.ProblemTask:
    folder = root / config.DATASET_PROBLEMS_DIR / problem_id
    metadata = Metadata.from_folder(folder)  # the limits come from the problem, never a constant
    return runtime_module.ProblemTask(
        problem_id=problem_id,
        source=(folder / "AC_ref.cpp").read_text(encoding="utf-8"),
        suite=suite_from_testes(Testes.from_folder(folder)),
        limits=ExecutionLimits(metadata.time_limit_seconds, metadata.memory_limit_bytes),
    )


def _finish(
    root: Path,
    label: str,
    problem_id: str,
    future: "Future[Selection]",
    seconds: float,
    result: GenerateResult,
    echo: Callable[[str], None],
) -> None:
    try:
        selection = future.result()  # an InfraError of the engine propagates from here
    except orchestrator.HigherOrderNotAvailable as exc:
        result.failed.append(problem_id)
        echo(f"{label} {problem_id}: FAILED: {exc}")
        return
    persistence.write_selection(root, problem_id, selection)
    by_order = Counter(m.order for m in selection.mutants)
    reasons = Counter(d.reason.value for d in selection.discards)
    (result.excluded if selection.alert else result.generated).append(problem_id)
    echo(
        f"{label} {problem_id}: {len(selection.mutants)} mutants "
        f"(by order: {dict(sorted(by_order.items()))}); "
        f"discarded: {dict(sorted(reasons.items())) or 'none'}; {seconds:.0f} s"
    )
    if selection.alert is not None:
        echo(
            f"  ALERT: {problem_id} reached only {selection.alert.mutants_reached} of "
            f"{config.MUTANTS_PER_PROBLEM} mutants (highest order tried: "
            f"{selection.alert.highest_order_attempted}); the problem is left out of the "
            "mutation score"
        )


def generate(
    root: Path,
    problems: list[str],
    runtime: runtime_module.Runtime,
    echo: Callable[[str], None],
) -> GenerateResult:
    """Generate and persist the mutants of each problem that is not closed yet.

    Up to ``2 * workers`` problems are in flight; each one is persisted by THIS process as soon as
    it finishes, so the content of ``data/mutants`` does not depend on the number of workers.
    """
    result = GenerateResult()
    persistence.reset_building(root)  # partial problems of an interrupted run start over
    pending: dict[Future, tuple[str, str, float]] = {}
    try:
        for position, problem_id in enumerate(problems, start=1):
            label = f"[{position}/{len(problems)}]"
            if persistence.problem_path(root, problem_id).exists():
                # Closed by an earlier run, or unzipped from data/mutants.zip (no generation.json):
                # either way it is never regenerated or overwritten.
                result.skipped.append(problem_id)
                echo(f"{label} {problem_id}: already generated, skipped")
                continue
            while len(pending) >= max(1, runtime.workers * 2):
                _drain(root, pending, result, echo, wait_for_one=True)
            echo(f"{label} {problem_id}: generating")
            pending[runtime.submit(_prepare(root, problem_id))] = (
                label,
                problem_id,
                time.monotonic(),
            )
            _drain(root, pending, result, echo, wait_for_one=False)
        while pending:
            _drain(root, pending, result, echo, wait_for_one=True)
    finally:
        for future in pending:
            future.cancel()
    return result


def _drain(root, pending, result, echo, *, wait_for_one: bool) -> None:
    """Persist every finished problem; if asked, first wait until at least one has finished."""
    if not pending:
        return
    done, _ = (
        wait(pending, return_when=FIRST_COMPLETED) if wait_for_one else wait(pending, timeout=0)
    )
    for future in done:
        label, problem_id, started = pending.pop(future)
        _finish(root, label, problem_id, future, time.monotonic() - started, result, echo)


def _make_runtime(workers: int) -> runtime_module.Runtime:
    """One worker runs in this process; more use a pool with one engine slot each."""
    from dataset.validation.engine import real_engine

    if workers == 1:
        return runtime_module.InlineRuntime(real_engine())
    return runtime_module.PoolRuntime(workers)


def _run_generate(args: argparse.Namespace) -> int:
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
    runtime = _make_runtime(args.workers)
    try:
        result = generate(root, problems, runtime, lambda message: print(message, flush=True))
    finally:
        runtime.close()
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
