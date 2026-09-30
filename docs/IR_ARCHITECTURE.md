# Zen IR and backend architecture

Status: **proposal, with its enforcement gate landed** (`make archcheck`).
Branch `ir-architecture`, cut from `unified-rooms` at 890acb1c on 2026-09-29.
`BACKENDS.md` remains the contract for what exists today, and this document
describes where that contract goes next. §8 lists the decisions this document
does not make on the user's behalf.

The goal, in the user's words, is a language that compiles to C and has an IR
we can build Rust, NASM, FASM, asm, x86, TS, JS and C backends from, and later
zen-llvm and a JIT. The priorities are C (primary), JS, and one assembly
backend. Everything should eventually be able to run on raw syscalls, with no
libc, wherever the OS allows it.

The architecture in one sentence: **one lowering produces one verified IR, and
every backend is a renderer of that IR for a Target.** Everything below follows
from that sentence, or exists to make it true without breaking the compiler
that builds itself.

---

## 0. Where we are

These facts were read from the trees on 2026-09-29.

| Piece | Where | Size | Reads |
|---|---|---|---|
| Full C backend | `src/gen/gen_c/` (62 files) | ~30k lines | AST + sema directly: **306 direct frontend imports** in 59 of the 62 files |
| Scalar IR | `src/gen/gen_ir.zen` | 60 lines | i32/bool/unit slots, blocks, checked arithmetic, calls, print |
| Scalar lowering | `src/gen/gen_lower.zen` | 727 lines | AST + sema, into scalar IR |
| IR verifier | `src/gen/gen_verify.zen` | 341 lines | IR only |
| JS renderer | `src/gen/gen_js.zen` | 272 lines | IR only |
| x86-64 renderer | `src/gen/gen_asm_x86.zen` | 342 lines | IR only |
| IR→C pilot | `src/gen/gen_c_ir.zen` | 254 lines | IR only (a differential oracle, not selectable from the CLI) |

The in-flight branches this design has to absorb:

- **`native-asm-backend`** (`../zen-asm-backend`). Adds libc-free x86-64 and
  AArch64 (Linux and Darwin) renderers, a `gen_sys` syscall table, and a
  *native surface* of the IR (integer widths, `Ptr`, `Block(Layout)`
  aggregates, `Load`/`Store`, `SysCall`, `Trap` terminators). The renderers
  are clean: they read only the IR. The branch also adds a **second AST→IR
  lowering**, `gen_asm_lower`/`_call`/`_member`/`_shape` (~4.3k lines), which
  sits beside `gen_lower` and is named as if it were a backend. The gate
  (§4.4) flags those four files, and §6 stage 0 renames them and merges them
  into the one lowering. There is also a split to undo: the branch has two
  verifier entry points, `verify` and `verify_native`, for two IR "surfaces",
  and this design replaces both with a single IR plus per-backend capability
  declarations (§3.2).
- **`simd-u128`** (`../zen-simd`). Adds `u128`, `mul_wide`, explicit
  `truncate_*`, the full set of unsigned bit operations, `std.simd` vectors
  (`u8x16` … `u64x4`) with lane, shuffle and rotate operations, and
  target-feature capability tokens (`Avx2`, `Ssse3`, `Aes`, `Clmul`, `Neon`)
  obtained from runtime CPU checks. Today all of this lowers only through
  `gen_c` (`__int128`, GNU vector extensions, `__attribute__((target))`).
- **`match-safety`** (`../zen-match-safety`). Records every tag or literal test
  that `gen_c` emits in an `ArmTrace`, and makes sema's usefulness engine check
  that each arm's emitted tests and sema's reading of the pattern select the
  same values. That is correct, but it works per backend: every future backend
  would have to re-record its tests. §2.6 moves the check to the one place
  match tests are decided.
- **`native-pkgs`** (`../zen-native-pkgs`, `docs/proposals/NATIVE_PACKAGES.md`).
  Adds real targets (`--target arch-os-abi`, `b.target()`, `std.target`), and
  `b.native` libraries. The IR's `Target` (§3.1) *is* that target value. It is
  not a second description of the same thing.

---

## 1. Pipeline

```text
source ─▶ lex ─▶ parse ─▶ AST ─▶ sema ──────────────▶ lowering ──▶ Zen IR ──▶ verify ──▶ VerifiedProgram
          std.lex std.parse std.ast  src/sema          src/gen/gen_lower*   gen_ir*      gen_verify*       │
                                     (memoized queries,  (monomorphise,                                   │
                                      checked facts)      decide matches,                                 ▼
                                                          insert drops,                  ┌───── backends (+ Target) ─────┐
                                                          lay out types)                 │ C · JS/TS · asm (x86-64,      │
                                                                                         │ AArch64) · later: Rust, NASM, │
                                                                                         │ FASM, LLVM text, JIT, interp  │
                                                                                         └───────────────────────────────┘
```

### 1.1 No HIR tree. Sema's published facts are the HIR

A separate HIR, a desugared copy of the AST, would be a fourth tree
(CST/AST, sema tables, HIR, IR) with its own spans, arena and walkers. It would
also split the compiler's knowledge of "what this call means" between sema and
the HIR builder. Zen already has the part of a HIR that matters: sema is
memoized queries (DESIGN.md, decision 3), and it *publishes* checked facts per
node, such as `CheckedCall` with its selected declaration, substitutions,
result type and signature (BACKENDS.md, "Migration order").

**Decision:** there is no HIR tree. What `BACKENDS.md` calls "a complete call
execution plan" becomes a set of sema-published **plan tables**, one row per
instantiated node:

- the call plan: callee identity, substitutions, the binding of named and
  default arguments to parameter order, conversions, and receiver evaluation
- the capture plan for each closure
- the move and drop plan for each binding: moved on which paths, and whether
  a drop flag is needed
- the match plan: sema's normalized reading of each pattern, the same data
  the usefulness engine already uses

Lowering reads the AST *only* for structure (which statement comes next) and
reads every *meaning* from the plan tables. A rule such as "which overload" or
"is this a move" then has exactly one owner, sema, and lowering cannot
re-decide it. If a later optimization wants a desugared tree, it can have one
as a lowering-internal detail. It is never a phase boundary.

### 1.2 Zen IR: a CFG over mutable typed locals and places, not SSA

The existing `gen_ir` is already a control-flow graph of basic blocks over
mutable typed slots. **Keep that form and grow it.** Do not switch to SSA.

The reasons:

1. **The text backends want variables, not φ-nodes.** C and JS are the
   primary targets. A slot is a C local or a JS `let`, so C and JS render it
   one-to-one and the output stays readable. With SSA, every text backend
   would need an out-of-SSA pass (copy insertion and coalescing), duplicated or
   shared. That pass is exactly the kind of code that makes emitted C
   unreadable.
2. **LLVM builds SSA itself.** The zen-llvm path lowers slots to `alloca`, and
   `mem2reg`/SROA construct SSA for free. This is what `BACKENDS.md` already
   anticipates, and what rustc does with MIR.
3. **The asm backend needs liveness, not SSA.** A linear-scan or graph-coloring
   allocator over mutable slots runs on a liveness analysis. The asm branch
   today keeps every slot in a stack home plus a register cache, and a slot-based
   allocator is the direct next step.
4. **Places are the unit of ownership.** Moves, drops, partial moves, `Ptr`
   writes and field assignment are all statements about *places*. SSA values
   have no identity to move out of, so MIR is non-SSA for the same reason.
5. **SSA can still exist as an analysis.** An optimization pass that wants SSA
   (GVN, for example) may build an SSA *view* internally and write back to
   slots. The contract between lowering and backends stays slots.

The shape of the IR:

```text
Program   = { types: TypeTable, functions: [Func], statics: [Static],
              spans: [Span], entry: FuncId, runtime: RuntimeNeeds }
Func      = { symbol, params, result, locals: [Local], blocks: [Block],
              features: FeatureSet, attrs (inline, cold, behavior-of-actor),
              origin: SpanId }
Local     = { ty: TypeId, name: debug name | none, kind: param | user | temp }
Block     = { code: [Stmt], exit: Terminator }
Place     = local . projection*           projection = Field(i) | Index(local)
                                          | Deref | Payload(variant)
Operand   = Copy(place) | Move(place) | Const(bits, ty) | Static(id)
Stmt      = Assign(place, Rvalue, SpanId) | Drop(place) | StorageDead(local)
          | SetDiscriminant(place, variant) | Call(dest?, callee, [Operand])
          | Sys(dest, op, [Operand]) | Runtime(dest?, RtOp, [Operand])
          | Barrier | DebugBind(local, name)
Rvalue    = Use(Operand) | Binary(op, a, b) | Unary(op, a) | Convert(mode, a)
          | Aggregate(ty, [Operand]) | AddressOf(place) | Discriminant(place)
          | MulWide(a, b) | Vector(VecOp, [Operand]) | Len(place)
Terminator= Return | Goto(b) | Switch(Operand, [(value, b)], default b?)
          | Trap(kind, SpanId) | Unreachable
```

A few choices in that shape need their reasons stated:

- **Calls are statements, not terminators.** MIR makes calls terminators
  because of unwinding edges. Zen has no unwinding: a trap aborts the process
  (DESIGN.md, "The failure model"), and `Res` is an ordinary value. Calls
  therefore do not end blocks, which keeps blocks large and the C output flat.
- **Checked arithmetic is an operator, not an explicit compare and branch.**
  `Binary(Add{checked, span})` traps with the operator's span. Each backend
  has its best idiom for this: `__builtin_add_overflow` in C (DESIGN.md forbids
  checking after a UB add), `jo`/`b.vs` in asm, and a range test in JS.
  Expanding the check in lowering would throw those idioms away. Wrapping
  (`+%`) is a separate operator.
- **Bounds checks are explicit in the IR.** `buf[i]` lowers to a compare, a
  `Switch` to a `Trap(OutOfBounds, span)` block, and then an `Index`
  projection. The verifier can then require that every `Index` is dominated by
  its check (§4.1). Backends do not bounds-check, which removes a whole class
  of divergence.
- **Types are nominal and laid out once.** The type table holds `Int(width,
  signed)` for 8/16/32/64/128 bits, `Usize`/`Isize`, `Bool`, `F32`/`F64`,
  `Unit`, `Never`, `Ptr(T)`, `FnPtr(sig)`, `Array(T, N)`, `Vector(elem,
  lanes)`, `Struct(id)`, `Enum(id)` and `Str` (a pointer and a length). Every
  aggregate carries a **symbol name** (chosen by lowering, so a C backend
  prints `zen_Vec_u8`, not `block_24`) *and* a layout that
  `layout(type, Target)` computes once. C prints struct declarations. asm reads
  offsets. JS reads offsets into linear memory (§3.3). This reconciles the asm
  branch's `Block(Layout)` with C readability: both views come from the same
  record.
- **`Usize` stays symbolic until a Target is known.** Lowering does not decide
  the pointer width. The layout function does, and the verifier runs with the
  Target's data layout.

### 1.3 How each language feature appears in the IR

| Feature | In the IR | Owner |
|---|---|---|
| **Generics** | **Monomorphised in lowering.** The IR has no type parameters. The instance worklist is keyed by (declaration, substitution), comes from sema's published `CheckedCall` and instantiation edges, and is drained in a deterministic order (DESIGN.md: `gen_c` is deterministic). Whole-program compilation already makes this the natural point, and it is where `gen_c_mono` does it today. | lowering |
| **Error unions and `Res`** | `Res<T, E>` is an ordinary `Enum` with `Ok(T)` and `Err(E)`. An error *set* `A \| B` becomes one flattened enum per distinct instantiated set, with a canonical tag order (sorted by declaring module and name, so it is deterministic). Propagating from a narrower set into a wider one is an explicit `Convert(Retag, …)` whose tag map lowering computes: sets merge, so their tags differ. `.try()` lowers to `Discriminant`, then `Switch`, then the cleanup path (drops in scope), then `Return` of the rewrapped error. No backend knows what `.try()` is. | lowering |
| **Match** | Compiled to a **decision tree** in lowering: `Switch` on discriminants and integers, calls for `str` equality, and `Payload(variant)` projections for bindings. §2.6 describes the check that holds it to sema. | lowering |
| **Closures** | A non-escaping callback passed to `loop`, `then` or `match` helpers is inlined at lowering (as `gen_c` does today). Any other closure becomes an explicit environment `Struct` plus an `FnPtr` taking the environment as its first parameter. Escaping environments are allocated through an explicit `Alloc` operand. | lowering |
| **Allocators** | **An `Alloc` is an ordinary value**: a fat struct holding a data pointer and a vtable pointer. Allocation is an indirect `Call` through the vtable. There is no `malloc` or `alloc` instruction, so law 1 ("no ambient allocator") also holds in the IR. The only memory primitive below that is `Sys(mmap/munmap)` (or the host equivalent) inside the page allocator. | lowering, std |
| **Drops and ownership** | Checked in sema, and made explicit in lowering: `Drop(place)` on every exit edge of a scope in reverse declaration order, including the `.try()` and `break` edges. A conditionally moved binding gets a `bool` drop-flag local. `consume` is `Move(place)`. `@scope.defer` closures run on the same exit edges. The verifier checks that no moved place is read before it is reassigned (§4.1). | sema decides, lowering places |
| **Actors and messages** | Behaviors are ordinary `Func`s marked `behavior-of(actor type)`. Spawn, send, stop and join are `Runtime(RtOp)` statements with explicit message layouts. The payload is `Move`d, because sendability was proved in sema. The mailbox, admission limits and scheduling belong to the *runtime*, per target (§3.4), not to the IR. | lowering; runtime per target |
| **u128 / wide multiply / truncation** | `Int(128, false)` is a first-class type. `MulWide(u64, u64) → u128`. `Convert(Truncate, …)` is the only rvalue that discards bits (`Convert(Extend)` widens, `Convert(Checked)` yields a `Res`). The bit operations `And`/`Or`/`Xor`/`Shl`/`Shr`/`Rotl`/`Rotr` have the DESIGN.md semantics built into the operator (a count ≥ width gives 0, rotation counts reduce modulo the width), so no backend re-derives C's UB guards. | IR semantics |
| **SIMD** | `Vector(elem, lanes)` types. `Vector(op)` rvalues cover lane-wise `add_wrap`, `sub_wrap`, `mul_wrap`, bit operations, shifts, rotates, `Splat`, `Lane`, `WithLane` (the lane index is bounds-checked like `Index`), `Load`/`Store` (unaligned), and `Shuffle` with a constant pattern or a dynamic one. Lane arithmetic never traps. | IR semantics |
| **Target-feature regions** | Every `Func` has a `features` set. A capability token such as `Avx2` is proof that a runtime `CpuHas(avx2)` check succeeded. Lowering turns "call `f` while holding the `Avx2` token" into a call to the `+avx2` clone of `f`. The verifier requires callee features ⊆ caller features, unless the call is dominated by the `CpuHas` check that produced the token (§4.1). Backends: C uses `__attribute__((target("avx2")))`; asm emits only the permitted instructions; JS takes the portable path. | lowering, verifier |
| **Debug and source positions** | Every `Assign`, `Call` and `Trap` carries a `SpanId` into `Program.spans`, a table of spans rather than a copy on every instruction. Locals carry their source names. Backends turn these into `#line` in C, source maps in JS, and `.loc` directives with DWARF/CFI in asm. The trap report (`file:line:col: trap: what`) comes from the same table, so all backends print identical traps. | lowering; backends render |
| **FFI (`c.bind`, `b.native`)** | An `Extern` function declaration names a symbol, a signature, and the native library that provides it (native-pkgs). Calls to it use the Target's C ABI. The IR does not know about headers: the C backend includes them, and asm backends only need the symbol and the ABI. | lowering; backend ABI |
| **Env capabilities / io** | These are *not* IR primitives. `std` implements io on `std.sys` (§3.4), and `std.sys` bottoms out in `Sys(op, …)` statements or `Extern` calls, depending on the Target's sys flavor. | std |
| **comptime / `@meta`** | Evaluated in sema. Lowering sees only the results (constants and generated declarations). A later IR interpreter (§8, Q5) could become the comptime engine, but that is a choice, not a dependency. | sema |

---

## 2. Lowering (the one owner of meaning)

### 2.1 One lowering, in `gen_lower*`

All AST-to-IR translation lives in files named `src/gen/gen_lower*.zen`, or
in a future `src/lower/`. **No file named for a backend may lower.** The gate
treats `gen.gen_lower*` as frontend (§4.4), so a renderer cannot call back into
lowering either.

### 2.2 The lowering pipeline, inside the one phase

1. **Instance discovery.** Walk the program from `main` (and from exported
   roots for library builds) over sema's call and instantiation edges. This
   yields the monomorphic function list, in a deterministic order.
2. **Type layout.** Build the IR type table for every reachable instantiated
   type, give each aggregate a symbol name (today's `gen_name`, which moves to
   the lowering side), and store layouts parameterized by the Target data
   layout.
3. **Function lowering.** For each instance, translate the body into blocks and
   places, reading the plan tables. Matches become decision trees (§2.6).
   Drops and drop flags are inserted, and closures are inlined or converted.
4. **Runtime needs.** Record which runtime services the program uses (stdout,
   the page allocator, actors, clocks). A backend can then emit or link only
   those, and a target that lacks one refuses with a diagnostic before
   anything is published.

### 2.3 Support boundaries are declared, not discovered

Today the IR has two "surfaces" (scalar and native) and two verifier entry
points. **Replace that with one IR and a capability list per backend**: each
backend exports `supports(feature) bool` over a closed `IrFeature` enum
(`WideInt`, `Int128`, `Float`, `Vector`, `Memory`, `Aggregates`, `Actors`,
`Extern`, `Sys`, and so on). The driver checks the lowered program's feature
set against the chosen backend *before* rendering, and reports the first
unsupported construct at its source span. The verifier stays single.

### 2.4 Symbol names are lowering's job

C readability depends on stable, meaningful names (`zen_std_text_String_add`).
Today `gen_name` computes them from sema types. In the new design they are
computed once, in lowering, and stored in the IR (`Func.symbol`,
`TypeDef.symbol`). Every text backend then prints the same names: C,
JS, asm labels and LLVM symbols all agree, and a crash in any of them can be
traced to the same function.

### 2.5 Determinism

Lowering is a pure function of (source graph, Target). Instances, types and
spans are numbered in discovery order, and discovery order is deterministic.
The existing determinism and fixpoint gates keep this true for C. The
differential harness (§4.2) extends it to every backend.

### 2.6 The match cross-check becomes structural

In the `match-safety` branch, `gen_c` records each emitted tag or literal test
and sema checks that the record agrees with its pattern reading. In the IR
design, **the decision tree is built exactly once, in lowering**, and the check
runs there:

1. Lowering compiles the arms into a decision tree over IR `Switch`es.
2. For each arm, lowering derives from the tree the value set that reaches the
   arm's body: the conjunction of `Switch` edges along its paths. The same
   usefulness engine the branch already calls then checks that this set equals
   sema's reading of the pattern minus the earlier arms. A disagreement is an
   internal compiler error that names both readings, as in the branch.
3. Backends render `Switch` and never see a pattern.

The IR verifier adds the structural half that no per-backend trace can give:
**every `Payload(variant)` projection must be dominated by a `Switch` on that
place's discriminant that takes the `variant` edge**, with no intervening
assignment to the place. Reading the wrong variant's payload then becomes a
verifier failure, whichever backend was selected. The `ArmTrace` machinery in
`gen_c` is deleted once C renders matches from the IR (§6, stage C4).

---

## 3. The backend contract

### 3.1 The rule

> **A backend consumes a `VerifiedProgram` and a `Target`, and nothing else.**
> It never imports the AST (`std.ast`; source positions come from `std.source`), the lexer, the
> parser, sema (`sema.*`), lowering (`gen.gen_lower*`), or the driver and tools
> (`zen.*`, `fmt.*`, `lsp.*`), directly or through a helper.

Why the rule has to be absolute:

- **One owner per rule.** A backend that can see the AST will eventually
  re-derive something from it: a type, an overload, a pattern's meaning. Two
  derivations then drift. The match-safety bug (sema read `Err(Authentication)`
  as a case, while C tested only the `Err` tag) was exactly this drift, between
  sema and one backend. With N backends it becomes N drifts.
- **Backends become cheap.** A renderer that consumes only the IR is a few
  thousand lines with no knowledge of the language. That is what makes Rust,
  NASM, FASM, LLVM and a JIT *later text emitters* rather than second compilers.
- **The IR stays honest.** If a backend needs a fact, the fact goes into the
  IR, where the verifier checks it and every other backend gets it too.
- **Testing composes.** Lowering is tested once, against the IR printer and the
  verifier. Each backend is tested on IR, by the differential harness (§4.2).

`VerifiedProgram` is a type that only `gen_verify` can construct: it wraps a
`Program` and has no exported constructor. Renderers take `VerifiedProgram`,
so "verify before rendering" becomes a type rule instead of the
documented-precondition comment it is today (`BACKENDS.md`: "Direct renderer
callers must satisfy that precondition").

The `Target` comes from native-pkgs and holds `arch`, `os`, `abi`, the object
format, the data layout (pointer width, endianness, alignment rules), the
feature set, and the **sys flavor** (§3.4): `Raw`, `LibSystem`, `Win32`,
`Libc`, `JsNode` or `JsBrowser`.

**Enforcement:** `make archcheck` (§4.4), which is part of `make verify`.

### 3.2 The interface

```text
Backend = {
    supports* = (self, feature: IrFeature) bool
    emit*     = (self :: @Self, program: VerifiedProgram, target: Target,
                 publish: (artifact: Artifact) Res<usize, AllocError>)
                Res<usize, AllocError>
}
```

This is the existing `Generation`/`publish` shape: artifacts are borrowed and
published synchronously, and output storage is chosen by the caller. It is
generalized from the current `ScalarBackend` enum and the `gen_asm.Target`
bound. Registration stays static, through a `Codegen` case plus a recipe, with
no plugin loader, per `BACKENDS.md`.

### 3.3 What each backend owns

**C (primary, and the bootstrap path)**
- Readable C99/C11. Named structs from the type table, `static inline` for
  small functions, locals named after source bindings, `#line` directives,
  and one function per IR function.
- Headers and the split layout: `emit_header` and `emit_unit` over IR modules
  (functions keep their origin module), the symbol map, and deterministic
  output (the fixpoint gate).
- C UB avoidance: `__builtin_*_overflow`, guarded shifts, `unsigned __int128`,
  vector extensions, and `__attribute__((target))` for feature regions.
- The C runtime prelude (today's `gen_c_runtime` and friends) becomes an
  implementation of `std.sys` plus the actor runtime, chosen by sys flavor
  (§3.4).
- `c.bind` headers (`#include`) for `Extern`s from native libraries.

**JS and TS**
- **Integers.** `i8`–`i32` and `u8`–`u32` are JS numbers with explicit checks
  (`(a+b)|0` compared against the exact sum, or a range test), and `>>>0` for
  u32. `i64`, `u64`, `u128` and `usize`-when-64-bit are `BigInt`s, wrapped with
  `BigInt.asUintN` / `asIntN` (see §8 Q2). Checked operations test the range
  and trap with the IR span.
- **Memory model.** Everything addressable lives in **one linear heap**, an
  `ArrayBuffer` with typed-array and `DataView` views, which gives `Ptr`,
  arenas, `Load`/`Store`, aggregates by layout offset, and `str` as
  (offset, length). Non-address-taken scalar locals stay JS `let`s. This is
  the only model that keeps `Ptr` semantics and allocator laws (see §8 Q1).
  The page allocator grows the buffer.
- **Actors.** In a single thread, each actor is a FIFO queue drained by the
  event loop, one message per task, with the same admission limits as native.
  Stop and join resolve promises. Workers with a `SharedArrayBuffer` heap are
  a later upgrade that needs no IR change.
- **Host sys.** Node uses `fs.writeSync`, `process.exit` and `crypto`. The
  browser gets a restricted sys: stdout goes to a callback, and file and
  process operations are refused at the support check.
- TS is the same emitter with type annotations (`number` / `bigint`) and
  branded pointer types.
- Structured control flow: blocks are emitted through a Relooper/Stackifier
  algorithm into `while`/`if`/labeled `break`, falling back to the current
  block-dispatch loop only for irreducible CFGs.

**Assembly (x86-64 and AArch64; the other agent's branch)**
- Instruction selection, **register allocation** (linear scan over slot
  liveness replaces the current stack home plus `%eax` cache), frame layout,
  and the calling conventions (System V, AAPCS64, and later Microsoft x64).
- The object/link story (`as` + `ld`, static ELF, Mach-O against libSystem),
  CFI and DWARF from the span table.
- The per-target runtime in assembly: buffered stdout, number formatting,
  traps, `_start`/`_main`, and `std.sys` over raw syscalls or libSystem, as in
  `NATIVE_BACKEND.md`.
- Vector lowering to SSE/AVX2/NEON, and `mulq`/`umulh` for `MulWide`.

**Later text emitters** (Rust, NASM, FASM, LLVM IR text). Each is an IR
renderer with no semantic work:
- **LLVM:** slots become `alloca`s, checked operations become
  `llvm.*.with.overflow` plus a trap block, and debug info comes from spans.
  This is `zen-llvm`, and it could live in its own repository and consume a
  serialized IR (§8 Q6).
- **NASM/FASM:** alternative x86 syntaxes that share the x86 instruction
  selector and register allocator. They are a syntax layer over the x86
  backend, not new backends.
- **Rust:** `unsafe` Rust over a byte heap, useful as a portable oracle and for
  embedding. It has the lowest priority.

**JIT**
- **Tier 0:** an IR interpreter (§8 Q5). It is also the differential oracle,
  and potentially the comptime engine.
- **Tier 1:** an in-memory encoder that reuses the asm backend's instruction
  selection and register allocation, and writes machine code bytes instead of
  text into `mmap`ed pages (W^X, with `MAP_JIT` plus
  `pthread_jit_write_protect_np` on Darwin arm64).
- **Alternative:** LLVM ORC via zen-llvm. The IR contract is the same, so the
  choice can wait.

### 3.4 Runtime layering: std on `std.sys`, sys per target, libc optional

```text
 user code
    │
 std (io, fs, net, mem pages, time, entropy, proc, actor)   ← Zen, target-independent
    │
 std.sys   ← Zen: one Sys enumeration of kernel-level operations, -errno results
    │
 ┌──────────────┬───────────────┬──────────────┬──────────────┬───────────────┐
 Raw (Linux)     LibSystem       Win32 (later)   Libc          JsNode / JsBrowser
 syscall/svc #0  _write, _mmap   kernel32/ntdll  write(), mmap  fs.writeSync …
 own _start,     dyld calls      own entry       crt0, any OS   host functions
 static ELF      _main                           with a libc
```

- **`std.sys`** is the `gen_sys` idea from the asm branch, promoted into std: a
  closed `Sys` enumeration (`read`, `write`, `openat`, `close`, `mmap`,
  `munmap`, `exit_group`, `clock_gettime`, `getrandom`, the socket family,
  `epoll`/`kqueue`, `futex`, `clone`, and so on), with Linux-convention results
  (negative means `-errno`) on every OS. std above it has no `#ifdef`, only
  `std.target.os.match` where semantics really differ (kqueue versus epoll
  readiness).
- **Raw** is the default for Linux asm, and available to C through
  per-architecture inline-asm syscall stubs plus `-nostdlib -static` and an
  emitted `_start`. **LibSystem** is the only supported Darwin interface, since
  Darwin has no stable syscall ABI (the Go 1.11 precedent, as `NATIVE_BACKEND.md`
  records). **Win32** comes later and defines its own imports; it does not
  reuse Linux numbers.
- **Libc is a sys flavor, not a requirement.** It is the portability fallback
  and the default when a program links native C libraries (`b.native`), since
  those assume a C runtime (see §8 Q4 for the C backend's default).
- Threads and actors sit on `std.sys`: `clone` plus `futex` on raw Linux,
  pthreads through libSystem or libc, and the event loop on JS.
- The **runtime needs** recorded by lowering (§2.2 step 4) decide what gets
  emitted, so a `println`-only program on raw Linux is a few hundred bytes of
  runtime.

---

## 4. Verification

### 4.1 The IR verifier (one, shared)

The verifier runs after lowering and after every IR-to-IR pass, and returns
the `VerifiedProgram` token. Its rules, beyond what `gen_verify` checks today
(references, types, branch targets, definite assignment):

1. **Types.** Every operand type matches its use, projections are valid for
   the base type, `Convert` modes are legal (for example, `Truncate` only
   narrows), and a `Switch` value set is well typed.
2. **Definite assignment and move state.** No read of an unassigned local. No
   `Copy`/`Move` of a place that was moved on some path and not reassigned. A
   `Drop` of a possibly moved place requires its drop flag.
3. **Payload guard (§2.6).** Every `Payload(v)` is dominated by a
   discriminant `Switch` edge for `v` on the same place, with no intervening
   write. *Implemented* over today's IR: the lowering records its tag tests
   and payload reads in `Func.guards`, and `gen_verify` checks each test's
   shape and each read's dominating fact.
4. **Bounds guard.** Every `Index` and every vector `Lane`/`WithLane` is
   dominated by its bounds check, or indexes with a constant below a
   statically known length.
5. **Features.** Callee features ⊆ caller features, or the call is dominated
   by the matching `CpuHas`.
6. **Spans.** Every `Trap`, checked operation and `Call` has a valid `SpanId`,
   so no trap prints `?:0:0`.
7. **Terminators.** Every block ends in exactly one terminator, and a function
   returning `Never` has no `Return`.
8. **Determinism** is checked by the gates, not the verifier: the same
   program must print the same IR text twice.

A verification failure is an internal compiler error with the IR printed
around the failing statement. **`zen build --emit ir`** prints the IR text,
and golden tests over it pin lowering independently of every backend.

### 4.2 Differential testing: every corpus program, every backend

A matrix runner (written in Zen, per the no-Python rule; it can start as a
`tests/gates`-style program driven from `make`) takes each executable corpus
program and each registered backend (and target, where emulation exists):

- If the backend's support check refuses the program, the result is recorded
  as **unsupported**, with the first `IrFeature`. That is not a failure.
- Otherwise it builds, runs, and compares **exit status, stdout, stderr (the
  trap report)**, and the `.expected` files.
- **Any disagreement between two backends that both claim support fails the
  build**, even when both disagree with nothing in `.expected`.
- The per-backend *supported count* is a ratchet, like the gen_c allowlist:
  it may only rise, and `make verify` fails when it drops.

The oracles, in order of trust: `.expected` files, then AST-`gen_c` (until C4),
then IR-C, then the IR interpreter once it exists. The fuzzer in
`tests/differential` should generate IR-level programs as well as source
programs, so that renderers are stress-tested below the language surface.

### 4.3 Where each class of bug is caught

| Bug class | Caught by |
|---|---|
| sema and lowering disagree on a pattern | lowering cross-check (§2.6) |
| lowering emits an ill-typed or unguarded payload/index access | IR verifier |
| a backend renders a valid IR construct wrongly | differential matrix |
| a backend re-derives language meaning | `make archcheck` (it cannot see the AST) |
| nondeterministic output | determinism and fixpoint gates, IR print twice |

### 4.4 The architecture gate (landed on this branch)

`make archcheck` compiles `tests/gates/arch_boundary.zen`, a Zen program that
reads every `src/gen/**/*.zen` through the real `std.parse` and checks the §3.1
rule:

- **Roles come from paths.** Backends are the top-level `gen_js*`, `gen_ts*`,
  `gen_asm*`, `gen_c_ir*`, `gen_sys*`, `gen_rust*`, `gen_nasm*`, `gen_fasm*`,
  `gen_llvm*`, `gen_jit*` and `gen_wasm*` files, the IR itself
  (`gen_ir*`, `gen_verify*`), and **every file in any `src/gen/` subdirectory
  except `gen_c/`**. A new backend directory is checked on the day it lands.
- **Taint is transitive within `src/gen`.** A backend may not import a helper
  that reaches the frontend.
- **`gen_c` is grandfathered edge by edge** in
  `tests/gates/arch_boundary.allow`: 306 `(file, module)` edges at 890acb1c,
  304 once gen_c read the copy and mailbox-transfer facts from the Checker's
  published queries instead of importing `sema.sema_copy`.
  That list is a **ratchet**. It may not name anything outside `gen_c/`, a line
  whose import has gone fails as stale, and its length must equal
  `ARCH_GEN_C_CEILING` in the Makefile. It can therefore shrink, and cannot
  grow without a visible edit to a number commented "DO NOT RAISE".
- **Tests.** There are 12 fixture cases in `tests/gates/arch_fixtures/`
  (`run.sh`), covering a clean tree, direct imports, `Span` imported from
  `std.ast` (a violation since positions moved to `std.source`),
  new backend directories, two-hop transitive taint, and each ratchet failure
  (new edge, stale edge, out-of-scope entry, ceiling too high or too low), plus
  exit 2 for unparseable input and for a set with no backends. The fixtures run
  before the real tree, so a gate that stopped detecting would fail the build.

When `native-asm-backend` merges, the gate reports its four lowering files
(`gen_asm_lower`, `gen_asm_call`, `gen_asm_member`, `gen_asm_shape`) and
nothing else: the x86-64 and AArch64 renderers already pass. That is stage 0
below.

---

## 5. Why not the alternatives

- **Keep gen_c AST-driven and make the others IR-driven.** That is today's
  state, and it means two implementations of the language, with C as the
  "real" one. Every IR feature is then built twice, and the scalar backends
  never catch up (0 of 961 corpus programs lowered through the IR at the asm
  branch's survey).
- **Emit C, then compile C to everything.** This is simple, but JS through
  Emscripten loses readability, a JIT would need a C compiler at runtime, and
  "no libc" is fought at every step.
- **LLVM as the IR.** It is a large C++ dependency in a self-hosted compiler
  whose bootstrap is `cc seed/zen.c`, it offers no JS path, and it carries
  Zen's traps poorly. zen-llvm is valuable *as a backend*.
- **SSA IR.** See §1.2. The right choice for an optimizer-centric compiler
  whose one backend is machine code. Zen's primary outputs are readable text.

---

## 6. Migration: AST-driven gen_c to IR-driven gen_c, with no regressions

**Strangler pattern, per function, gated by the corpus.** During migration,
one C translation unit mixes functions rendered from the IR with functions
rendered by the AST path. This works because the IR carries the *same* symbol
names and type names (§2.4), and C struct definitions come from one place: the
AST path's, until stage C3 moves them. For each reachable function instance,
the driver tries IR lowering. If every construct in the body is supported by
the lowering, IR-C renders it; otherwise the AST path does. A per-construct
fallback counter (`zen build --emit-stats`) reports why each function fell
back. Each stage raises IR coverage, and **deletes** AST-path code only when its
fallback count reaches zero over the corpus *and* the compiler's own build
(fixpoint).

Gates for every stage: `make verify` green (corpus, fixpoint, determinism,
seed), `archcheck` (allowlist non-increasing), differential matrix
(supported counts non-decreasing), and the fallback counter for the stage's
family at zero before AST code is deleted.

Stages are sized for one agent run each (roughly a 1–2k-line diff, one feature
family). Letters mark the lanes: **L** is lowering, **I** is IR core, **C**, **J**
and **A** are the backends.

| # | Stage | Lane | Depends on | Parallel with |
|---|---|---|---|---|
| 0a | This branch: architecture gate, this doc | I | — | all |
| 0b | Rename the asm branch's `gen_asm_lower/_call/_member/_shape` to `gen_lower_*`, and merge them with `gen_lower` into one lowering. Collapse `verify`/`verify_native` into one verifier plus backend `supports()` (§2.3). **Done** on `shared-lowering`: `gen_lower` is the entry point, `gen_ir_feature` holds `IrFeature` and the refusal check. | L | asm branch merged | C1 |
| 1 | IR core: type table (named aggregates plus layout per Target, `Int(128)`, `Vector`), places and projections, `SpanId` table, `VerifiedProgram` token, **IR text printer and `--emit ir`**, verifier rules 1, 2, 6, 7. Split `gen_ir` into per-family files (`gen_ir_type`, `gen_ir_mem`, `gen_ir_ctl`, …) so later families do not collide. | I | 0b | C1 |
| C1 | Per-function strangler in the C driver: try IR lowering, render with IR-C, fall back; plus the fallback counter. At first only scalar functions qualify. | C | 1 | J1, A1 |
| 2 | Scalars at every width: wrapping, bit operations, `u128`, `MulWide`, `Truncate`/`Extend`/`Checked` conversions, floats. | L+I | 1 | — |
| 2C/2J/2A | Render family 2 in C / JS (BigInt) / asm. The differential matrix gains these rows. | C, J, A | 2 | each other |
| 3 | `str`, static bytes, formatted printing (`Display` via ordinary calls). | L | 2 | 3C/3J/3A after |
| 4 | Structs and places: construction, field read and write, by-value copy, UFCS methods, struct `==`. | L+I | 1 | 3 |
| 5 | Enums, `Res`, error-set retagging, **match decision trees plus the §2.6 cross-check**, `.try()` with cleanup edges, verifier rule 3. | L+I | 4 | — |
| C4 | C renders matches only from the IR. Delete `ArmTrace` and the per-arm emission in `gen_c` once family 5 has zero fallbacks. | C | 5 | 5J, 5A |
| 6 | Loops and non-escaping closures (the `loop`/`then`/`match` helpers inlined), fixed arrays with bounds guards (verifier rule 4). | L | 5 | 5J, 5A |
| 7 | Generics: the monomorphisation worklist from `CheckedCall` and instantiation edges, and the call-plan tables in sema (§1.1). **The largest stage. Split it into 7a (free functions) and 7b (methods and struct generics).** | L (+sema) | 4 | 6 |
| 8 | `Ptr`/memory intrinsics, `Alloc` as a vtable value, the page allocator on `Sys`. | L+I | 7 | — |
| 9 | Drop, `consume`, `@scope.defer`, drop flags, verifier move-state rule. | L+I | 8 | — |
| 10 | Escaping closures (environment via `Alloc`). | L | 9 | 11, 12 |
| 11 | SIMD vectors and target-feature regions (verifier rule 5), from simd-u128. | L+I | 2, 8 | 10, 12 |
| 12 | FFI (`Extern`, native-pkgs libraries), then `Env` capabilities, then `std.sys` flavors (Raw, LibSystem, Libc). | L | 8 | 10, 11 |
| 13 | Actors: `Runtime` ops, message layouts, per-target actor runtime (C pthread first). | L | 9, 12 | — |
| C-end | Struct definitions from the IR type table; delete the AST path; `gen_c` becomes a pure IR renderer; allowlist empty; `ARCH_GEN_C_CEILING := 0`; regenerate the seed; fixpoint. | C | all | — |

**What runs in parallel.** After stage 1, the lanes separate cleanly by file
ownership:
- **L** owns `gen_lower*` and sema's plan tables.
- **I** owns `gen_ir*` and `gen_verify*`.
- **C** owns `gen_c/`, `gen_c_ir*` and the C runtime.
- **J** owns `gen_js*`/`gen_ts*` and the JS runtime.
- **A** owns `gen_asm_<arch>*` and `std.sys` Raw/LibSystem.

For each family, **I+L land the IR definitions first, with hand-built IR
tests and the printer**. C, J and A then render that family in parallel, and
the differential matrix is the integration test between them. The JS and asm
lanes are never on the critical path of C's migration: C can reach C-end with
JS and asm at partial support, since the support check (§2.3) keeps partial
backends honest.

**What must not run in parallel.** Two lowering stages at once: they share the
lowering driver and the plan tables, so the L lane is serial. The per-family IR
file split in stage 1 is what lets the backend lanes proceed without
collisions.

**Regression safety.** A function only moves to IR-C when *every* construct
in it lowers, so partial support never changes the output of a function it
cannot fully handle. Seed regeneration happens at each integration, not per
stage (AGENTS.md). Between stages the compiler builds itself through the mixed
path, so the fixpoint gate checks IR-C on ~30k lines of real Zen from the
first function it takes over.

---

## 7. Invariants this document adds

1. Backends read a `VerifiedProgram` and a `Target` only (enforced by
   `archcheck`).
2. There is one lowering, one IR, and one verifier. There are no per-backend
   IR surfaces.
3. Every construct a backend does not support is refused before publication,
   with a source span. No backend ever falls back to another backend.
4. `std` does its io through `std.sys`. libc is one sys flavor among several.
5. The gen_c allowlist and the per-backend supported counts are ratchets.

---

## 8. Open questions for the user

Each question is a real fork. A recommendation is given, but the choice is
yours.

1. **JS memory model.** Option (a) is a linear `ArrayBuffer` heap, which keeps
   `Ptr`, arenas and allocator laws, with pointers as offsets. The JS is
   readable but WebAssembly-shaped, and interop with JS objects needs
   marshalling. Option (b) maps Zen structs to JS objects: idiomatic JS, but
   `Ptr` and custom allocators become unsupported on JS. *Recommendation: (a).
   Zen's laws are about memory, and (b) would make JS a different language.*
2. **JS 64/128-bit integers.** Option (a) is `BigInt`: simple and exact, but
   roughly 10–50× slower on hot 64-bit arithmetic. Option (b) represents them
   as pairs of u32: fast, but a lot of emitter code. *Recommendation: (a) now,
   with (b) later as an emitter-local change.* A related choice: is `usize` 32
   or 64 bits on JS?
3. **Which assembly backend is the one.** The asm branch has both x86-64
   (Linux, raw) and AArch64 (Linux raw, Darwin libSystem). *Recommendation:
   AArch64 first, since your development machine is macOS arm64 and it runs
   natively without an emulator, with x86-64 Linux kept at scalar parity in CI.*
   Separately, keep GNU `as` syntax for both, and add NASM/FASM later as x86
   syntax layers.
4. **The C backend's default sys flavor.** Option (a) is libc by default
   (portable, FFI-friendly), with raw syscalls as a `--target …-none` opt-in.
   Option (b) is raw by default on Linux. *Recommendation: (a) for C, and raw by
   default for Linux asm.* "Runs without libc" is then a Target choice, not a
   backend choice.
5. **Build an IR interpreter?** It would serve as a differential oracle, a JIT
   tier 0, and potentially the comptime/`@meta` engine, replacing sema's
   evaluator. It costs about one stage and saves writing a third evaluator
   later. *Recommendation: yes, after stage 5.*
6. **Is the IR a stable, serialized format?** A textual `.zir` with a parser
   would let zen-llvm (or a Rust emitter) live in a separate repository or
   process. Otherwise the IR stays in-process, and printed text is for tests
   only. *Recommendation: printer now, parser and stability only when zen-llvm
   starts.*
7. **Coordinating with the asm agent.** Stage 0b renames and merges that
   branch's lowering. Should that happen (a) on the asm branch before it
   merges, or (b) right after merge, on this lane? *Recommendation: (b). It
   avoids asking an in-flight agent to restructure, and the gate makes the
   merge's four violations the explicit to-do list.*
8. **Where `Span` lives.** *Decided and done:* `Pos`, `Span` and `nowhere`
   live in `std.source`, and the gate no longer has an exception for `Span`
   from `std.ast` (any `std.ast` import by a backend is a violation).
   `std.ast` still re-exports the three names for frontend code.
