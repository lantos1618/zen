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
t = c.ask(Counter.total).try();     // one-shot request/reply
```

- **An actor owns its state and its arena.** Only one worker runs it at a time; it handles one message per turn, FIFO per sender.
- **A behaviour is a method whose call is a send.** It returns nothing to the sender, and replies come back as messages (`Reply<T>`, one-shot).
- **Mailboxes are bounded (256).** A sender that hits a full mailbox waits. That's backpressure, not unbounded memory. A cycle of waiting senders is detected, and one send goes through, so it can't wedge.
- **No locks, no atomics, no shared mutable memory in the language.** The runtime uses atomics internally, in C, and nothing else does (COMPILER.md removed atomics from the core IR).

## 4. Sync or async is a capability, not a function colour

Waiting is something only a capability can do (law 2: no ambient authority). So, like `Alloc` decides where bytes live, an **`Io` decides how a call waits**. The same function runs blocking in a CLI and suspending inside an actor, and it is written once.

```zen
Io* = {                                    // passed like Alloc: a fat value, copied freely
    wait*  = (self: @Self, on: Pending) Res<Wake, IoError>   // the one place a call stops
    stack* = (self: @Self) Alloc                             // where a waiting call's frames live
}
fetch = (io: Io, net: Net, url: str, a: Alloc) Res<String, NetError> {
    conn = net.connect(io, url).try();     // may wait: how is io's business
    conn.read_all(io, a)
}
```

| `Io` | Where it comes from | A wait does | Waiting frames live in | Other work meanwhile |
|---|---|---|---|---|
| `Blocking` | `env.io` in `main` | parks the OS thread | the thread's own stack | other threads only |
| `Turn` | `ctx.io` inside an actor | suspends this turn, and the worker runs other actors | a stack carved from **the actor's arena** | other actors |
| `Seeded` | tests (`ZEN_ACTOR_SEED`) | as `Turn`, with the next actor picked by a seeded generator | the actor's arena | deterministic interleaving |

```text
 Blocking:  thread stack ─ f ─ g ─ net.read ──(OS parks thread)──► resumes in place
 Turn:      actor arena:  [stack 64 KiB: f ─ g ─ net.read] ──(switch to scheduler)
            worker runs other actors ... reply arrives ──(switch back)──► resumes in place
```

- **Stackful, not a compiler transform.** A suspended call keeps its real stack, so the compiler emits the same code for both. No state machines, no colouring, nothing in the IR. The switch is a small per-target routine in `runtime/actor` (save callee-saved registers and `sp`, load another).
- **Nothing moves while waiting.** The suspended frames sit in memory the waiting actor owns, so pointers into them stay valid. A reply is written into the waiting frame's result slot under section 5's rules. That's the only copy.
- **Stacks are memory like any other.** A `Turn` stack is a fixed-size block from the actor's arena (or `Mem` pages with a guard page). Deep recursion inside an actor hits the stack limit as a trap, ending that actor (section 6).
- **A waiting actor is not re-entered.** While its turn waits, its mailbox queues and its state can't change underneath it. A wait cycle (A asks B, and B asks A) is detected like a mailbox cycle and fails the newest ask with `Cycle`.

The compiler checks none of this specially. `Io` is an ordinary interface, `wait` is an ordinary call into the runtime, and fit's normal rules decide who may hold an `Io` (it is SCOPED to the actor or thread that made it).

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

- **One worker thread per CPU.** A turn runs up to 100 messages, then the actor goes to the back of the ready queue.
- **Seeded schedules for tests:** `ZEN_ACTOR_SEED=n` runs everything on one thread, choosing the next actor from a seeded generator. Each seed is one reproducible interleaving, so concurrency bugs become ordinary failing tests.
- **Plain threads** (`env.threads`) are an escape hatch. Data crossing to them follows the same section 5 rule, and they wait through `Blocking`.

## 8. How the compiler sees it

| Rule | Pass |
|---|---|
| `REGION(A)` / SCOPED values can't outlive their owner | fit (qualifiers) |
| A send argument is plain, `str`, `val` or a consumed `Region` | fit, at the call |
| The sender has no name left after `.consume()` | flow (I.3, maybe-moved) |
| A behaviour becomes `turn(state: Ptr, msg: Ptr)`; a send becomes `zen_send(ref, behaviour_id, msg, size)` | lower |
| Threads, mailboxes, atomics, parking, stack switching | runtime C (`runtime/actor/`), not the IR |

## 9. Tiers and budgets

| Piece | Tier | Budget |
|---|---|---|
| `Mem`, `Alloc`, `Arena`, `REGION` checks | T0: the compiler itself runs on arenas | `std/mem` ≤ 400 lines |
| `Fixed`, `copy_to` | T1 | (inside `std/mem`) |
| `Io` with `Blocking` | T1: the compiler and CLIs wait this way | (inside `std/io`) |
| Actors, `Turn` / `Seeded` Io, `Region`, `Frozen`, `Reply`, the scheduler | T2 | `std/actor` ≤ 800 Zen + `runtime/actor` ≤ 400 C |

## 10. Open decisions

- **`Frozen<T>` release:** counted per region (as above), or frozen data lives until process exit (simpler, and it leaks by design)?
- **`Turn` stack size:** a fixed 64 KiB per waiting turn, or set per actor at `spawn`?
- **Bounded mailbox size:** a fixed 256, or set per actor at `spawn`?
- **`grow` on an arena that isn't at the last allocation:** copy (as above), or refuse so the caller picks a fresh region?
