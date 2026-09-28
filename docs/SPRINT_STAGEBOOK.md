# Compiler integration checkpoint

This file retains the current compiler handoff and unresolved verification work.
Completed execution logs, previous checkpoints and review transcripts live in
Git history. Architecture and library contracts belong in [LIBRARIES.md](LIBRARIES.md),
[DESIGN.md](DESIGN.md) and [ARCHITECTURE.md](ARCHITECTURE.md).

## Owning lookup integration (2026-09-28)

Copying Ptr.read/copy_from operations now reject inline Drop owners, including
nested records, result payloads and arrays. Generic instances receive the same
check during lowering. Vec.take uses explicit raw-slot transfer and shifts each
remaining slot without creating another destruction obligation. Vec.get/require,
value iteration and Map lookup do not provide an owning-copy escape. Ptr.take
leaves source bytes unchanged; raw callers must retire or overwrite the slot.

LSP Documents now stores owners separately from copyable URI/text/version views.
Queries cannot register a second Document destructor. The 13 protocol/lifecycle
tests pass. Nine rejected-copy cases and five runtime cases pass; the old compiler
control still destroys one inserted owner twice. Runtime controls use UBSan.
Allocator overflow/retry, page alignment and bounded pool gates pass with their
negative controls. Ownership corpus: 133 pass, one deferred, one failing deep
constant-expression case. That case also overflows the stack with the prior
compiler at the same -O0 setting; its optimized control passes.

The application runtime self-hosts and its generated seed bootstraps successfully.
The tested compiler/seed pair is installed locally in both source trees; backups
are under build/source_health/ownership-lookup/pre-promotion. The primary opaque
source draft remains intact and is not part of this runtime-derived seed.
`make -j1 seed verify` in the isolated integration snapshot generated the seed,
then stopped because Git refuses to stage its ignored build path. A separate
`make -j1 verify` reached the warning gate and failed: 7,081 versus the 315 limit.
Actor-related corpus checks: 17 pass; HTTP/2 remains blocked at native C/link
compilation. Numeric pointer-comparison and failing bool-spill controls pass.
Later aggregate gates remain unverified. No repository-wide green or complete
memory-safety claim. Logs and snapshot are under the runtime's build/dev/ownership-*
and build/source_health/ownership-lookup directories.

## Current checkpoint: native voice libraries

Header-backed native bindings support explicitly typed nongeneric scalar/pointer
callbacks. The callback gate executes libc qsort and rejects unsupported captures
and ABI shapes. The last recorded compiler integration passed the 194-unit/seed
fixpoint. Aggregate `make -j1 seed verify` stopped at the unavailable `npx` grammar
prerequisite after seed generation and source lint; this is not aggregate-green.

`std.math` owns scalar f64 mathematics. `std.stats` owns caller-allocated bounded
rolling samples and nearest-rank summaries. Focused numerical, allocation-budget
and negative-control tests passed. The stats addition used the existing compiler;
no later compiler rebuild or seed regeneration is claimed.

`std.math.vector` adds Zen-only bulk f64 dot/squared-distance kernels using the
existing backend optimizer. Focused tests and target-specific assembly checks
live in `tests/library/vector`; this does not introduce native vector types or
change the paused compiler draft.

The native application libraries and app are separate sibling repositories.
Their setup, threading contracts and measured performance are documented there,
with shared ownership boundaries in [LIBRARIES.md](LIBRARIES.md).

## Memory and actor hardening candidate

Primary and application-runtime sources now reject allocation-size overflow,
preserve refused Vec/Arena growth, clean up consumed actors on spawn refusal,
and align native page payloads. Permanent allocator, page and spawn regression
gates include allocation failures and deliberately broken controls. Actor
contention is included in actorcheck. Focused UBSan checks pass; this does not
establish whole-language memory or race safety.

An isolated runtime snapshot rebuilt the compiler and regenerated its seed.
Aggregate verification stopped at the generated-C warning ratchet (7069 versus
315); later gates did not run. That candidate was initially unpromoted; the owning lookup integration above
records the current compiler/seed pair. The paused opaque draft remains separate.

Numeric pointer-read comparison lowering now preserves operand types; 48 numeric
cases, a failing old-compiler control, UBSan and 20 related corpus cases pass.
The candidate self-hosts to C accepted by Clang. The follow-on owning lookup integration above closes the recorded duplicate
destruction case and retains its old-compiler counter control.
ThreadSanitizer exits139 even for a trivial program on this host, so race-detector
coverage is unavailable. See ERGONOMICS_PLAN for acceptance criteria.

## Unfinished work

- Preserve the existing uncommitted opaque-type draft in `gen_c_build.zen`,
  `gen_c_layout.zen`, `gen_c_type.zen`, `ast_node.zen` and `parse_decl.zen`.
  It is paused and has not passed compiler or seed integration.
- Restore aggregate-test prerequisites and rerun `make -j1 seed verify` before
  claiming repository-wide verification.
- The historical 92-case soundness hunt still needs its original inputs and
  case-by-case classification. Parser memoization alone does not prove linear
  scaling for all incomplete nested inputs.
- Native record import, SIMD lowering and package resolution remain future
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

## Actor admission candidate

`gen_c_actor.zen` now applies overflow-safe, pre-allocation count/byte admission
using `std.actor.actor_limits`: 64 active-or-queued messages, 32 MiB including
message overhead. The queue is still emitted C; allocation/copy holds the
registry/mailbox locks. Checked reservations and a typed Zen runtime remain
future work. A source snapshot under ignored `build/dev/actor-source` excludes
the paused opaque edits; `build/dev/actor-zen` is the candidate compiler.
Admission fault tests, negative controls, actor cases excluding unavailable
libssl, voice scheduling and WAV export pass. Seed generation succeeded in
the snapshot, but seed staging failed because it is ignored. Separate verify
passed lint then stopped at missing npx. Main compiler and seed are unchanged.

## Mailbox allocation and join candidate

`build/dev/actor-memory-zen` is a separate compiler built from the prior actor
snapshot plus typed std mailbox storage and synchronized joins; paused opaque
edits remain excluded and intact. Mailbox reuse policy lives in
`std.actor.actor_storage`, backed by `std.mem.mem_pool`; compiler adapters retain
layout and pthread integration. See LIBRARIES.md for ownership and limits.

Focused evidence: admission/fault controls pass; four join cases and broken
controls pass; 10,000 actual generated actor turns require 67 native allocations
with a failing no-cache control; typed pool bounds/reuse/teardown and UBSan pass.
Rooms 2,000-update live-malloc soak stays flat; UI interaction/stress pass.
Actor/transfer corpus: 13 pass, HTTP/2 blocked at link by unavailable libssl.
ASan stalls before main, also on a minimal independent C control; its gate is
unresolved, not waived. Diagnostic artifacts live under build/source_health.
No seed promotion or aggregate-green claim. Actor records and ArenaState still
use native allocation; spawn has no caller-selected allocator policy yet.

The follow-on wake candidate `build/dev/actor-wake-zen` signals only empty-to-
nonempty mailbox transitions. Admission tests cover 63 queued messages with one
wake, repeated idle/drain cycles and failing redundant-wakeup control; join and
UI stress pass. Fifteen-trial pipeline median was 21.663ms versus 21.976ms for
the previous pooled candidate; ranges overlap, so no established speedup claim.
Reusable Pool/PoolAlloc/PoolPolicy now export through std.mem, with caller-owned
storage and explicit cache policy. The focused std-only upstream branch is
isolated at ../zen-std-pool; compiler runtime changes remain outside that PR.

## Upstream actor and observability review

The clean actor runtime and bounded std.trace buffer are published in draft
PR #4, stacked on std allocator PR #3. The worktree is ../zen-actor-runtime;
its compiler and regenerated seed exclude the paused opaque draft. Focused
admission/join/storage/contention and trace-buffer gates pass with mutation
controls and UBSan; the host ASan startup failure remains unresolved. The
aggregate reports 1341 passes, 12 failures, one deferred, with the same failure
identities as the std base (1339 passes). Later aggregate gates did not execute.
Failures include platform-specific backend/path assumptions, Clang nesting,
TLS prerequisites and macOS socket ABI incompatibilities. Main is not promoted.

Zen Code now exports correlated actor phases live, including partial batches,
and flushes the live telemetry owner on both normal and error returns. Native
smoke and headless telemetry gates pass. zen-otel exports immutable pool metrics,
stops writing after destination failure, and provides a bounded CLI inspector
with per-operation latency percentiles. No graphical/source-linked debugger,
HTTP exporter or automatic runtime-wide pool sampling is claimed.
