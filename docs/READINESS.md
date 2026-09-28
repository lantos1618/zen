# Native readiness

`std.net.readiness` owns a level-triggered kqueue/epoll queue independently of
HTTP and actor scheduling. Import `Readiness`, `Interest`, `WaitResult` and
`ReadinessError` from that module. Compile emitted C with `-I src/std/net` from
this compiler checkout so its `zen_readiness.h` ABI adapter is available.

`Readiness.open(alloc, capacity)` uses the caller allocator for an aligned native
event buffer and creates a close-on-exec queue descriptor. Capacity must be
1..2147483647. `close` and Drop close the queue and release its buffer once;
watched descriptors are borrowed and remain open. The allocator must outlive the
queue. This is a single-owner, single-thread API, not a concurrent registry.

`add(fd, slot, Interest.Read|Write)` registers an arbitrary usize identity;
`modify` changes that identity/interest, and `remove` unregisters a descriptor.
Only one interest is enabled at a time. Closing a watched descriptor removes its
kernel registration. Callers must track add versus modify: duplicate add and
missing modify/remove behavior follows the platform (kqueue can upsert; epoll
rejects duplicate add). A failing kqueue change may have applied one filter before
another fails: close/unregister the watched descriptor before reuse. Registration
errors retain their native errno in `System(errno)`.

`wait(milliseconds)` accepts -1 (indefinite), 0 (poll), or a positive timeout.
It returns `Ready(count)` or `Interrupted` for EINTR, never silently restarting a
full timeout. Timeout returns `Ready(0)`. Other syscall failures retain errno.
Every wait, including invalid/failed/interrupted waits, invalidates the previous
batch. `ready_slot(index)` checks bounds against the current batch. EOF and error
readiness still deliver the identity; the descriptor operation determines the
actual EOF/error. Duplicate identities are possible; callers choose whether to
coalesce them. Already returned identities remain snapshots even if registrations
change, so applications must protect against slot reuse while processing a batch.

All allocation, bounds, lifetime, timeout validation and interruption policy are
Zen. The small C header handles platform event layouts, syscall arguments,
close-on-exec creation and errno macros. It has no allocation or scheduler.
The kqueue close-on-exec flag requires a separate fcntl call; creation is not atomic
with concurrent process execution on that platform.

The current actor backend creates a pthread worker per actor and uses condition
variables for mailbox wakeups. It has no existing network reactor to reuse.
An actor-owned event loop can use this lower-level primitive; this change does
not add actor-per-socket threads, integrate mailbox wakeups, or claim cooperative
actor I/O. Such integration needs a wake descriptor and explicit scheduling policy.

Validation: `python3 tests/library/readiness/run.py --zen ./zen --std src --ubsan`
checks real socketpair read/write readiness, level triggering, identities, interest
changes, unregister, timeout, signal interruption, EOF, invalid arguments,
close-on-exec and explicit/Drop cleanup. A corrupted slot expectation must fail.
EOF/error readiness is not a guarantee of a successful subsequent read or write.
