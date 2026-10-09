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
- `r.try_send(m)` is `send` that never waits: a full mailbox answers
  `Full` at once, through the runtime's `actor_offer`. A send to the sender
  itself is never refused for room, so `ctx.me.try_send` answers `Full` only
  for an oversized message.
- `r.watch(to, done, failed)`: when `r` ends, `to` gets `done` after a
  normal stop or `failed` after a checked trap ended its turn; when `r` has
  already ended, `done` goes at once. Both messages are built and copied at
  the call into a 64-byte entry on the actor slot's watch list (`S_WATCH`,
  guarded by `G_WATCH_LOCK`), and the slot's `WATCHED` life bit tells
  finalization to take the list before the slot is reused. Finalization
  sends the chosen message and frees the other, so nothing is allocated
  while an actor ends; an unwatched actor's end is unchanged.
- `r.send_after(ms, m)` builds and copies `m` at the call and delivers it
  `ms` milliseconds later. One timer thread, started by the first call,
  keeps the pending entries ordered by deadline (equal deadlines in call
  order) and sleeps on its parker with a timeout. A message whose receiver
  has stopped by then is dropped. A pending timer counts as an accepted
  message at exit, and a turn waiting for one is not blocked, so the
  watchdog does not report it. There is no cancel: a receiver that no
  longer wants a tick ignores it.
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
  on stderr: each blocked actor (`Name#index`: its type's name and registry
  index), its mailbox depth and the actor it waits on, then the cycles. For
  the first few blocked actors it also prints the turn whose send is waiting
  and that turn's chain of causes from the flight recorder. Nothing can block or unblock while every
  worker sleeps, so the registry is walked once per quiet spell, when it
  reaches the limit, not on every sysmon tick.
- Message trace: `ZEN_ACTOR_TRACE=<file>` records each message's path, an
  event every time it moves: sent into a mailbox, parked in the sender's
  outbox, released into the mailbox, refused, taken by a worker, run (with
  the turn's code address, or failed), dropped by a failed actor, plus
  actors spawned (with the spawner) and finalised, actors blocking,
  unblocking and waiting on a receiver, workers sleeping and waking, and
  loops broken. Events go into a ring of `ZEN_ACTOR_TRACE_EVENTS` (default
  1000000) that a trace thread writes out every `ZEN_ACTOR_TRACE_FLUSH_MS`
  (default 100), so the file grows while the program runs; an event that
  finds the ring full of unwritten events is counted lost. The file is
  text: `#` lines for the header, `# name <code> <Type.behaviour>` for each
  turn the compiler generated, then one
  line per event, `index ns kind from to message id cause`, and `# end events N
  lost L` at `actor_shutdown`. `from` and `to` are registry indices (0 for
  a thread that is no actor; the worker for take, done, fail, drop, sleep
  and wake; the spawner for spawn), and the message is its block's
  address, unique while it lives. A take and the next done or fail on the
  same worker bracket one turn. On a take, `id` is the message's flight-recorder id and
  `cause` the id of the message whose turn sent it (0: none); other events
  have 0 in both. With the variable unset each trace point
  is one load and a branch.
- Viewing it: `tools/zen-view` serves a dashboard over the file — actor
  tree by spawner, topology with messages per second, mailbox fill, queue
  and turn latency, timeline, worker lanes and failures — following it
  live. `./zen build tools/zen-view --std src`, then
  `tools/zen-view/build/zen-view <file>` and open http://127.0.0.1:7878/.
  The page plays the recorded trace back at a chosen speed. Messages in
  flight are dots on their edges, and the flame tab stacks each turn on the
  turn whose send caused it. `tools/zen-view/demo/market.zen` is a nested
  pipeline, one strategy of which fails, to try it on.
- Flight recorder, on unless `ZEN_ACTOR_RECORDER=0`: every message carries
  `M_CAUSE`, the id of the message whose turn sent it (0 from main or any
  other thread outside a turn). Each thread that runs turns keeps a ring of
  its last 256 takes (id, cause, actor Ref, the actor type's name), 8 KiB,
  written with plain stores when a message is taken; that take gives the
  message its id, `m<thread>.<n>` (the thread's ring tag and its count), so
  no shared counter is touched. A checked trap then prints, after the trap's
  line, the actor and message (`Fragile#1 trapped handling m1.3`) and one
  line per hop back: which actor's turn sent each message while handling
  which earlier one, until a send from outside any turn or until the cause
  has left its ring (`older history is not kept`), at most 16 hops. The
  rings are read without locks: a report about a message still being
  recorded may read a stale entry, which shows as history not kept.
  Spawn passes the actor type's name to `actor_start` (`B_NAME`: the static
  name's address and length in one word).

- Seeded schedule, under `ZEN_ACTOR_SEED=n`: the runtime starts no worker,
  sysmon or timer thread. A ready actor goes into one array (`G_READY`), and
  turns run on whichever thread would otherwise wait: `join`, a send from
  outside a turn to a full mailbox, and the exit hook's drain. Each step a
  xorshift state seeded from `n` (`G_SIM`) picks the ready actor and the
  turn's batch (1 to 32 messages), so the seed fixes the interleaving and
  different seeds explore different ones; each sender's messages still
  arrive in order. Timers read a virtual clock (`G_SIM_NOW`, also the trace
  clock): when nothing is ready the clock jumps to the earliest deadline and
  those timers fire, so a long `send_after` costs no real time. A wait with
  nothing ready and no timer pending can never end: the runtime prints the
  stuck report and `rerun with ZEN_ACTOR_SEED=n`, flushes standard output and
  exits with status 3. Trap, stuck and cycle reports name the seed too.
  Not covered: time the program reads itself (`monotonic_ns`, `sleep`), a
  turn that never returns (there is no preemption), and plain threads, whose
  sends still work but whose timing the seed does not fix.

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
cross its actor boundary. Runtime-wide span tracing is not implemented; the
actor message trace above is the runtime's own record.
