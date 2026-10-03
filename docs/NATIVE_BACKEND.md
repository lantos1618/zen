# Native assembly backend

Goal: `--backend asm` emits machine assembly per architecture and talks to the
operating system directly, with no C compiler and no libc in the build path.
The system assembler and linker (`as`, `ld`) are the only native tools.
This document is the plan of record and the status report; `BACKENDS.md`
remains the contract for the shared scalar IR and the renderer interface.

## Stage 1 survey (starting point)

The starting tree (`remove-std-http`, b2b31884) had:

| Piece | Lines | Covers |
| --- | --- | --- |
| `gen_ir` | 60 | typed mutable slots (`I32 \| Bool \| Unit`), blocks, `Return/Jump/Branch`, constants, copies, unary/binary checked arithmetic, direct calls, scalar print, byte text |
| `gen_lower` | 727 | non-generic functions, `i32`/`bool`/unit, bool matches with explicit arms, `&&`/`\|\|`, `print`/`println` sugar with format holes |
| `gen_verify` | 341 | slot/type/branch/call checks and definite assignment |
| `gen_asm_x86` | 342 | Linux x86-64 System V, 4-byte stack slots, `printf`/`fwrite`/`exit` from libc, linked by `cc` |
| `gen_c` (AST → C) | 29 515 | the whole language |

Measured corpus reach at that point: **0 of 961** executable corpus tests lower
through the scalar path (837 stop at "supports only i32, bool and unit",
the rest need compiler-internal roots or other constructs). The only programs
the asm backend could build were the hand-made IR tests and a scalar `fib`
demo.

### Gap list: what `gen_c` does that the IR path does not

Ordered by how many corpus programs each blocks (rough counts from the
first unsupported construct each program reaches):

1. **`main = (env: Env) Res<i32, E>` and `Env` capabilities** – nearly every
   program. Needs `Res` layout, `Ok(n)` → exit status, `env.mem.alloc()`.
2. **Integer widths and conversions** – `u8 … u64`, `usize`, `i64`, wrapping
   `+% -% *%`, `std.core.num` conversions and bit operations.
3. **`str` values** – literals as (pointer, length), `len`, indexing with
   bounds traps, equality, printing through `{}`.
4. **Loops** – `loop(cond, body)`, `loop((h) {..})`, `Range(a, b).loop`,
   array/Vec `loop` overloads, `h.break(v)`, `h.next()`.
5. **Structs** – construction by name with defaults, field read/write,
   by-value copy/pass/return, methods (UFCS with `self`), `==` on structs.
6. **Enums and `Res`** – tagged layout, payload binding patterns, exhaustive
   `match` over enums, integers, strings and `_`, `.try()` non-local return,
   `ok_or`, `value_or`, `then`, `ensure`.
7. **Generics** – monomorphisation from the checked call substitutions
   (`CheckedCall`), generic structs (`Vec<T>`, `Ptr<T>`, `Res<T, E>`).
8. **Closures** – non-escaping callbacks passed to `loop`/`then`/`match`
   helpers (inlining or context-pointer calls), captures, escaping closures.
9. **Memory** – `Ptr<T>` intrinsics (`read`, `write`, `offset`, `copy_from`),
   the `Alloc` interface (dynamic handle), arenas over page authority.
10. **Collections and text from std** – `Vec`, `String`, `Map`, `fmt` with
    `Display` impls; these are ordinary Zen once 1–9 exist.
11. **Cleanup** – `Drop`, `@scope.defer`, arena release at scope exit.
12. **Fixed arrays** – `[T, N]` literals, bounds-checked indexing, `loop`.
13. **Floats**, `@meta`, actors, threads, `c.bind` FFI, `proc`, `fs`, `net`.

### Crypto-driven requirements (from the ChaCha20-Poly1305 port)

`zen-crypto-perf/docs/NATIVE_CRYPTO.md` measures what holds pure-Zen crypto
back. None of these exist in the C backend either; the IR is designed so each
has an obvious home rather than being bolted onto a target later.

| Need | IR shape | Target lowering |
| --- | --- | --- |
| Vector types: 4/8 lanes of u32 with add, xor, rotate and lane shuffles | `Vector(lanes, elem)` slot kind (16/32-byte slots, 16-byte aligned); `VectorBinary`, `VectorRotate`, `Shuffle(pattern)` instructions | NEON (`add.4s`, `eor`, `ushr`+`sli` or `tbl`) on arm64; SSE2/AVX2 on x86-64 |
| u128 or 64x64->128 multiply | `MulWide(out_lo, out_hi, a, b)` over u64 (signed/unsigned) | `mul`+`umulh` on arm64, `mulq` on x86-64 |
| Explicit u64 -> u32 truncation | `Convert` with an explicit `Truncate` mode (never implicit) | `mov wN, wM` / `movl` |
| Target-feature selection, runtime dispatch between CPU paths | features on the target value (`avx2`, `neon`, `sha`); a `CpuHas(feature)` instruction for dispatch | `cpuid` on x86-64; `hw.optional.*`/`HWCAP` on arm64 (NEON is baseline) |
| Left shift, bit-or | `Op.Shl`, `Op.Or` beside `Xor`, `And`, `Shr`, `Rotr` | one instruction each |
| Forced inlining | a function attribute carried in `Func`, honoured by an IR inliner before rendering | target independent |
| Volatile store, compiler barrier (secure wiping) | `Store` with a `volatile` flag; `Barrier` instruction that no pass may move memory across | plain stores (the renderer never elides stores) plus no reordering; a barrier emits nothing on these in-order renderers but must stop future optimisation passes |

Because the renderers emit every IR store and never reorder memory, a volatile
store and a compiler barrier are already honoured today; the flags exist so
that later optimisation passes (register allocation, dead-store elimination,
inlining) keep that guarantee.

### Plan

The design rules in `BACKENDS.md` bind this work: language semantics are
extended in shared lowering and verified IR, one feature family at a time;
machine details stay inside each target; targets never fall back to C.

* **Stage 2 – targets and runtime.** Add `gen_asm_arm64` beside
  `gen_asm_x86`. Replace every libc call in the generated code with a small
  per-target runtime emitted as assembly: buffered stdout, decimal
  formatting, traps, `exit_group`. Linux uses raw `syscall` / `svc #0` and its
  own `_start`. macOS calls libSystem (see below). Build with `as` + `ld`.
* **Stage 3 – real programs.** Widen the IR from scalar slots to sized slots
  (integers of every width, pointers, aggregates in frame memory), add memory
  and syscall instructions, and grow `gen_lower` along the gap list. Every
  step is checked differentially: the same corpus program through the C
  backend (the `.expected` oracle) and the asm backend must agree on stdout
  and exit status.
* **Stage 4 – measurement.** Compile a crypto primitive with both backends and
  compare runtime.

## Architecture

```text
AST + checked sema facts
  → gen_lower_core / gen_lower_call / gen_lower_member / gen_lower_shape   (full lowering)
  → gen_ir.Program  → gen_verify.verify
  → gen_asm_prepare   (tables, inlining, scalar replacement, block layout)
  → gen_asm_regalloc  (per function: simplify, liveness, linear scan)
  → gen_asm_x86.X86_64Linux | gen_asm_arm64.Arm64(Linux | Darwin)   (renderers)
  → gen_asm_peephole → as + ld (zen.zen_native)
```

**The IR stays target-neutral.** There is one IR: integer widths
(`I8 … U64`), `Ptr`, `Block(Layout)` aggregates held in frame memory,
`Convert`, `AddressOf`, `Load`/`Store` at byte offsets, `CopyBytes`,
`StaticBytes`, stream output (`WriteOut`, `Print` with a stream), `System`
(portable `Sys` operation), `SysConst` (portable constant name), `Startup`
(argc/argv/envp), `MapPages`/`UnmapPages`, `Flush`, and a `Trap` terminator,
beside the original scalar instructions. Nothing in it names a register, an
instruction or an ABI; checked arithmetic, wrapping arithmetic, shifts and
rotates are operations on typed slots. One verifier (`gen_verify.verify`)
checks it; a renderer that implements only part of it (JavaScript and the IR C
renderer today) declares that part through `supports` (`gen_ir_feature`).

**Full lowering** (`src/gen/gen_lower_*`, target-independent; the arch gate in
`tests/gates/arch_boundary.zen` classifies `gen.gen_lower*` as frontend, so
renderers may not import it and it may not import a renderer). It is named
for lowering, not for assembly: its output is the one IR, which every renderer
consumes. `gen_lower` is its entry point (`lower`) and owns `LowerError`; the
former scalar-only lowering is gone.

* `gen_lower_shape` — machine layouts of checked types: words, `str` as
  `{data: Ptr<u8>, len: usize}`, records at natural alignment, tagged
  unions (u32 tag + payload; payload-free enums are the tag word), fixed
  arrays, bounds as `{tag, receiver pointer}` handles, capabilities as
  zero-size. An unsettled type parameter has a zero-size placeholder layout.
* `gen_lower_core` — frames, slots, places (`InSlot`/`Through`), statements,
  expressions, patterns (nested), `.try()` across frames, error-set
  widening, coercions (literal widths, `Ok` lifting, union membership,
  same-named alternatives), instantiation of functions per substitution.
* Matches: each arm's tests are compiled from sema's reading of its pattern
  (`sema.read_pattern`, the tree coverage checking used), never from the
  pattern's spelling, so `Err(Authentication)` on `Res<T, Kind | Fail>`
  tests the member `Kind` and then its case; a case the reading names that
  the layout lacks refuses the program. Error-set members are tagged in name
  order, so `Kind | Fail` and a declared `Both = Kind | Fail` share a layout.
  Every tag test the lowering branches on and every payload read is recorded
  in `Func.guards`, and `gen_verify` refuses a payload read that is not
  behind a test of that slot for that alternative on every path
  (IR_ARCHITECTURE §4.1 rule 3).
* `gen_lower_call` — calls: arguments in written order, mutable parameters by
  address, closure-taking callees inlined in the frame that wrote the
  closure (so `.try()` and `h.break()` keep their meaning), `loop`
  overloads and handles, `Ptr`, numeric conversions and bit operations,
  console formatting, constructions with defaults, inference of open
  parameters from arguments, closures, ranges and breaks.
* `gen_lower_member` — member resolution (own struct, impl override, bound
  default), bound values dispatched at run time over the program's
  implementors (`Alloc` → `Arena`, `Pages`, test allocators), `Mem`
  (arenas over `mmap`), and the `std.sys` operations.

**What is still target-specific in the lowering.** Frames, registers, the
calling convention, stack layout, syscall numbers, OS constants and libSystem
symbols are all decided by the renderers and `gen_sys` from the IR and the
`Target`. The lowering itself still assumes three things:

* a 64-bit machine word: `usize`/`isize` lower to `U64`/`I64` and `Ptr` is
  8 bytes, so pointer arithmetic and `str.len` are 64-bit;
* the layouts `gen_lower_shape` computes (natural alignment with 8-byte
  pointers, `str` as `{ptr@0, len@8}`, a `u32` tag before union payloads,
  bound handles as `{u32 tag, receiver pointer}`), which are shared by all
  three current targets but would need a data-layout parameter for a 32-bit
  or wasm32 target;
* the page header size used by `Pages`/`MapPages` (16 bytes), a runtime
  convention the renderers implement identically.

None of these names a register, an instruction or an OS; a `Layout` input
(pointer width, alignment of `u64`) is the planned fix when a non-64-bit
target arrives.

**Renderers** own registers, frames, calls and object syntax. They consume
only the IR program and the `Target` value, through the machine-level
passes described under *Performance* below. Words hold their value extended
to 64 bits wherever they live (a register, the frame, or a constant); aggregates are passed by pointer to the
caller's copy and returned through a hidden pointer (`%rdi` / `x8`), which is
the System V MEMORY class and the AAPCS64 indirect-result convention for
large composites (small-struct register classification is not implemented;
it only matters for foreign calls, which this backend does not make). The
runtime (buffered stdout, decimal printing, traps, exit, page mapping,
Darwin adapters) is emitted as assembly beside the program.

## Operating system policy

| Target | Entry | Kernel interface | Object/link |
| --- | --- | --- | --- |
| Linux x86-64 | own `_start` | `syscall`, numbers from the x86-64 table | ELF, `as` + `ld -static` |
| Linux AArch64 | own `_start` | `svc #0`, numbers from the generic table | ELF, `as` + `ld -static` |
| macOS arm64 | `_main` called by dyld | **libSystem** function calls | Mach-O, `as` + `ld -lSystem` |

Darwin does not promise a stable system-call ABI: numbers and calling details
belong to libSystem and have changed between releases, and Apple only supports
static binaries for the kernel itself. Following Go (since 1.11), the macOS
target keeps generating the complete program in assembly but links against
`libSystem.dylib` and calls its exported `write`, `mmap`, `exit`, ... symbols.
No C source is compiled and no C runtime startup object is used; dyld calls
`_main` directly. Linux, whose syscall ABI is stable, gets raw syscalls and no
dynamic linker at all (static ELF, no interpreter).

### The syscall layer

Two Zen pieces make the kernel interface first-class:

* **`std.sys`** (`src/std/sys/sys.zen`) is the reusable module programs and
  std import. Its bodiless declarations are the kernel operations — `read`,
  `write`, `openat`, `close`, `mmap`, `munmap`, `exit_group`,
  `clock_gettime`, `getrandom`, `socket`, `bind`, `listen`, `accept4`,
  `connect`, `epoll_create1/ctl/pwait`, `kqueue`, `kevent`, `futex`, `clone` —
  plus process start values (`argc`, `argv`, `envp`) and constants whose
  values differ per OS (`at_fdcwd`, `o_creat`, `clock_monotonic`, ...). On
  them, in ordinary Zen: `c_len`, `arg`, `env_var`, `write_all`,
  `read_full`, `read_file`, `write_file`, `monotonic_ns`, `realtime_ns`,
  `random_bytes`, and **`Pages`, an `Alloc` whose runs are individual
  anonymous mappings** (header with the mapping length; `free` unmaps).
  `std.sys.sys_env` gives the `Env` capabilities (`var`, `argv`,
  `fs.read/write/exists/is_dir`, the clock) their native meaning; the
  native lowering calls these Zen functions for the bodiless `Env` members.
* **`gen.gen_sys`** holds the target facts: the `Sys` operations, their Linux
  x86-64 numbers (`syscall_64.tbl`), Linux AArch64 numbers (asm-generic
  `unistd.h`), their libSystem symbols, and the per-platform constant table.

Every operation returns a word; a negative value is `-errno` on every OS. The
Darwin renderer converts libSystem's `-1` + `errno` into that form, and
adapts the two calls whose C shape differs: `openat`'s variadic mode goes on
the stack, and `getrandom` becomes `getentropy` in 256-byte chunks returning
the byte count. `accept4` is `accept` on Darwin (flags must be zero), epoll
and futex/clone answer `-ENOSYS` there, kqueue answers `-ENOSYS` on Linux.
The pthread operations (`pthread_start`, `pthread_join`, the mutex and
condition calls) exist only on Darwin and answer `-ENOSYS` on Linux; they
return their error number directly, which the renderer negates.

### Threads and actors

Threads follow the same OS policy: raw `clone` and futexes on Linux,
libSystem pthreads on macOS, one API above both.

* **IR.** Atomics are instructions (`AtomicLoad`, `AtomicStore`,
  `AtomicUpdate` Swap/Add, `CompareSwap`), sequentially consistent on 4- and
  8-byte words: plain `mov` loads and `xchg`/`lock xadd`/`lock cmpxchg` on
  x86-64, `ldar`/`stlr` and `ldaxr`/`stlxr` loops on AArch64 (ARMv8.0, so no
  feature check). `CodeAddress` names a function's machine address and
  `InvokeAt` calls through one with word arguments (at most six, the System V
  register count). `StartValue.Globals` is a zeroed 256-byte process block;
  its first word is an exit hook the runtime calls on the main thread after
  the entry function returns, before stdout is flushed.
* **Runtime (asm).** Every thread starts at `entry(arg)` read from its
  control block (`+8`, `+16`). Linux: `_start` installs the main thread's
  block as TLS (`arch_prctl(ARCH_SET_FS)` / `tpidr_el0`); `za_clone` issues
  `clone(CLONE_VM|FS|FILES|SIGHAND|THREAD|SYSVSEM|SETTLS|PARENT_SETTID|
  CHILD_CLEARTID)` on a caller-built stack, with the block as the new
  thread's TLS and its id word at `+24`; the child calls the entry and
  leaves with `exit` (not `exit_group`). Darwin: `za_d_thread_start` wraps
  `pthread_create` with an 8 MiB stack and a C entry point that preserves
  x19-x28/d8-d15. The shared stdout buffer is locked: a futex word on Linux,
  an `os_unfair_lock` on Darwin.
* **`std.sys.sys_thread` (Zen).** Mutexes and condition variables in caller
  memory (`MUTEX_BYTES` 64, `COND_BYTES` 48 — the size of Darwin's
  `pthread_mutex_t`/`pthread_cond_t`). On Linux the mutex is Drepper's
  three-state futex lock and the condition a sequence word; on macOS they
  are `pthread_mutex_t`/`pthread_cond_t` (`os_unfair_lock` has no condition
  variable to pair with, so it guards only the runtime's stdout buffer).
  `thread_spawn` maps an 8 MiB stack with a 64 KiB guard below it and the
  control block above it; `thread_join` waits on the id word with a shared
  futex (the kernel's `CHILD_CLEARTID` wake), then unmaps the stack.
* **`std.actor.actor_runtime` (Zen).** The actor runtime both backends
  share (`ACTOR_RUNTIME.md`): workers per CPU over std.sys threads, parkers
  and atomics; the native backend reaches it exactly as the C backend does.
* **Lowering** (`gen_lower_thread`, `gen_lower_actor`). A spawned closure is
  lifted into a synthesized function over a capture record (values copied,
  `::` bindings by address, capabilities free); its answer is written into
  the record and read by `join` at the join's expected type. `env.spawn`
  lays out the actor record (state, Context, arena) and starts the worker; a
  behavior call copies its arguments into a payload record (str bytes into
  the message) and each send site gets a synthesized turn; the stopped hook
  also drops the state and the arena. A byte buffer (`Vec<u8>`) argument's
  bytes travel in the message like a str's, and the turn moves them into the
  actor's own allocator before the behavior runs, so the behavior may keep
  and grow the buffer (the C backend gives each such message its own
  receiver-owned arena instead; both live until the actor stops).

The C and JavaScript backends do not provide the bodiless `std.sys`
operations; C programs keep reaching the OS through `Env` and libc.

## Status

### Stage 3: real programs (differential corpus)

`tests/native` is a Zen program (`tests/native/main.zen`, built by
`tests/native/build.zen` with the C backend) that compiles every corpus
program with `--backend asm --target T`, assembles and links it with the
system tools only, runs it with the test's arguments, stdin and environment,
and compares stdout, exit status and stderr substrings with the recorded C
behaviour (`.expected`, `.exit`, `.stderr`). Verdicts: PASS, FAIL (behaviour
differs), UNSUPPORTED (refused before publishing assembly), BROKEN (assembler
or linker rejected the output).

| Target | Pass | Fail | Unsupported | Broken | Of |
| --- | --- | --- | --- | --- | --- |
| x86_64-linux (dev-box) | 638 (66.3%) | 0 | 324 | 0 | 962 |
| aarch64-linux (qemu-user) | 638 (66.3%) | 0 | 324 | 0 | 962 |
| arm64-darwin (this Mac) | 638 (66.3%) | 1 | 323 | 0 | 962 |
| x86_64-linux, `shared-lowering` | 708 (72.4%) | 1 | 269 | 0 | 978 |

The `shared-lowering` row is after the lowering merge and the gap work
below; at the merge point (2b70b639) the same runner read 643 / 3 / 331 of
977. The remaining failure, `env/fs_read_special_file_with_zero_stat_size`,
also fails on Linux: the program sees 0 bytes from a zero-stat-size file.

The one macOS failure, `env/fs_read_special_file_with_zero_stat_size`, reads
a file under `/proc`, which exists only on Linux; its expectation was recorded
on Linux. On a loaded Mac, about 20 more programs exceed the runner's 10 s alarm
(exit 142) because of the first-launch scan of each new binary. They pass when
re-run with less parallelism.

Run it: `cd tests/native && ../../zen build`, then from the repository root
`tests/native/build/<os>-<arch>/native-corpus ./zen <target> [filter] [shard shards]`.

Refused constructs on `shared-lowering`, by the first one each unsupported
program reaches (x86_64-linux, 269 programs): compiler-internal test roots
that import `gen`/`sema`/`lsp`/`zen` modules the runner does not stage (117),
other `Env` operations (actors, threads, fs.lock/cwd/mkdir, args schema: 30),
floats (19), value conversions not modelled yet (15: `str` to `u8`, AST
`Variant` to `Member`, unit results into records), unknown variants (11),
expressions sema left unchecked below a call it could not type (11; mostly
`alloc.create<T>()` on a bound in `main`, whose result sema leaves open, and
closure captures), native-only expressions (10), `invalid IR` type mismatches
in `.then`/`.try()` compositions and the cli library (9), impl-computed fields
(`width: self.side` in an impl; 5), and a tail of single causes.

Resolved on this branch: unsettled types in generic corners (35 to 1; a name
sema left open takes its instance local's type, and a method call on it the
result type of the method its type resolves to, including UFCS free functions
such as `bool.then`), folding loops, loop handles passed into closures,
`create<T>()` typed from its type argument, generic enum payloads (`Opt<T>`
substituted per instance), and the error-set match failures.

Not yet lowered, from branches that have not merged here: module-qualified
constants such as `Controller.LIMIT` (lang-gaps; `type_member` would send
them to the variant lookup, so they must go through `global_const`), local
functions `name = (params) T { .. }` inside a body (lang-gaps; inlined at each
call with live captures, `.try()` returning from the enclosing function), the
float conversions `narrow_f32`/`narrow_f64` and checked f64/int conversions
(lang-gaps), and the bitwise operators `& | ^ ~ << >>` (bitwise-operators:
the lowering's operator table is now explicit, and `complement` is the `~`
lowering). Floats themselves need an `F64` slot class, which the JavaScript
branch adds to the IR and the lowering; the assembly renderers still refuse it.

The runner stages each program as `tests/run.py` does: it runs as
`<scratch>/prog` in a directory where its root is visible as `src`, with the
harness-only environment variables, the symlink loop and the rewritten epoch
for the tests that need them.

### Stage 4: performance

`tests/native/bench/{sha256,blake2b,chacha20}` build zen-crypto's
`sha256.zen`, `blake2b.zen` and `chacha20poly1305.zen` unchanged with the C
backend (`cc -O2`) and the asm backend, hash or seal a 1 MiB buffer `rounds`
times, and print a digest that must agree between the two builds. dev-box
(AMD EPYC-Milan, pinned to one CPU, load below 4), 32 rounds:

| Benchmark | C -O2 | asm before | asm now | ratio before | ratio now |
| --- | --- | --- | --- | --- | --- |
| SHA-256 | 0.133 s | 3.18 s | 0.209 s | 23.9x | 1.56x |
| BLAKE2b | 0.141 s | 2.18 s | 0.184 s | 15.5x | 1.30x |
| ChaCha20-Poly1305 | 0.218 s | 4.48 s | 0.392 s | 20.6x | 1.79x |

Native corpus verdicts are unchanged by this work on x86_64-linux and
aarch64-linux (643 pass, the same 3 failures, 331 unsupported of 977).

The work sits in a machine-level layer between the verified IR and the
renderers; the shared lowering and the IR are unchanged.

* `gen_asm_prepare` rewrites the whole program: an integer `match` choosing
  among constants becomes a bounds check and a load from a read-only table
  (little-endian, the byte order of every target here); calls to small
  functions that call nothing are inlined; aggregates reached only through
  their own frame address and whole copies are split into one word slot
  per field; blocks are laid out in reverse postorder (a branch's taken
  side first) with empty jump blocks threaded away.
* `gen_asm_regalloc` simplifies each function (copy propagation, constant
  folding that never removes a trap, removal of dead pure instructions
  including self-feeding counters, sinking of single-use pure instructions
  next to their reader) and allocates registers by linear scan over
  interval hulls computed from per-slot liveness (`gen_asm_flow`). Values
  live across or read by a call, a kernel call, a large aggregate copy or
  any instruction not known to be simple get callee-saved registers only
  (rbx, r12-r15; x19-x28); others prefer caller-saved ones (rsi, rdi,
  r8-r11; x4-x7, x10-x15). Spills pick the interval with the lowest
  loop-weighted use density. A slot written only with one constant, or
  only with one frame address, has no register: it is materialized where
  read. Address-taken slots and aggregates stay in the frame.
* The renderers select instructions over those homes: memory and immediate
  operands, 32-bit instructions for 32-bit classes (the flags check 32-bit
  overflow, so checked arithmetic keeps its trap and `Wrap*` needs no
  check), rotates and shifts by immediate, base+index*scale addressing that
  absorbs the pointer arithmetic before an access, loads folded into ALU
  operands (x86), compare-and-branch without materializing the boolean,
  fallthrough to the next block, and unsigned division, remainder and
  checked multiplication by powers of two as shifts and masks.
* `gen_asm_peephole` cleans the seams between instructions: a stack store
  reloaded on the next line becomes a register move, a move straight back
  is dropped, and so is a jump to the next line.

Not done yet: byte-swapped or whole-word loads for byte-assembled words
(SHA-256 reads its message a byte at a time; the IR has no byte-swap
operation, `gen_ir_machine`'s vocabulary is where one would come from),
multiply-by-reciprocal division by other constants, interval splitting,
and using %rbp and the scratch registers for allocation.

### Roadmap to zen-crypto and zen-http on the native backend

1. **Performance.** Done to within 2x of `cc -O2` on SHA-256, BLAKE2b and
   ChaCha20-Poly1305 (see Stage 4). Next: a byte-swap/whole-word load IR
   operation, interval splitting, and more allocatable registers.
2. **Crypto surface** (see the requirements table above): `u128`/`mul_wide`,
   vectors, target-feature dispatch (`CpuHas`), forced inlining, and
   volatile store plus a compiler barrier for wiping secrets.
3. **Remaining language coverage:** floats, the missing conversions, loop
   handles as values, folding loops, and the unsettled generic corners.
4. **zen-http:** sockets and readiness are in `std.sys` (epoll on Linux,
   kqueue on macOS), and threads and actors run natively (above). Missing
   are the `Env` operations the corpus still refuses (`args` schemas,
   `fs.cwd/mkdir/remove`).
5. **Backend unification** (per `IR_ARCHITECTURE.md`): done for the IR paths.
   One lowering feeds JavaScript, the IR C renderer and assembly, and each
   declares its support. The full C backend (`gen_c`) is still AST-driven.

### Stage 2: three targets, no libc

* `gen_asm_x86.X86_64Linux`: rewritten without libc. Own `_start`, `syscall`
  for `write`/`exit_group`, 8-byte slots, out-of-line trap stubs.
* `gen_asm_arm64.Arm64(os: Linux | Darwin)`: new. Slots addressed from `sp`
  with a preallocated outgoing-argument area, `movz/movk` constants,
  `adds/subs/negs` + `b.vs`, `smull` + sign-extension compare for checked
  multiply, explicit zero and `MIN / -1` checks around `sdiv`.
* Runtime per target, in assembly: a 64 KiB stdout buffer (`za_out`,
  `za_flush`), `za_write_all` (retries `EINTR` and short writes),
  `za_print_i64/u64`, `za_trap` (flush, `file:line:col: trap: what` to fd 2,
  exit 134) and `za_exit`. The Darwin build imports exactly `_write`,
  `__exit` and `___error` from libSystem.
* `gen_sys`: the syscall layer (`Sys` operations; Linux x86-64 and
  generic-table numbers; libSystem symbols; `-errno` result convention).
* Driver: `zen build --backend asm [--target T]` (host by default);
  `Codegen.Asm` projects assemble and link with `as` + `ld`
  (`zen.zen_native`), cross-prefixed binutils and `qemu-<arch>` when the
  target architecture differs from a Linux host.
* Tests (Zen): `gen/asm_renderer` (calls with 6-9 arguments, stack alignment
  probe on x86-64, exact bytes, register-cache invalidation, add/mul traps)
  and `gen/asm_traps` (div/rem overflow, divide by zero) build for the host;
  `ZEN_ASM_TARGET=aarch64-linux` runs them for AArch64 under qemu.
  Verified: macOS arm64 (native), Linux x86-64 (dev-box), Linux AArch64
  (dev-box, qemu-aarch64 8.2 + binutils 2.42).

On this macOS host every freshly linked executable (C or assembly) takes about
3-4 s to launch the first time (a system policy scan), so tests that launch
many new binaries (`gen/scalar_backends`, `backends/c_ir_pilot`) exceed the
harness's 20 s default here; they pass with `--run-timeout 300`, as they did
not before this change for the asm cases.
