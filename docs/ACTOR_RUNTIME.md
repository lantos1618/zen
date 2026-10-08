# Actor runtime

The runtime is Zen: `std.actor.actor_runtime` with `actor_registry`,
`actor_pool` and `actor_layout`, over `std.sys` (threads, parkers, atomics,
pages). Both backends compile it into every program that spawns an actor;
`gen_c_actor` and `gen_lower_actor` generate only what depends on the actor's
type (its record, one turn entry per behaviour send site, the started and
stopped entries) and call the runtime's entry points. The design and its
measurements are in `reports/actors/w2-runtime.md` of the workspace.

## Semantics

- An actor owns its state; only one worker runs it at a time, and its
  messages run in FIFO order per sender.
- Workers: one per CPU the process may use (`ZEN_ACTOR_WORKERS` overrides).
  A turn runs up to 100 messages.
- A mailbox holds 256 messages. A send from a turn to a full mailbox waits
  in the sender's outbox: the sender runs no more turns until the receiver has
  taken those messages. A send whose receiver waits, through full mailboxes, on
  the sender itself goes through instead, so a cycle never wedges. A sender
  waits on one receiver at a time, oldest send first, so the actor it names
  as waited on is the whole wait-for edge and a cycle that closes after the
  first wait is still found. A send from any other thread waits for room. A send to a stopped actor is `Closed`; a
  message larger than `MAX_MESSAGE_BYTES` (32 MiB) is `Full`.
- `stop()` closes admission; accepted messages still run, then `stopped`,
  then Drop of the state and of the actor's allocator, then the memory is
  freed. Senders still waiting for room in a stopped actor are refused.
- `join()` waits until that has happened; from the actor itself it returns
  at once. A worker thread that joins hands its worker to another thread
  while it waits.
- At process exit the runtime waits until every accepted message, and every
  message those sent, has run; then it stops every actor still alive.
- A str argument is copied into the message; a consumed `Vec<u8>` is copied
  into the message and moved into the receiver's allocator before its
  behaviour runs.
- Preemption: a sysmon thread flags a turn that outlives one tick
  (`ZEN_ACTOR_SYSMON_US`, default 1000; 0 turns it off). The runtime's
  `actor_yield_check` (for compiler-inserted loop checks) then hands the
  worker to another thread.
- Watchdog: when every worker has been asleep for `ZEN_ACTOR_WATCHDOG_MS`
  (default 1000; 0 turns it off; needs sysmon) while actors are blocked, or
  when actors are still wedged at exit, the runtime prints the wait-for graph
  on stderr: each blocked actor's registry index, mailbox depth and the actor
  it waits on, then the cycles. Nothing can block or unblock while every
  worker sleeps, so the registry is walked once per quiet spell, when it
  reaches the limit, not on every sysmon tick.
- Message trace: `ZEN_ACTOR_TRACE=<file>` records each message's path, an
  event every time it moves: sent into a mailbox, parked in the sender's
  outbox, released into the mailbox, refused, taken by a worker, plus actors
  blocking, unblocking and waiting on a receiver, workers sleeping and
  waking, and loops broken. Events go into a fixed buffer
  (`ZEN_ACTOR_TRACE_EVENTS`, default 1000000; later events are counted, not
  kept) and are written at `actor_shutdown`, one line each:
  `index ns kind from to message`. `from` and `to` are registry indices (0
  for a thread that is no actor; the worker for take, sleep and wake), and
  the message is its block's address, unique while it lives. With the
  variable unset each trace point is one load and a branch.

- Pages: everything the runtime keeps (globals, per-thread state, workers,
  the registry, 2 MiB spans of slabs, large messages, trace buffers) comes
  through `actor_pool.grab`/`give_back`. Without `env.actor_mem` that is
  the kernel, aligned mappings and huge-page advice as before. With one,
  `grab` asks the Mem's `page` for the size plus the alignment plus a word,
  aligns inside the page, keeps the page's address in the word before the
  block for `give_back`'s `release`, and zeroes the block. The Mem lives in
  the process block (`PB_MEM`); `PB_ONCE` 4 marks a call in progress, which
  the runtime's first start waits out.

## Executable checks

`make actorcheck` runs the actor corpus (`tests/corpus/actor`), whose
one-worker tests fix the interleaving of send-or-park, and the page
allocation checks. Stress scenarios and benchmarks are in `tests/bench/actors`.

## Trace records

`std.trace.Buffer` owns bounded storage supplied by a caller allocator. It records
completed scalar spans without reading clocks, allocating, or performing I/O.
Names are borrowed and must outlive the buffer; the owner must serialize access.
`zen-otel` owns wire encoding and optional export, and copies names before they
cross its actor boundary. Runtime-wide automatic tracing is not implemented.
