"""Command line entry point for the commands that cut across modules: ``python -m cli <command>``.

Today: ``check`` (are the artifacts of the pipeline consistent with each other). Exit codes: 0 success,
1 at least one failure, 2 usage error or a required manifest that is missing.
"""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from cli import consistency

EXIT_OK = 0
EXIT_FAILURE = 1
EXIT_USAGE = 2


def _configure_check(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--only",
        help="comma separated layers to check (default: all): "
        + ", ".join(layer.key for layer in consistency.LAYERS),
    )
    parser.add_argument(
        "--deep",
        action="store_true",
        help="also recompute the SHA-256 of every file and of the zips and compare with the manifests",
    )


def _run_check(args: argparse.Namespace) -> int:
    only = [p.strip() for p in args.only.split(",") if p.strip()] if args.only else None
    unknown = consistency.unknown_layers(only)
    if unknown:
        print(f"error: unknown layer(s): {', '.join(unknown)}", file=sys.stderr)
        return EXIT_USAGE
    root = Path(args.root).resolve()
    missing = consistency.missing_manifest(root, only)
    if missing:
        print(f"error: manifest not found: {missing}", file=sys.stderr)
        return EXIT_USAGE
    report = consistency.run_checks(root, only, args.deep)
    print(report.render())
    return EXIT_OK if report.ok else EXIT_FAILURE


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m cli",
        description="Commands that cut across the modules of the pipeline.",
    )
    parser.add_argument("--root", default=".", help=argparse.SUPPRESS)  # only for the tests
    subparsers = parser.add_subparsers(dest="command")
    check = subparsers.add_parser(
        "check",
        help="check that dataset, mutants, the suites of the four models and the evaluations are complete and 1:1 (reads only)",
        description="Check that the artifacts of the pipeline agree with each other.",
    )
    _configure_check(check)
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
    return _run_check(args)


if __name__ == "__main__":
    sys.exit(main())
