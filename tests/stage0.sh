#!/bin/sh
# The old compiler as a test-runner backend: stage0.sh <test.zen | test-dir> <exe>
# ZEN0      the old compiler binary   (default ~/zen/zen/zen)
# ZEN0_STD  its standard library      (default ~/zen/jit-land/src/std)
set -eu
test=$1 exe=$2
zen=${ZEN0:-$HOME/zen/zen/zen}
std=${ZEN0_STD:-$HOME/zen/jit-land/src/std}
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

if [ -d "$test" ]; then
    cp -R "$test" "$work/root"
    entry=main.zen
    [ -f "$work/root/$entry" ] || entry=$(basename "$test").zen
else
    mkdir "$work/root" && cp "$test" "$work/root/"
    entry=$(basename "$test")
fi
ln -s "$std" "$work/root/std"

"$zen" build "$work/root" --std "$work/root" --entry "$entry" --emit-c -o "$work/out.c" 1>&2
cc -std=c11 -O0 -w "$work/out.c" -lm -o "$exe" 1>&2
