#ifndef ZEN_READINESS_TEST_PROBE_H
#define ZEN_READINESS_TEST_PROBE_H
/* Test-only OS fixtures. No readiness implementation lives here. */
#include <sys/socket.h>
#include <sys/time.h>
#include <time.h>
#include <signal.h>
#include <unistd.h>
#include <fcntl.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

static int fixture_pair[2] = {-1, -1};
static volatile sig_atomic_t fixture_signals = 0;
static int fixture_start(void) {
    if (socketpair(AF_UNIX, SOCK_STREAM, 0, fixture_pair)) return 0;
    for (int i = 0; i < 2; ++i) {
        int flags = fcntl(fixture_pair[i], F_GETFL);
        if (flags < 0 || fcntl(fixture_pair[i], F_SETFL, flags | O_NONBLOCK)) return 0;
    }
    return 1;
}
static int fixture_fd(int index) { return fixture_pair[index]; }
static int fixture_write(void) { return write(fixture_pair[1], "x", 1) == 1; }
static int fixture_drain(void) { char byte; return read(fixture_pair[0], &byte, 1) == 1; }
static int fixture_open(int fd) { return fcntl(fd, F_GETFD) >= 0; }
static void fixture_close_peer(void) { close(fixture_pair[1]); fixture_pair[1] = -1; }
static void fixture_finish(void) {
    if (fixture_pair[0] >= 0) close(fixture_pair[0]);
    if (fixture_pair[1] >= 0) close(fixture_pair[1]);
    fixture_pair[0] = fixture_pair[1] = -1;
}
static unsigned char fixture_original_fds[1024];
static void fixture_snapshot(void) {
    for (int fd = 0; fd < 1024; ++fd) fixture_original_fds[fd] = fcntl(fd, F_GETFD) >= 0;
}
static int fixture_new_cloexec(void) {
    int count = 0;
    for (int fd = 0; fd < 1024; ++fd) {
        int flags = fcntl(fd, F_GETFD);
        if (flags >= 0 && !fixture_original_fds[fd]) {
            if (!(flags & FD_CLOEXEC)) return 0;
            ++count;
        }
    }
    return count == 1;
}
static int fixture_fd_count(void) {
    int count = 0;
    for (int fd = 0; fd < 1024; ++fd) count += fcntl(fd, F_GETFD) >= 0;
    return count;
}
static int64_t fixture_millis(void) {
    struct timespec time;
    if (clock_gettime(CLOCK_MONOTONIC, &time)) abort();
    return (int64_t)time.tv_sec * 1000 + time.tv_nsec / 1000000;
}
static void fixture_signal(int signal) { (void)signal; ++fixture_signals; }
static int fixture_alarm(int milliseconds) {
    struct sigaction action = {0};
    struct itimerval timer = {0};
    action.sa_handler = fixture_signal;
    sigemptyset(&action.sa_mask);
    if (sigaction(SIGALRM, &action, NULL)) return 0;
    timer.it_value.tv_sec = milliseconds / 1000;
    timer.it_value.tv_usec = (milliseconds % 1000) * 1000;
    return setitimer(ITIMER_REAL, &timer, NULL) == 0;
}
static int fixture_signal_count(void) { return fixture_signals; }
static void fixture_check(int value, int line) {
    if (!value) { fprintf(stderr, "readiness assertion failed at test line %d\n", line); exit(1); }
}
#endif
