"""Command line entry point of the dataset module: ``python -m dataset <command>``.

Commands are registered by their stories (extract and report, selfcheck, validate and audit,
package and verify). Exit codes (specs/001-dataset-extraction/contracts/cli.md):
0 success, 1 data failure, 2 usage error, 3 infrastructure failure, 130 interrupted.
"""

import argparse
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from dataset import config
from dataset.extraction import stream
from dataset.persistence import report as reporting
from dataset.persistence import store
from dataset.schemas.pool import Pool
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
    try:
        return _REGISTRY[args.command].run(args)
    except KeyboardInterrupt:
        print("interrupted; it is safe to run the command again", file=sys.stderr)
        return EXIT_INTERRUPTED
    except InfraError as exc:
        print(f"infrastructure failure: {exc}", file=sys.stderr)
        return EXIT_INFRA


if __name__ == "__main__":
    sys.exit(main())
