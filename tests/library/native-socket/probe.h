#ifndef ZEN_NATIVE_SOCKET_PROBE_H
#define ZEN_NATIVE_SOCKET_PROBE_H
/* Test instrumentation only: never installed or linked into std. */
#include <stdlib.h>
#include <stdint.h>
#include <unistd.h>
#include <fcntl.h>
#include <errno.h>
#include <signal.h>
#include <sys/socket.h>
#include <netdb.h>
static int probe_addr_live;
static int probe_getaddrinfo(const char *h, const char *s, const struct addrinfo *i, struct addrinfo **a) {
    int rc = getaddrinfo(h,s,i,a);
    if (rc == 0 && *a) probe_addr_live++;
    return rc;
}
static void probe_freeaddrinfo(struct addrinfo *a) { if (a) probe_addr_live--; freeaddrinfo(a); }
static int probe_addr_balance(void) { return probe_addr_live; }
#define getaddrinfo probe_getaddrinfo
#define freeaddrinfo probe_freeaddrinfo
#define FIXTURE_MAGIC 734
enum { FIXTURE_ENUM = 913 };
/* Deliberately unlike the Zen declaration; hidden bytes make stride observable. */
struct fixture_record { unsigned char hidden[37]; void *pointer; int value; };
static int fixture_verify(struct fixture_record *p) {
    for (int i=0;i<2;i++) {
        if (p[i].value != 71+i || p[i].pointer != NULL) return 0;
        for (int j=0;j<37;j++) if (p[i].hidden[j]) return 0;
    }
    p[1].value = 123;
    return 1;
}
static void probe_check(int yes) { if (!yes) abort(); }
static int probe_cloexec(int fd) { return (fcntl(fd, F_GETFD) & FD_CLOEXEC) != 0; }
static int probe_closed(int fd) { errno=0; return fcntl(fd,F_GETFD)==-1 && errno==EBADF; }
static int probe_fds(void) {
    int total=0;
    /* Tests make only low descriptors; this deliberately has a finite cost. */
    for (int fd=0;fd<1024;fd++) if (fcntl(fd,F_GETFD)!=-1) total++;
    return total;
}
static void probe_default_sigpipe(void) { signal(SIGPIPE, SIG_DFL); }
#endif
