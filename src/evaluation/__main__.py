"""Command line entry point of the evaluation module: ``python -m evaluation <command>``.

contracts/cli.md (specs/009-suite-evaluation). Exit codes: 0 success, 1 data failure (a gate or a
refused package), 2 usage error (also a ``run.json`` of other inputs, or a run already going on),
3 infrastructure failure, 130 interrupted.
"""

import argparse
import os
import signal
import sys
import time
from collections.abc import Callable, Sequence
from concurrent.futures import FIRST_COMPLETED, Future, wait
from pathlib import Path

from evaluation import config, gate, packaging, problem_task, report, sources, store
from evaluation import runtime as runtime_module
from sandbox.types import InfraError

EXIT_OK = 0
EXIT_DATA_FAILURE = 1
EXIT_USAGE = 2
EXIT_INFRA = 3
EXIT_INTERRUPTED = 130


def default_workers() -> int:
    return max(1, (os.cpu_count() or 2) - 1)


def _positive_int(text: str) -> int:
    value = int(text)
    if value < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return value


# Injection points for the tests (a fake engine and gates); the real ones need the sandbox service.
def _make_engine() -> problem_task.Engine:
    return problem_task.real_engine()


def _make_runtime(workers: int, engine: problem_task.Engine) -> runtime_module.Runtime:
    if workers == 1:
        return runtime_module.InlineRuntime(engine)
    return runtime_module.PoolRuntime(workers)


def _run_gates(root: Path, sets: Sequence[str]) -> list[str]:
    return gate.run_gates(root, sets)


# --------------------------------------------------------------------------------------- run


def _configure_run(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--set", action="append", choices=config.SETS, dest="sets", default=[])
    parser.add_argument("--problem", action="append", default=[], metavar="ID")
    parser.add_argument(
        "--scenario", action="append", choices=config.SCENARIOS, dest="scenarios", default=[]
    )
    parser.add_argument("--workers", type=_positive_int, default=default_workers())
    parser.add_argument("--output-dir", default=str(config.EVALUATION_DIR), metavar="DIR")


def _tasks(
    root: Path, base: Path, problems: Sequence[str], sets: Sequence[str], scenarios: Sequence[str]
):
    """One task per problem with the sets that are still missing in it (FR-015)."""
    for problem_id in problems:
        missing = [s for s in sets if not store.is_closed(base, s, problem_id)]
        if not missing:
            continue
        suites = tuple(
            ((s, sc), sources.suite_for(root, s, problem_id, sc))
            for s in missing
            for sc in scenarios
        )
        yield problem_task.ProblemTask(sources.problem_targets(root, problem_id), suites)


def evaluate(
    root: Path,
    base: Path,
    problems: Sequence[str],
    sets: Sequence[str],
    scenarios: Sequence[str],
    runtime: runtime_module.Runtime,
    echo: Callable[[str], None],
) -> tuple[int, int]:
    """Evaluate and persist; returns (problems evaluated, problems already closed)."""
    done = skipped = 0
    pending: dict[Future, tuple[str, float]] = {}

    def collect(futures) -> None:
        nonlocal done
        for future in futures:
            problem_id, started = pending.pop(future)
            outcome = future.result()  # re-raises an InfraError of the worker
            grouped = problem_task.group_by_set(outcome)
            for set_name in sorted(grouped):
                store.write_problem(base, set_name, problem_id, grouped[set_name])
            done += 1
            echo(f"ok {problem_id} ({len(outcome)} suites, {time.monotonic() - started:.0f} s)")

    for problem_id in problems:
        if all(store.is_closed(base, s, problem_id) for s in sets):
            skipped += 1
    for task in _tasks(root, base, problems, sets, scenarios):
        while len(pending) >= max(1, runtime.workers * 2):
            finished, _ = wait(list(pending), return_when=FIRST_COMPLETED)
            collect(finished)
        pending[runtime.submit(task)] = (task.problem.problem_id, time.monotonic())
    while pending:
        finished, _ = wait(list(pending), return_when=FIRST_COMPLETED)
        collect(finished)
    return done, skipped


def _run_run(args: argparse.Namespace) -> int:
    root = Path(".")
    base = Path(args.output_dir)
    sets = sorted(set(args.sets) or set(config.SETS), key=config.SETS.index)
    scenarios = [s for s in config.SCENARIOS if not args.scenarios or s in args.scenarios]
    if args.scenarios and base.resolve() == (root / config.EVALUATION_DIR).resolve():
        print(
            "error: --scenario is only for a check in another --output-dir (the default tree is "
            "packaged and needs the three scenarios)",
            file=sys.stderr,
        )
        return EXIT_USAGE
    available = sources.dataset_problem_ids(root)
    unknown = [p for p in args.problem if p not in available]
    if unknown:
        print(f"error: not in {config.DATASET_PROBLEMS_DIR}: {', '.join(unknown)}", file=sys.stderr)
        return EXIT_USAGE
    problems = sorted(set(args.problem)) if args.problem else available
    failures = _run_gates(root, sets)
    if failures:
        for failure in failures:
            print(f"error: {failure}", file=sys.stderr)
        return EXIT_DATA_FAILURE
    try:
        with store.exclusive_run(base):
            engine = _make_engine()
            for set_name in sets:
                store.open_run(
                    base, set_name, store.current_run(root, set_name, engine.gcc_version)
                )
                removed = store.reset_building(base, set_name)
                if removed:
                    print(f"{set_name}: {removed} half-written problem(s) will be redone")
            runtime = _make_runtime(args.workers, engine)
            try:
                done, skipped = evaluate(
                    root, base, problems, sets, scenarios, runtime, lambda m: print(m, flush=True)
                )
            except BaseException:
                runtime.close(abort=True)  # Ctrl+C, docker stop, an engine failure: no waiting
                raise
            runtime.close()
    except store.AlreadyRunningError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_USAGE
    except store.RunMismatchError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_USAGE
    print(f"done: {done} problem(s) evaluated, {skipped} already evaluated for every set")
    return EXIT_OK


# ------------------------------------------------------------------------- report / package


def _configure_report(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--set", action="append", choices=config.SETS, dest="sets", default=[])
    parser.add_argument("--output-dir", default=str(config.EVALUATION_DIR), metavar="DIR")


def _existing_sets(base: Path, requested: Sequence[str]) -> list[str]:
    sets = requested or config.SETS
    return [s for s in sets if store.set_dir(base, s).is_dir()]


def _run_report(args: argparse.Namespace) -> int:
    root, base = Path("."), Path(args.output_dir)
    sets = _existing_sets(base, args.sets)
    if not sets:
        print(f"error: no evaluation set in {base}", file=sys.stderr)
        return EXIT_USAGE
    for set_name in sets:
        try:
            csv_path, report_path, summary = report.write_outputs(root, base, set_name)
        except ValueError as exc:
            print(f"error: {set_name}: {exc}", file=sys.stderr)
            return EXIT_DATA_FAILURE
        print(report.render(summary))
        print(f"  table: {csv_path}\n  report: {report_path}")
    return EXIT_OK


def _configure_package(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--set", required=True, choices=config.SETS, dest="set_name")
    parser.add_argument("--output-dir", default=str(config.EVALUATION_DIR), metavar="DIR")


def _run_package(args: argparse.Namespace) -> int:
    root, base = Path("."), Path(args.output_dir)
    if not store.set_dir(base, args.set_name).is_dir():
        print(f"error: {args.set_name} was not evaluated in {base}", file=sys.stderr)
        return EXIT_USAGE
    try:
        _, report_path, summary = report.write_outputs(root, base, args.set_name)
        packaging.check_packable(base, args.set_name, summary.complete, summary.missing)
    except (packaging.PackageRefused, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_DATA_FAILURE
    zip_path = packaging.build_zip(base, args.set_name, root / config.zip_path(args.set_name))
    manifest_path = packaging.write_manifest(
        root, packaging.build_manifest(args.set_name, zip_path)
    )
    print(
        f"packaged {summary.combinations} combinations: {zip_path} ({zip_path.stat().st_size} bytes)"
    )
    print(f"manifest: {manifest_path}\nreport: {report_path}")
    return EXIT_OK


def _configure_verify(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--set", required=True, choices=config.SETS, dest="set_name")
    parser.add_argument("--extracted", default=None, metavar="DIR")


def _run_verify(args: argparse.Namespace) -> int:
    manifest_path = config.manifest_path(args.set_name)
    if not manifest_path.is_file():
        print(f"error: manifest not found: {manifest_path}", file=sys.stderr)
        return EXIT_USAGE
    extracted = Path(args.extracted) if args.extracted else None
    if extracted is not None and not extracted.is_dir():
        print(f"error: not a folder: {extracted}", file=sys.stderr)
        return EXIT_USAGE
    result = packaging.verify(config.zip_path(args.set_name), manifest_path, extracted)
    for path in result.changed:
        print(f"changed: {path}")
    for path in result.missing:
        print(f"missing: {path}")
    for path in result.extra:
        print(f"extra: {path}")
    print("OK" if result.ok else "FAIL")
    return EXIT_OK if result.ok else EXIT_DATA_FAILURE


COMMANDS = {
    "run": (
        "run the suites against AC_ref, the WAs and the mutants (sandbox service)",
        _configure_run,
        _run_run,
    ),
    "report": (
        "rebuild results.csv and manifests/evaluation_<set>_report.json (any time)",
        _configure_report,
        _run_report,
    ),
    "package": (
        "build data/evaluation_<set>.zip and its manifest (complete set only)",
        _configure_package,
        _run_package,
    ),
    "verify": (
        "recompute hashes and compare with the manifest (works right after cloning)",
        _configure_verify,
        _run_verify,
    ),
}


def _raise_interrupt(signum: int, frame: object) -> None:
    raise KeyboardInterrupt


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m evaluation",
        description="Run the generated suites against AC_ref, the WAs and the mutants.",
    )
    subparsers = parser.add_subparsers(dest="command")
    for name, (text, configure, _) in COMMANDS.items():
        configure(subparsers.add_parser(name, help=text, description=text))
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
    previous = signal.signal(signal.SIGTERM, _raise_interrupt)
    try:
        return COMMANDS[args.command][2](args)
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
