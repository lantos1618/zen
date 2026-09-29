#!/usr/bin/env python3
"""Deterministic OS-failure tests; no statistical claim about RNG quality."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
p = argparse.ArgumentParser()
p.add_argument('--zen', type=Path, required=True)
p.add_argument('--std', type=Path, default=ROOT / 'src')
p.add_argument('--ubsan', action='store_true')
args = p.parse_args()
with tempfile.TemporaryDirectory(prefix='zen-entropy-') as folder:
    work = Path(folder)
    for name in ('main.zen', 'probe.h', 'probe.c'):
        shutil.copyfile(HERE / name, work / name)
    generated = work / 'main.c'
    subprocess.run([str(args.zen.resolve()), 'build', str(work), '--std', str(args.std.resolve()),
                    '--emit-c', '-o', str(generated)], check=True, timeout=120)
    original = generated.read_text()
    flags = ['-fsanitize=undefined', '-fno-sanitize-recover=all'] if args.ubsan else []
    def check(name, source, expected):
        generated.write_text(source)
        binary = work / name
        built = subprocess.run([os.getenv('CC', 'clang'), '-O2', *flags, '-Darc4random_buf=zen_test_arc4random_buf',
                                '-I', str(work), str(generated), str(work / 'probe.c'), '-o', str(binary)],
                               timeout=90, capture_output=True, text=True)
        if built.returncode:
            raise RuntimeError(built.stderr)
        result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=10)
        assert result.returncode == expected, (name, result.returncode, result.stdout, result.stderr)
        print(result.stdout, end='')
    check('entropy', original, 0)
    # Deliberately leave the last requested byte unwritten; the exact-span
    # assertions must detect a short OS fill.
    probe = work / 'probe.c'
    source = probe.read_text()
    assert source.count('i < count;') == 1
    probe.write_text(source.replace('i < count;', 'i + 1 < count;'))
    check('entropy-negative-control', original, 1)
    print('PASS negative control: a short OS fill is detected')
