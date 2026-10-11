// sandbox-launch: runs ONE program and reports how it ended, with an accurate memory peak.
//
// Why it exists: the kernel folds the resident set of the process that called fork() into the
// ru_maxrss of the child at exec time. The orchestrator is a large Python process, so measuring
// the program from Python reports tens of MB for a program that uses 1 MB (and would report a
// false MLE for small memory limits). This launcher is tiny, so its child's ru_maxrss is the
// program's own peak.
//
// Usage: sandbox-launch <report-fd> <program> [args...]
// The uid, session and resource limits are already applied by the orchestrator before it execs
// this launcher; the program inherits them. Report line written to <report-fd>:
//   <exec-errno> <wait-status> <utime-s> <utime-us> <stime-s> <stime-us> <maxrss-KiB>
#include <fcntl.h>
#include <sys/resource.h>
#include <sys/wait.h>
#include <unistd.h>

#include <cerrno>
#include <cstdio>
#include <cstdlib>

int main(int argc, char** argv) {
    if (argc < 3) return 2;
    const int report_fd = std::atoi(argv[1]);
    int exec_pipe[2];
    if (pipe2(exec_pipe, O_CLOEXEC) != 0) return 3;
    const pid_t pid = fork();
    if (pid < 0) {
        dprintf(report_fd, "%d 0 0 0 0 0 0\n", errno);
        return 0;
    }
    if (pid == 0) {
        close(exec_pipe[0]);
        execv(argv[2], argv + 2);
        const int saved = errno;
        if (write(exec_pipe[1], &saved, sizeof saved) < 0) _exit(126);
        _exit(127);
    }
    close(exec_pipe[1]);
    int exec_errno = 0;
    const ssize_t got = read(exec_pipe[0], &exec_errno, sizeof exec_errno);
    if (got <= 0) exec_errno = 0;  // the pipe closes on a successful exec
    int status = 0;
    struct rusage usage {};
    while (wait4(pid, &status, 0, &usage) < 0) {
        if (errno != EINTR) break;
    }
    dprintf(report_fd, "%d %d %ld %ld %ld %ld %ld\n", exec_errno, status,
            static_cast<long>(usage.ru_utime.tv_sec), static_cast<long>(usage.ru_utime.tv_usec),
            static_cast<long>(usage.ru_stime.tv_sec), static_cast<long>(usage.ru_stime.tv_usec),
            usage.ru_maxrss);
    return 0;
}
