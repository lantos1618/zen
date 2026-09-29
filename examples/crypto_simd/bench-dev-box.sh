#!/bin/bash
# Final performance run on dev-box: CPUs 6-7 only (benchmarks pinned to 6),
# load recorded before and after; waits while load > 4.
set -e
B=~/simd-20260929
cd $B/zen-simd-base && make build CC=clang >/dev/null 2>&1
cd $B/zen-simd && make build CC=clang >/dev/null 2>&1
rm -rf $B/orig-perf/build $B/demo-perf/build $B/demo-certs/build
cd $B/orig-perf && ZEN_STD=$B/zen-simd-base/src CC=clang CFLAGS="-O3 -flto -DNDEBUG" taskset -c 6,7 $B/zen-simd-base/zen build bench-chacha20poly1305 >/dev/null 2>&1
cd $B/demo-perf && for t in bench-chacha20poly1305 bench-components; do ZEN_STD=$B/zen-simd/src CC=clang CFLAGS="-O3 -flto -DNDEBUG" taskset -c 6,7 $B/zen-simd/zen build $t >/dev/null 2>&1; done
cd $B/demo-certs && ZEN_STD=$B/zen-simd/src CC=clang CFLAGS="-O3 -flto -DNDEBUG" taskset -c 6,7 $B/zen-simd/zen build bench-aes-gcm >/dev/null 2>&1
while true; do l=$(cut -d' ' -f1 /proc/loadavg); if awk "BEGIN{exit !($l <= 4)}"; then break; fi; echo "load $l > 4, waiting"; sleep 30; done
echo "date: $(date -u)"; echo "cpu: $(grep -m1 'model name' /proc/cpuinfo)"; clang --version | head -1; openssl version
echo "load before: $(cat /proc/loadavg)"
for r in 1 2 3; do
  echo "== run $r"
  echo "-- zen origin/main ChaCha20-Poly1305 (zen-crypto-perf 7c5194d)"; taskset -c 6 $B/orig-perf/build/bench-chacha20poly1305 | grep -v ok
  echo "-- zen simd ChaCha20-Poly1305 components"; taskset -c 6 $B/demo-perf/build/bench-components | grep -v check
  echo "-- zen simd ChaCha20-Poly1305"; taskset -c 6 $B/demo-perf/build/bench-chacha20poly1305 | grep -v ok
  echo "-- zen simd AES-128-GCM"; taskset -c 6 $B/demo-certs/build/bench-aes-gcm | grep -v ok
  echo "-- openssl"; taskset -c 6 openssl speed -evp chacha20-poly1305 -seconds 1 2>/dev/null | tail -1
  taskset -c 6 openssl speed -evp aes-128-gcm -seconds 1 2>/dev/null | tail -1
done
echo "load after: $(cat /proc/loadavg)"
