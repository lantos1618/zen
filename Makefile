# Zen. See docs/PLAN.md for what each target gates.

# BASH, AND `-o pipefail`, FOR EVERY RECIPE. A pipeline's exit status is its
# LAST command's, so a failing gate on the left of a pipe can otherwise leave
# the build green.
# /bin/sh here is dash, which has no `pipefail` at all, so this cannot be a
# `set -o pipefail` line inside a recipe; it has to be the shell make invokes.
# The same trap is waiting in every terminal an agent works in -- docs/STYLE.md,
# "a pipeline reports the wrong exit status", has the incantation for that side.
SHELL       := /bin/bash
.SHELLFLAGS := -o pipefail -c

CC      ?= cc
CFLAGS  ?= -O2 -std=c99
PROFILE_CFLAGS ?= -O2 -std=c99 -g -fno-omit-frame-pointer
SYMBOL_MAP ?=
PY      ?= python3
TREE_SITTER ?= npx tree-sitter
ROOT    ?= src
ZEN_STD ?= $(CURDIR)/src

# Development lanes isolate generated C and the compiler output.
# Canonical build/verify paths remain fixed; lane variables affect dev-* only.
DEV_DIR ?= build/dev
DEV_ZEN ?= $(DEV_DIR)/zen
FILTER ?=
TEST_J ?= $(J)
TEST_ARGS ?=
TEST_RESULTS ?= build/test-results
TEST_CACHE_ARGS ?= --result-cache "$(TEST_RESULTS)"

# Worker count for tests and the split-C fixpoint gate. The Zen project
# builder currently compiles each native target as one translation unit.
J       ?= $(shell nproc 2>/dev/null || echo 4)

# Optional ccache for the seed, tests, and split-C verification. Project
# builds currently compile and link together and do not use object caching.
# `make CACHE=` turns it off.
CACHE   ?= $(shell command -v ccache 2>/dev/null)
ZCC      = $(CACHE) $(CC)

.PHONY: jscheck archcheck reviewcheck projectcheck lspcheck all check build dev-build dev-check dev-run bootstrap buildcheck runnercheck editorcheck seed test verify differential runtimecheck warnings lint parse cap dupcomments faults lextile determinism fixpoint grammar fmt asan ubsan leak profile clean clean-obj clean-reports clean-all help

# These gates share ./zen, build/, and grammar/zen.so. Keep their dependency
# graphs serial even when an operator invokes `make -j verify`.
.NOTPARALLEL: verify test fmt determinism fixpoint differential warnings ubsan

all: check

# Only this first C compilation is outside Zen. Every compiler-source build
# thereafter is the ordinary Zen project command reading the root build.zen.
BOOTSTRAP_ZEN := build/bootstrap/zen-seed

$(BOOTSTRAP_ZEN): seed/zen.c Makefile
	@mkdir -p "$(@D)"
	@set -eu; object="$@.o.$$$$"; candidate="$@.tmp.$$$$"; \
	  trap 'rm -f "$$object" "$$candidate"' EXIT; \
	  $(ZCC) $(CFLAGS) -c seed/zen.c -o "$$object"; \
	  $(CC) "$$object" -o "$$candidate"; \
	  mv -f "$$candidate" "$@"

## build: seed compiler executes build.zen and atomically publishes ./zen.
## Requires a C compiler and POSIX shell tools; Python is only used by tests.
build: export CC := $(CC)
build: export CFLAGS := $(CFLAGS)
build: export ZEN_SYMBOL_MAP := $(SYMBOL_MAP)
build dev-build profile: export ZEN_STD := $(ZEN_STD)
build: $(BOOTSTRAP_ZEN)
	@test "$(ROOT)" = src || { echo 'build.zen owns the compiler source entry; ROOT overrides are unsupported'; exit 1; }
	$(BOOTSTRAP_ZEN) build .

## check: self-hosted build and cached tests; the default development command.
## FILTER selects test IDs; TEST_ARGS='--no-result-cache' forces execution.
check: build
	$(PY) tests/run.py --zen ./zen --cc "$(CC)" --cc-cache "$(CACHE)" --jobs "$(TEST_J)" \
	  $(TEST_CACHE_ARGS) $(if $(strip $(FILTER)),--filter "$(FILTER)") $(TEST_ARGS)

## dev-build: the same build.zen graph with isolated artifacts and output.
dev-build: export CC := $(CC)
dev-build: export CFLAGS := $(CFLAGS)
dev-build: export ZEN_BUILD_DIR := $(DEV_DIR)
dev-build: export ZEN_BUILD_OUTPUT := $(DEV_ZEN)
dev-build: $(BOOTSTRAP_ZEN)
	$(BOOTSTRAP_ZEN) build .

## dev-check: build the development compiler, then run FILTER-selected tests.
## TEST_J controls test workers; TEST_ARGS forwards runner options such as timings.
dev-check: dev-build

## dev-run: run FILTER-selected tests with an existing DEV_ZEN, without rebuilding.
## An empty FILTER runs the corpus; make verify remains the complete required gate.
dev-check dev-run:
	$(PY) tests/run.py --zen "$(DEV_ZEN)" --cc "$(CC)" --cc-cache "$(CACHE)" --jobs "$(TEST_J)" \
	  $(TEST_CACHE_ARGS) $(if $(strip $(FILTER)),--filter "$(FILTER)") $(TEST_ARGS)

## buildcheck: native project builds, toolchain settings and atomic publication.
buildcheck: build
	$(PY) tests/quality/build_selfhost.py --zen ./zen
	$(PY) tests/quality/native_bindings.py --zen ./zen
	$(PY) tests/quality/native_callbacks.py --zen ./zen

## runnercheck: selection/report checks and optional real-C cache regressions.
runnercheck:
	$(PY) tests/quality/test_runner_parallel.py

## reviewcheck: regression tests for local source-review artifact tooling.
## Generated snapshots stay local; fresh checkouts need no pre-existing reports.
reviewcheck:
	$(PY) -m unittest discover -s tests/quality -p 'test_review_scripts.py'

## projectcheck: real CLI execution, selection, and failure propagation for test targets.
projectcheck: build
	$(PY) tests/quality/project_tests.py --zen ./zen

## editorcheck: compile the extension and execute its nonempty lifecycle suites.
editorcheck: editors/vscode/node_modules/.zen-dependencies
	$(PY) tests/quality/editor_check.py

editors/vscode/node_modules/.zen-dependencies: editors/vscode/package.json editors/vscode/package-lock.json
	npm ci --prefix editors/vscode --include=dev --no-audit --no-fund
	@touch $@

## bootstrap: build from the C seed through build.zen, with no existing ./zen.
bootstrap: build

## seed: regenerate from the just-built compiler, leaving Git staging to the caller.
## Depends on `build`, not `zen`: there
## is no `zen` rule — `build` is what produces ./zen, and a name with
## no rule fails after `make clean` and goes stale while it exists.
seed: build
	./zen build $(ROOT) --emit-c -o seed/zen.c

## test: the corpus, must-fail and example suites, against the built ./zen.
##
## It depends on `build` because there is no second implementation any more:
## the Python bootstrapper was deleted once `--toolchain zen` carried the whole
## corpus (528/528), and with it went `refmap`, whose only job was to keep
## docs/GENC_REFERENCE_MAP.md pointing into bootstrap/gen_c.py.
##
test: build lint parse cap dupcomments faults lextile
	$(PY) tests/run.py --zen ./zen --cc "$(CC)" --cc-cache "$(CACHE)" --jobs "$(TEST_J)" $(TEST_CACHE_ARGS)

## jscheck: every corpus program through --backend js under Node must match the
## C oracle, except the shrink-only list in tests/js/known_gaps.txt. The Zen
## runner prints a notice and passes when node is not on PATH.
jscheck: build
	./zen run tests/js -- ./zen --gaps tests/js/known_gaps.txt

## lspcheck: real-process protocol, document, and lifecycle regressions.
lspcheck: build
	$(PY) tests/quality/lsp_protocol.py --zen ./zen

## verify: the authoritative repository-green door used by CI and releases.
##
## Keep this target as the single list of required gates. Shared prerequisites
## are built once per invocation, then formatting and determinism inspect the
## same compiler that ran the test suite.
verify: override TEST_CACHE_ARGS := --result-cache "$(TEST_RESULTS)" --refresh-result-cache
verify: warnings nativecheck jscheck test archcheck fmt determinism fixpoint differential runtimecheck ownershipcheck actorcheck tracecheck poolcheck ubsan buildcheck runnercheck reviewcheck editorcheck lspcheck projectcheck

.PHONY: nativecheck
nativecheck: build
	$(PY) tests/library/native-bindings/run.py --zen ./zen
	$(PY) tests/library/native-socket/run.py --zen ./zen --ubsan
	$(PY) tests/library/readiness/run.py --zen ./zen --ubsan
	$(PY) tests/library/entropy/run.py --zen ./zen --ubsan

.PHONY: poolcheck
poolcheck: build
	$(PY) tests/quality/pool_alloc.py --zen ./zen --ubsan
	ZEN="$(CURDIR)/zen" ZEN_STD="$(CURDIR)/src" $(PY) tests/library/allocation-limits/run.py

.PHONY: ownershipcheck
ownershipcheck: build
	$(PY) tests/quality/ownership_lookup.py --zen ./zen
	$(PY) tests/quality/ownership_sanitizers.py --zen ./zen --cc "$(CC)"

## fixpoint: rebuilding the whole compiler preserves C and reproduces the seed.
fixpoint: build
	$(PY) -m unittest discover -s tests/determinism -p 'test_*.py'
	$(PY) tests/determinism/fixpoint.py --zen ./zen --source "$(ROOT)" \
	  --cc "$(CC)" --cflags="$(CFLAGS)" --cache "$(CACHE)" --jobs "$(J)"

## differential: classify maintained programs at the Zen, C, and process
## boundaries. Zen-accepted C rejection is always red; the manifest cannot
## bless it as an expected result.
differential: build
	$(PY) tests/differential/run.py --zen ./zen
	$(PY) tests/differential/randomized.py --zen ./zen --cc "$(CC)"
	$(PY) tests/differential/generic_literals.py --zen ./zen --cc "$(CC)"
	$(PY) -m unittest discover -s tests/quality -p 'test_differential_controls.py'

runtimecheck: build
	$(PY) tests/quality/comparison_operands.py --zen ./zen
	$(PY) tests/bench/runtime/run.py --zen ./zen --cc "$(CC)" \
	  --out build/source_health/runtime-check --quick --enforce-map-budget

## warnings: ratchet generated-C warnings under GCC and Clang. The gate proves
## both compilers diagnose its positive control before trusting recorded
## warning counts for the seed and a representative emitted program.
warnings: build
	tests/quality/generated_c_warnings.sh

## faults: every fault the compiler declares must have a site that raises
## it. Green here does NOT mean every diagnostic works — it means none is
## silently absent. Any that are absent are written down in the script's
## OWED ledger, so the debt can shrink and cannot quietly grow; the
## ledger currently records ComptimeBudget, and a name in it that gains a
## raise site is an error too, so it cannot drift back into fiction.
##
## A Zen gate — tests/gates/faults_reachable.zen; see `gate` above. It reads
## the variant list off `std.parse`, where the python it replaced matched a
## regex demanding a leading `|`: that missed the FIRST variant of every enum,
## so `SemaFault.UndefinedName` and `GenFault.Unsupported` were exempt from
## this check for its whole life. Proved by mutation -- delete every
## construction of `UndefinedName` and the python stays green.
faults: build
	@mkdir -p build/gates
	@$(call gate,faults_reachable)
	@$(call nonempty,faults,$(ROOT) -name '*.zen' -print0 | LC_ALL=C sort -z); \
	  build/gates/faults_reachable "$${files[@]}"

## A GATE IS A ZEN PROGRAM. `$(call gate,name)` compiles
## tests/gates/<name>.zen with ./zen and leaves the binary in build/gates/.
## The compilation root is tests/gates, whose `std` is a SYMLINK to src/std:
## a module path is COMPUTED (`<folder>/<folder>.zen`), never searched for, so
## a program importing `std.lex` needs `std` under its own root and the
## symlink is what puts it there without copying the tree.
##
## Gates are Zen programs, compiled with the compiler they check.
gate = ./zen build tests/gates --entry $(1).zen --emit-c -o build/gates/$(1).c \
	&& $(ZCC) $(CFLAGS) -c build/gates/$(1).c -o build/gates/$(1).o \
	&& $(CC) build/gates/$(1).o -o build/gates/$(1)

# THE ONE DOOR FOR "a gate over a file set must have files". Six targets
# carried hand-copies of this assertion and the copies drifted (#799): a
# find that matches nothing hands a gate zero inputs and reads exit 0,
# which is this repo's recorded shape for a check that cannot fail --
# "checked everything, clean" and "checked nothing" may not be the same
# answer. Expands to a shell fragment that fills `files` from the find(1)
# spelled verbatim by the second argument (paths, predicates, an optional
# `| LC_ALL=C sort -z`) and exits 2 naming the gate if it matched nothing.
# Semicolon-join it to the consumer ON THE SAME LINE so `files` stays in
# one shell:
##
##     @$(call nonempty,cap,$(ROOT) -name '*.zen' -print0 | LC_ALL=C sort -z); \
##       build/gates/line_cap "$${files[@]}"
define nonempty
files=(); while IFS= read -r -d '' file; do files+=("$$file"); done < <(find $(2)); test $${#files[@]} -gt 0 || { echo "$(1): found no .zen files — this gate is checking nothing" >&2; exit 2; }
endef

## cap: a structural-review prompt. Long files print notes but do not fail:
## line count finds candidates, while STYLE.md names the architectural smells
## that decide whether a split is useful. No-input and read failures stay red,
## because a review that inspected nothing is not a successful review.
##
## THE FILE LIST COMES FROM `find` AND NOT FROM THE GATE. `std.env.Fs` has no
## listing, on purpose ("no open handle, seek, listing, or permission
## surface"), so a gate over a file SET cannot compute its own inputs. Same
## shape as `fmt` and `parse` below, and the same assertion for the same
## reason: an empty list must not read as a clean report. `LC_ALL=C` because the
## report is ordered by path and a locale-dependent order is a diff nobody
## asked for.
cap: build
	@mkdir -p build/gates
	@$(call gate,line_cap)
	@$(call nonempty,cap,$(ROOT) -name '*.zen' -print0 | LC_ALL=C sort -z); \
	  build/gates/line_cap "$${files[@]}"

## archcheck: backends consume gen_ir plus a Target, never the AST or sema.
## docs/IR_ARCHITECTURE.md §3 is the rule; tests/gates/arch_boundary.zen says
## how roles follow from paths and why taint is transitive inside src/gen.
## Today's AST-driven gen_c is grandfathered edge by edge in
## tests/gates/arch_boundary.allow, a ratchet: the list must match the tree
## exactly and hold ARCH_GEN_C_CEILING edges, so it can shrink and cannot grow.
## The fixture cases run first, so a gate that stopped detecting violations
## fails here before it can pass the real tree.
##
## DO NOT RAISE THIS NUMBER. Lower it when an import migrates to gen_ir.
ARCH_GEN_C_CEILING := 306
archcheck: build
	@mkdir -p build/gates
	@$(call gate,arch_boundary)
	@tests/gates/arch_fixtures/run.sh build/gates/arch_boundary
	@$(call nonempty,archcheck,$(ROOT)/gen -name '*.zen' -print0 | LC_ALL=C sort -z); \
	  build/gates/arch_boundary $(ROOT) tests/gates/arch_boundary.allow $(ARCH_GEN_C_CEILING) "$${files[@]}"

## dupcomments: no comment block may sit immediately above a copy of itself.
## A merge or a bad paste leaves that behind and it survives review, because
## a reader who has already read the paragraph does not notice reading it
## again — gen_c_inline.zen held twelve such pairs and gen_c_settle.zen six.
## ADJACENT only: the same explanation above two sibling helpers is somebody's
## judgement about where a reader needs it, and this gate does not overrule it.
## A Zen gate — tests/gates/dup_comments.zen; see `gate` above.
dupcomments: build
	@mkdir -p build/gates
	@$(call gate,dup_comments)
	@$(call nonempty,dupcomments,$(ROOT) -name '*.zen' -print0 | LC_ALL=C sort -z); \
	  build/gates/dup_comments "$${files[@]}"

## lextile: the tokens tile the file, and every line:col in them is right.
##
## THE ONE PROPERTY NOTHING ELSE CHECKS. `make fmt` proves the formatter
## reprints a file, but the formatter reads the TEXT a span slices — so a span
## whose line:col is wrong reprints perfectly and points the editor's squiggle
## at the wrong character. Positions were unmeasured in this tree until this
## gate: 664 files, both ends of every token, against a second walk over the
## bytes that shares no line with lex_cursor.zen.
##
## It also proves the token stream RECONSTRUCTS the file: tokens in order,
## never overlapping, nothing but whitespace between two of them, and the last
## one ending at the last byte. A dropped byte has nowhere to hide.
##
## must-fail/ and tests/parse/errors are excluded for the reason `parse`
## excludes them: those files exist NOT to lex, and their faults are the
## must-fail suite's assertion, not this one's.
##
## Proved non-vacuous by mutation — stop `bump` counting the newline and the
## position check goes red on the first file with two lines in it.
## A Zen gate — tests/gates/lex_tiling.zen; see `gate` above.
lextile: build
	@mkdir -p build/gates
	@$(call gate,lex_tiling)
	@$(call nonempty,lextile,$(ROOT) example tests/corpus tests/gates -name '*.zen' -print0 | LC_ALL=C sort -z); \
	  files+=(build.zen); \
	  build/gates/lex_tiling "$${files[@]}"

## parse: every .zen the tree claims is valid must parse, and every
## tests/parse/errors fixture must fail to parse. cheap, and example/ is also
## compiled by `tests/run.py`. must-fail/ is excluded because the compiler's
## rejection -- not tree-sitter's -- is what those tests assert.
##
## THE FILE COUNT IS ASSERTED. A find that matches nothing leaves xargs
## with no work and exits 0, which is this repo's own recorded shape for
## a gate that cannot fail; one renamed directory would have retired
## this check in silence.
##
## `-l`/`--lang-name` ARE MANDATORY. The CLI otherwise resolves the
## language through ~/.cache/tree-sitter/lib/<name>.so, a cache keyed by
## language NAME and shared with every other checkout of this grammar on
## the box -- so a parse gate could execute whichever tree regenerated
## last rather than the one being gated (that divergence is exactly how
## the #770 ruling was briefly "disproven"). `-l` names THIS tree's
## zen.so and bypasses the cache; `--lang-name zen` tells the CLI which
## symbol to load from it.
parse: grammar
	@$(call nonempty,parse,$(ROOT) example tests/corpus -name '*.zen' -print0); \
	  files+=(build.zen); \
	  cd grammar && $(TREE_SITTER) parse --quiet --stat -l "$$(pwd)/zen.so" --lang-name zen "$${files[@]/#/../}"
	@$(call nonempty,parse-errors,tests/parse/errors -name '*.zen' -print0); \
	  cd grammar; \
	  set +e; report="$$($(TREE_SITTER) parse --quiet --stat -l "$$(pwd)/zen.so" --lang-name zen "$${files[@]/#/../}" 2>&1)"; rc=$$?; set -e; \
	  printf '%s\n' "$$report"; \
	  test $$rc -eq 1; \
	  grep -Fq "Total parses: $${#files[@]}; successful parses: 0; failed parses: $${#files[@]};" <<<"$$report"

## lint: every test conforms to the format in docs/TESTING.md.
##
## Pure Python over the test tree, about one second.
lint:
	$(PY) tests/lint.py

## determinism: five checks that gen_c is a pure function of input
determinism: build
	ZEN=./zen tests/determinism/check.sh

## grammar: regenerate the parser and build the shared object cst.py loads.
## --abi 14 is not optional: the CLI defaults to 15, and py-tree-sitter
## rejects anything above 14 with "Incompatible Language version".
grammar: grammar/zen.so

grammar/zen.so: grammar/grammar.js grammar/tree-sitter.json
	cd grammar && $(TREE_SITTER) generate --abi 14
	@mkdir -p build/obj
	$(ZCC) -fPIC -I grammar/src -c grammar/src/parser.c -o build/obj/grammar-parser.o
	$(CC) -shared -o grammar/zen.so build/obj/grammar-parser.o

## fmt: the whole tree must already be formatted.
##
## `find`, and not a directory argument, because `zen fmt` takes FILES.
## std.env.Fs has no listing on purpose, and unlike a build a format
## cannot compute its own file set from an entry's imports: a file
## nobody imports still has to be formatted. Same shape as `parse`
## above, for the same reason. This said `--check src example tests`,
## which named three directories at a command that has never been able
## to open one.
##
## THREE EXCLUSIONS, and each is a suite whose BYTES are the test.
## must-fail/ and tests/parse/ exist to not parse, and a formatter
## refuses a file it cannot parse. tests/corpus/lex/ carries a BOM, a
## CRLF, a missing final newline and trailing whitespace on purpose --
## formatting those files would delete the seven tests in them.
##
## `tests/gates` IS IN THE LIST because the gates are Zen programs now and
## a gate nothing formats drifts like any other file -- all three landed
## unformatted the day they were written. `find` does not follow symlinks,
## so `tests/gates/std` (the symlink `gate` compiles against) contributes
## nothing here and src/std is not counted twice.
##
## THE FILE COUNT IS ASSERTED, for the reason `parse` gives above, and
## more sharply here: this recipe used to end `xargs --no-run-if-empty`,
## which is an instruction to do nothing and succeed when the find comes
## up empty.
fmt: build
	@$(call nonempty,fmt,$(ROOT) example tests/corpus tests/gates -name '*.zen' \
	  -not -path 'tests/corpus/lex/*' -print0); \
	  files+=(build.zen); \
	  ./zen fmt --check "$${files[@]}"

## asan: the compiler under AddressSanitizer + LeakSanitizer, built as
## zen-asan (./zen is never clobbered), running one representative compile.
## The deliberate argv-rows allocation is suppressed BY NAME in
## tests/bench/lsan.supp -- widen that file and real leaks go quiet.
asan: seed/zen.c
	@mkdir -p build/obj
	$(ZCC) -std=c99 -O1 -g -fsanitize=address,leak -c seed/zen.c -o build/obj/seed-asan.o
	$(CC) -fsanitize=address,leak build/obj/seed-asan.o -o zen-asan
	tests/bench/asan.sh ./zen-asan

## ubsan: the compiler under UndefinedBehaviorSanitizer. A signed-overflow
## canary must report before a clean representative compile can pass.
ubsan: seed/zen.c
	@mkdir -p build/obj
	$(ZCC) -std=c99 -O1 -g -fno-omit-frame-pointer -fsanitize=undefined -fno-sanitize-recover=undefined -c seed/zen.c -o build/obj/seed-ubsan.o
	$(CC) -fsanitize=undefined -fno-sanitize-recover=undefined build/obj/seed-ubsan.o -o zen-ubsan
	tests/bench/ubsan.sh ./zen-ubsan

## leak: valgrind's answer to the same question. definite leaks only --
## still-reachable memory is where the deliberate argv rows land, and
## reporting them would fail every run on a known-non-bug.
leak: profile
	tests/bench/leak.sh ./zen-fp

## profile: build.zen produces an isolated compiler with native debug frames.
profile: export CC := $(CC)
profile: export CFLAGS := $(PROFILE_CFLAGS)
profile: export ZEN_BUILD_OUTPUT := zen-fp
profile: export ZEN_BUILD_DIR := build/profile
profile: export ZEN_SYMBOL_MAP := build/zen.symbols.tsv
profile: $(BOOTSTRAP_ZEN)
	$(BOOTSTRAP_ZEN) build .

## clean: remove all build products, generated compiler outputs, and test outputs.
clean:
	rm -f zen zen-new zen-asan zen-ubsan zen-fp grammar/zen.so
	rm -rf build/ tests/bench/out/

## clean-obj: remove compiler objects while preserving reports and review data.
clean-obj:
	rm -rf build/obj build/dev/obj build/bootstrap/obj
	rm -f grammar/zen.so

## clean-reports: remove generated test, profile, review, and source-health reports.
clean-reports:
	rm -rf build/test-results build/profiles build/review build/reviews build/source_health
	rm -rf build/*.log build/*.json build/*.tsv

## clean-all: remove the complete local build workspace and generated executables.
clean-all: clean

help:
	@grep -E '^## ' $(MAKEFILE_LIST) | sed 's/^## //'

.PHONY: actorcheck tracecheck
actorcheck: build
	$(PY) tests/quality/actor_shutdown.py --zen ./zen
	$(PY) tests/quality/actor_admission.py --zen ./zen
	$(PY) tests/quality/actor_buffers.py --zen ./zen
	$(PY) tests/quality/actor_join.py --zen ./zen
	$(PY) tests/quality/actor_spawn_drop.py --zen ./zen
	$(PY) tests/quality/page_allocation.py --zen ./zen
	$(PY) tests/quality/actor_storage.py --zen ./zen
	$(PY) tests/quality/actor_contention.py --zen ./zen

tracecheck: build
	$(PY) tests/library/trace/run.py --zen ./zen
