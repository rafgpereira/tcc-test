"""Unit tests of the runner helpers that need neither root nor a container (T043)."""

import pytest

from sandbox import runner


def test_parse_report_reads_errno_status_cpu_and_peak():
    errno, status, cpu, peak_kib = runner.parse_report("0 0 1 500000 0 250000 40960\n")
    assert (errno, status, peak_kib) == (0, 0, 40960)
    assert cpu == pytest.approx(1.75)


def test_parse_report_keeps_the_exec_errno_and_the_raw_wait_status():
    errno, status, _, _ = runner.parse_report("2 0 0 0 0 0 0")
    assert errno == 2
    _, status, _, _ = runner.parse_report("0 139 0 1000 0 0 100")
    assert status == 139  # SIGSEGV with core flag, decoded later with os.W* helpers


@pytest.mark.parametrize("text", ["", "1 2 3", "a b c d e f g", "0 0 0 0 0 0 0 0"])
def test_parse_report_rejects_a_malformed_report(text):
    if text == "a b c d e f g":
        with pytest.raises(ValueError):
            runner.parse_report(text)
    else:
        assert runner.parse_report(text) is None
