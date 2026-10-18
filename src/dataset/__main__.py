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
from dataset.integrity import manifest as manifest_module
from dataset.integrity import packaging
from dataset.integrity import verify as verify_module
from dataset.persistence import report as reporting
from dataset.persistence import store
from dataset.schemas.pool import Pool
from dataset.schemas.report import Provenance
from dataset.validation import pipeline
from dataset.validation.engine import gcc_version
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


# ---------------------------------------------------------------------------------- package and verify


def _configure_package(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--target",
        type=_positive_int,
        default=config.TARGET_PROBLEMS,
        help=f"complete problems required to package (default {config.TARGET_PROBLEMS})",
    )
    parser.add_argument(
        "--allow-partial",
        action="store_true",
        help="package even if fewer than --target problems are complete",
    )


def _run_package(args: argparse.Namespace) -> int:
    root = Path(".")
    pool_path = root / config.STAGING_DIR / "pool.json"
    if not pool_path.is_file():
        print("error: no pool found; run `python -m dataset extract` first", file=sys.stderr)
        return EXIT_DATA_FAILURE
    pool = Pool.model_validate(store.read_json(pool_path))
    included = len(packaging.list_complete_problems(root))
    if included < args.target and not args.allow_partial:
        print(
            f"error: only {included} of {args.target} complete problems; pass --allow-partial "
            "to package anyway",
            file=sys.stderr,
        )
        return EXIT_DATA_FAILURE
    result = packaging.build_dataset_zip(root, config.DATASET_ZIP)
    if result.over_size_warning:
        print(
            f"warning: {result.zip_path} is {result.size} bytes, above the 95 MB warning "
            "threshold (GitHub refuses pushes above 100 MB)",
            file=sys.stderr,
        )
    provenance = Provenance(
        hf_dataset=pool.hf_dataset,
        hf_revision=pool.hf_revision,
        seed=pool.seed,
        gcc_version=gcc_version(),
    )
    manifest = manifest_module.build_manifest(root, result.zip_path, provenance=provenance)
    manifest_path = manifest_module.write_manifest(root, manifest)
    print(
        f"packaged {result.problem_count} of {args.target} problems: {result.zip_path} ({result.size} bytes)"
    )
    print(f"manifest: {manifest_path}")
    report_path = root / config.REPORTS_DIR / "extraction_report.json"
    if report_path.is_file():
        print(f"extraction report: {manifest_module.copy_extraction_report(root)}")
    else:
        print(
            "warning: no data/work/reports/extraction_report.json to copy; run "
            "`python -m dataset report` if you need it in manifests/",
            file=sys.stderr,
        )
    return EXIT_OK


def _configure_verify(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--zip", default=str(config.DATASET_ZIP), help="packaged dataset to verify")
    parser.add_argument("--manifest", default=str(config.MANIFEST_PATH), help="integrity manifest")
    parser.add_argument(
        "--extracted", default=None, metavar="DIR", help="also check the extracted `dataset/` tree"
    )


def _run_verify(args: argparse.Namespace) -> int:
    manifest_path = Path(args.manifest)
    if not manifest_path.is_file():
        print(f"error: manifest not found: {manifest_path}", file=sys.stderr)
        return EXIT_USAGE
    extracted = Path(args.extracted) if args.extracted else None
    result = verify_module.verify(Path(args.zip), manifest_path, extracted_dir=extracted)
    for path in result.changed:
        print(f"changed: {path}")
    for path in result.missing:
        print(f"missing: {path}")
    for path in result.extra:
        print(f"extra: {path}")
    print("OK" if result.ok else "FAIL")
    return EXIT_OK if result.ok else EXIT_DATA_FAILURE


# ------------------------------------------------------------ check-statements, correct-statements

# Replaced by the tests (a clock that does not wait).
make_statements_clock = None  # None: the real clock (dataset.statements.fetch.SystemClock)


def _dataset_problems(root: Path) -> list[str]:
    folder = root / config.EXTRACTED_PROBLEMS_DIR
    return sorted(p.name for p in folder.iterdir() if p.is_dir()) if folder.is_dir() else []


def _dataset_gate(root: Path) -> int | None:
    manifest = root / config.MANIFEST_PATH
    if not manifest.is_file():
        print(f"error: manifest not found: {manifest}", file=sys.stderr)
        return EXIT_DATA_FAILURE
    result = verify_module.verify(
        root / config.DATASET_ZIP, manifest, extracted_dir=root / config.DATA_DIR / "dataset"
    )
    if not result.ok:
        print(
            "error: data/dataset does not match manifests/dataset.manifest.json; restore it with: "
            "unzip data/dataset.zip -d data/",
            file=sys.stderr,
        )
        return EXIT_DATA_FAILURE
    return None


def _configure_check_statements(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--refetch",
        action="store_true",
        help="get the original pages again (those of --problem, or all), even if kept",
    )
    parser.add_argument(
        "--problem",
        action="append",
        default=[],
        metavar="ID",
        help="only this problem (repeatable): the result is printed, the report is not written",
    )


def _summary_lines(problems) -> list[str]:
    from dataset.schemas.statements import KINDS
    from dataset.statements.compare import totals

    t = totals(problems)
    first = (
        f"statements: {t.problems} checked; faithful {t.faithful}, with losses {t.with_losses}, "
        f"unchecked {t.unchecked}"
    )
    lines = [first]
    parts = []
    for kind in KINDS:
        n, p = t.by_kind[kind], t.problems_by_kind[kind]
        parts.append(f"{kind}: {n} in {p} problems" if n else f"{kind}: 0")
    lines.append("; ".join(parts))
    return lines


def _run_check_statements(args: argparse.Namespace) -> int:
    from dataset.statements import compare as comparing
    from dataset.statements import fetch

    root = Path(".")
    failed = _dataset_gate(root)
    if failed is not None:
        return failed
    available = _dataset_problems(root)
    unknown = [p for p in args.problem if p not in available]
    if unknown:
        print(f"error: not in data/dataset: {', '.join(unknown)}", file=sys.stderr)
        return EXIT_USAGE
    targets = sorted(set(args.problem)) if args.problem else available
    current = fetch.read_manifest(root)
    if current is not None:
        try:
            fetch.verify_originals(root, current)
        except fetch.OriginalMismatch as exc:
            print(f"error: {exc}", file=sys.stderr)
            return EXIT_DATA_FAILURE
    clock = make_statements_clock() if make_statements_clock is not None else None
    try:
        manifest = fetch.ensure_originals(root, targets, refetch=args.refetch, clock=clock)
    except fetch.FetchStopped as exc:
        print(f"infrastructure failure: {exc}; run the command again later", file=sys.stderr)
        return EXIT_INFRA
    blocks = fetch.read_statement_blocks(root, manifest)
    report = comparing.build_report(
        root,
        targets,
        blocks,
        manifest,
        dataset_manifest_sha256=fetch.dataset_manifest_sha256(root),
        originals_manifest_sha256=fetch.sha256(fetch.manifest_path(root).read_bytes()),
    )
    if args.problem:
        for p in report.problems:
            kinds: dict[str, int] = {}
            for d in p.differences:
                kinds[d.kind] = kinds.get(d.kind, 0) + 1
            detail = (
                f" ({p.unchecked_reason})"
                if p.status == "unchecked"
                else "".join(f" {k} {n}" for k, n in kinds.items())
            )
            print(f"{p.problem_id}: {p.status}{detail}")
    for line in _summary_lines(report.problems):
        print(line)
    if not args.problem:
        store.atomic_write_json(root / config.STATEMENT_FIDELITY_REPORT, report)
        fetch.package_originals(root, blocks)
        print(f"report: {config.STATEMENT_FIDELITY_REPORT.as_posix()}")
    return EXIT_OK


def _configure_correct_statements(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--output-dir",
        required=True,
        type=Path,
        metavar="DIR",
        help="where to write <id>.md (the accepted corrections) and summary.json; never inside "
        "data/dataset, data/suites or manifests",
    )
    parser.add_argument("--force", action="store_true", help="replace DIR if it has files")


def _run_correct_statements(args: argparse.Namespace) -> int:
    from dataset.schemas.statements import FidelityReport
    from dataset.statements import UsageError as StatementsUsage
    from dataset.statements import correct as correcting
    from dataset.statements import fetch

    root = Path(".")
    try:
        correcting.check_destination(root, args.output_dir, force=args.force)
    except StatementsUsage as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_USAGE
    report_path = root / config.STATEMENT_FIDELITY_REPORT
    manifest = fetch.read_manifest(root)
    if not report_path.is_file() or manifest is None:
        print(
            f"error: {config.STATEMENT_FIDELITY_REPORT.as_posix()} not found; run "
            "python -m dataset check-statements first",
            file=sys.stderr,
        )
        return EXIT_DATA_FAILURE
    raw = report_path.read_bytes()
    report = FidelityReport.model_validate_json(raw)
    if report.dataset_manifest_sha256 != fetch.dataset_manifest_sha256(root):
        print(
            "error: the report was made from another dataset; run check-statements again",
            file=sys.stderr,
        )
        return EXIT_DATA_FAILURE
    blocks = fetch.read_statement_blocks(root, manifest)
    summary = correcting.correct_all(
        root, report, fetch.sha256(raw), blocks, args.output_dir, force=args.force
    )
    kinds: dict[str, int] = {}
    for c in summary.corrected:
        for k, n in c.markups_inserted.items():
            kinds[k] = kinds.get(k, 0) + n
    detail = ", ".join(f"{k} {n}" for k, n in sorted(kinds.items()))
    print(
        f"corrected: {len(summary.corrected)} ({detail}); unchanged: {len(summary.unchanged)}; "
        f"review: {len(summary.review)}"
    )
    for entry in summary.review:
        print(f"review: {entry.problem_id}: {', '.join(entry.reasons)}")
    print(f"written: {args.output_dir.as_posix()} ({len(summary.corrected)} files + summary.json)")
    failed = any(r.startswith("check failed") for e in summary.review for r in e.reasons)
    return EXIT_DATA_FAILURE if failed else EXIT_OK


register(
    "check-statements",
    "compare every enunciado.md with the original statement on Codeforces (gets each page once, "
    "3 s apart; run it in the app service) and write manifests/statement_fidelity_report.json",
    _configure_check_statements,
    _run_check_statements,
)
register(
    "correct-statements",
    "write, for review, the statements with the exponents and indices the original has "
    "(^{...}, _{...}), each checked three times; never changes the dataset",
    _configure_correct_statements,
    _run_correct_statements,
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
    "package",
    "build data/dataset.zip and its manifest from the complete problems",
    _configure_package,
    _run_package,
)
register(
    "verify",
    "recompute hashes and compare with the manifest (works right after cloning)",
    _configure_verify,
    _run_verify,
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
