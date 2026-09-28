#!/usr/bin/env python3
"""Exercise std.net.readiness with independent socket/signal OS fixtures."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
parser = argparse.ArgumentParser()
parser.add_argument('--zen', type=Path, required=True)
parser.add_argument('--std', type=Path, default=ROOT / 'src')
parser.add_argument('--ubsan', action='store_true')
args = parser.parse_args()
std = args.std.resolve()
env = dict(os.environ, ZEN_STD=str(std))

with tempfile.TemporaryDirectory(prefix='zen-readiness-') as folder:
    work = Path(folder)
    shutil.copy(HERE / 'probe.h', work)
    original = (HERE / 'main.zen').read_text()

    def build(source, name):
        (work / 'main.zen').write_text(source)
        generated = work / f'{name}.c'
        subprocess.run([str(args.zen.resolve()), 'build', str(work), '--std', str(std),
                        '--emit-c', '-o', str(generated)], env=env, check=True, timeout=120)
        binary = work / name
        flags = ['-fsanitize=undefined', '-fno-sanitize-recover=all'] if args.ubsan else []
        subprocess.run([os.environ.get('CC', 'clang'), '-O2', '-g', *flags,
                        '-I', str(work), '-I', str(std / 'std/net'),
                        str(generated), '-o', str(binary)], check=True, timeout=90)
        return binary

    def execute(binary):
        return subprocess.run([str(binary)], capture_output=True, text=True, timeout=15)

    result = execute(build(original, 'readiness'))
    assert result.returncode == 0, (result.returncode, result.stdout, result.stderr)
    print(result.stdout, end='')
    # Deliberately falsify the expected preserved slot. This must be detected.
    expected = 'Ok(value) => value == slot'
    assert original.count(expected) == 1
    mutation = original.replace(expected, 'Ok(value) => value == slot + 1', 1)
    result = execute(build(mutation, 'readiness-negative-control'))
    assert result.returncode == 1 and 'test line 18' in result.stderr, (
        result.returncode, result.stdout, result.stderr)
    print('PASS negative control: incorrect slot identity is rejected')
