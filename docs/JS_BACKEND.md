# JavaScript backend

`--backend js` (`src/gen/gen_js.zen`) renders the executable IR as a Node.js
script. `BACKENDS.md` is the renderer contract; this file records the JS
backend's measured state, its representation decisions and the plan of record.

## Measurement gate

`make jscheck` (part of `make verify`) runs `tests/js`, a Zen program built
with the C backend. For every executable corpus test it compiles with
`--backend js`, runs the script under Node with the test's `.args`, `.env`
and `.stdin`, and requires the same stdout, exit status and `.stderr` lines
as the recorded C oracle (`make test` holds the C backend to those same
sidecars, so agreement with them is agreement with C). Tests with a `.stage`
sidecar are deferred by the ordinary harness and skipped here.

`tests/js/known_gaps.txt` is a shrink-only ratchet: a failing test not listed
fails the gate, and a listed test that passes fails it too until the entry is
removed (`./zen run tests/js -- ./zen --shrink` rewrites the list, never
adding to it). Without `node` on PATH the gate prints a notice and passes.

Single run, all lanes: `./zen run tests/js -- ./zen`; one lane:
`--filter match-payloads`; every verdict: `--verbose`.

### Pass rate

| Tree | Pass | Notes |
| --- | --- | --- |
| `unified-rooms` 890acb1c | 1 / 976 (0.1 %) | the scalar IR admits only `i32`, `bool`, unit; every lane is 0 % except `codegen` (1 / 76) |

Every other corpus program is refused before JS is emitted ("this backend
supports only i32, bool and unit values"), so no lane has behavioural
failures yet; the first gap in nearly every program is
`main = (env: Env) Res<i32, E>`.

## Plan of record: render the native IR surface

The language coverage the JS backend lacks is not JS-specific. The
`native-asm-backend` branch widens `gen_ir` with integer widths, pointers,
frame aggregates, `Load`/`Store`/`AddressOf`, `CopyBytes`, static bytes,
stream writes, system calls, page mapping and `Trap` terminators, and lowers
records, enums/`Res`, patterns, `.try()`, generics, closures-as-inlined
callbacks, `Alloc` and arenas into it (`gen_asm_lower`). The JS backend should
consume that same lowered form rather than grow a second AST lowering: one
lowering owns language semantics, and each renderer owns only machine
details. That branch is not merged here yet, so this work stops at the gate
and the decisions below.

The JS renderer of that surface is a machine target like arm64 or x86-64:

### Memory

One `ArrayBuffer` heap addressed through a `DataView` and `Uint8Array`
views. `Ptr` is a byte offset into it held as a JS number (the heap stays
below 2^32 bytes, so offsets are exact and comparisons are integer
comparisons). Address zero is reserved so null traps as it does natively.
Frame aggregates (`Block` slots, and any slot whose address is taken) live in
a downward-growing stack region of the same heap with an explicit stack
pointer; the frame is released on return. `MapPages` grows the heap
(`ArrayBuffer.prototype.resize` on a resizable buffer, so existing views stay
valid) and returns zeroed pages; `UnmapPages` returns them to a free list.
Every Zen-visible allocation therefore goes through Zen's own `Alloc` over
pages, exactly as on the native targets; the JS garbage collector never owns
a Zen value, and `str`/`String` are byte ranges in the heap (UTF-8 bytes, not
JS strings). Output writes bytes straight from the heap view.

### Integer widths

Slots of 32 bits or fewer are JS numbers normalised after every operation
(`| 0`, `>>> 0`, `<< 24 >> 24`, ...); checked operations compute exactly in
float64 (a 32x32 product needs `Math.imul` plus a range test of the exact
product, which float64 represents for |x| < 2^53) and trap outside the range.

`I64`/`U64` choice, measured on Node 24.4 (Apple M-series), 2x10^7
iterations of a checked u64 add plus a wrapping FNV-1a multiply
(scratch benchmark; all three agree on the result):

| Representation | Time | vs. i32 numbers |
| --- | --- | --- |
| JS numbers (i32 reference) | 25 ms | 1x |
| split (`hi`, `lo`) uint32 pair | 118 ms | 4.7x |
| `BigInt` with `BigInt.asUintN` | 404 ms | 16x |
| `BigInt`, BigInt loop counter | 705 ms | 28x |

Decision: 64-bit slots are split pairs. The renderer gives every `I64`/`U64`
slot two JS locals (`vN`, `vN_hi`), passes both halves as arguments, and
returns the high half of a 64-bit result through one module-level register
(`zg_hi`) beside the ordinary return value, as a two-register machine ABI
would. Checked add/sub detect overflow from the carry and sign bits; checked
multiply uses 16-bit limbs; division and remainder, which are rare on hot
paths, go through `BigInt` in runtime helpers. Decimal printing of 64-bit
values also goes through `BigInt`. `usize` is `U64` in the IR, so this cost
lands on lengths and indices; if profiling shows that dominating, the IR can
mark lengths whose range is bounded by the heap, but that is an IR decision,
not a renderer shortcut. `u128` (from the SIMD work) would be four limbs.

### Traps and exit

A trap throws a private `ZenTrap` that the entry wrapper catches; it flushes
buffered stdout, writes `file:line:col: trap: what` to stderr and sets exit
status 134, matching the C backend. `process.exit` is never called while
output is pending, so nothing is truncated.

### System calls (host shim)

`SysCall` maps each `gen_sys` operation to one synchronous Node call in a
small runtime written in JS, and keeps the native `-errno` convention:
`read`/`write` → `fs.readSync`/`fs.writeSync`; `openat`/`close` →
`fs.openSync`/`fs.closeSync`; `clock_gettime` → `process.hrtime.bigint()`;
`getrandom` → `crypto.randomFillSync`; `exit_group` → the exit path above;
`Startup` values from `process.argv`/`process.env` copied into the heap.
Sockets, `epoll`/`kqueue` and process spawning have no synchronous Node
equivalent and remain unsupported (the compiler refuses them for JS).
`c.bind` natives used by std today (`unistd.h`, `fcntl.h`, `stdlib.h`,
`math.h`, `errno.h`, `sys/stat.h`, `arc4random_buf`, `malloc`/`free` in the
pool) are reached through the same syscall layer once std's natives are
expressed as `gen_sys` operations, which the native targets need too; only
`math.h` functions map to `Math.*` directly.

### Actors

The C backend runs actors on pthreads. The JS mapping keeps Zen's own actor
runtime and supplies its thread and wait primitives: the heap becomes a
`SharedArrayBuffer`, `clone` starts a `worker_threads` Worker running the same
script on that heap, and `futex` wait/wake are `Atomics.wait`/`Atomics.notify`
on an `Int32Array` view. That preserves blocking semantics, which an
async/microtask mapping would not (a Zen actor may block in a loop without
yielding). Single-actor programs never start a worker.

### TypeScript

A `.d.ts` is not useful for the current output: a generated program is a
closed script with no exports. When the backend emits a module for embedding
(exported Zen functions taking heap offsets), a `.d.ts` beside it is a few
dozen lines of renderer work (one signature per exported function, numbers
for 32-bit slots and pointers, `bigint` at the boundary for 64-bit slots).
Emitting TypeScript source instead of JS buys nothing at runtime and would
add a `tsc` step to the gate; it is not planned.
