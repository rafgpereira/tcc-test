"""``python -m dashboard serve`` builds the right command and environment (T008)."""

import dashboard.__main__ as cli


def test_serve_runs_streamlit_locally_without_telemetry(tmp_path):
    calls = []

    def run(command, env):
        calls.append((command, env))
        return 0

    code = cli.main(
        ["serve", "--evaluation-dir", str(tmp_path), "--port", "8600"],
        run=run,
        has_streamlit=lambda: True,
    )
    assert code == 0
    command, env = calls[0]
    assert command[1:4] == ["-m", "streamlit", "run"] and command[4].endswith("dashboard/app.py")
    assert command[5:] == [
        "--server.address",
        "0.0.0.0",
        "--server.port",
        "8600",
        "--server.headless",
        "true",
    ]
    assert env["HOME"] == "/tmp"
    assert env["STREAMLIT_BROWSER_GATHER_USAGE_STATS"] == "false"
    assert env["STREAMLIT_SERVER_FILE_WATCHER_TYPE"] == "none"
    assert env["STREAMLIT_BROWSER_SERVER_ADDRESS"] == "localhost"
    assert env["DASHBOARD_EVALUATION_DIR"] == str(tmp_path)


def test_usage_errors_and_missing_streamlit(tmp_path):
    def never(*args, **kwargs):
        raise AssertionError("must not start")

    assert cli.main(["serve", "--evaluation-dir", str(tmp_path / "x")], run=never) == 2
    assert cli.main([], run=never) == 2
    assert (
        cli.main(
            ["serve", "--evaluation-dir", str(tmp_path)], run=never, has_streamlit=lambda: False
        )
        == 3
    )


def test_ctrl_c_is_a_normal_exit(tmp_path):
    def interrupted(command, env):
        raise KeyboardInterrupt

    assert cli.main(["serve", "--evaluation-dir", str(tmp_path)], run=interrupted) == 0
