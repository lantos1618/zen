# Memory, allocators and actors

One model from the page to the message, and from the call to the wait. `Alloc` is memory; `Env` is the zone (memory pages plus how calls wait): **every byte has exactly one owner, and the only things that cross between owners are values nobody can change (`val`) or values handed over whole (`iso`).** An actor is the unit of ownership, so concurrency needs no locks, and a failure frees exactly what the failing owner held.

```text
 OS pages ──► Mem (env.mem: page / release)              capability, from main's Env
                │
                ▼
             Arena  ── bump inside 64 KiB+ chunks; Drop gives every chunk back
                │      one per actor, one for main, more on demand (scratch, regions)
                ▼
             Alloc  ── interface: a fat value { data, table }, copied freely
                │
                ▼
     Vec / String / Map ...  take an Alloc; their bytes live in that arena
```

## 0. Lineage: Go's machinery, Pony's ownership

| Idea | From | Taken as | Not taken, and why |
|---|---|---|---|
| Stackful lightweight tasks, plain calls, no `async` | Go goroutines | every actor turn runs on its own stack; waits suspend it (section 4) | **growable copied stacks**: moving a stack needs exact pointer maps, and `Ptr<T>` makes that impossible. Stacks are fixed-size, checked in the prologue as Go does. |
| A capability that decides how calls wait, with blocking and evented implementations | Zig `std.Io` | `Env` (section 4) | — |
| Blocking call with a mandatory timeout; late replies dropped | Erlang `gen_server:call` | `ask` with a deadline (section 3) | **calls without a timeout** |
| M:N scheduler, per-worker run queues, work stealing | Go (G-M-P), Pony | section 7 | — |
| Netpoller: a socket wait parks the task, not the thread | Go | one poller thread (epoll / kqueue) behind `Turn` | — |
| Syscall handoff: a blocked thread gives its queue away | Go | the same for every C call (section 7) | — |
| `select` over many waits | Go | `env.any` / `env.all` (section 4) | **channels**: a mailbox already is one; two ways to send would be one too many |
| Actors with behaviours, causal per-sender order | Pony | section 3 | — |
| Reference capabilities `iso` / `val` / `ref` / `tag` | Pony | `iso` = `Region` consumed, `val` = `Frozen`/static, `ref` = anything inside one actor, `tag` = `Ref<A>` | **`box`, `trn` and capability syntax**: proven at the send, never written |
| Per-actor heap | Pony | a per-actor `Pool` (frees) plus arenas (scratch, messages) | **ORCA garbage collection**: memory is freed by `Drop` or with its arena |
| No data races, no locks | Pony | the send rule (section 5) | **Go's shared memory and mutexes** |
| Request/reply by address | Pony | the default: pass a `Reply<T>`, answer with a send | — |
| Blocking `ask` | Erlang, Go's ergonomics | `ask` with a deadline, for when the answer is needed inline | **Pony's no-blocking-ever rule**: promises everywhere are a colour by another name |
| Sends that never block | Pony | a full mailbox answers `Full` | **Go's blocking channel send**: bounded queues plus blocking sends deadlock in trees, not just cycles |
| Failure isolation | Pony / Erlang | a trap ends one actor (section 6) | **Go's panic that kills the process** |
| Preemption | — | none; a turn is short by contract, and the watchdog names one that isn't | **Go's async preemption**: signals and safe points cost a lot of runtime for a bug class we report instead |

## 1. Allocators

```zen
Mem* = {                                  // page authority; only Env has one
    page*    = (self: @Self, bytes: usize) Res<Ptr<u8>, AllocError>
    release* = (self: @Self, p: Ptr<u8>, bytes: usize)
}
Alloc* = {                                // what allocating code takes
    raw*  = (self: @Self, size: usize, align: usize) Res<Ptr<u8>, AllocError>
    grow* = (self: @Self, p: Ptr<u8>, old: usize, new: usize, align: usize) Res<Ptr<u8>, AllocError>
}
AllocError* = { | OutOfMemory }
```

| Allocator | Tier | Behaviour |
|---|---|---|
| `Arena` (`env.mem.arena()`) | T0 | bump pointer in chunks from `Mem`. `grow` extends in place when `p` is the last allocation, else copies. No per-object free. Drop releases every chunk. |
| `Fixed` (`Fixed(buf)`) | T1 | an arena over a caller's buffer: no pages, `OutOfMemory` when full |
| `Pool` (`env.mem.pool()`) | T2 | size classes (16 B to 4 KiB, larger blocks straight from `Mem`) with a free list per class. `free` returns a block, `Drop` of a `Vec` or `String` frees its storage, and dropping the pool releases everything. It belongs to one zone, so it needs no locks. |

**Which to use:** an arena for anything with a clear end (a request, a turn, a parse, a message), and a pool for a long-lived actor's state that changes for ever (a cache, a connection table, a router). Without the pool, a long-lived actor would have to rebuild its arena by hand, which is garbage collection written by the user. There's still no global heap, no reference counting and no GC: every block has one owner, and `Drop` or the owner's end frees it.

`Alloc` gains one member for this, and arenas ignore it:

```zen
    free* = (self: @Self, p: Ptr<u8>, size: usize, align: usize)   // Arena and Fixed: no-op
```

**Lifetimes are checked, not counted.** A value allocated from arena `A` carries the qualifier `REGION(A)` in `fits()` (COMPILER.md I). It can't be stored into anything that outlives `A`, and it can't be returned past `A`'s scope. There's no reference counting and no GC.

```zen
parse = (env: Env, text: str) Res<Ast, ParseError> {
    tmp ::= env.mem.arena();               // scratch: dropped at scope exit
    tokens = lex(tmp, text).try();         // REGION(tmp)
    build(env.mem.arena(), tokens)         // result in its own arena; tokens die with tmp
}
```

## 2. How a value moves

Inside one owner, there are four moves and they're all plain:

| Operation | What happens to the bytes |
|---|---|
| assign, pass, return a value | bitwise copy (small) or one out-of-line copy call per type (large; COMPILER.md I) |
| pass to a parameter | a borrow: the callee gets a pointer for `::`, a copy or pointer for `:`; nothing moves |
| `.consume()` | bitwise copy, and the source is dead (flow checks it); `Drop` runs once, at the new owner |
| a container header (`Vec`, `String`) | three words move; the elements stay in their arena |

There are no copy constructors, no `Clone` and no hidden deep copies. A deep copy is a function you call, and it takes the destination `Alloc`: `v.copy_to(other_arena)`.

## 3. Actors: the unit of ownership

```text
   actor A                              actor B
 ┌──────────────────┐   send(msg)    ┌──────────────────┐
 │ state            │ ─────────────► │ mailbox (bounded)│
 │ arena A (owned)  │                │ state            │
 │ one turn at once │ ◄───────────── │ arena B (owned)  │
 └──────────────────┘   reply        └──────────────────┘
   no pointer from A's arena ever reaches B (unless it is val)
```

```zen
Counter = { n :: u64 = 0 }
Counter.impl(Actor, {
    add   = (self :: @Self, env: Env, k: u64) { self.n = self.n + k }           // behaviour
    total = (self: @Self, env: Env, reply: Reply<u64>) { reply.send(self.n) }
})
c = env.spawn(Counter()).try();                     // Ref<Counter>: an address, copies freely
c.add(5).try();                                     // a send: Ok, or Err(Full | Closed); never waits
c.total(env.reply_to(Watcher.got_total)).try();     // inside an actor: the answer arrives as a send to my got_total
t = c.ask(env, Counter.total, ms(250)).try();       // inline answer: waits, at most 250 ms
```

`ask` returns `Res<T, AskError>` with `AskError = { Timeout | Closed | Cycle | Cancelled }`. There is no `ask` without a deadline.

- **Each behaviour receives its actor's own `Env`** (section 4), not `main`'s. That `Env` is the actor's memory and its way of waiting.
- **An actor owns its state and its arena.** Only one worker runs it at a time; it handles one message per turn, FIFO per sender.
- **A behaviour is a method whose call is a send.** It returns nothing to the sender, and replies come back as messages (`Reply<T>`, one-shot).
- **Request/reply by address is the default.** Pass a `Reply<T>` that names one of your own behaviours; the answer arrives as an ordinary message, and nothing waits. Use `ask` only when the next line needs the answer.
- **Reply slots belong to the runtime, not the stack.** An `ask` registers a slot with a generation number. A reply that arrives after a timeout or a cancel finds a newer generation and is dropped, so it can never write into a frame that has already returned. A dropped `Reply<T>` (the receiver never answered) fails the waiter with `Closed`, and so does the receiver's end.
- **Mailboxes are bounded** (default 256, set per actor at `spawn`). **A send never waits:** a full mailbox answers `Err(Full)` at once, and the sender decides whether to drop, retry later (`send_after`) or shed load. Only `ask` waits, and it always has a deadline. Bounded queues with sends that wait deadlock in trees, not just cycles; sends that never wait can't.
- **No locks, no atomics, no shared mutable memory in the language.** The runtime uses atomics internally, in C, and nothing else does (COMPILER.md removed atomics from the core IR).

## 4. `Env` is the zone: memory and waiting in one capability

`Alloc` is memory and nothing else. **`Env` is the zone you're running in**: where pages come from, and how a call waits. `main` gets the process's `Env`; every actor gets its own and hands it to each behaviour. A function is sync or async only through the `Env` it was given, so every function is "multisync" by default (Nim needs a macro and two copies for this; here it's one compiled function).

```text
 zone = { Env, its arena(s), its mailbox }
        Env.mem   pages -> arenas -> Alloc        what memory is
        Env.fs / net / out / spawn / ask          what you may do, and how it waits
 main's Env  : Blocking  (waits park the OS thread)
 actor's Env : Turn      (waits suspend the turn; the worker runs other actors)
 test Env    : Seeded    (as Turn, with a seeded schedule)
 between zones: only send / receive / ask, carrying plain | str | val | iso Region (section 5)
```

```zen
fetch = (env: Env, url: str, a: Alloc) Res<String, NetError> {
    conn = env.net.connect(url).try();     // may wait: how depends on whose Env this is
    conn.read_all(a)                       // conn came from env.net, so it waits the same way
}
parse = (a: Alloc, text: str) Res<Ast, ParseError>   // takes no Env: it can't wait, and the signature says so
```

| `Env` of | A wait does | Waiting frames live in | Other work meanwhile |
|---|---|---|---|
| `main` (Blocking) | parks the OS thread | the thread's own stack | other threads only |
| an actor (Turn) | suspends this turn, and the worker runs other actors | the turn's own stack (below) | other actors |
| a test (Seeded) | as Turn, with the next actor picked by a seeded generator | the turn's own stack | deterministic interleaving |

```text
 Blocking:  thread stack ─ f ─ g ─ net.read ──(OS parks thread)──► resumes in place
 Turn:      turn stack:   [f ─ g ─ net.read] ──(switch to scheduler)
            worker runs other actors ... reply arrives ──(switch back)──► resumes in place
```

- **Why `Alloc` isn't the gate.** Most code allocates without waiting: parsing, formatting, the compiler itself. If the allocator carried the waiting mode, every allocating function would look like it might wait.
- **The no-wait rule, stated exactly:** a function whose parameters include no `Env` and no capability obtained from one (a connection, a file, a reader over either) can't wait. An `Alloc` alone never makes a function wait. This is capability discipline, not a timing promise: a pure function can still run long.
- **A capability keeps its zone's mode.** `env.net.connect` returns a connection that waits the way its `Env` does, so the mode follows the capability, not an extra parameter.
- **Stackful, not a compiler transform.** A suspended call keeps its real stack, so the compiler emits the same code for both. No state machines, no colouring, nothing in the IR. The switch is a small per-target routine in `runtime/actor` (save callee-saved registers and `sp`, load another).
- **Nothing moves while waiting.** The suspended frames sit in memory the waiting actor owns, so pointers into them stay valid. A reply is written into the waiting frame's result slot under section 5's rules. That's the only copy.
- **Turn stacks are fixed-size and checked, not guarded.** Every turn stack is carved from **one** large reserved mapping, so thousands of stacks cost one entry in the kernel's mapping table. A guard page per stack would cost two entries each, and Linux's default limit of 65,530 caps that at about 30k stacks.
  - **Overflow is caught in the prologue,** as in Go: a program that spawns actors is compiled in the *stack-checked* profile, where every function compares `sp - frame` against the current stack's limit before touching the frame, and branches to a `StackOverflow` trap (COMPILER.md §4.4). The trap ends that actor.
  - **Programs without actors are unchanged:** they run only on OS stacks, which have guard pages, so they're compiled without the check and §6 stays byte-identical.
  - **One default size everywhere:** 1 MiB for each turn stack and for `main`'s checked limit, set per actor at `spawn`. A recursion that works in `main` works in an actor.
  - **A turn that finishes without waiting** gives its stack straight back to the worker's pool, and the runtime returns the touched pages to the OS (`madvise`) past a high-water mark. Only a waiting turn keeps a stack.
  - **The OS commits pages only as they're touched,** so a typical waiting turn costs a few KiB.
- **Waiting on many things:** `env.any([...])` / `env.all([...])` wait on several pending operations in one turn. That's the `select` of this design. For real parallel work, spawn actors: they cost a mailbox and a state record, as in Pony.
- **C calls count as blocking.** A `c.bind` call can't wait through `Env`, so the worker marks itself "in C". If the call runs longer than 20 µs **and other actors are ready**, the monitor thread hands that worker's run queue to a spare thread (Go's syscall handoff). The handoff thread pool is capped (default: one per CPU); past the cap, the queue waits.
- **Known-slow C calls are marked:** `c.blocking(sqlite_exec(db, sql))` hands the worker's queue off before the call, not after 20 µs, so a database or DNS call never stalls other actors.
- **A turn never moves threads while C state is live.** A turn may resume on a different OS thread after a wait, so C thread-local state (`errno`, locale, a library's per-thread handle) must not be held across a wait. A binding that needs one OS thread declares it, `c.bind(.., thread: pinned)`, and the actor that uses it is pinned to one worker.
- **A C callback never gets an `Env`.** Its frame may sit on a C stack that assumes one OS thread (thread-local state such as `errno`), so it must not suspend. `callback` takes a named, non-capturing function, so it can't capture an `Env`; fit refuses an `Env` parameter on one.
- **A waiting actor is not re-entered.** While its turn waits, its mailbox queues and its state can't change underneath it.
  - **A wait cycle** (A asks B, and B asks A) fails the newest `ask` with `Cycle`. A turn waiting in `ask` waits on exactly one actor, so detection is a walk down one chain of pointers.
  - **Waiting on several actors at once** (`env.all` over asks) can't form a cycle the walk misses, because the deadline ends it.

### Cancellation: structured, on `@scope`

Every wait can end early, and ending early is an error value, never an exception:

```zen
@scope.deadline(ms(500));                          // every wait in this block ends by then
r = env.net.connect(url);                          // Err(Timeout) if it runs past the deadline
@scope.cancel_on(stop_signal);                     // a message or another scope can cancel
```

- **A cancelled wait resumes with `Err(Cancelled)` (or `Timeout`).** The code returns through it like any error, and the block's defers run on the way out (COMPILER.md C.4). There's no unwinding machinery: it's the existing `.try()` path.
- **Work started in a scope ends with it.** `env.all` and `ask` inside a scope can't outlive it: when the scope exits, anything still pending is cancelled and its reply slot is retired.
- **The runtime checks the deadline only at waits.** A pure loop isn't interrupted; that's the no-preemption rule, and the watchdog reports a turn that runs past its tick.

An `Env` is SCOPED to its zone: it can be passed inward to any function, but it can't be sent, stored in another actor, or returned out of its zone. That one fit rule keeps a function from waiting in the wrong zone.

**What this does to red/blue, exactly.** One function, many `Env`s.
- **Solved:** there's no execution split. Any function runs in any zone, compiled once, with no `async`, no `.await`, no state-machine transform and no second library. Actors alone wouldn't do this (Pony's never-block rule turns results into promises, which spread); stackful turns do, as in Erlang and Go.
- **Moved, on purpose:** "may wait" is a visible capability parameter, and adding a wait deep in a call chain means passing an `Env` or a capability down to it. That's the no-ambient-authority law, the same as `Alloc`, and it's the price of seeing waits in signatures (Go hides them; Zig made the same trade as Zen).
- **Not allowed:** code called from C can't wait.

The full debate behind these choices is `~/zen/DEBATE_red_blue_2026-10-29.md` (Claude and Gemini, judged).

## 5. What a message may carry

Checked at every send, in fit. The parameter types of a behaviour don't say it; the **argument** proves it.

| Argument | Proven by | How the bytes move | Cost |
|---|---|---|---|
| plain data (no pointers: numbers, enums, fixed arrays, records of those) | its type | copied into the message block | its size |
| `str` and borrowed views | its type | copied into the message; valid for the receiver's **turn** only (SCOPED) | its length |
| `val` (static data, literals, a `Frozen<T>`) | nothing can write it, anywhere | the pointer is shared | 0 |
| `iso`: a `Region<T>` (a value plus its own private arena), `.consume()`d | the sender has no other name for it | the arena's chunks change owner | 0 |
| anything else (a `Vec` in the sender's arena, a `Ptr`, a trait value) | — | **compile error** naming the fix: `.copy_to(region)` or send a `Region` | — |

```zen
batch ::= env.mem.region<Vec<Job>>();       // Region: a value and the arena it lives in
batch.value.add(job).try();
worker.run(batch.consume());                 // zero copy: B now owns those pages
```

`Frozen<T>` is a `Region<T>` given up for writing: `region.freeze()` returns a `val` that any actor may read. **In v1, frozen data lives until the process exits**: there's no counting at all. Use it for configuration, tables and other data built once; churning data goes through `Region` handoff instead.

## 6. Failure and shutdown

- **A trap inside a turn ends that actor, not the process.** Its turn stops, and its state and arena are dropped. Its watchers get `failed`, and messages to it answer `Closed`. Nothing else could see its memory, so nothing else is damaged.
- **A trap in `main` (outside any actor) ends the process**, with exit 134 (ZEN_LANGUAGE.md §8).
- **`stop()`** closes admission: accepted messages still run, then `Drop` of the state, then the arena goes back to `Mem`.
- **At process exit** the runtime runs every accepted message, then stops every actor.

## 7. Scheduling

- **One worker per CPU, each with its own run queue; an idle worker steals half of another's** (Go's P queues, Pony's scheduler).
- **A turn runs up to 100 messages,** then the actor goes to the back of its worker's queue.
- **One poller thread** (epoll on Linux, kqueue on macOS) owns every socket wait. A ready socket makes its waiting actor ready again.
- **One monitor thread** does four jobs: hand off workers stuck in C calls (section 4), fire `send_after` timers and `@scope` deadlines, and run the watchdog. The watchdog prints the wait-for graph when nothing can make progress, and names a turn that has run past its tick.
- **No preemption.** A turn that loops forever is a bug the watchdog reports, not something the scheduler hides.
- **Seeded schedules for tests:** `ZEN_ACTOR_SEED=n` runs everything on one thread, choosing the next actor from a seeded generator. Each seed is one reproducible interleaving, so concurrency bugs become ordinary failing tests.
- **Plain threads** (`env.threads`) are an escape hatch. Data crossing to them follows the same section 5 rule, and they wait through `Blocking`.

## 8. How the compiler sees it

| Rule | Pass |
|---|---|
| `REGION(A)` / SCOPED values can't outlive their owner | fit (qualifiers) |
| A send argument is plain, `str`, `val` or a consumed `Region` | fit, at the call |
| The sender has no name left after `.consume()` | flow (I.3, maybe-moved) |
| A behaviour becomes `turn(state: Ptr, msg: Ptr)`; a send becomes `zen_send(ref, behaviour_id, msg, size)` | lower |
| Threads, run queues, stealing, poller, monitor, atomics, stack switching | runtime C (`runtime/actor/`), not the IR |
| A C callback has no `Env` parameter; an `Env` never leaves its zone | fit |
| A program that spawns actors is compiled stack-checked (COMPILER.md §4.4) | driver: decided once per program after cull |
| `@scope.deadline` / `cancel_on` register with the runtime; their exit retires pending waits | lower (C.4 cleanups) |

## 9. Tiers and budgets

| Piece | Tier | Budget |
|---|---|---|
| `Mem`, `Alloc`, `Arena`, `REGION` checks | T0: the compiler itself runs on arenas | `std/mem` ≤ 400 lines |
| `Fixed`, `copy_to` | T1 | (inside `std/mem`) |
| `Pool` | T2 | `std/mem` ≤ 400 lines including it |
| `main`'s Blocking `Env` | T0: the compiler and CLIs wait this way | (inside `std/env`) |
| Actors, Turn / Seeded `Env`, `Region`, `Frozen`, `Reply`, the scheduler | T2 | `std/actor` ≤ 800 Zen + `runtime/actor` ≤ 600 C |

## 10. Decided

| Question | Decision |
|---|---|
| Can a send wait? | No. A full mailbox answers `Full`; only `ask` waits. |
| `ask` without a deadline? | Not allowed. `AskError = { Timeout \| Closed \| Cycle \| Cancelled }`. |
| Late replies | Runtime-owned, generation-checked reply slots; late replies are dropped. |
| Default request/reply style | Pass a `Reply<T>` address; `ask` when the answer is needed inline. |
| Stack overflow | Prologue check in the stack-checked profile; stacks carved from one mapping. |
| Stack and mailbox sizes | Defaults 1 MiB and 256, set per actor at `spawn`. |
| Long-lived actor memory | A per-zone `Pool` with `free`; arenas for everything with a clear end. |
| `Frozen<T>` | Lives until process exit in v1. |
| Slow C calls | `c.blocking(..)` hands off before the call; the handoff pool is capped. |
| C thread-local state | `thread: pinned` on the binding pins the actor to one worker. |
| Cancellation | Structured, on `@scope`: deadlines and cancel signals become error values at waits. |

## 11. Still open

- **`grow` on an arena that isn't at the last allocation:** copy (as now), or refuse so the caller picks a fresh region?
- **`c.blocking` vs automatic handoff only:** keep both, or require the marker and drop the 20 µs heuristic?
