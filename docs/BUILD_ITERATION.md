# Build and iteration

The compiler is an ordinary Zen project defined by the root `build.zen`.
`make build` compiles `seed/zen.c` into `build/bootstrap/zen-seed`, then runs
that compiler's `build .` command. Zen checks the project graph, emits the
compiler's C, invokes the native toolchain, and publishes `./zen`.
`make bootstrap` uses the same path. Neither command needs Python or an
installed Zen compiler. Once bootstrapped, `./zen build --release .` rebuilds itself.
Make supplies `ZEN_STD` as the checkout's own `src`, so the seed executable
locates the standard library from its bootstrap directory and builds against
the library versioned with the compiler. A `ZEN_STD` exported by the shell does
not reach the build; `make build ZEN_STD=<dir>` selects another tree.

Project builds skip the front end and the C compiler for targets whose
recorded inputs are unchanged; DESIGN.md ("How the compiler gets built") lists
what is recorded. `zen build -v` shows which steps ran. Project builds default
to the unoptimized debug mode, and the Makefile's exported `CFLAGS=-O2` follows
the mode's flag, so `make build` still produces an optimized compiler. `J` controls
parallel test/fixpoint work; it does not parallelize project C compilation.
The Make seed compilation can use optional `ccache` through `CACHE`.

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
