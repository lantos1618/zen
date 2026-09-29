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
the asm backend could build were the hand-made IR tests and
`example/backends`.

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
  → gen_asm_lower / gen_asm_call / gen_asm_member / gen_asm_shape   (native lowering)
  → gen_ir.Program (native surface)  → gen_verify.verify_native
  → gen_asm_x86.X86_64Linux | gen_asm_arm64.Arm64(Linux | Darwin)   (renderers)
  → as + ld (zen.zen_native)
```

**The IR stays target-neutral.** `gen_ir` has two surfaces. The scalar surface
(`I32 | Bool | Unit`, the original instructions) is what `gen_lower` produces
for JavaScript and the IR-C pilot. The native surface adds integer widths
(`I8 … U64`), `Ptr`, `Block(Layout)` aggregates held in frame memory,
`Convert`, `AddressOf`, `Load`/`Store` at byte offsets, `CopyBytes`,
`StaticBytes`, stream output (`WriteOut`, `Print` with a stream), `System`
(portable `Sys` operation), `SysConst` (portable constant name), `Startup`
(argc/argv/envp), `MapPages`/`UnmapPages`, `Flush`, and a `Trap` terminator.
Nothing in it names a register, an instruction or an ABI; checked arithmetic,
wrapping arithmetic, shifts and rotates are operations on typed slots. A C,
JavaScript or LLVM renderer can consume the same program: `verify_native`
checks it, and `verify` keeps the scalar renderers on their subset.

**Native lowering** (target-independent, shared by both asm renderers):

* `gen_asm_shape` — machine layouts of checked types: words, `str` as
  `{data: Ptr<u8>, len: usize}`, records at natural alignment, tagged
  unions (u32 tag + payload; payload-free enums are the tag word), fixed
  arrays, bounds as `{tag, receiver pointer}` handles, capabilities as
  zero-size. An unsettled type parameter has a zero-size placeholder layout.
* `gen_asm_lower` — frames, slots, places (`InSlot`/`Through`), statements,
  expressions, patterns (nested), `.try()` across frames, error-set
  widening, coercions (literal widths, `Ok` lifting, union membership,
  same-named alternatives), instantiation of functions per substitution.
* `gen_asm_call` — calls: arguments in written order, mutable parameters by
  address, closure-taking callees inlined in the frame that wrote the
  closure (so `.try()` and `h.break()` keep their meaning), `loop`
  overloads and handles, `Ptr`, numeric conversions and bit operations,
  console formatting, constructions with defaults, inference of open
  parameters from arguments, closures, ranges and breaks.
* `gen_asm_member` — member resolution (own struct, impl override, bound
  default), bound values dispatched at run time over the program's
  implementors (`Alloc` → `Arena`, `Pages`, test allocators), `Mem`
  (arenas over `mmap`), and the `std.sys` operations.

**Renderers** own registers, frames, calls and object syntax. Words live in
8-byte slots extended to 64 bits; aggregates are passed by pointer to the
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
Threads over `clone` + futex are not built yet; macOS threads would go through
pthreads in libSystem.

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
| x86_64-linux (dev-box) | 507 (52.7%) | 0 | 455 | 0 | 962 |
| aarch64-linux (qemu-user) | 507 (52.7%) | 0 | 455 | 0 | 962 |
| arm64-darwin (this Mac) | see the latest run below | | | | 962 |

Run it: `cd tests/native && ../../zen build`, then from the repository root
`tests/native/build/<os>-<arch>/native-corpus ./zen <target> [filter] [shard shards]`.

Refused constructs, by the first one each unsupported program reaches
(x86_64-linux, 455 programs): `String`/`fmt` formatting and `Display`
(~50), `Drop` cleanup (36), unsettled types in remaining generic corners
(~30), other `Env` operations (actors, threads, fs.lock/cwd/mkdir, args
schema: ~27), `@scope`/`defer`, `consume`, `@meta` (~19), floats (18),
`==` on records (16), folding loops (9), compiler-internal test roots that
import `gen`/`sema` (~40).

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
