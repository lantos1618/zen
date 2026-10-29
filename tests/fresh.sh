#!/bin/sh
# This compiler as a test-runner backend: fresh.sh <test.zen> <exe>
# It compiles and runs in one step, so <exe> is a two-line script that runs it on the test.
# Build the compiler first: tools/zen0.sh -o build/zen main.zen
set -eu
zen=$(cd "$(dirname "$0")/.." && pwd)/build/zen
[ -x "$zen" ] || { echo "no build/zen: run tools/zen0.sh -o build/zen main.zen" >&2; exit 2; }
"$zen" "$1" >/dev/null 2>&1 || [ $? -ne 1 ] || { "$zen" "$1"; exit 1; }
printf '#!/bin/sh\nexec "%s" "%s"\n' "$zen" "$1" > "$2"
chmod +x "$2"
