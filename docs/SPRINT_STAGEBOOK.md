# Compiler integration checkpoint

This file retains the current compiler handoff and unresolved verification work.
Completed execution logs, previous checkpoints and review transcripts live in
Git history. Architecture and library contracts belong in [LIBRARIES.md](LIBRARIES.md),
[DESIGN.md](DESIGN.md) and [ARCHITECTURE.md](ARCHITECTURE.md).

## Current checkpoint: generated condition warnings (2026-09-29)

Match conditions now rely on the enclosing C `if` parentheses, retaining
comparison precedence and tag-before-payload short-circuiting. The readiness
UBSan fixture and its negative control pass without warnings. The warning gate
now treats Clang parentheses-equality as an error, proves rejection with a C
control, and executes enum/scalar/payload/string pattern regression cases.
It detects Apple's gcc-as-Clang alias rather than applying the GCC budget to it.
The expanded emitted fixture reduces Clang's warning baseline from seven to six.

The seed is regenerated. Local `make -j1 seed verify` stops at 321 Clang seed
warnings versus the Linux baseline of 320. The original seed also emits exactly
321 warnings on this SDK with the same enabled warning classes; no warning was
added and no budget raised. This includes the macOS 26 deprecation of the
existing posix_spawn_file_actions_addchdir_np binding. Full Linux verification
remains the merge gate.

## Current checkpoint: OS entropy (2026-09-29)

`std.entropy.fill_random` adds caller-buffer OS cryptographic randomness for
macOS/Linux via header-backed `getentropy`. Zen owns bounded 256-byte chunking
and error propagation; there is no allocation, package dependency, PRNG state,
or fallback to `std.core.rand`. On OS failure callers must discard the whole
output because earlier chunks may already have been written.

The real-OS corpus and deterministic UBSan OS-failure fixture pass on macOS.
The latter checks empty/null spans, exact chunk boundaries, first/later-call
failure and a deliberately false-success control. Seed regeneration produces
no seed changes. `make -j1 seed verify` stops at the known macOS compiler-name
warning issue (Apple Clang as gcc: 7,094 warnings against GCC budget 315), with
no budget changes. Full Linux CI remains the merge gate.

## Current checkpoint: canonical unit-return spelling (2026-09-28)

Named functions and methods with bodies now use `name = (...) { ... }` rather
than an explicit unit return. Compiler/std source, examples, test harnesses,
documentation and generated snippets were migrated. Legacy parser coverage
uses quoted source and checks the explicit Unit AST; unit types in bodiless
signatures and anonymous callback constraints remain unchanged.

The formatter normalizes only AST Function nodes with a body and literal Unit
return delimiters. A dedicated token guard permits only those deletions;
comments, strings and every other token remain checked. Lambda return types
are preserved because they can affect generic callback inference.

All 1,351 formatter-gate files pass. The final 25 focused cases pass, including
16 formatter tests; the separate migration checks passed 76 cases and 42
quality tests (five existing skips). Compiler fixpoint confirms all 195 C units,
zen.h and the regenerated seed match. `make -j1 seed verify` stops at the known
macOS compiler-name/warning-budget issue (Apple Clang as gcc: 7,095 warnings
against the GCC budget of 315). No budget was relaxed; aggregate success for
this change is not claimed. Logs are in ignored build/source_health/omit-unit-return.

## Current checkpoint: native TLS integer and byte floor (2026-09-28)

The isolated `native-tls-bits` branch extends validated std.core.num primitives
with u32 XOR/AND/rotate-right/logical-right-shift and u64 AND/logical-right-shift.
Logical shifts at or beyond the width return zero; rotations reduce modulo
width. Operands are held once in source order. `std.bytes` adds borrowed bounded
reader/writer cursors with 1–8-byte endian operations and transactional failure.
The native zen-crypto TLS client consumes these generic std helpers.

Seven integer-bit corpus/contract cases and the byte cursor corpus pass.
UBSan and deliberate wrong-XOR, wrong-AND, wrong-shift, swapped-endian and
removed-overflow-check controls pass their expected failure checks. Compiler
fixpoint passes: all 194 generated C units, zen.h and the regenerated seed match.
`make -j1 seed verify` again stops at the pre-existing Mac warning gate (Apple
Clang invoked as gcc: 7,081 warnings versus the GCC budget of 315). The gate
was not relaxed. A fresh full corpus run and Linux CI remain separate checks;
this checkpoint does not claim the aggregate verify target passed.

## Current checkpoint: native u64 bit operations (2026-09-28)

The isolated crypto-numeric branch adds identity-validated `std.core.num`
`u64.bit_xor` and `u64.rotate_right` primitives on the public main base.
The C backend evaluates operands once in order and masks both rotation shifts.
Seven focused tests pass, including signature refusal, high bits, zero and
wrapped counts, free/receiver calls, operand order and short-circuit guards.
The executable bit-vector fixture passes UBSan; deliberate XOR-to-OR and
rotate-right-to-left generated-C mutations fail its output oracle. Five existing
numeric conversion tests pass. Fresh fixpoint validation confirms all 194 C
units, `zen.h`, and the regenerated checked-in seed are byte-identical.

`make -j1 seed verify` was attempted but stops at the warning gate on this Mac:
`gcc` is Apple Clang, which the main branch's gate treats as GCC. The exact
command reports 7,067 warnings for pristine main and 7,081 for this change,
against the GCC budget of 315. With Clang's intended diagnostic flags, both
pristine main and this change report the same 321 warnings (the recorded Clang
budget is 320), with no added diagnostic after stripping source line numbers.
The warning budgets and gate were not changed. Later aggregate gates are not
claimed passed. Logs and generated fault controls remain in ignored build paths.

## Current checkpoint: portable native sockets

Header-backed bindings now support typed integer constants, optional macro
fallbacks and `c.record` with header-owned layout and scalar type assertions.
`std.net` uses native constants and `addrinfo`, signed I/O counts, close-on-exec
and SIGPIPE protection. Connection and cleanup logic remain Zen. See DESIGN.md
and the native-binding/native-socket library fixtures for contracts and limits.

The macOS integration on this branch regenerated the seed and passed the
194-unit/seed fixpoint. Native checks passed: 13 binding contracts, 13 existing
binding tests and IPv4/IPv6 socket/allocator-failure checks under UBSan. Grammar
accepted 1,373 valid files and rejected all 24 invalid fixtures. The final
`make -j1 seed verify` corpus result was 1,344 passed, 10 failed, 1 deferred.
It stopped at the corpus, so later aggregate gates are not claimed complete.
The Linux socket run passed 1,354 corpus cases with one deferred case, native
networking and actor/allocator checks. Merge preparation then removed unused
arithmetic helpers, fixed warning regressions and made scalar ABI assertions
C99-compatible. Final compiler fixpoint and focused runtime checks pass locally.
CI now installs the pinned review-tool dependency from tests/requirements.txt;
full verification of the prepared PRs #3–#5 is pending.

`std.math` owns scalar f64 mathematics. `std.stats` owns caller-allocated bounded
rolling samples and nearest-rank summaries. Focused numerical, allocation-budget
and negative-control tests passed. The stats addition used the existing compiler;
no later compiler rebuild or seed regeneration is claimed.

The native application libraries and app are separate sibling repositories.
Their setup, threading contracts and measured performance are documented there,
with shared ownership boundaries in [LIBRARIES.md](LIBRARIES.md).

`std.net.readiness` now provides caller-allocated, level-triggered kqueue/epoll
readiness with explicit EINTR and native-error results. Focused UBSan checks
and the negative slot control pass on macOS and Linux. Full aggregate
verification remains pending. Actor mailbox scheduling is unchanged. See
[READINESS.md](READINESS.md) for ownership and platform semantics.

## Unfinished work

- Preserve the paused opaque-type draft in the separate primary checkout.
  It was not included in this native-socket branch. Also preserve the unrelated
  local `grammar/src/tree_sitter/array.h` drift; it is not part of this change.
- Resolve the remaining macOS corpus failures: Linux-specific backend/path
  expectations, `/proc` fixture, Clang nesting limits and TLS linking. Check
  Linux CI before claiming portability verified on both operating systems.
- Linux warning checks now pass at GCC315 and Clang320 for the seed, with the
  Clang budget lowered after removing 24 unused arithmetic helpers. The later
  review-tool dependency failure is fixed in the workflow; confirm the full CI
  rerun before merging. No warning class or test gate was disabled.
- The historical 92-case soundness hunt still needs its original inputs and
  case-by-case classification. Parser memoization alone does not prove linear
  scaling for all incomplete nested inputs.
- Automatic header import, SIMD lowering and package resolution remain future
  capabilities. Consult [ERGONOMICS_PLAN.md](ERGONOMICS_PLAN.md) and
  [ISSUES.md](../ISSUES.md) before choosing a compiler change.

## Integration rules

Preserve uncommitted work and assign disjoint file ownership. Use isolated
`make dev-check DEV_DIR=build/dev/<lane> FILTER=<id> TEST_ARGS=--no-result-cache`
lanes for compiler work. Correctness changes need executable regressions and
negative controls; never suppress a diagnostic or skip a gate to obtain green.

Run `make -j1 seed verify` once at compiler integration, then inspect
`git diff --check` and `git status --short`. Report incomplete checks explicitly.
Update this checkpoint with the current state, not an accumulating session log.
