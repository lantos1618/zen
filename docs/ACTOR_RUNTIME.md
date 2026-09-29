# Bounded actor runtime

An actor owns its state and processes accepted messages in FIFO admission order.
Admission includes the executing message: at most 64 messages and 32 MiB,
including message and pool metadata. Oversized requests and arithmetic overflow
are rejected before allocation or payload copying. Full and Closed are explicit
results; producers choose whether to retry, coalesce or drop.

Mailbox storage policy lives in `std.actor.actor_storage` and uses `std.mem.Pool`.
Each actor retains at most 1 MiB or 64 free blocks; blocks above 64 KiB payload
are not cached. Cache lookup is exact-size. Changing message sizes can therefore
cause allocation churn even while retained memory remains bounded. Native
control records and actor-lifetime arena storage are additional allocations.
Spawning does not yet accept a caller-selected allocator.

`stop()` closes admission, drains accepted work, and runs the stopped callback.
Concurrent external `join()` callers share one native join. A self-join returns
without calling pthread_join; it is not a wait for the current turn to finish.
Failed native joins can be retried. External users must stop accessing actors
before process-wide runtime teardown. Joining a blocked native operation has no
hard deadline or cancellation guarantee.

The runtime currently uses one pthread per actor. A global registry/send lock
covers lookup and message allocation/copy, followed by mailbox synchronization.
This preserves lifetime safety but can serialize independent senders. A worker
pool or narrower lock design needs a separately proven lifetime/reservation
protocol; bounded mailbox memory alone does not establish scalability.

## Executable checks

`make actorcheck` runs admission/overflow/fault injection, concurrent joins,
typed storage reuse, and multi-producer contention against generated runtime
code. Deliberate regressions must fail the gates. The contention workload checks
64,000 messages from eight producers, exact delivery and producer order, a
stop/send race, and zero additional allocations in its second steady-size round.
The observed first-round growth is 63 native allocations; this is workload and
ABI specific, not a public byte-count contract. UBSan covers storage/contention.

The host ASan startup issue remains unresolved: a minimal independent C control
also stalled before main. UBSan and accounting tests do not replace ASan or prove
freedom from all lifetime errors. Full `make verify` remains the integration gate.

## Trace records

`std.trace.Buffer` owns bounded storage supplied by a caller allocator. It records
completed scalar spans without reading clocks, allocating, or performing I/O.
Names are borrowed and must outlive the buffer; the owner must serialize access.
`zen-otel` owns wire encoding and optional export, and copies names before they
cross its actor boundary. Runtime-wide automatic tracing is not implemented.
