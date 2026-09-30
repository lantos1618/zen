# Quality of the C that `gen_c` emits

Measured 2026-09-29. This compares the C that `gen_c` emits for real project
code with hand-written C for the same work (libsodium's portable C, or minimal
idiomatic C), and with what clang makes of both. It ranks the inefficiencies
by measured cost and records which ones this branch fixed.

## Method

- **Code studied.**
  - Crypto: `zen-crypto-integrated/src` (SHA-256, SHA-512 via `sha2x64`,
    BLAKE2b, HMAC, ChaCha20-Poly1305), plus X25519 from `zen-crypto-x25519`.
    Each was driven through the `zen-compare` adapter protocol (`adapters/zen/main.zen`).
  - The zen-http server hot path: `server_core` `Connection.parse`/`respond`
    and `HttpShard`.
  - The compiler compiling itself: lexer, sema `StoreScan`, and checker lookups.
- **Timing.** All timing ran on dev-box (AMD EPYC-Milan, clang 18,
  `-O3 -flto -DNDEBUG`), pinned with `taskset -c 2`. The table below gives the
  median ns/op of 3 rounds × 5 trials of about 100 ms each. The 1-minute load
  average was recorded around every batch. The Mac was used for correctness
  only.
- **Instruction counts** come from `callgrind`. `perf` is not permitted on the
  VM.
- **Attribution.** Each suspected cause was checked by a minimal hand patch
  of the emitted C: rebuild, re-verify every vector against
  `vectors/expected.txt`, then time it. That separates three kinds of cost:
  - **(a)** codegen cost: the backend could emit better C from the same Zen source;
  - **(b)** idiom cost: the Zen source is written that way because a
    language or std feature is missing;
  - **(c)** algorithmic cost.

Baseline, generated C against libsodium portable C (`--disable-asm`), in
ns/op:

| cell | Zen | libsodium portable | ratio |
|---|---:|---:|---:|
| ChaCha20-Poly1305 seal 16 KiB | 20 891 | 30 711 | 1.47× faster |
| SHA-256 16 KiB | 74 464 | 50 239 | 0.67× |
| SHA-512 16 KiB | 61 245 | 31 977 | 0.52× |
| BLAKE2b-256 16 KiB | 39 457 | 16 203 | 0.41× |
| HMAC-SHA-512-256 64 B | 2 070 | 1 070 | 0.52× |
| X25519 | 84 836 | 42 335 | 0.50× |

The same generated file with only the compress bodies replaced by libsodium's
shape beats libsodium: SHA-256 45 187 vs 50 441, SHA-512 29 470 vs 32 007.
The driver code, buffering and HMAC plumbing are not where the time goes.

## What does not cost anything

The emitted C is verbose, but clang at `-O2` removes all of the following:

- `Range` and `Res` loop temporaries;
- `(void)(0)` statements;
- `zg_idx_u` bounds checks on constant-range loops;
- index arithmetic checks such as `zg_sub_usize(i, 15)` in a loop from 16.

The inner loops of SHA-256/512, BLAKE2b and X25519 contain no trap branch on
x86-64 or arm64. Checked arithmetic survives only where the range is not
provable. Byte-to-word loops written as `w = w * 256 + b[i]` already fold to
`ldr`+`rev`/`bswap` once they are wrapping.

## Ranked inefficiencies

The rank is by measured cost on real code. "Freq" counts occurrences in the
code studied. "Owner" says whether the fix belongs in the C backend only, or
in the shared IR (`zen-ir-design/docs/IR_ARCHITECTURE.md`) so that every
backend inherits it.

| # | Pattern | Where it comes from | Freq | Measured cost | Fix | Owner |
|---|---|---|---|---|---|---|
| 1 | Byte-at-a-time word loads with checked `*`/`+` (b; the checks are a) | Source idiom, for lack of a load intrinsic. The checks come from `gen_c_op` checked helpers, and clang cannot prove `factor ≤ 256^7` | 6 sites in crypto (`blake2b.load_block`, `sha512`/`sha2x64` byte assembly) | BLAKE2b −43% (39.8 → 22.7 µs/16 KiB). The checks alone are ~7 µs | **Fixed**: `Ptr<u8>.read_le/be32/64`, `write_le/be32/64`, lowered to shift-assembly that clang folds into one load or store (`gen_c_ptr`) | IR: `Load(width, order)` on a place. All backends |
| 2 | Wide `:` parameters passed by value: every call memcpys the aggregate | `gen_c_decl.write_param`: every `:` parameter was a C by-value parameter | Compiler: 6 744 by-value params > 16 B, 1 734 > 256 B (`CBackend` 9.5 KB, `Checker` 5.7 KB, `StoreScan` 7.3 KB, `Ast` 768 B). http: 302 > 16 B, 110 > 64 B (`Env` 336 B, `HttpShard`, `Handle`) | Self-compile: 40.3 G → 21.9 G instructions (−46%). memcpy alone 12.3 G → 6.0 G. Wall time on EPYC unchanged (5.27 vs 5.29 s): the copies are high-IPC `rep movs` and the run is bound elsewhere (2.2 GB RSS, 548 k faults) | **Fixed**: `gen_c_borrow` — wide `:` params are `const T *`, with caller aliasing proof and copy-in on lend | IR: parameter passing mode (`ByRef` for readonly aggregates) chosen once in lowering, with the aliasing rule in the verifier |
| 3 | Index-rotated state in rolled constant-trip loops (`v[(8-i%8)%8]`) | Source shape. The backend emits `while` loops with no unroll hint | 66 constant-bound `Range` loops in crypto | SHA-512 −32% (61.2 → 41.9 µs) with `#pragma clang loop unroll(full)` | Not fixed: needs a heuristic or a language `comptime`/`unroll` form. A blanket pragma on 64–80-trip loops is too blunt for general code | IR: `Loop{trip: Const(n)}` plus a cost-based unroll pass, shared |
| 4 | Internal state in caller-provided `Ptr` scratch instead of local arrays; missing `restrict` | Source idiom, because the libsodium-surface APIs take a scratch `Ptr`. `restrict` is not provable for raw `Ptr` | 40 `ptr + const` scratch carvings, 54 functions with ≥ 2 `Ptr` params | BLAKE2b −22% after #1 (local `v[16]`). `restrict` recovers about half. X25519 0 | Not fixed. Source-level: use `[u64, 16]` locals. `restrict` only where the language can prove it (`::` exclusivity, once sema enforces it) | IR: noalias facts on params/places |
| 5 | `Sha256.update` buffers byte by byte, and `u8` stores alias `self` | Source (b), plus char-type aliasing in C | 1 | SHA-256 −16% (−3% is the aliasing part) | Source: a block fast path plus bulk `copy_from` | — |
| 6 | Dense integer `match` returning literals becomes an `if` chain (a) | `gen_c_flow.lower_match` | 5 functions in crypto (`sha256.constant`, `sha2x64.k512`, `blake2b.iv`, adapter tables), 2 in the compiler | SHA-256 −3…5% | **Fixed**: `gen_c_table` emits a `static const` table and one guarded load | IR: `Switch` → table lowering in each backend; the decision tree is shared |
| 7 | Match scrutinee and payload bindings copied (`zg_s1 = event; node = zg_s1.zg_data.Enter`) | `gen_c_flow.lower_arms` always spills the scrutinee; `PatternSite.bind` copies payloads | Every match. `WalkEvent` 512 B, `WalkNode` 504 B, `Expr` 280 B in the compiler | Part of the memcpy left after #2 (6.0 G instructions) | Not fixed. Use the place directly when it is rooted in an immutable binding (the `gen_c_borrow.stays_put` rule), and bind wide payloads by `const T *` | IR: `Payload(variant)` projections on places; no copy unless moved |
| 8 | `Res<T>` of wide `T` returned by value, then the payload copied out again | `gen_c_try`/`gen_c_call`: `zg_t = f(...); x = zg_t.zg_data.Ok` | 1 273 functions return > 16 B (701 > 64 B) in the compiler; `Vec.get` → `Res<Entry>` 280 B per lookup | Part of the remaining memcpy | Not fixed: destination-passing (`sret` into the binding) | IR: return slot / destination-passing, shared |
| 9 | 64×64→128 multiply and add-with-carry are unavailable (b/c) | Language: no `u128`/`mul_hi` | X25519 (10×25.5-bit limbs), P-256 fiat `bits64.mul64` (4-multiply emulation; clang 18 does not fuse it to one `mulq`) | X25519 −50%: libsodium's own fe25_5 runs 90 µs vs its fe51 at 42 µs. Zen's 85 µs already beats same-algorithm C | Not fixed: `u128` / `MulWide` (simd-u128 branch) | IR: `MulWide`, `Int(128)` (already in the IR plan) |
| 10 | Wipes end in an opaque libc call (`arc4random_buf(p, 0)`) as a compiler barrier | Language: no barrier intrinsic | 1 barrier, 12 memzero sites | 0 on glibc (was up to 5× at 64 B with `getentropy` on macOS) | Not fixed: a `Barrier` intrinsic lowered to `asm volatile("" ::: "memory")`, for correctness rather than speed | IR: `Barrier` statement (already in the IR plan) |
| 11 | Zero-initialising fixed arrays that are fully overwritten; divide/modulo by a non-zero literal still calling `zg_div_*`/`zg_mod_*` | `gen_c_expr` array literal; `gen_c_op` | 4 arrays; 47 `zg_div`/`zg_mod` by literal | 0 measured (clang folds them) | Readability only: emit plain `/` and `%` for a non-zero literal divisor | IR: const-fold in lowering |

Readability and C compile time: of the self-hosted seed's 225 k lines, the
visible noise is 2 416 `(void)(0);` lines, 1 216 `else if (1)` arms, 1 214
`(void)(zg_nN)` loop results, and 8 239 `zg_unreachable` fallbacks on
exhaustive `if` chains. None of it costs runtime, and C compile time is the
larger build cost (docs/PROFILE_REVIEW.md). The IR renderer should emit
`switch` for tag dispatch and plain `for` for ranges instead of carrying this
over.

## What this branch changed

### 1. Wide `:` parameters by address (`gen_c_borrow.zen`)

A `:` parameter whose estimated C size is over 16 bytes is declared
`const T *` and read as `(*p)` (`LocalSlot.borrowed`). This covers user
structs, enums, `Res`, unions and arrays. The following keep the old ABI:

- `Ptr`, `Scope`, bound (fat) values, header records, and foreign opaques;
- bodyless (foreign) functions.

The semantics are unchanged. Sema accepts some things a copy made invisible,
so each case is handled explicitly:

- **Caller.** It lends its own storage only when nothing can change that
  storage during the call:
  - the place is rooted in an immutable binding (Zen has no address-of for
    locals except a `::` argument), or
  - it is rooted in a mutable binding and the callee has no `::` parameter.
  - Otherwise, including when the argument is held for evaluation order, it
    passes the address of a copy.
- **Lends.** Sema accepts lending a `:` parameter to a `::` parameter, and the
  write used to land in the callee's copy. Such a parameter
  (`note_lend`/`own_lent`) is copied in at entry, so writes stay local and
  later reads see them. The corpus test
  `codegen/a_wide_parameter_is_lent_not_copied` pins this, and the base
  compiler gives the same output.
- **Captures.** A spawned thread copies a borrowed parameter into its heap
  record. A defer record keeps the `const` address, because it runs inside
  the frame.
- **Every other call path** now asks `passes_address`, so C's type checker
  rejects any mismatch. The paths are fat thunks, display, actor handlers and
  lifecycle hooks, `env.args` helpers, omitted `None` arguments, and `main`.

Effect on the compiler compiling itself:

- 1 734 by-value parameters over 256 B → 1.
- Callgrind instructions 40.3 G → 21.9 G, of which memcpy 12.3 G → 6.0 G.

On EPYC the wall and user time did not move: 5.27–5.38 s over 6 alternating
runs each, load ≤ 1.0. The copies were cheap on this machine; the fix removes
instructions, not measured time there. The other workloads:

- Emitting the crypto bench program went from 0.18 s to 0.15 s (5 runs each).
- Crypto cells are unchanged, since the crypto code passes `Ptr`s.

### 2. Dense literal `match` as a table (`gen_c_table.zen`)

A match qualifies when all of the following hold:

- the arms are `0, 1, …, n-1, _` with n ≥ 4;
- every body is an integer literal;
- the scrutinee and result are integers;
- a value is wanted.

It emits `static const T zg_kN[n] = {…}` and
`((uint64_t)(s) < n ? zg_kN[s] : fallback)`, and pins the negative-scrutinee
case (`codegen/a_dense_literal_match_is_a_table`).

- SHA-256 16 KiB: 74 697 → 72 373 ns (−3.1%).
- SHA-256 64 B: 573 → 569 ns.
- HMAC-SHA-256 64 B: 1 410 → 1 369 ns.

### 3. Byte-order loads and stores (`Ptr<u8>.read_le64` …)

Eight bodyless `Ptr` members were added: `read_{le,be}{32,64}` and
`write_{le,be}{32,64}`. They take a byte index and allow unaligned access.
`gen_c_ptr` lowers them to a held pointer and a shift assembly, which clang
and gcc fold into one load or store plus `bswap`/`rev` where needed:

- no alignment or strict-aliasing assumption;
- no overflow checks;
- no runtime helper.

They are pinned against independently computed values
(`codegen/byte_order_reads_and_writes_round_trip`).

Using it in `blake2b.load_block`, a three-line source change measured on a
patched copy (the crypto repo is not changed here):

- BLAKE2b-256 16 KiB: 40 072 → 22 686 ns (−43%; libsodium 16 343).
- BLAKE2b-256 64 B: 274 → 224 ns.

### Crypto before/after

dev-box CPU 2, ns/op, median of 3×5. Load 3.2 before and 5.9 after, from
other agents.

| cell | base compiler | this branch | + `read_le64` in blake2b | libsodium portable |
|---|---:|---:|---:|---:|
| ChaCha20-Poly1305 seal 16 KiB | 20 880 | 20 892 | 21 109 | 30 808 |
| SHA-256 64 B | 573 | 569 | 562 | 418 |
| SHA-256 16 KiB | 74 697 | 72 373 | 72 392 | 50 283 |
| SHA-512 16 KiB | 62 030 | 62 322 | 61 708 | 32 278 |
| BLAKE2b-256 64 B | 277 | 274 | 224 | 149 |
| BLAKE2b-256 16 KiB | 39 786 | 40 072 | 22 686 | 16 343 |
| HMAC-SHA-256 64 B | 1 410 | 1 369 | 1 375 | 1 056 |
| HMAC-SHA-512-256 64 B | 2 072 | 2 065 | 2 089 | 1 095 |
| X25519 | 84 057 | 84 649 | 84 707 | 42 450 |

## Next, in order of expected value

1. **Crypto sources.** Adopt `read_le64`/`read_be64` in `blake2b`,
   `sha512`/`sha2x64` and the HMAC paths. Keep BLAKE2b's `v` in a local
   `[u64, 16]`: the experiment reached libsodium parity (16 240 vs 16 229).
2. **Borrowed scrutinees and payloads (#7), then destination-passing returns
   (#8).** These remove most of the compiler's remaining 6 G memcpy
   instructions. Both use the `stays_put` rule from `gen_c_borrow`.
3. **`u128`/`MulWide` (#9).** X25519 and P-256 at libsodium's fe51 speed.
4. **An unroll decision for small constant-trip loops (#3).** Make it in the
   IR, where one cost model serves C, asm and JS.
