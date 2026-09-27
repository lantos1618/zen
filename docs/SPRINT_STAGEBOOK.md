# Correctness sprint: resumable stagebook

This is the execution ledger for the parallel correctness sprint. It exists so a
new agent can resume from one message after interruption, a failed tool run, or
session turnover. Update it after every integration batch; do not rely on chat
history.

## Current state — resume here

**Checkpoint:** `NATIVE-VOICE-LIBRARIES`
**Status:** Header-backed native bindings now include `std.native.callback` for
explicitly typed nongeneric scalar/pointer functions. The callback gate executes
real libc qsort and rejects unsupported captures and ABI shapes. The final
compiler passes the 194-unit/seed fixpoint. `make -j1 seed verify` regenerates
the seed and passes source lint (one existing warning), then stops at the
unavailable `npx` grammar prerequisite. This is not aggregate repository-green.

Follow-up: `std.math` now owns scalar f64 cos/sin/sqrt/log10/round APIs;
sibling audio/window/app libraries import them instead of duplicating math.h
bindings. Scalar numerical/NaN/rounding and FFT tests pass; app rebuild passes.
Fresh source emission matches the existing compiler seed byte-for-byte, so this
standard-library-only addition does not require seed regeneration. Source lint:
1348 cases, zero errors, one existing warning.

Follow-up: `std.stats` now provides caller-allocated bounded rolling samples,
nearest-rank p50/p95/p99, mean and maximum. Two focused corpus regressions pass,
including allocation budgets and failing controls for nonfinite admission and
unexpected allocation. This standard-library addition uses the existing compiler;
no compiler rebuild or seed regeneration is claimed. The five pre-existing
opaque-type draft files remain uncommitted and outside this change.

Sibling projects now separate macOS capture/windowing (`zen-macos`), FFT/WAV
processing (`zen-audio`), direct native Parakeet inference (`zen-parakeet`), an
optional Whisper CLI adapter (`zen-whisper`), and application composition
(`zen-tui`). No Python inference layer or handwritten C forwarding shim is used
in the selected Parakeet path. External Apple/NVIDIA libraries remain native
runtime dependencies. Git excludes downloaded SDKs, model weights, and audio.
Focused evidence is in ignored `build/source_health/voice/` and sibling build
validation notes. `docs/LIBRARIES.md` records dependency and ownership boundaries.

Earlier proc/memory C emitters are not yet converted to the new binding API.
SIMD vector types, automatic C record import, a package resolver, custom GPU
glyph rendering, and terminal emulation remain future work.

**Previous checkpoint:** `REVIEW-INTEGRATION`
**Previous status:** Reviewed the accumulated changes on `main` at `f6662bf44`.
Executable tests use `Builder.exe_test(Exe)` consistently in the planner,
fixtures, and maintained documentation. Parser memoization now falls back to
scanning when cache allocation is incomplete. The repeated-build test holds
the previous executable open until replacement completes. Local `.worktrees/`
checkouts are ignored and preserved.

Fresh `make -j1 seed verify J=8 TEST_J=8` passed. The corpus had
1347 passed, zero failed, and one deferred. Formatting, determinism, fixpoint,
differential controls, runtime budgets, ownership sanitizers, warning ratchets,
UBSan, build publication, runner, editor, LSP, and eight project-test checks
all passed. The seed was regenerated in the same invocation.
Do not mark every sprint stage complete from this result: the historical
92-case hunt still needs its original inputs, and memoizing repeated group
starts does not prove linear scaling across all nested starts.

## Rules for every stage

1. Give each agent disjoint file ownership. Shared tests, `Makefile`,
   `ISSUES.md`, and generated `seed/zen.c` belong to the integration agent.
2. Every correctness change includes a minimized reproducer and regression in
   the same batch. A successful build is not a regression test.
3. No agent suppresses warnings, skips a test, weakens an expected diagnostic,
   or blesses a Zen-accepted/CC-rejected result.
4. Semantic decisions go in `docs/DESIGN.md`; tests must pin the decision.
5. Use `make dev-check DEV_DIR=build/dev/<agent> FILTER=<id> TEST_ARGS=--no-result-cache`
   for isolated development checks. Never share a development binary.
6. The integration agent runs `make -j1 seed verify` after related semantic
   batches. The seed is regenerated at integration, not once per helper.
7. Record every failure, even setup or environment failures. Never label a
   failure unrelated without a minimal reproduction.
8. A stage is complete only when its exit gate passes or every remaining item
   has a named owner, reproducer, and next command.

## Stage graph

Stages may run in parallel when file ownership permits. Integration happens at
every numbered checkpoint.

### S0 — Baseline and ownership map — integration only

**Purpose:** preserve the dirty tree and establish exactly what currently fails.

**Commands**

```sh
git status --short
make build
make check FILTER=project_test_tests TEST_ARGS=--no-result-cache
```

If the focused test ID is absent, use `python3 tests/run.py --list | grep project`
to select the real ID. Do not discard the uncommitted project-test work.

**Exit gate:** current changes are attributable, the compiler builds, and the
in-progress project-test lane is either green or has a written blocker.

**Handoff:** list modified paths, active agents, and the first failing command.

### S1 — Build publication and repeatable build — build agent

**Files:** `src/zen/zen_project.zen`, `tests/quality/build_selfhost.py`, the root
`build.zen`, and build-specific Makefile changes coordinated with integration.
The Python incremental driver was retired at `ZEN-SELF-BUILD`.

**Work:** verify temporary output, successful execution, and one atomic rename;
eliminate overlapping publication paths. Add a repeated-build regression and
a busy-output negative control.

**Exit gate:** focused build checks pass; at least 20 consecutive clean
incremental builds show no transient publication or module-resolution failure.

### S2 — Assignment/rebinding contract — sema agent

**Files:** assignment-related sema/codegen modules plus owned must-fail tests.

**Work:** decide whether repeated `x =` is assignment or a new binding. Pin the
decision in `docs/DESIGN.md`; reject type-changing rebinding; emit and run the
two `Noisy` values exactly as specified.

**Exit gate:** integer-to-float rebinding is rejected before codegen and both
resource-owning bindings drop. Focused sema, ownership, and C-warning checks pass.

### S3 — Call evaluation order — codegen agent

**Files:** call lowering and its corpus tests.

**Work:** preserve the documented evaluation order using temporaries or another
specification-backed lowering. Cover receiver and argument side effects.

**Exit gate:** deterministic `0,1,2` output for statement and nested-call forms;
no accepted emitted C warning.

### S4 — Binder declarations and union values — codegen agent

**Files:** match binder lowering and union widening only.

**Work:** declare every renamed binder and lower ordinary declared-union values
without invalid C initialization.

**Exit gate:** both minimized reproducers compile and run correctly; focused
corpus, must-fail, and `cc -Werror` checks pass.

### S5 — Accepted-to-C soundness sweep — differential agent

**Files:** the root causes selected from the 92-case triage; integration agent
owns the differential manifest and quality gates.

**Work:** cluster `CC_REJECTED` and `CC_WARNING` cases by semantic root cause.
Fix the semantic owner, not the final C spelling. Preserve minimized cases.

**Exit gate:** all 92 are classified; every case is fixed or mapped to an
assigned root-cause batch; no expected-result exemption exists.

### S6 — Parser and LSP quick safety — parser agent

**Files:** `parse_lookahead`, parser enter/leave/recovery modules, and parser/LSP
tests.

**Work:** make `group_end_at` linear, make depth cleanup failure-safe, exercise
module-leading `;`, `}`, and `+`, and remove sticky cross-file suppression.

**Exit gate:** malformed-input corpus and real LSP protocol tests pass; the
one-character, 1k/4k/8k incomplete-input scaling check does not show quadratic
growth.

### S7 — Verification hardening — verification agent

**Files:** test-quality scripts and Makefile changes coordinated with integration.

**Work:** nonempty collection controls, known-bad controls, zero
`CC_REJECTED`/`CC_WARNING` differential buckets, and proof that declared verify
prerequisites execute.

**Exit gate:** positive controls make their gates red; repaired controls make
them green; no control silently succeeds without running.

### S8 — CLI inspection quick wins — CLI agent

**Files:** `zen_cli`, AST display support, and CLI corpus tests. Coordinate the
JSON representation with the existing LSP diagnostic model before implementation.

**Work:** `zen --help`, `zen --version`, and deterministic `zen ast` output.
Machine-readable diagnostics follow only after the shared representation is
identified.

**Exit gate:** focused CLI tests pass, AST output is deterministic, and
diagnostics are not duplicated by a second handwritten protocol.

### S9 — Safe single-owner cleanup — refactor agents

**Files:** separately assigned modules; no stage may combine this stage with a
semantic decision.

**Work:** shared UTF-8 encoder, duplicate digit/string constants, and free-name
collision gate. Preserve fixpoint and output byte-for-byte.

**Exit gate:** focused tests and source-health non-regression pass; no new
UFCS or import-cycle debt.

### S10 — Final integration and evidence

**Commands**

```sh
make -j1 seed verify
git diff --check
git status --short
```

**Exit gate:** aggregate verification passes from a clean incremental start;
remaining failures are explicitly owned; moved issues cite the exact test and
fix. Record the commit IDs in the stage history.

## Issue routing

- Correctness/soundness: S2–S5
- Flaky build/publication: S1
- Parser/LSP responsiveness: S6
- False-green gates: S7
- CLI inspection: S8
- Refactoring requested by a soundness fix: S9, after its behavioral stage

## One-message resume template

A new agent should send only this information:

```text
Resume Zen sprint at <stage/checkpoint>.
Read AGENTS.md and docs/SPRINT_STAGEBOOK.md.
Last recorded checkpoint: <id and status>.
Completed since that checkpoint: <commits/tests/commands>.
Current dirty paths and their owner: <paths>.
First failing or next command: <exact command and short output>.
Do not reset/stash existing work. Assign disjoint ownership and update the
stagebook after the integration run.
```

## Stage history

| Checkpoint | UTC | Result | Commit/test evidence | Next |
|---|---|---|---|---|
| S0-BASELINE | 2026-09-25 | Ledger created; dirty tree observed | `main` `2bab4016d`; `git status --short` | Integration agent runs baseline commands |

| REVIEW-INTEGRATION | 2026-09-25 | Reviewed batch; fresh aggregate passed | `make -j1 seed verify J=8 TEST_J=8`; 1347 passed, 0 failed, 1 deferred | Resume unresolved stages from the current checkpoint |

| PROC-ZEN-MIGRATION | 2026-09-26 | Process runtime moved to Zen; macOS focused checks and fixpoint pass; aggregate blocked | Local uncommitted changes; `make -j1 seed verify`; 7 process / 8 project tests; 193-unit fixpoint; full corpus 1329 passed, 19 failed, 1 deferred | Resolve recorded platform/toolchain limits before claiming aggregate green |

| ZEN-SELF-BUILD | 2026-09-26 | Root build graph now builds the compiler in Zen; Python driver retired | `make -j1 seed verify` built/staged seed then stopped at missing npx; direct `./zen build .`; 7 self-build and 8 project tests | Restore aggregate test prerequisites; see local self-build check report |

| NATIVE-BINDINGS-MACOS | 2026-09-26 | Header-backed bindings, library imports, and native SDK app integrated | 13 binding tests; app build and 30 Metal frames; aggregate blocked by missing npx; final fixpoint in local report | Migrate standard native modules; extend app rendering and async pipeline |

| NATIVE-VOICE-LIBRARIES | 2026-09-26 | Native callbacks and separate audio/model libraries integrated | 194-unit/seed fixpoint; native binding/callback gates; aggregate blocked at missing npx | Continue library ergonomics and native type import; consult voice validation report |
