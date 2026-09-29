#!/usr/bin/env bash
# Fixture tests for tests/gates/arch_boundary.zen, run by `make archcheck`.
#
# Each directory here is one case:
#     src/       a miniature source root; every file under src/gen is an input
#     allow      the allowlist handed to the gate
#     ceiling    the CEILING argument
#     expected   the gate's exact stdout followed by a final `exit N` line
#
# A case passes only when stdout AND the exit status match, so a gate that
# goes red for the wrong reason (or green with the right words) still fails.
# `run.sh --update GATE` rewrites every `expected` from the current gate;
# review that diff like code, because it is the gate's specification.
set -euo pipefail

update=0
if [ "${1:-}" = "--update" ]; then update=1; shift; fi
gate="${1:?usage: run.sh [--update] BUILT_GATE}"
# Resolve before the cd below; a missing gate is a harness failure, not a case.
gate="$(cd "$(dirname "$gate")" && pwd)/$(basename "$gate")"
[ -x "$gate" ] || { echo "arch_fixtures: no gate at $gate"; exit 2; }
here="$(cd "$(dirname "$0")" && pwd)"
cd "$here/../../.."   # repository root: printed paths are repo-relative

fixtures="tests/gates/arch_fixtures"
cases=0
failed=0
for dir in "$fixtures"/*/; do
    dir="${dir%/}"
    name="${dir##*/}"
    files=()
    while IFS= read -r -d '' f; do files+=("$f"); done \
        < <(find "$dir/src/gen" -type f -print0 | LC_ALL=C sort -z)
    set +e
    out="$("$gate" "$dir/src" "$dir/allow" "$(cat "$dir/ceiling")" "${files[@]}")"
    rc=$?
    set -e
    actual="$(printf '%s\nexit %s' "$out" "$rc")"
    cases=$((cases + 1))
    if [ "$update" = 1 ]; then
        printf '%s\n' "$actual" > "$dir/expected"
    elif [ "$actual" != "$(cat "$dir/expected")" ]; then
        failed=$((failed + 1))
        echo "arch_fixtures: $name: output differs from $dir/expected"
        diff <(cat "$dir/expected") <(printf '%s\n' "$actual") || true
    fi
done

# Zero cases would read as green; it is the recorded shape of a check that
# cannot fail (Makefile, `nonempty`).
if [ "$cases" -eq 0 ]; then echo "arch_fixtures: no cases found"; exit 2; fi
if [ "$failed" -gt 0 ]; then echo "arch_fixtures: $failed of $cases case(s) failed"; exit 1; fi
echo "arch_fixtures: $cases case(s) pass"
