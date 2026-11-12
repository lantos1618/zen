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
/* Per-fd interest tracking for EOF-only delivery under Write interest on
   kqueue.  EVFILT_READ must stay enabled to detect a peer half-close
   (EV_EOF on the read filter) even when the send buffer is full and
   EVFILT_WRITE is not pending, but ordinary readable data must not wake a
   Write-interest wait.  EV_CLEAR makes EVFILT_READ edge-triggered so the
   event does not level-pending and busy-spin, and zen_ready_wait filters
   non-EOF read events so they never reach the caller. */
struct zen_ready_interest_entry { int fd; int write; };
static struct zen_ready_interest_entry zen_ready_interests[256];
static int zen_ready_interest_count = 0;
static int zen_ready_interest_find(int fd) {
    for (int i = 0; i < zen_ready_interest_count; ++i)
        if (zen_ready_interests[i].fd == fd) return i;
    return -1;
}
static void zen_ready_interest_set(int fd, int write) {
    int i = zen_ready_interest_find(fd);
    if (i < 0) {
        if (zen_ready_interest_count < 256) i = zen_ready_interest_count++;
        else return;
    }
    zen_ready_interests[i].fd = fd;
    zen_ready_interests[i].write = write;
}
static void zen_ready_interest_clear(int fd) {
    int i = zen_ready_interest_find(fd);
    if (i >= 0) {
        --zen_ready_interest_count;
        if (i < zen_ready_interest_count)
            zen_ready_interests[i] = zen_ready_interests[zen_ready_interest_count];
    }
}
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
    /* Under Write interest EVFILT_READ is edge-triggered (EV_CLEAR) and
       non-EOF events are filtered in zen_ready_wait, so ordinary readable
       data does not wake the wait or level-pending and busy-spin the loop.
       EVFILT_READ stays enabled so a peer half-close (EV_EOF on the read
       filter) can wake the wait even with the send buffer full.  Under Read
       interest EVFILT_READ stays level-triggered for the documented contract. */
    EV_SET(&changes[0], fd, EVFILT_READ, EV_ADD | EV_ENABLE | (write ? EV_CLEAR : 0), 0, 0, (void *)(uintptr_t)slot);
    EV_SET(&changes[1], fd, EVFILT_WRITE, EV_ADD | (write ? EV_ENABLE : EV_DISABLE), 0, 0, (void *)(uintptr_t)slot);
    zen_ready_interest_set(fd, write);
    return kevent(queue, changes, 2, NULL, 0, NULL);
#else
    struct epoll_event event = {0};
    /* Under Write interest, EPOLLOUT and EPOLLRDHUP (where available) are
       sufficient: EPOLLRDHUP wakes on a peer half-close (FIN) even with the
       send buffer full and unread data pending.  EPOLLIN is not included so
       ordinary readable data does not level-pending and busy-spin the wait.
       Without EPOLLRDHUP, EPOLLIN is the only FIN signal on Linux, so the
       fallback keeps it and accepts the residual data-wakeup gap. */
#ifdef EPOLLRDHUP
    event.events = write ? (EPOLLOUT | EPOLLRDHUP) : EPOLLIN;
#else
    event.events = write ? (EPOLLOUT | EPOLLIN) : EPOLLIN;
#endif
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
    zen_ready_interest_clear(fd);
    if (saved) { errno = saved; return -1; }
    return 0;
#else
    return epoll_ctl(queue, EPOLL_CTL_DEL, fd, NULL);
#endif
}
static int zen_ready_wait(int queue, uintptr_t *events, int capacity, int timeout_ms) {
#ifdef __APPLE__
    struct timespec timeout = {timeout_ms / 1000, (timeout_ms % 1000) * 1000000L};
    struct timespec *tp = timeout_ms < 0 ? NULL : &timeout;
    for (;;) {
        int n = kevent(queue, NULL, 0, (zen_ready_event *)events, capacity, tp);
        if (n < 0) return n;
        int kept = 0;
        for (int i = 0; i < n; ++i) {
            struct kevent *ev = &((zen_ready_event *)events)[i];
            /* Under Write interest, drop readable-data events from
               EVFILT_READ that are not EOF; only terminal read-side
               conditions (peer half-close) should wake the wait. */
            if (!(ev->flags & EV_ERROR) && ev->filter == EVFILT_READ && !(ev->flags & EV_EOF)) {
                int idx = zen_ready_interest_find((int)ev->ident);
                if (idx >= 0 && zen_ready_interests[idx].write) continue;
            }
            if (kept != i) ((zen_ready_event *)events)[kept] = *ev;
            ++kept;
        }
        if (kept > 0 || n == 0 || timeout_ms == 0) return kept;
        /* All events were filtered out.  With EV_CLEAR the consumed events
           will not re-fire, so the next kevent call blocks until a new
           event or timeout. */
    }
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
