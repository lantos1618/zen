# Memory, allocators and actors

One model from the page to the message, and from the call to the wait: **every byte has exactly one owner, and the only things that cross between owners are values nobody can change (`val`) or values handed over whole (`iso`).** An actor is the unit of ownership, so concurrency needs no locks, and a failure frees exactly what the failing owner held.

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
| Stackful lightweight tasks, plain calls, no `async` | Go goroutines | every actor turn runs on its own small stack; waits suspend it (section 4) | **growable copied stacks**: moving a stack needs exact pointer maps, and `Ptr<T>` makes that impossible. We reserve virtual memory instead. |
| M:N scheduler, per-worker run queues, work stealing | Go (G-M-P), Pony | section 7 | — |
| Netpoller: a socket wait parks the task, not the thread | Go | one poller thread (epoll / kqueue) behind `Turn` | — |
| Syscall handoff: a blocked thread gives its queue away | Go | the same for every C call (section 7) | — |
| `select` over many waits | Go | `io.any` / `io.all` (section 4) | **channels**: a mailbox already is one; two ways to send would be one too many |
| Actors with behaviours, causal per-sender order | Pony | section 3 | — |
| Reference capabilities `iso` / `val` / `ref` / `tag` | Pony | `iso` = `Region` consumed, `val` = `Frozen`/static, `ref` = anything inside one actor, `tag` = `Ref<A>` | **`box`, `trn` and capability syntax**: proven at the send, never written |
| Per-actor heap | Pony | per-actor arena | **ORCA garbage collection**: an arena is dropped whole; churn gets a fresh region |
| No data races, no locks | Pony | the send rule (section 5) | **Go's shared memory and mutexes** |
| Blocking `ask` | Go's ergonomics | one-shot `ask` that suspends the turn | **Pony's no-blocking-ever rule**: promises everywhere are a colour by another name |
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

That's the whole list. There's no `malloc`-style general heap: a long-lived structure that churns gets its own arena and is rebuilt (copied into a fresh arena) when its garbage matters. That's one rule instead of a heap allocator, and it is what actors already do.

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
Counter = {
    n :: u64 = 0,
    add*   ::= (self :: @Self, k: u64) { self.n = self.n + k }        // a behaviour: runs in a turn
    total* ::= (self: @Self, reply: Reply<u64>) { reply.send(self.n) }
}
c = env.spawn(Counter()).try();     // Ref<Counter>: an address, copies freely
c.add(5);                           // a send: enqueued, returns at once
t = c.ask(io, Counter.total).try(); // one-shot request/reply: waits, so it takes an Io
```

- **An actor owns its state and its arena.** Only one worker runs it at a time; it handles one message per turn, FIFO per sender.
- **A behaviour is a method whose call is a send.** It returns nothing to the sender, and replies come back as messages (`Reply<T>`, one-shot).
- **Mailboxes are bounded (256).** A sender that hits a full mailbox waits. That's backpressure, not unbounded memory. A cycle of waiting senders is detected, and one send goes through, so it can't wedge.
- **No locks, no atomics, no shared mutable memory in the language.** The runtime uses atomics internally, in C, and nothing else does (COMPILER.md removed atomics from the core IR).

## 4. Sync or async is a capability, not a function colour

Waiting is something only a capability can do (law 2: no ambient authority). So, like `Alloc` decides where bytes live, an **`Io` decides how a call waits**. The same function runs blocking in a CLI and suspending inside an actor, and it is written once.

```zen
Io* = {                                    // passed like Alloc: a fat value, copied freely
    wait* = (self: @Self, on: Pending) Res<Wake, IoError>          // the one place a call stops
    any*  = (self: @Self, on: [Pending]) Res<usize, IoError>       // Go's select: the first to finish
    all*  = (self: @Self, on: [Pending]) Res<IoError>              // wait for every one
}
fetch = (io: Io, net: Net, url: str, a: Alloc) Res<String, NetError> {
    conn = net.connect(io, url).try();     // may wait: how is io's business
    conn.read_all(io, a)
}
```

| `Io` | Where it comes from | A wait does | Waiting frames live in | Other work meanwhile |
|---|---|---|---|---|
| `Blocking` | `env.io` in `main` | parks the OS thread | the thread's own stack | other threads only |
| `Turn` | `ctx.io` inside an actor | suspends this turn, and the worker runs other actors | the turn's own stack (below) | other actors |
| `Seeded` | tests (`ZEN_ACTOR_SEED`) | as `Turn`, with the next actor picked by a seeded generator | the turn's own stack | deterministic interleaving |

```text
 Blocking:  thread stack ─ f ─ g ─ net.read ──(OS parks thread)──► resumes in place
 Turn:      turn stack:   [f ─ g ─ net.read] ──(switch to scheduler)
            worker runs other actors ... reply arrives ──(switch back)──► resumes in place
```

- **Stackful, not a compiler transform.** A suspended call keeps its real stack, so the compiler emits the same code for both. No state machines, no colouring, nothing in the IR. The switch is a small per-target routine in `runtime/actor` (save callee-saved registers and `sp`, load another).
- **Nothing moves while waiting.** The suspended frames sit in memory the waiting actor owns, so pointers into them stay valid. A reply is written into the waiting frame's result slot under section 5's rules. That's the only copy.
- **Turn stacks are reserved, not grown.** Each is 1 MiB of *reserved* virtual memory from `Mem`, with a guard page below it. The OS commits pages only as they're touched, so a typical turn costs a few KiB.
  - **No overflow slips past the guard:** frames over 4 KiB already probe each page in order (COMPILER.md F), so a deep call always hits the guard page. The runtime turns that fault into a `StackOverflow` trap that ends the actor. No prologue check and no change to §6.
  - **A turn that finishes without waiting** gives its stack straight back to the worker's pool, so a hot stack is reused. Only a waiting turn keeps one.
  - **Stacks never come from an arena:** arena memory has no guard page.
- **Waiting on many things:** `io.any` / `io.all` wait on several pending operations in one turn. That's the `select` of this design. For real parallel work, spawn actors: they cost a mailbox and a state record, as in Pony.
- **C calls count as blocking.** A `c.bind` call can't wait through `Io`, so the worker marks itself "in C". If the call runs longer than 20 µs, the monitor thread hands that worker's run queue to a spare thread (Go's syscall handoff). Other actors keep running, and nothing is spelled differently at the call.
- **A C callback never gets an `Io`.** Its frame may sit on a C stack that assumes one OS thread (thread-local state such as `errno`), so it must not suspend. `callback` takes a named, non-capturing function, so it can't capture an `Io`; fit refuses an `Io` parameter on one.
- **A waiting actor is not re-entered.** While its turn waits, its mailbox queues and its state can't change underneath it. A wait cycle (A asks B, and B asks A) is detected like a mailbox cycle and fails the newest ask with `Cycle`.

The compiler checks none of this specially. `Io` is an ordinary interface, `wait` is an ordinary call into the runtime, and fit's normal rules decide who may hold an `Io` (it is SCOPED to the actor or thread that made it).

**Why this, not the actors, removes red/blue.** Actors alone don't: Pony's behaviours never block, so results come back as promises and promises spread, which is the colour problem again. Erlang has actors and no colours because `receive` suspends a process that has its own stack. This design is on Erlang's side: `ask` and every other wait suspend a turn on its own stack. What remains is visible but not a split: a function that may wait takes an `Io`, and any `Io` works, including `Blocking`. The one true restriction is that code called from C can't wait.

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

`Frozen<T>` is a `Region<T>` given up for writing: `region.freeze()` returns a `val` that any actor may read. Its pages are released when the last holder's actor ends. This is the only counted thing in the system, and it's counted per region, not per object.

## 6. Failure and shutdown

- **A trap inside a turn ends that actor, not the process.** Its turn stops, and its state and arena are dropped. Its watchers get `failed`, and messages to it answer `Closed`. Nothing else could see its memory, so nothing else is damaged.
- **A trap in `main` (outside any actor) ends the process**, with exit 134 (ZEN_LANGUAGE.md §8).
- **`stop()`** closes admission: accepted messages still run, then `Drop` of the state, then the arena goes back to `Mem`.
- **At process exit** the runtime runs every accepted message, then stops every actor.

## 7. Scheduling

- **One worker per CPU, each with its own run queue; an idle worker steals half of another's** (Go's P queues, Pony's scheduler).
- **A turn runs up to 100 messages,** then the actor goes to the back of its worker's queue.
- **One poller thread** (epoll on Linux, kqueue on macOS) owns every socket wait. A ready socket makes its waiting actor ready again.
- **One monitor thread** does three jobs: hand off workers stuck in C calls (section 4), fire `send_after` timers, and run the watchdog. The watchdog prints the wait-for graph when nothing can make progress, and names a turn that has run past its tick.
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
| A C callback has no `Io` parameter | fit |

## 9. Tiers and budgets

| Piece | Tier | Budget |
|---|---|---|
| `Mem`, `Alloc`, `Arena`, `REGION` checks | T0: the compiler itself runs on arenas | `std/mem` ≤ 400 lines |
| `Fixed`, `copy_to` | T1 | (inside `std/mem`) |
| `Io` with `Blocking` | T1: the compiler and CLIs wait this way | (inside `std/io`) |
| Actors, `Turn` / `Seeded` Io, `Region`, `Frozen`, `Reply`, the scheduler | T2 | `std/actor` ≤ 800 Zen + `runtime/actor` ≤ 600 C |

## 10. Open decisions

- **`Frozen<T>` release:** counted per region (as above), or frozen data lives until process exit (simpler, and it leaks by design)?
- **Turn stack reservation:** a fixed 1 MiB reserved per turn, or set per actor at `spawn`?
- **Bounded mailbox size:** a fixed 256, or set per actor at `spawn`?
- **`grow` on an arena that isn't at the last allocation:** copy (as above), or refuse so the caller picks a fresh region?
