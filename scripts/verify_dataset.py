"""Verify the packaged dataset against its manifest (spec FR-028; contracts/cli.md).

A thin wrapper over ``dataset.integrity.verify``, meant to work right after cloning the
repository, before any extraction: with the defaults it only needs ``data/dataset.zip`` and
``manifests/dataset.manifest.json``, both versioned. With ``--extracted DIR`` it additionally
checks the extracted tree, file by file.

Run inside the container (it needs no network, but does need the project's dependencies)::

    docker compose run --rm app python scripts/verify_dataset.py
    docker compose run --rm app python scripts/verify_dataset.py --extracted data/dataset

Exit codes: ``0`` the dataset is intact, ``1`` at least one file diverges, ``2`` usage error.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dataset.integrity.verify import verify

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_USAGE = 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--zip", default="data/dataset.zip", help="packaged dataset to verify")
    parser.add_argument(
        "--manifest", default="manifests/dataset.manifest.json", help="integrity manifest"
    )
    parser.add_argument(
        "--extracted",
        default=None,
        metavar="DIR",
        help="also check the extracted tree file by file (the `dataset/` folder itself, e.g. "
        "data/dataset, not its parent)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    zip_path, manifest_path = Path(args.zip), Path(args.manifest)
    if not manifest_path.is_file():
        print(f"error: manifest not found: {manifest_path}", file=sys.stderr)
        return EXIT_USAGE
    extracted = Path(args.extracted) if args.extracted else None
    result = verify(zip_path, manifest_path, extracted_dir=extracted)
    for path in result.changed:
        print(f"changed: {path}")
    for path in result.missing:
        print(f"missing: {path}")
    for path in result.extra:
        print(f"extra: {path}")
    print("OK" if result.ok else "FAIL")
    return EXIT_OK if result.ok else EXIT_FAIL


if __name__ == "__main__":
    sys.exit(main())
