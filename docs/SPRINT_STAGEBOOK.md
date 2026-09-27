# Compiler integration checkpoint

This file retains the current compiler handoff and unresolved verification work.
Completed execution logs, previous checkpoints and review transcripts live in
Git history. Architecture and library contracts belong in [LIBRARIES.md](LIBRARIES.md),
[DESIGN.md](DESIGN.md) and [ARCHITECTURE.md](ARCHITECTURE.md).

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

The native application libraries and app are separate sibling repositories.
Their setup, threading contracts and measured performance are documented there,
with shared ownership boundaries in [LIBRARIES.md](LIBRARIES.md).

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
