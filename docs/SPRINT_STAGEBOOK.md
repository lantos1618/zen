# Compiler integration checkpoint

This file retains the current compiler handoff and unresolved verification work.
Completed execution logs, previous checkpoints and review transcripts live in
Git history. Architecture and library contracts belong in [LIBRARIES.md](LIBRARIES.md),
[DESIGN.md](DESIGN.md) and [ARCHITECTURE.md](ARCHITECTURE.md).

## Current checkpoint: HTTP package boundary (2026-09-29)

HTTP/1 and HTTP/2 implementations, std re-exports and `Net.http` have been
removed. The compiler/std have no new package dependency or facade; `Net`
remains an empty capability. Applications explicitly import the maintained
`zen-http` package. Seven HTTP-specific corpus fixtures are preserved there:
five existing H2 copies were equivalent after import normalization, and the
HTTP/1 response/Sink and H2 actor receiver fixtures were moved with their
expected outputs unchanged. Generic network primitives remain in std.

The seed is regenerated and the 195-unit/header/seed fixpoint passes. The full
zen-http macOS suite passes against the reduced std; all seven moved cases
retain their outputs. Package coverage is published at zen-http `d7f94b2`.
Local aggregate verification stops at the same pre-existing macOS SDK warning
count (321 versus the Linux budget 320), with no budget increase. Full Linux
CI remains the merge gate. The warning fix in PR #11 is the prerequisite.
See LIBRARIES.md for caller migration.

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

Follow-up: the iOS SDK has no `sys/random.h`, so the source is now
`arc4random_buf` from `stdlib.h` (Apple SDKs, glibc 2.36+). It has no error
result, so chunking and the OS-refusal fixture were removed; `Unavailable` is
kept but no longer produced. See docs/LIBRARIES.md.

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

## Streaming file extraction (2026-09-28)

Rooms upload/download file operations now use `std.fs.posix`: explicit native
descriptors, caller-allocated paths, complete reads/writes with EINTR retry,
cursor-preserving size queries, and exclusive temporary files. Rooms retains
protocol, progress and attachment policy. No compiler lowering or seed change
is needed. This native API does not promise checked pointer capacity or unique
descriptor ownership; its lifecycle contract is documented in LIBRARIES.md.

All eight file-I/O corpus cases pass without result caching. The new streaming
case also passes under UBSan and forces a short pipe read interrupted by a
signal; removing EINTR retry makes it fail. Rooms' isolated media suite passes
under UBSan, and macOS/iOS simulator builds pass with existing native qualifier
warnings. Logs and the failing mutation are under
`build/source_health/upload-consolidation`; app logs are under Rooms/build.
Full `make verify`, Linux execution and device runtime checks were not run for
this library extraction.

## Project dependencies follow-up (2026-09-28)

`std.build` now returns a Builder from successful exe/exe_test registrations,
with checked `.try()` chaining evaluated in order. `b.add` resolves explicit
HTTPS/file Git sources pinned to 40-character commits. Selected dependencies
share a locked project cache; origin, commit, Git objects and clean worktree are
verified before use. The former version/hash Package declaration was only a
stub. See BUILD_PACKAGES.md for the implemented boundary and remaining gaps.

The rebuilt local compiler passes 18 project/package tests, seven project build
and bootstrap checks, and 13 native-binding checks. The previous compiler fails
the two new positive chaining/package cases as expected. Rooms macOS, iOS
simulator and server builds pass with pinned sources; the Rooms model test passes.
Existing native-pointer qualifier warnings remain in the application builds.
The matching std.build declarations were copied to std-readiness for the Rooms
server's existing std selection; its older compiler driver is not updated.
Logs are in ignored build/source_health/packages. The previous local binary is
build/packages-compiler/zen-before-packages. No aggregate make verify, Linux run
or seed regeneration was performed for this follow-up.

## Native callback follow-up (2026-09-28)

An omitted return annotation on a named native callback now reaches the existing
unit ABI check instead of being rejected for missing syntax. The new libc atexit
regression fails with the prior compiler and passes with the rebuilt compiler;
all five native-callback checks and thirteen native-binding checks pass. Rooms
macOS/iOS builds also pass. The local compiler was rebuilt; its previous binary
is retained in ignored build/ui-transition-compiler/zen-before-callback-unit.
This focused repair has not rerun aggregate `make verify` or regenerated the seed.

## Current checkpoint: allocator and actor safety audit (2026-09-28)

The runtime checkout contains the integrated owning-lookup fixes plus an
iterative bounded constant folder, actor join/shutdown lifetime pins, registry
validation of retired handles, concurrent/idempotent shutdown and 16-byte
mailbox payload alignment. The original deep_binary_callback_provenance test
passes at -O0. The shutdown test forces overlap and detects deliberately removed
pin waiting and deliberately misaligned payloads. Admission, join, contention,
spawn-failure cleanup, pool allocation and page-alignment checks pass with
negative controls. Nine owning-copy refusals and five UBSan transfer cases pass.
Owning collection storage is nevertheless NOT sound: maintained failing examples
in tests/library/ownership-storage demonstrate borrowed insertion double-drop
and consumed-input loss on invalid set. Successful Vec replacement now destroys
the displaced owner; the corpus regression detects the original loss across
two replacements. Empty str.slice(0, 0) also preserves a null backing pointer
without evaluating null + 0. Its regression fails under UBSan before the fix;
both new regressions and the ownership-drop group pass under UBSan. See ISSUES.md.

Storage/slice repair validation is in build/source_health/storage-repair:
14 ownership-drop/slice cases and 124 std/string cases pass under UBSan;
the owning-lookup gate passes nine diagnostic and five runtime cases. The fresh
compiler repeats the 14 focused passes, and the 194-unit/header fixpoint plus
seed equality pass. The original replacement implementation omits both displaced
destructors in the new regression. The original empty-slice implementation
triggers UBSan's zero-offset-on-null diagnostic. Jev reassessed the changed
source and new tests, but these executable controls establish the repairs.
The ten failing corpus cases and deferred consumed-buffer case have now been
repaired. The final guarded fresh run passes 1,367 cases with zero failures and
zero deferrals, no cached results and no executable reuse. Generated-C expression nesting is bounded, platform fixtures
use explicit Darwin expectations and ELF assembly checks, and network tests
use the configured OpenSSL installation. Direct consumed byte buffers receive
private receiver-backed storage through stopped/destruction. Mailbox reservations
keep allocator callbacks outside runtime locks and protect in-flight preparation
from shutdown. Forced allocation failures, reentrant admission, stop races and
512 concurrent buffer deliveries pass under UBSan with negative controls.

Further review found that implicit union conversions could hide buffer/string
pointers from transfer descriptors, and behavior-only bounds carry hidden
receiver pointers. Destination representations are now checked; five new
rejection cases cover these paths and unspecialized generic buffer sends.
The final guarded aggregate is recorded in
build/source_health/verification-repair/verify-guarded.log. ASan startup remains
a host/toolchain blocker: even an empty C program hangs outside the sandbox;
TSan's empty control exits on signal 11. The final aggregate finishes with only
ownershipcheck and actorcheck failing at ASan startup; all other aggregate gates
pass, and actor contention after the blocked step passes separately. Sanitizer
gates remain mandatory and are not waived. See verification-repair/REPORT.md for the final gate results.

Generated C no longer adds redundant match equality parentheses; ignored
bindings are marked used, and SDK26 process spawning uses its available API.
The warning gate identifies the actual compiler family (macOS gcc is Clang).
Clang seed317/emitted7 passes without raising budgets or suppressing a new
warning class. Real GCC remains unmeasured for this change. The seed recipe no
longer stages Git files, and TREE_SITTER can select an installed CLI explicitly.
The 194-unit/header compiler fixpoint and exact seed comparison pass. All 14
maintained differential cases and 13 LSP protocol/lifecycle checks pass.

Earlier aggregate verification passed warnings, native bindings/sockets, grammar,
and source gates. Its corpus result is 1345 passed, 12 failed, one deferred;
see build/dev/reliability-verify-equipped.log. Failures include Linux/x86 backend
assumptions, absent Node/OpenSSL setup, /proc, two codegen stack overflows and
Clang expression nesting. This is not repository-wide green. Dependencies for
Python gates are installed locally in build/verification-python; the existing
CLI is grammar/node_modules/tree-sitter-cli/tree-sitter.

UBSan's hook gate falsely failed because grep -q could SIGPIPE nm under pipefail;
it now reads the complete symbol table and supports Bash3 report arrays. The
live signed-overflow canary and representative compiler run now pass after the
str.slice fix and seed regeneration. Iterative parenthesis removal, binary-spine temporaries and static scalar call
sequencing are now integrated; the original nesting and long-line cases pass.
These code-generation candidates are NOT promoted to canonical source/seed. The candidate
build must use explicit --std build/source_health/reliability-next/src; relying
on ZEN_STD accidentally used the old standard library during its UBSan run.

Local ASan startup hangs even for a standalone malloc/free control outside the
sandbox with a 60-second timeout; TSan crashes before main. The actor_storage
ASan phase also times out. Do not waive these gates. Docker is installed but
cannot launch (missing executable). A Linux source upload to configured dev-box
was automatically rejected and has NOT happened. Explicit user approval remains
pending for the named source/test payload and /tmp/zen-reliability.YTai1F.
Do not bypass that rejection or upload another private artifact indirectly.

This turn's canonical fixes are still in zen-actor-runtime only; the primary
zen tree retains the prior owning-lookup compiler/seed and its separate opaque
draft. Mirror only targeted validated changes, preserving that draft and the
unrelated grammar/src/tree_sitter/array.h drift. No commit or push was made.

Jev test-quality triage is implemented in tests/quality/jev_test_review.py with
an offline browser template and six passing transport/provenance validation
checks. The user explicitly authorized the 1,358 canonical corpus test cases,
source, expectations, fixtures and metadata to TypeSafe's official endpoint
https://api.typesafe.ai/v1/systemone. This does not authorize the separate Linux
source upload above. The pinned model is jev-1.13.0. Reports and resumable
request-hash responses live under build/source_health/jev-test-review. See
tests/quality/JEV_REVIEW.md for the rubric, commands and limitations. The first pass completed all 1,358 cases (1,269 keep, 89 strengthen), with
3,062 files and no truncated packets. The 89 flagged cases were then inspected:
13 gained executable checks or controlled inputs, 71 were retained with written
reasons, and five remain constrained by missing feature support or the local TLS
failure. Audit decisions live in build/source_health/jev-test-review/audit.json.

All 89 were reassessed with identical Jev model/questions; the final bounds
fixture received one additional assessment after its explicit environment input
was added. The 13 changed cases averaged 53.6 before and 70.3 after; unchanged
cases averaged +0.32, and two edited cases scored lower. Current whole-inventory
suggestions are 1,288 keep and 70 strengthen. Before sources/reviews remain in
before-strengthening/ and comparison.json records individual deltas. Static
scores do not establish correctness and no tests were removed.

The 13 edited fixtures pass. The wider selected regression set includes seven
substring-matched neighbors: 94 passed, one TLS timeout, one deferred; the final
bounds/environment and allocator checks also passed fresh. Local OpenSSL needs
include/library paths and a linked runtime rpath on macOS; DYLD_LIBRARY_PATH is
lost across the system Python launch. The original TLS fixture also times out
with corrected linking. Generated-C fault controls in
tests/quality/strengthened_oracles.py demonstrate five faults that survived the
original fixtures and are detected by the strengthened fixtures; all clean and
faulty C variants compile. These are lowering simulations, not exhaustive
compiler mutation coverage. Six review-tool checks and formatting/diff checks
pass. No compiler source or seed was changed in this test-strengthening pass;
the earlier aggregate verification and allocator safety blockers remain.

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
