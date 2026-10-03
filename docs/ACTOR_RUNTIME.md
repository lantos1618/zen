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
  the sender itself goes through instead, so a cycle never wedges. A send from
  any other thread waits for room. A send to a stopped actor is `Closed`; a
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
