"""``python -m dashboard serve``: open the read-only results dashboard (contracts/cli.md).

It runs ``streamlit run`` on ``app.py`` listening on every interface of the container; the README
publishes the port only on ``127.0.0.1`` of the host, so only this machine reaches it. ``HOME`` goes
to ``/tmp`` (the container root is read only and Streamlit keeps its settings in ``~/.streamlit``),
the usage statistics are off and the announced address is ``localhost`` (no lookup of the
external IP): nothing leaves the machine.

Exit codes: 0 closed (also with Ctrl+C), 2 usage error, 3 Streamlit missing in the image.
"""

import argparse
import importlib.util
import os
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from dashboard import config

EXIT_OK, EXIT_USAGE, EXIT_MISSING = 0, 2, 3
APP = Path(__file__).with_name("app.py")


def build_command(port: int) -> list[str]:
    return [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(APP),
        "--server.address",
        "0.0.0.0",
        "--server.port",
        str(port),
        "--server.headless",
        "true",
    ]


def build_env(base: Mapping[str, str], evaluation_dir: Path) -> dict[str, str]:
    env = dict(base)
    env.update(
        {
            "HOME": "/tmp",
            "STREAMLIT_BROWSER_GATHER_USAGE_STATS": "false",
            "STREAMLIT_SERVER_FILE_WATCHER_TYPE": "none",
            # Announce localhost: otherwise Streamlit looks up the external IP on the internet.
            "STREAMLIT_BROWSER_SERVER_ADDRESS": "localhost",
            config.ENV_EVALUATION_DIR: str(evaluation_dir),
        }
    )
    return env


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m dashboard", description="Read-only dashboard of the evaluation results."
    )
    sub = parser.add_subparsers(dest="command")
    serve = sub.add_parser(
        "serve", help="open the dashboard at http://localhost:8501 (app service, port published)"
    )
    serve.add_argument(
        "--evaluation-dir", default=str(config.DEFAULT_EVALUATION_DIR), metavar="DIR"
    )
    serve.add_argument("--port", type=int, default=config.PORT)
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    run: Callable[..., int] = subprocess.call,
    has_streamlit: Callable[[], bool] = lambda: importlib.util.find_spec("streamlit") is not None,
) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code or 0)
    if args.command != "serve":
        parser.print_help(sys.stderr)
        return EXIT_USAGE
    folder = Path(args.evaluation_dir)
    if not folder.is_dir():
        print(
            f"error: not a folder: {folder} (run `python -m evaluation run` first)", file=sys.stderr
        )
        return EXIT_USAGE
    if not has_streamlit():
        print(
            "error: streamlit is not installed in the image; run `docker compose build`",
            file=sys.stderr,
        )
        return EXIT_MISSING
    print(f"dashboard: http://localhost:{args.port} (Ctrl+C para fechar)", flush=True)
    try:
        run(build_command(args.port), env=build_env(os.environ, folder))
    except KeyboardInterrupt:
        pass
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
