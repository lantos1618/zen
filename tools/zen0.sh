#!/bin/sh
# Build src/<entry> with the stage-0 compiler and run it: tools/zen0.sh ir/selftest.zen [args...]
# ZEN0, ZEN0_STD as in tests/stage0.sh. Until src/std exists, programs use the old std.
set -eu
here=$(cd "$(dirname "$0")/.." && pwd)
entry=$1; shift
zen=${ZEN0:-$HOME/zen/zen/zen}
std=${ZEN0_STD:-$HOME/zen/jit-land/src/std}
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

mkdir "$work/root"
for part in "$here"/src/*; do
    [ "$(basename "$part")" = std ] || ln -s "$part" "$work/root/$(basename "$part")"
done
ln -s "$std" "$work/root/std"

"$zen" build "$work/root" --std "$work/root" --entry "$entry" --emit-c -o "$work/out.c"
cc -std=c11 -O0 -g -w "$work/out.c" -lm -o "$work/a.out"
"$work/a.out" "$@"
