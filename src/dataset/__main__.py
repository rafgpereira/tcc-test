"""Command line entry point of the dataset module: ``python -m dataset <command>``.

Commands are registered by their stories (extract and report, selfcheck, validate and audit,
package and verify). Exit codes (specs/001-dataset-extraction/contracts/cli.md):
0 success, 1 data failure, 2 usage error, 3 infrastructure failure, 130 interrupted.
"""

import argparse
import os
import signal
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from dataset import config
from dataset.extraction import stream
from dataset.persistence import report as reporting
from dataset.persistence import store
from dataset.schemas.pool import Pool
from dataset.validation import pipeline
from sandbox.selfcheck import selfcheck
from sandbox.types import InfraError

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


# ---------------------------------------------------------------------------- extract and report

_NETWORK_LIBRARIES = {
    "httpx",
    "httpcore",
    "requests",
    "urllib3",
    "huggingface_hub",
    "fsspec",
    "aiohttp",
}


def _is_network_error(exc: Exception) -> bool:
    return isinstance(exc, OSError) or type(exc).__module__.split(".")[0] in _NETWORK_LIBRARIES


def _configure_extract(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--seed",
        type=int,
        default=config.SEED,
        help=f"seed of the processing order (default {config.SEED})",
    )
    parser.add_argument(
        "--splits",
        default=",".join(config.SPLITS),
        help="comma separated splits, read in this order (default: train,valid,test)",
    )
    parser.add_argument(
        "--limit-rows", type=int, default=None, help="rows read per split (smoke tests only)"
    )


def _summarize(pool: Pool) -> None:
    counts = pool.counts
    print(f"read {counts.funnel.get('read', 0)} rows; {counts.eligible} eligible problems")
    by_category: dict[str, int] = {}
    for problem in pool.problems.values():
        by_category[problem.macrocategoria.value] = (
            by_category.get(problem.macrocategoria.value, 0) + 1
        )
    print("  " + ", ".join(f"{name}: {n}" for name, n in sorted(by_category.items())))


def _run_extract(args: argparse.Namespace) -> int:
    splits = tuple(part.strip() for part in args.splits.split(",") if part.strip())
    unknown = [s for s in splits if s not in config.SPLITS]
    if not splits or unknown:
        print(
            f"error: --splits must list {', '.join(config.SPLITS)}; got {args.splits!r}",
            file=sys.stderr,
        )
        return EXIT_USAGE
    root = Path(".")
    try:
        pool = stream.extract(
            root,
            splits=splits,
            limit_rows=args.limit_rows,
            seed=args.seed,
            progress=lambda message: print(message, flush=True),
        )
    except Exception as exc:
        if _is_network_error(exc):
            raise InfraError(
                f"reading the dataset failed ({type(exc).__name__}: {exc}); "
                "run the same command again to resume from the last finished shard"
            ) from exc
        raise
    _summarize(pool)
    _, md_path = reporting.write_report(root, reporting.build_report(pool))
    print(f"report: {md_path}")
    return EXIT_OK


def _run_report(args: argparse.Namespace) -> int:
    root = Path(".")
    pool_path = root / config.STAGING_DIR / "pool.json"
    if not pool_path.is_file():
        print("error: no pool found; run `python -m dataset extract` first", file=sys.stderr)
        return EXIT_DATA_FAILURE
    pool = Pool.model_validate(store.read_json(pool_path))
    state = reporting.collect_validation_state(root, pool)
    report = reporting.build_report(
        pool,
        included=state.included,
        pending_triage=state.pending,
        discarded_by_reason=state.discarded,
        selection_final=state.selection_is_final(pool),
    )
    _, md_path = reporting.write_report(root, report)
    print(f"included {report.funnel.included} of {report.target} (deficit {report.deficit})")
    for alert in report.category_alerts:
        print(
            f"ALERT: {alert.macrocategoria.value} has {alert.count} problems (< {alert.threshold})"
        )
    for item in report.pending_triage:
        print(f"PENDING TRIAGE: {item.problem_id} ({item.stage}): {item.reason}")
    print(f"report: {md_path}")
    return EXIT_OK


# ---------------------------------------------------------------------------- selfcheck


def _run_selfcheck(args: argparse.Namespace) -> int:
    """Run the known-verdict programs through the engine; exit 0 only if every verdict matches."""
    report = selfcheck()
    print(report.render())
    return EXIT_OK if report.ok else EXIT_DATA_FAILURE


# ---------------------------------------------------------------------------- validate and audit


def default_workers() -> int:
    return max(1, (os.cpu_count() or 2) // 2)


def _positive_int(text: str) -> int:
    value = int(text)
    if value < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return value


def _configure_validate(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--target",
        type=_positive_int,
        default=config.TARGET_PROBLEMS,
        help=f"complete problems to reach (default {config.TARGET_PROBLEMS})",
    )
    parser.add_argument(
        "--workers",
        type=_positive_int,
        default=default_workers(),
        help="parallel processes per problem, default half of the CPUs; never changes the result",
    )
    parser.add_argument(
        "--problem", default=None, help="validate only this problem and ignore the target"
    )


def _configure_audit(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--problem",
        action="append",
        default=[],
        help="audit only this problem (repeatable); default: every complete problem",
    )
    parser.add_argument(
        "--workers", type=_positive_int, default=default_workers(), help="parallel processes"
    )


def _served(action: Callable[[], int]) -> int:
    try:
        return action()
    except pipeline.NoPoolError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_DATA_FAILURE
    except pipeline.UsageError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_USAGE


def _run_validate(args: argparse.Namespace) -> int:
    from dataset.validation.runtime import PoolRuntime

    return _served(
        lambda: pipeline.run_validate(
            Path("."),
            target=args.target,
            workers=args.workers,
            problem=args.problem,
            runtime_factory=PoolRuntime,
            selfcheck_fn=selfcheck,
        )
    )


def _run_audit(args: argparse.Namespace) -> int:
    from dataset.validation.runtime import PoolRuntime

    return _served(
        lambda: pipeline.run_audit(
            Path("."),
            problems=list(args.problem),
            workers=args.workers,
            runtime_factory=PoolRuntime,
        )
    )


register(
    "extract",
    "read the dataset in streaming mode and write the pool of eligible problems",
    _configure_extract,
    _run_extract,
)
register(
    "report",
    "regenerate the extraction report from the pool and the validated problems",
    lambda parser: None,
    _run_report,
)
register(
    "validate",
    "run the engine over the pool until enough problems are complete (run it in the sandbox service)",
    _configure_validate,
    _run_validate,
)
register(
    "audit",
    "re-run the engine over the complete problems and compare with validacao.json",
    _configure_audit,
    _run_audit,
)
register(
    "selfcheck",
    "run programs of known verdict through the engine (run it in the sandbox service)",
    lambda parser: None,
    _run_selfcheck,
)


def _raise_interrupt(signum: int, frame: object) -> None:
    raise KeyboardInterrupt


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m dataset",
        description="Dataset extraction, validation and packaging (feature 001-dataset-extraction).",
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
    # blocks run (worker processes and their children are cleaned up) and the run can resume.
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
