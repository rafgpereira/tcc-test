"""Integration tests of the runner and of the isolation of third-party code (T040; D13 rule 7).

They compile and run real C++ as the dedicated slot uid, so they only run in the `sandbox`
service (root with CHOWN, DAC_OVERRIDE, SETUID, SETGID and KILL; no network; `/sandbox` tmpfs).
"""

import os
import shutil
import signal
import time
from pathlib import Path

import pytest

from dataset.persistence import store
from sandbox import isolation, judge
from sandbox.limits import STACK_LIMIT_BYTES
from sandbox.runner import run_binary
from sandbox.types import ExecutionLimits, InfraError, RunStatus, Verdict

MIB = 1024 * 1024
LIMITS = ExecutionLimits(time_limit_seconds=2.0, memory_limit_bytes=256 * MIB)
BIG_LIMITS = ExecutionLimits(time_limit_seconds=5.0, memory_limit_bytes=1024 * MIB)

PROBE = r"""
#include <cstdio>
#include <cstring>
#include <initializer_list>
#include <unistd.h>
int main() {
    std::printf("uid=%d euid=%d gid=%d egid=%d\n", (int)getuid(), (int)geteuid(),
                (int)getgid(), (int)getegid());
    for (const char* path : {"/proc/self/status", "/proc/self/limits"}) {
        FILE* f = std::fopen(path, "r");
        char line[512];
        while (f && std::fgets(line, sizeof line, f)) {
            if (!std::strncmp(line, "CapEff", 6) || !std::strncmp(line, "CapPrm", 6) ||
                !std::strncmp(line, "Groups", 6) || !std::strncmp(line, "NoNewPrivs", 10) ||
                !std::strncmp(line, "Max stack size", 14) ||
                !std::strncmp(line, "Max address space", 17) ||
                !std::strncmp(line, "Max processes", 13) || !std::strncmp(line, "Max core", 8))
                std::fputs(line, stdout);
        }
        if (f) std::fclose(f);
    }
}
"""

RECURSION = r"""
#include <cstdio>
static __attribute__((noinline)) long f(long n) {
    volatile char buf[1024];
    buf[0] = (char)n;
    if (n == 0) return buf[0];
    long r = f(n - 1);
    buf[1] = (char)r;
    return r + buf[0] + buf[1];
}
int main() { long depth; if (std::scanf("%ld", &depth) != 1) return 2; std::printf("%ld\n", f(depth)); }
"""

FILESYSTEM = r"""
#include <cerrno>
#include <cstdio>
#include <dirent.h>
#include <fcntl.h>
#include <string>
#include <unistd.h>
int main() {
    char path[1024];
    while (std::scanf("%1023s", path) == 1) {
        DIR* d = opendir(path);
        int list = d ? 0 : errno;
        if (d) closedir(d);
        std::string file = std::string(path) + "/child-was-here";
        int fd = open(file.c_str(), O_WRONLY | O_CREAT | O_EXCL, 0600);
        int create = fd >= 0 ? 0 : errno;
        if (fd >= 0) { close(fd); unlink(file.c_str()); }
        int rd = open((std::string(path) + "/secret.txt").c_str(), O_RDONLY);
        int read_ = rd >= 0 ? 0 : errno;
        if (rd >= 0) close(rd);
        std::printf("%s list=%d create=%d read=%d\n", path, list, create, read_);
    }
}
"""

FORK_COUNT = r"""
#include <cstdio>
#include <sys/wait.h>
#include <unistd.h>
int main() {
    int made = 0;
    for (int i = 0; i < 200; i++) {
        pid_t p = fork();
        if (p == 0) { pause(); _exit(0); }
        if (p < 0) break;
        made++;
    }
    std::printf("%d\n", made);
    std::fflush(stdout);
}
"""

FORK_BOMB = r"""
#include <unistd.h>
int main() { for (;;) fork(); }
"""

ALLOCATE = r"""
#include <cstdio>
#include <cstring>
int main() {
    const unsigned long n = 512ul * 1024 * 1024;
    char* p = new char[n];
    asm volatile("" : : "r"(p) : "memory");  // keep the allocation: -O2 would elide it otherwise
    std::memset(p, 1, n);
    asm volatile("" : : "r"(p) : "memory");
    std::printf("%d\n", (int)p[1000]);
}
"""

HELLO = r"""
#include <cstdio>
int main() { std::puts("hi"); }
"""

TOUCH_100_MB = r"""
#include <cstdio>
#include <cstring>
int main() {
    const unsigned long n = 100ul * 1024 * 1024;
    char* p = new char[n];
    asm volatile("" : : "r"(p) : "memory");
    std::memset(p, 1, n);
    asm volatile("" : : "r"(p) : "memory");
    std::printf("%d\n", (int)p[1000]);
}
"""

SLEEP = r"""
#include <unistd.h>
int main() { sleep(100); }
"""

FLOOD = r"""
#include <cstdio>
int main() { for (;;) std::puts("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"); }
"""

CHATTY = r"""
#include <cstdio>
int main() { int n; std::scanf("%d", &n); std::printf("%d\n", n * 2); }
"""


def parse_lines(text: str) -> dict[str, str]:
    """`key: value` style lines of /proc files and of the probes, keyed by the first token."""
    result = {}
    for line in text.splitlines():
        if line.startswith("Max "):
            name, _, rest = line.partition("  ")
            result[name.strip()] = " ".join(rest.split())
        elif ":" in line:
            key, _, value = line.partition(":")
            result[key.strip()] = value.strip()
    return result


def processes_of_uid(uid: int) -> list[int]:
    found = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            for line in (entry / "status").read_text().splitlines():
                if line.startswith("Uid:") and int(line.split()[1]) == uid:
                    found.append(int(entry.name))
        except (OSError, ValueError):
            continue
    return found


def wait_until_no_process(uid: int, seconds: float = 3.0) -> list[int]:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if not processes_of_uid(uid):
            return []
        time.sleep(0.05)
    return processes_of_uid(uid)


# ---------------------------------------------------------------------------- unit


def test_a_failure_to_launch_is_an_infra_error_and_never_a_verdict(slot):
    with pytest.raises(InfraError):
        run_binary(Path("/sandbox/does-not-exist/main"), b"", LIMITS, slot)


# ---------------------------------------------------------------------------- integration


@pytest.mark.integration
def test_the_child_runs_as_the_dedicated_uid_without_any_capability(build, slot):
    run = run_binary(build(PROBE), b"", LIMITS, slot)
    assert run.status is RunStatus.OK, run.stderr_tail
    text = run.stdout.decode()
    uid = isolation.slot_uid(slot)
    assert f"uid={uid} euid={uid} gid={uid} egid={uid}" in text
    fields = parse_lines(text)
    assert int(fields["CapEff"], 16) == 0
    assert int(fields["CapPrm"], 16) == 0
    assert fields["Groups"] == ""  # setgroups([]): no supplementary groups


@pytest.mark.integration
def test_the_child_limits_are_applied_in_bytes(build, slot):
    run = run_binary(build(PROBE), b"", LIMITS, slot)
    limits = parse_lines(run.stdout.decode())
    assert limits["Max stack size"].startswith(f"{STACK_LIMIT_BYTES} {STACK_LIMIT_BYTES} bytes")
    assert limits["Max address space"].startswith(
        f"{LIMITS.memory_limit_bytes} {LIMITS.memory_limit_bytes} bytes"
    )
    assert limits["Max processes"].startswith("32 32")
    assert (
        limits["Max core file size"].startswith("0 0") if "Max core file size" in limits else True
    )


@pytest.mark.integration
def test_a_recursion_of_about_150_mb_passes_under_the_256_mib_stack(build, slot):
    run = run_binary(build(RECURSION), b"150000\n", BIG_LIMITS, slot)
    assert run.status is RunStatus.OK, run.stderr_tail
    assert run.peak_rss_bytes > 100 * MIB  # the stack really grew


@pytest.mark.integration
def test_a_recursion_beyond_256_mib_ends_as_a_runtime_error(build, slot):
    run = run_binary(build(RECURSION), b"400000\n", BIG_LIMITS, slot)
    assert run.status is RunStatus.SIGNALED
    assert run.signal == signal.SIGSEGV
    assert judge.judge_test(run, "0\n", BIG_LIMITS) is Verdict.RE


@pytest.mark.integration
def test_the_child_cannot_touch_the_work_dir_nor_the_file_system(build, slot, workdir):
    root = Path("/sandbox/isolation-root")
    shutil.rmtree(root, ignore_errors=True)
    try:
        root.mkdir(mode=0o755)
        work = store.ensure_work_dir(root)  # data/work with mode 0700, as in production
        (work / "secret.txt").write_text("top secret")
        other = isolation.prepare_slot_workdir(1)  # the workdir of ANOTHER slot
        targets = [str(work), "/", "/etc", "/sandbox", "/tmp", "/dev/shm", "/dev/mqueue"]
        targets += [str(other), "."]
        run = run_binary(build(FILESYSTEM), "\n".join(targets).encode(), LIMITS, slot)
        assert run.status is RunStatus.OK, run.stderr_tail
        seen = {}
        for line in run.stdout.decode().splitlines():
            path, *pairs = line.split()
            seen[path] = dict(pair.split("=") for pair in pairs)
        denied = {"13", "30", "1", "2"}  # EACCES, EROFS, EPERM, ENOENT
        for path in (str(work), str(other)):
            assert seen[path]["list"] != "0", f"the child listed {path}"
            assert seen[path]["create"] in denied, f"the child wrote in {path}"
            assert seen[path]["read"] != "0", f"the child read a file in {path}"
        for path in ("/", "/etc", "/sandbox", "/tmp", "/dev/shm", "/dev/mqueue"):
            assert seen[path]["create"] != "0", f"the child wrote in {path}"
        assert seen["."]["create"] == "0", "the child must write in its own slot workdir"
    finally:
        shutil.rmtree(root, ignore_errors=True)
        shutil.rmtree(isolation.slot_workdir(1), ignore_errors=True)


@pytest.mark.integration
def test_a_bounded_number_of_children_can_be_created_and_none_survives(build, slot):
    run = run_binary(build(FORK_COUNT), b"", LIMITS, slot)
    assert run.status is RunStatus.OK, run.stderr_tail
    made = int(run.stdout.decode().strip())
    assert 1 <= made < 32
    assert wait_until_no_process(isolation.slot_uid(slot)) == []


@pytest.mark.integration
def test_a_fork_bomb_is_contained_and_the_orchestrator_survives(build, slot):
    limits = ExecutionLimits(time_limit_seconds=0.5, memory_limit_bytes=256 * MIB)
    binary = build(FORK_BOMB)
    run = run_binary(binary, b"", limits, slot)
    assert run.status in {RunStatus.TIMEOUT, RunStatus.SIGNALED, RunStatus.OK}
    assert wait_until_no_process(isolation.slot_uid(slot)) == []
    assert os.getpid() > 0  # still here
    again = run_binary(build(CHATTY), b"21\n", LIMITS, slot)  # the engine still works
    assert again.stdout.decode().strip() == "42"


@pytest.mark.integration
def test_allocating_more_than_the_memory_limit_ends_as_mle(build, slot):
    limits = ExecutionLimits(time_limit_seconds=2.0, memory_limit_bytes=128 * MIB)
    run = run_binary(build(ALLOCATE), b"", limits, slot)
    assert run.status is RunStatus.SIGNALED
    assert run.signal == signal.SIGABRT
    assert b"bad_alloc" in run.stderr_tail
    assert judge.judge_test(run, "1\n", limits) is Verdict.MLE


@pytest.mark.integration
def test_a_blocked_program_is_killed_by_the_wall_clock_reserve(build, slot):
    limits = ExecutionLimits(time_limit_seconds=0.3, memory_limit_bytes=256 * MIB)
    run = run_binary(build(SLEEP), b"", limits, slot)
    assert run.status is RunStatus.TIMEOUT
    assert run.wall_time_s < 5
    assert judge.judge_test(run, "", limits) is Verdict.TLE
    assert wait_until_no_process(isolation.slot_uid(slot)) == []


@pytest.mark.integration
def test_unbounded_output_is_cut_and_classified_as_a_runtime_error(build, slot):
    run = run_binary(build(FLOOD), b"", LIMITS, slot)
    assert run.status is RunStatus.OUTPUT_LIMIT
    assert judge.judge_test(run, "", LIMITS) is Verdict.RE


@pytest.mark.integration
def test_the_same_program_twice_gives_the_same_verdict_and_output(build, slot):
    binary = build(CHATTY)
    first = run_binary(binary, b"21\n", LIMITS, slot)
    second = run_binary(binary, b"21\n", LIMITS, slot)
    assert first.stdout == second.stdout == b"42\n"
    verdicts = {judge.judge_test(r, "42\n", LIMITS) for r in (first, second)}
    assert verdicts == {Verdict.AC}


@pytest.mark.integration
def test_the_cpu_time_is_measured_from_the_child_not_from_the_wall_clock(build, slot):
    run = run_binary(build(SLEEP), b"", ExecutionLimits(0.3, 256 * MIB), slot)
    assert run.cpu_time_s < 0.2  # a sleeping program burns no CPU


@pytest.mark.integration
def test_the_memory_peak_is_the_programs_own_and_not_the_orchestrators(build, slot):
    # The orchestrator here is a Python process of tens of MB: measuring from it would inflate the
    # peak of a program that uses about 1 MB (and give false MLEs under small limits).
    run = run_binary(build(HELLO), b"", LIMITS, slot)
    assert run.status is RunStatus.OK
    assert run.peak_rss_bytes < 8 * MIB


@pytest.mark.integration
def test_a_program_that_touches_100_mb_reports_about_100_mb(build, slot):
    run = run_binary(build(TOUCH_100_MB), b"", LIMITS, slot)
    assert run.status is RunStatus.OK, run.stderr_tail
    assert 100 * MIB <= run.peak_rss_bytes < 130 * MIB


@pytest.mark.integration
def test_a_small_memory_limit_is_not_a_false_mle_of_the_orchestrator_footprint(build, slot):
    limits = ExecutionLimits(
        time_limit_seconds=2.0, memory_limit_bytes=64_000_000
    )  # smallest of the pool
    run = run_binary(build(CHATTY), b"21\n", limits, slot)
    assert judge.judge_test(run, "42\n", limits) is Verdict.AC


@pytest.mark.integration
def test_a_missing_binary_in_an_existing_directory_is_an_infra_error(workdir, slot):
    with pytest.raises(InfraError):
        run_binary(workdir / "no-such-binary", b"", LIMITS, slot)
