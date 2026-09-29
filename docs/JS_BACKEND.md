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
| `web-backend` on `unified-rooms` 2b70b639 | 661 / 977 (67.7 %) | renders the full lowering; 3 FAIL, 313 UNSUPPORTED, 0 BROKEN |

(On the pre-merge `native-asm-backend` base the same renderer passed 656 of
961; the assembly backend passes 638 of 962 there on this Mac.) The gate
also runs the JavaScript-only cases in `tests/js/cases` (the `js-host`
lane: `js.bind` and suspension under Node), which must always pass.

The three FAILs: `env/fs_read_special_file_with_zero_stat_size` reads a
file under `/proc`, which exists only on Linux (asm fails it on macOS too);
`errors-variant/err_binder_arm_joins_its_set_into_the_match` and
`match-payloads/err_case_on_a_union_tests_only_that_case` are matches on
error-set unions that the shared lowering decides differently from C, and
the asm backend fails them identically, so the fix belongs in
`gen_lower_core`, not the renderer. The 313 refusals also come from the
shared lowering, by the first construct each program reaches: 117 are
compiler-internal tests that import `gen`/`sema`/`lsp` modules the runner
does not stage; then types sema left unsettled in generic corners (35),
other `Env` operations such as actors, threads, `fs.lock`/`cwd`/`mkdir` and
argument schemas (30), value conversions not modelled yet (19),
expressions only the C backend lowers (10), loop handles used as values
(10) and folding loops (9). Closing those is lowering work that serves both
targets.

The gap list was regenerated for this base (it had been measured on an
earlier `unified-rooms`, whose corpus differs); `--shrink` keeps it
ratcheting from here.

## The renderer of the native IR surface (implemented)

The language coverage the JS backend lacked was not JS-specific. `--backend
js` now consumes the same lowered form as the assembly targets
(`gen_lower_core` and friends, verified by `verify_native`) instead of the
scalar `gen_lower`: one lowering owns language semantics, and `gen_js` owns
only machine details. `gen_js` imports only the IR, `gen_sys` and its
runtime (`gen_js_runtime`), which `make archcheck` enforces. What the
lowering refuses is refused for JS too, before any script is published.

Lowering work done for this (target-neutral, so asm gains it as well):
`F64` slots, IEEE arithmetic and comparisons, and float literals converted
to exact bits (Clinger's fast path; other literals are refused rather than
rounded twice); static struct-member calls through a type
(`View.create(...)`); `Ptr.take`. The assembly renderers refuse `F64`
programs with a reason before rendering. `docs/WEB_DEMO.md` shows the result
driving zen-ui in a browser.

The JS renderer of that surface is a machine target like arm64 or x86-64.
The sections below are the model as implemented; differences from the
original plan are marked.

The JS renderer of that surface is a machine target like arm64 or x86-64:

### Memory

One `ArrayBuffer` heap addressed through a `DataView` and `Uint8Array`
views. `Ptr` is a byte offset into it held as a JS number (the heap stays
below 2^31 bytes, so offsets are exact and comparisons are integer
comparisons; a `Ptr` stores as eight bytes with a zero high half). Address
zero is never allocated, but unlike a native target a read through null
returns zeros instead of faulting, and an access past the heap raises a JS
`RangeError`. Layout: bytes 16 up hold static data, the stack grows down
from 8 MiB (overflow into the data traps), mapped pages lie above it.
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

Decision (implemented): 64-bit slots are split pairs. The renderer gives every `I64`/`U64`
slot two JS locals (`vN`, `vN_hi`), passes both halves as arguments, and
returns the high half of a 64-bit result through one module-level register
(`zg_hi`) beside the ordinary return value, as a two-register machine ABI
would. Checked add/sub detect overflow from the carry and sign bits; checked
multiply takes a float64 fast path when the exact product is below 2^53
and otherwise checks through `BigInt` (wrapping multiply uses 16-bit
limbs); division and remainder of values above 32 bits, which are rare on
hot paths, go through `BigInt` in runtime helpers. The helpers were fuzzed
against `BigInt` references (2x10^5 random and edge operand pairs, every
operation, zero mismatches). Decimal printing of 64-bit
values also goes through `BigInt`. `usize` is `U64` in the IR, so this cost
lands on lengths and indices; if profiling shows that dominating, the IR can
mark lengths whose range is bounded by the heap, but that is an IR decision,
not a renderer shortcut. `u128` (from the SIMD work) would be four limbs.

### Traps and exit

A trap throws a private `ZenTrap` that the entry wrapper catches; it flushes
buffered stdout, writes `file:line:col: trap: what` to stderr and sets exit
status 134, matching the C backend. `process.exit` is never called while
output is pending, so nothing is truncated. `exit_group` throws a
`ZenExit` the same wrapper turns into the exit status.

### Frames and calls (as implemented)

Each IR function is one JS function whose body is a `switch` over its basic
blocks inside `for (;;)`. A word slot is a JS local unless its address is
taken; a `Block` slot, and any address-taken slot, has a home in the
function's frame on the heap stack (`fp + offset`), reserved on entry and
released on return. A 64-bit argument is two JS arguments; an aggregate
argument is the address of the caller's copy, copied into the callee's
frame; an aggregate result is written through a trailing destination
address. Generated names are `zfN` (functions), `vN`/`vNh` (slots) and
`zkN` (module constants: static bytes and `f64` bit patterns); runtime names
all start with `z` and never collide with `zf` + digits.

### Floats

`F64` is a JS number. `Add`/`Sub`/`Mul`/`Div` are the JS operators and
`Rem` is `%` (C's `fmod`); none trap. A constant is carried as its bit
pattern and materialised once at load. Printing uses a `%g` formatter that
matches C's output.

### System calls (host layer)

`SysCall` maps each `gen_sys` operation to one synchronous Node call in a
small runtime written in JS, and keeps the native `-errno` convention:
`read`/`write` → `fs.readSync`/`fs.writeSync`; `openat`/`close` →
`fs.openSync`/`fs.closeSync`; `clock_gettime` → `process.hrtime.bigint()`;
`getrandom` → `crypto.randomFillSync`; `exit_group` → the exit path above;
`Startup` values from `process.argv`/`process.env` copied into the heap.
Sockets, `epoll`/`kqueue` and process spawning have no synchronous Node
equivalent and answer `-ENOSYS` at run time. Constants (`SysConst`) take
their Linux x86-64 values and the Node host translates open flags and
error codes.

In a page the program runs on the page's own thread (the page host):
standard output and error go to the console, standard input is empty, and
the DOM is reached through `js.bind` (below). This is the `JsBrowser` sys
flavor of IR_ARCHITECTURE §3.1.

### Host bindings and suspension

`js.bind("object.path", {..})` declares host objects the way `c.bind`
declares a header (contract in `src/std/js/js.zen`). Lowering turns each
call into a `Host` instruction that names the object path, the member,
whether the first argument is the receiver, and each argument's boundary
form (`Marshal`: number, bool, `str`, handle, handler). The renderer emits
one stub per distinct signature; the stub converts arguments (`zstr` decodes
a UTF-8 slice, `zobj` looks a handle up, `zhandler` makes a listener that
queues an id), makes the call or property access, and converts the result
back (`zref` registers an object in the handle table).

`std.js.wait()` is the only way to receive events. It lowers to `Wait`; the
renderer makes every function that can reach a `Wait` a generator
(`function*`), makes calls to those functions `yield*`, and makes the `Wait`
itself `yield`. The runtime drives the entry generator: a queued handler id
resumes it at once, otherwise a host with events (a page) resumes it when a
listener fires, and a host without events (Node) resumes it with 0. Zen code
never runs inside a JavaScript callback, and functions that cannot reach
`Wait` are ordinary functions with no generator cost.

### Output layouts

`--backend js -o FILE` writes one self-contained script (the runtime, then
the program) for Node. `--backend js --target js-browser -o DIR` (or
`web: true` on a project executable) writes `DIR/index.html` (a fixed page
that loads the two scripts), `DIR/runtime.js` (the runtime, identical for
every program) and `DIR/app.js` (the program). `WEB_DEMO.md` walks a zen-ui
app through both.

### Actors (not implemented yet)

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
