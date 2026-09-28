#ifndef ZEN_STD_READINESS_H
#define ZEN_STD_READINESS_H
/* Platform ABI only: no scheduler, allocation, timeout or retry policy. */
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stddef.h>
#include <unistd.h>
#ifdef __APPLE__
#include <sys/event.h>
typedef struct kevent zen_ready_event;
#else
#include <sys/epoll.h>
typedef struct epoll_event zen_ready_event;
#endif
static size_t zen_ready_words(int capacity) {
    return ((size_t)capacity * sizeof(zen_ready_event) + sizeof(uintptr_t) - 1) / sizeof(uintptr_t);
}
static int zen_ready_open(void) {
#ifdef __APPLE__
    int fd = kqueue();
    if (fd >= 0 && fcntl(fd, F_SETFD, FD_CLOEXEC) < 0) {
        int saved = errno; close(fd); errno = saved; return -1;
    }
    return fd;
#else
    return epoll_create1(EPOLL_CLOEXEC);
#endif
}
static int zen_ready_change(int queue, int fd, size_t slot, int write, int fresh) {
#ifdef __APPLE__
    (void)fresh;
    struct kevent changes[2];
    EV_SET(&changes[0], fd, EVFILT_READ, EV_ADD | (write ? EV_DISABLE : EV_ENABLE), 0, 0, (void *)(uintptr_t)slot);
    EV_SET(&changes[1], fd, EVFILT_WRITE, EV_ADD | (write ? EV_ENABLE : EV_DISABLE), 0, 0, (void *)(uintptr_t)slot);
    return kevent(queue, changes, 2, NULL, 0, NULL);
#else
    struct epoll_event event = {0};
    event.events = write ? EPOLLOUT : EPOLLIN;
    event.data.u64 = slot;
    return epoll_ctl(queue, fresh ? EPOLL_CTL_ADD : EPOLL_CTL_MOD, fd, &event);
#endif
}
static int zen_ready_remove(int queue, int fd) {
#ifdef __APPLE__
    struct kevent change;
    int saved = 0;
    EV_SET(&change, fd, EVFILT_READ, EV_DELETE, 0, 0, NULL);
    if (kevent(queue, &change, 1, NULL, 0, NULL) < 0 && errno != ENOENT) saved = errno;
    EV_SET(&change, fd, EVFILT_WRITE, EV_DELETE, 0, 0, NULL);
    if (kevent(queue, &change, 1, NULL, 0, NULL) < 0 && errno != ENOENT && !saved) saved = errno;
    if (saved) { errno = saved; return -1; }
    return 0;
#else
    return epoll_ctl(queue, EPOLL_CTL_DEL, fd, NULL);
#endif
}
static int zen_ready_wait(int queue, uintptr_t *events, int capacity, int timeout_ms) {
#ifdef __APPLE__
    struct timespec timeout = {timeout_ms / 1000, (timeout_ms % 1000) * 1000000L};
    return kevent(queue, NULL, 0, (zen_ready_event *)events, capacity, timeout_ms < 0 ? NULL : &timeout);
#else
    return epoll_wait(queue, (zen_ready_event *)events, capacity, timeout_ms);
#endif
}
static size_t zen_ready_slot(uintptr_t *events, size_t index) {
#ifdef __APPLE__
    return (uintptr_t)((zen_ready_event *)events)[index].udata;
#else
    return (size_t)((zen_ready_event *)events)[index].data.u64;
#endif
}
static int zen_ready_errno(void) { return errno; }
static int zen_ready_interrupted(int error) { return error == EINTR; }
#endif
