#!/usr/bin/env python3
"""Focused std bulk-math tests, negative control, sanitizer and ARM SIMD probe."""
from pathlib import Path
import os
import platform
import re
import subprocess

ROOT = Path(__file__).resolve().parent
ZEN = ROOT.parents[2]
env = dict(os.environ, ZEN_STD=str(ZEN / 'src'), CFLAGS='-O2 -Wno-parentheses-equality')
subprocess.run([str(ZEN / 'zen'), 'build', '.'], cwd=ROOT, env=env, check=True)
subprocess.run([str(ROOT / 'build/check')], check=True)
source = (ROOT / 'build/.zen/check/program.c').read_text()
pattern = r'static double (zu_f4_3std4math6vector16squared_distance\w+)\([^;\n]+\) \{'
match = re.search(pattern, source)
assert match
name = match.group(1)
# Prove the correctness harness notices a broken distance kernel.
broken = source[:match.end()] + '\nreturn 0.0;\n' + source[match.end():]
(ROOT / 'build/negative.c').write_text(broken)
subprocess.run(['clang', '-O2', '-Wno-parentheses-equality', str(ROOT / 'build/negative.c'), '-o', str(ROOT / 'build/negative')], check=True)
assert subprocess.run([str(ROOT / 'build/negative')], capture_output=True).returncode != 0
subprocess.run(['clang', '-O1', '-g', '-fsanitize=address,undefined', '-Wno-parentheses-equality', str(ROOT / 'build/.zen/check/program.c'), '-o', str(ROOT / 'build/sanitized')], check=True)
sanitizer_ok = True
try:
    subprocess.run([str(ROOT / 'build/sanitized')], check=True, timeout=20)
except subprocess.TimeoutExpired:
    sanitizer_ok = False
    print('UNVERIFIED: sanitizer runtime timed out on this host', flush=True)
# Keep only the tested kernels out of line so assembly attribution is precise.
s = re.sub(r'static double (zu_f4_3std4math6vector\w+\([^;\n]+\) \{)', r'__attribute__((noinline)) static double \1', source)
(ROOT / 'build/probe.c').write_text(s)
subprocess.run(['clang', '-O2', '-S', '-Wno-parentheses-equality', str(ROOT / 'build/probe.c'), '-o', str(ROOT / 'build/probe.s')], check=True)
if platform.system() == 'Darwin' and platform.machine() == 'arm64':
    assembly = (ROOT / 'build/probe.s').read_text()
    for operation in ['squared_distance', '3dot']:
        function = re.search(r'^(_zu_f4_3std4math6vector\w*' + operation + r'\w*):.*?(?=^\s*\.cfi_endproc)', assembly, re.M | re.S)
        assert function and re.search(r'fmul\.2d|fmla\.2d', function.group()), operation
    print('PASS: ARM SIMD instructions in both std kernels at -O2')
else:
    print('SKIP: architecture-specific SIMD instruction assertion')
# Benchmark reference and driver are compiled from Zen, not C source strings.
subprocess.run([str(ROOT / 'build/benchmark')], check=True, timeout=30)

if not sanitizer_ok:
    raise SystemExit(2)
