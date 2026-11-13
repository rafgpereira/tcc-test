"""``python -m metrics compute|figures|package|verify`` (contracts/cli.md).

Exit codes: 0 success; 1 gate failure, missing tables or a refused package; 2 usage error
(including a filter that leaves a single problem).
"""

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from metrics import config, cuts, figures, gate, packaging, tables

EXIT_OK, EXIT_DATA, EXIT_USAGE = 0, 1, 2


def _run_gate(root: Path) -> list[str]:  # replaced in the tests
    return gate.run_gate(root)


def _summary(metrics) -> str:
    rows = metrics[metrics["cut"] == "all"]
    header = (
        "set           scenario    TDF      MS       TFP      TC       TDF*     MS*      "
        "WAs mortos     mutantes mortos"
    )
    lines = [header]
    for _, r in rows.iterrows():
        lines.append(
            f"{r['set']:<13} {r['scenario']:<11} {r['TDF']:<8.2f} {r['MS']:<8.2f} "
            f"{r['TFP']:<8.2f} {r['TC']:<8.2f} {r['TDF_star']:<8.2f} {r['MS_star']:<8.2f} "
            f"{r['WA_killed']:>6}/{r['WA_total']:<7} {r['mutants_killed']:>6}/{r['mutants_total']}"
        )
    return "\n".join(lines)


def _compute(args) -> int:
    root = Path(".")
    failures = _run_gate(root)
    if failures:
        for failure in failures:
            print(f"error: {failure}", file=sys.stderr)
        return EXIT_DATA
    built = tables.build(root, Path(args.evaluation_dir))
    target = tables.write(root, built, tables.run_info(root))
    print(_summary(built["metrics"]))
    print(f"tables: {target}")
    return EXIT_OK


def _figures(args) -> int:
    root = Path(".")
    try:
        loaded = tables.read(root)
        run = json.loads((root / config.METRICS_DIR / config.RUN_FILE).read_text())
    except (OSError, ValueError) as exc:
        print(f"error: metrics tables not found ({exc}); run `compute` first", file=sys.stderr)
        return EXIT_DATA
    filters = {
        "macrocategorias": args.macrocategoria,
        "ratings": args.rating,
        "statuses": args.status,
        "sets": args.set,
        "scenarios": args.scenario,
        "problems": args.problem,
    }
    try:
        if cuts.apply(loaded["per_problem"], **filters).empty:
            raise cuts.CutError("no combination with these filters")
    except cuts.CutError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_USAGE
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    names = args.figure or list(figures.FIGURES)
    for name in names:
        for fmt in args.format.split(","):
            try:
                file_name, data = figures.render(
                    name, loaded, filters, fmt, figures.source_label(run)
                )
            except cuts.CutError as exc:
                if args.figure:
                    print(f"error: {exc}", file=sys.stderr)
                    return EXIT_USAGE
                print(f"skipped {name}: {exc}")
                break
            except ValueError as exc:
                print(f"error: {exc}", file=sys.stderr)
                return EXIT_USAGE
            (out / file_name).write_bytes(data)
            print(f"figure: {out / file_name}")
    return EXIT_OK


def _package(args) -> int:
    root = Path(".")
    folder = root / config.METRICS_DIR
    missing = [f for f in config.TABLES.values() if not (folder / f).is_file()]
    defaults = [
        figures.file_name(n, {}, fmt) for n in figures.FIGURES for fmt in figures.PACKAGED_FORMATS
    ]
    missing += [f"figures/{f}" for f in defaults if not (folder / "figures" / f).is_file()]
    if missing:
        print(
            f"error: missing in {folder}: {', '.join(missing[:5])}; run `compute` and `figures`",
            file=sys.stderr,
        )
        return EXIT_DATA
    zip_path = packaging.build_zip(root)
    packaging.build_manifest(root, zip_path)
    print(
        f"packaged: {zip_path} ({zip_path.stat().st_size} bytes)\nmanifest: {config.METRICS_MANIFEST}"
    )
    return EXIT_OK


def _verify(args) -> int:
    root = Path(".")
    if not (root / config.METRICS_MANIFEST).is_file():
        print(f"error: manifest not found: {config.METRICS_MANIFEST}", file=sys.stderr)
        return EXIT_USAGE
    result = packaging.verify(root, Path(args.extracted) if args.extracted else None)
    for label, items in (
        ("changed", result.changed),
        ("missing", result.missing),
        ("extra", result.extra),
    ):
        for item in items:
            print(f"{label}: {item}")
    print("OK" if result.ok else "FAIL")
    return EXIT_OK if result.ok else EXIT_DATA


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m metrics", description="Metrics of the thesis.")
    sub = parser.add_subparsers(dest="command")
    compute = sub.add_parser("compute", help="compute the metrics tables into data/metrics")
    compute.add_argument("--evaluation-dir", default=str(config.EVALUATION_DIR))
    figs = sub.add_parser("figures", help="draw the figures (with optional filters)")
    figs.add_argument("--figure", action="append", choices=list(figures.FIGURES), default=[])
    figs.add_argument("--macrocategoria", action="append", default=[])
    figs.add_argument("--rating", action="append", type=int, default=[], metavar="RATING")
    figs.add_argument("--status", action="append", default=[])
    figs.add_argument("--set", action="append", choices=config.SETS, default=[])
    figs.add_argument("--scenario", action="append", choices=config.SCENARIOS, default=[])
    figs.add_argument("--problem", action="append", default=[], metavar="ID")
    figs.add_argument("--format", default="png,svg,pdf")
    figs.add_argument("--output-dir", default=str(config.FIGURES_DIR))
    sub.add_parser("package", help="build data/metrics.zip and its manifest")
    verify = sub.add_parser(
        "verify", help="check the zip (and an extracted folder) against the manifest"
    )
    verify.add_argument("--extracted", default=None, metavar="DIR")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code or 0)
    run = {"compute": _compute, "figures": _figures, "package": _package, "verify": _verify}
    if args.command not in run:
        parser.print_help(sys.stderr)
        return EXIT_USAGE
    return run[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
