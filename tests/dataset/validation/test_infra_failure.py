"""`InfraError` is never a verdict, and SIGINT is a safe interruption (T076; FR-010).

Every other invariant this task lists is already exercised where the behavior actually lives:
`InfraError` from a compile or run call propagates without becoming a verdict, at the engine
boundary (`test_ac.py::test_an_infra_error_is_not_an_ac_failure_and_creates_no_triage`,
`test_wa.py`), through a whole problem, leaving it in `building/`
(`test_problem.py::test_an_infra_error_leaves_the_problem_in_building_and_is_not_a_verdict`), with
a limited retry at the pipeline level
(`test_pipeline.py::test_an_infra_error_is_retried_once_and_then_propagates_leaving_building`),
and mapped to exit code 3 by the CLI (`test_cli_validate_audit.py::test_an_infrastructure_failure_exits_with_3`).
That file also proves `SIGTERM` is treated as a safe interruption (exit 130, `finally` blocks
run). What is genuinely new here is `SIGINT` itself (Ctrl+C, not `docker stop`'s `SIGTERM`): unlike
`SIGTERM`, `main()` installs no handler for it, so it relies on Python's default behavior
(`KeyboardInterrupt`) reaching the same `except KeyboardInterrupt` in `main()` — worth its own
regression, since a future refactor could add a competing `SIGINT` handler without anyone
noticing it broke this path.
"""

import os
import signal

from dataset import __main__ as cli
from dataset.validation import pipeline


def test_sigint_during_validate_exits_130_and_leaves_a_resumable_state(monkeypatch, capsys):
    cleaned = []

    def killed(*args, **kwargs):
        try:
            os.kill(os.getpid(), signal.SIGINT)
        finally:
            cleaned.append("finally ran")  # a running worker pool would be closed here too

    monkeypatch.setattr(pipeline, "run_validate", killed)
    before = signal.getsignal(signal.SIGINT)
    assert cli.main(["validate"]) == 130
    assert "safe to run the command again" in capsys.readouterr().err
    assert cleaned == ["finally ran"]
    assert signal.getsignal(signal.SIGINT) == before  # main() never touches SIGINT's handler
