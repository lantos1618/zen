# Build and iteration

The compiler is an ordinary Zen project defined by the root `build.zen`.
`make build` compiles `seed/zen.c` into `build/bootstrap/zen-seed`, then runs
that compiler's `build .` command. Zen checks the project graph, emits the
compiler's C, invokes the native toolchain, and publishes `./zen`.
`make bootstrap` uses the same path. Neither command needs Python or an
installed Zen compiler. Once bootstrapped, `./zen build --release .` rebuilds itself.
Make supplies `ZEN_STD` (defaulting to the checkout's `src`) so the seed
executable can locate the standard library from its bootstrap directory.

Project builds reuse work from the target's last successful build, recorded
beside its generated file. The front end is skipped when the compiler
executable, the compilation settings, every source file read, and every module
path probe (`program.c.inputs`, listed in `program.c.paths`) are unchanged; the
probes make a newly created module that would shadow an existing one force a
recompile. The native compiler is skipped when the generated C and the complete
compiler command match the last link (`program.c.linked`). Targets that depend
on C imports always recompile, and targets with extern C sources or C imports
always relink, because their project headers are not recorded; neither are
system headers or libraries found through search paths. A requested symbol map
also forces a recompile. Delete the executable and the target's directory under
`build/.zen/` to force a full rebuild. `J` controls parallel test/fixpoint work; it does not
parallelize project C compilation. The Make seed compilation can use optional
`ccache` through `CACHE`.

`zen build`, `zen run`, and `zen test` compile native targets at `-O0` by
default. `--release`, before or after the project or target word, applies each
target's `optimize` setting (`speed` → `-O2`, `size` → `-Oz` with section
garbage collection). `CFLAGS` follows the profile flag, so the Makefile's
`CFLAGS=-O2` keeps compiler builds optimized. `make projectcheck` covers
skipped and forced recompiles and relinks, module shadowing, failed builds, and
the placement of `--release`.

Native project builds hold a workspace lock while generating and linking.
A competing build using that workspace fails explicitly. Native compiler
children retain the lock if the Zen driver is killed. Linking writes a sibling
candidate; only a successful build replaces the published executable, using
an atomic rename. An already running executable continues using its old bytes.
Use separate workspaces and outputs for concurrent builds. Do not publish to
one output from multiple workspaces.

`CC` and `CFLAGS` accept quoted command words without shell evaluation.
`ZEN_BUILD_DIR` selects the generated-artifact directory, `ZEN_BUILD_OUTPUT`
overrides the output of one selected target, and `ZEN_SYMBOL_MAP` requests a
symbol map. The root build graph owns the compiler source entry; `ROOT`
overrides are no longer supported by `make build`.

For an isolated build, run from the repository root:

```sh
make dev-build DEV_DIR=build/lanes/example CFLAGS='-O0 -std=c99'
# Or use an existing compiler directly:
ZEN_BUILD_DIR=build/lanes/direct ZEN_BUILD_OUTPUT=build/lanes/direct/zen ./zen build --release .
```

Batch related edits before rebuilding. `make` or `make check` combines a build
with cached development test results. Use `make verify` for the complete
repository checks. When regenerating the seed, run `make -j1 seed verify` in
one invocation so both targets share their build prerequisite.

`make buildcheck` runs real native project checks in temporary directories.
They cover fresh bootstrap without a Python driver, graph-selected source,
source/header changes, quoted toolchain options, failure preservation, atomic
replacement of a running executable, inherited locks, and automatic native
library detection. Python is used for this test harness only.

## Parallel work and full validation

[Parallel work](PARALLEL_WORK.md) documents `dev-build`, `dev-check`, and
`dev-run`, which give each worker a separate compiler and build directory.
[Test iteration](TEST_ITERATION.md) covers disjoint shards, timing reports,
and the source import manifest shared within a runner invocation.

The full compiler fixpoint now uses a locked, stable scratch path under
`build/fixpoint`. Outputs are generated into fresh directories and removed
afterward. Stable paths allow ordinary ccache hits without saving successful
gate results or bypassing either compiler emission or the seed comparison.
`tests/determinism/fixpoint.py --work-dir PATH` selects a separate lane.

On the same machine, three alternating runs per implementation with eight C
workers measured the complete fixpoint gate:

| Full compiler validation | Median wall time |
| --- | ---: |
| Previous random temporary paths | 18.701 s |
| Stable scratch paths, warm ccache | 12.193 s |

That is about 35% less wall time (1.53× faster). Every measured run compared all
182 C units, the shared header, and the regenerated seed. The first stable-path
run took 19.063 s before its cache was warm. These measurements use the existing
ccache and are local observations, not cold-build or CI timing guarantees.
The complete corpus with the faster runner also passed: 1,175 passed, one
stage-6 deferred, zero failed or uncollected, with eight workers in 91.27 s.
The corpus timing is a final validation observation, not a before/after claim.
