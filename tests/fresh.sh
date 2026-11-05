#!/bin/sh
# This compiler as a test-runner backend: fresh.sh <test.zen> <exe>
# `zen --check` decides whether the program is refused; <exe> is then a two-line script
# that runs it, so a program may exit 1 without looking refused.
# Build the compiler first: tools/zen0.sh -o build/zen main.zen
set -eu
zen=$(cd "$(dirname "$0")/.." && pwd)/build/zen
[ -x "$zen" ] || { echo "no build/zen: run tools/zen0.sh -o build/zen main.zen" >&2; exit 2; }
"$zen" --check "$1"
printf '#!/bin/sh\nexec "%s" "%s"\n' "$zen" "$1" > "$2"
chmod +x "$2"
