#!/usr/bin/env bash
set -euo pipefail

# This gate supports GCC and Clang warning classes with equivalent C99 intent.
# Explicit classes avoid compiler-specific warnings hidden inside -Wall/-Wextra.
readonly warning_flags=(
    -std=c99
    -Wpedantic
    -Wconversion
    -Wsign-conversion
    -Wsign-compare
    -Wunused-function
    -Wunused-label
    -Wunused-parameter
    -Wunused-variable
    -Wunused-but-set-variable
    -fdiagnostics-color=never
    -fsyntax-only
)
# Redundant equality parentheses are an error, independent of warning budgets.
# GCC does not implement this Clang diagnostic.
readonly clang_warning_flags=(-Werror=parentheses-equality)

readonly script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly repo_root="$(cd "$script_dir/../.." && pwd)"
readonly baseline_file="$script_dir/generated_c_warnings.baseline"
readonly fixture_dir="$script_dir/fixtures/generated_c"
readonly positive_control="$script_dir/fixtures/unused_variable.c"
readonly zen="${ZEN:-$repo_root/zen}"
readonly gcc_bin="${GCC:-gcc}"
readonly clang_bin="${CLANG:-clang}"
readonly work_dir="$(mktemp -d "${TMPDIR:-/tmp}/zen-generated-c-warnings.XXXXXX")"
trap 'rm -rf -- "$work_dir"' EXIT

fail() {
    printf 'generated-c-warnings: %s\n' "$*" >&2
    exit 1
}

for required in "$zen" "$gcc_bin" "$clang_bin"; do
    command -v "$required" >/dev/null 2>&1 || fail "required tool not found: $required"
done

# macOS ships Clang under the name gcc. Detect the implementation before using
# compiler-specific budgets; an explicit override must match its promised tool.
compiler_kind() {
    local macros
    macros="$("$1" -dM -E -x c /dev/null)" || fail "cannot identify compiler: $1"
    if grep -q '__clang__' <<<"$macros"; then printf 'clang';
    elif grep -q '__GNUC__' <<<"$macros"; then printf 'gcc';
    else fail "unsupported compiler: $1"; fi
}
[[ "$(compiler_kind "$clang_bin")" == clang ]] || fail "CLANG must name Clang"
run_gcc=true
if [[ "$(compiler_kind "$gcc_bin")" != gcc ]]; then
    [[ -z "${GCC+x}" ]] || fail "GCC override must name real GCC, not Clang"
    run_gcc=false
    printf 'generated-c-warnings: gcc is Clang; checking Clang once (set GCC for real GCC)\n'
fi

mkdir -p "$work_dir/tree"
cp -R "$fixture_dir/." "$work_dir/tree/"
cp -R "$repo_root/src/std" "$work_dir/tree/std"
"$zen" build "$work_dir/tree" --emit-c -o "$work_dir/emitted.c"

baseline_for() {
    local compiler="$1"
    local artifact="$2"
    awk -v compiler="$compiler" -v artifact="$artifact" '
        $1 == compiler && $2 == artifact { print $3; found = 1 }
        END { if (!found) exit 1 }
    ' "$baseline_file"
}

check_positive_control() {
    local compiler="$1"
    local binary="$2"
    local log="$work_dir/$compiler-positive-control.log"

    local -a compiler_flags=()
    [[ "$compiler" == clang ]] && compiler_flags=("${clang_warning_flags[@]}")

    if LC_ALL=C "$binary" "${warning_flags[@]}" ${compiler_flags[@]+"${compiler_flags[@]}"} \
        -Werror=unused-variable \
        "$positive_control" >"$log" 2>&1; then
        fail "$compiler did not reject the unused-variable positive control"
    fi
    grep -q -- 'unused-variable' "$log" || {
        sed -n '1,20p' "$log" >&2
        fail "$compiler failed the positive control without the expected diagnostic"
    }
    if [[ "$compiler" == clang ]]; then
        log="$work_dir/clang-parentheses-control.log"
        if LC_ALL=C "$binary" "${warning_flags[@]}" "${clang_warning_flags[@]}" \
            "$script_dir/fixtures/parentheses_equality.c" >"$log" 2>&1; then
            fail "clang did not reject the parentheses-equality positive control"
        fi
        grep -q -- '-Werror,-Wparentheses-equality' "$log" || {
            cat "$log" >&2
            fail "clang positive control lacked parentheses-equality error"
        }
    fi
}

check_artifact() {
    local compiler="$1"
    local artifact="$2"
    local log="$work_dir/$compiler-$artifact.log"
    local expected actual

    expected="$(baseline_for "$compiler" "$artifact")" || \
        fail "missing baseline for $compiler $artifact"
    actual="$(grep -c ': warning:' "$log" || true)"

    if [[ "$actual" -gt "$expected" ]]; then
        cat "$log" >&2
        fail "$compiler $artifact warnings increased: expected at most $expected, found $actual"
    fi
    if [[ "$actual" -lt "$expected" ]]; then
        fail "$compiler $artifact warnings fell from $expected to $actual; lower the baseline"
    fi
    printf 'generated-c-warnings: %s %s: %s warnings\n' \
        "$compiler" "$artifact" "$actual"
}

declare -a jobs=()
declare -a job_names=()
for compiler in gcc clang; do
    compiler_flags=()
    if [[ "$compiler" == gcc ]]; then
        [[ "$run_gcc" == true ]] || continue
        binary="$gcc_bin"
    else
        binary="$clang_bin"
        compiler_flags=("${clang_warning_flags[@]}")
    fi
    check_positive_control "$compiler" "$binary"
    for artifact in seed emitted; do
        if [[ "$artifact" == seed ]]; then
            input="$repo_root/seed/zen.c"
        else
            input="$work_dir/emitted.c"
        fi
        LC_ALL=C "$binary" "${warning_flags[@]}" ${compiler_flags[@]+"${compiler_flags[@]}"} "$input" \
            >"$work_dir/$compiler-$artifact.log" 2>&1 &
        jobs+=("$!")
        job_names+=("$compiler $artifact")
    done
done

for index in "${!jobs[@]}"; do
    if ! wait "${jobs[$index]}"; then
        name="${job_names[$index]// /-}"
        sed -n '1,40p' "$work_dir/$name.log" >&2
        fail "${job_names[$index]} did not compile cleanly"
    fi
done

[[ "$run_gcc" != true ]] || check_artifact gcc seed
check_artifact clang seed
[[ "$run_gcc" != true ]] || check_artifact gcc emitted
check_artifact clang emitted

# Exercise the same enum, scalar, payload and string cases after diagnostics.
"$clang_bin" -std=c99 -Werror=parentheses-equality "$work_dir/emitted.c" -o "$work_dir/emitted"
"$work_dir/emitted" > "$work_dir/emitted.out"
grep -q '^generated C patterns: true$' "$work_dir/emitted.out" || fail "pattern fixture returned incorrect results"
printf 'generated-c-warnings: emitted pattern behavior passed\n'
