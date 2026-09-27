#!/usr/bin/env python3
"""Execute public Alloc pool semantics and a failing realloc-copy control."""
import argparse
import os
from pathlib import Path
import re
import subprocess
import tempfile
ROOT = Path(__file__).resolve().parents[2]
p = argparse.ArgumentParser()
p.add_argument('--zen', type=Path, required=True)
p.add_argument('--std', type=Path, default=ROOT / 'src')
p.add_argument('--sanitize', action='store_true')
p.add_argument('--ubsan', action='store_true')
args = p.parse_args()
with tempfile.TemporaryDirectory(prefix='zen-pool-alloc-') as folder:
    work = Path(folder)
    (work / 'main.zen').write_text((ROOT / 'tests/library/pool-alloc/main.zen').read_text())
    env = dict(os.environ, ZEN_STD=str(args.std.resolve()))
    subprocess.run([str(args.zen.resolve()), 'build', str(work), '--emit-c', '-o', str(work / 'generated.c')], env=env, check=True, timeout=120)
    source = (work / 'generated.c').read_text()
    def execute(name, text, flags=(), expected=True):
        path = work / (name + '.c')
        path.write_text(text)
        subprocess.run(['clang', '-O1', '-g', '-Wno-parentheses-equality', *flags, str(path), '-o', str(work / name)], check=True, timeout=90)
        result = subprocess.run([str(work / name)], capture_output=True, text=True, timeout=30)
        if expected:
            print(result.stdout, end='')
            assert result.returncode == 0, result.stderr
        else:
            assert result.returncode != 0, 'Broken realloc copy unexpectedly passed'
    execute('policy', source)
    # Remove only the copy from compiled PoolAlloc.realloc, retaining allocation
    # and freeing paths. The real Alloc caller must notice lost old contents.
    starts = list(re.finditer(r'^static [^;\n]*9PoolAlloc7realloc[^;\n]*\{', source, re.M))
    assert starts, 'PoolAlloc realloc implementation not found'
    negative = source
    removed = 0
    for match in reversed(starts):
        end = source.index('\n}', match.end())
        body = source[match.start():end]
        body, count = re.subn(r'\bmemcpy\([^;]+;', '(void)0;', body)
        removed += count
        negative = negative[:match.start()] + body + negative[end:]
    assert removed, 'PoolAlloc realloc copy not found'
    execute('negative', negative, expected=False)
    print('PASS: realloc-copy negative control')
    if args.ubsan:
        execute('ubsan', source, ('-fsanitize=undefined',))
    if args.sanitize:
        execute('sanitized', source, ('-fsanitize=address,undefined',))
    (work / 'main.zen').write_text((ROOT / 'tests/library/pool-alloc/failure.zen').read_text())
    subprocess.run([str(args.zen.resolve()), 'build', str(work), '--emit-c', '-o', str(work / 'failure.c')], env=env, check=True, timeout=120)
    failure = (work / 'failure.c').read_text()
    prefix = '''#include <stdlib.h>
static void *failure_malloc(size_t n) { return n == 273 ? NULL : malloc(n); }
#define malloc failure_malloc
'''
    execute('native-failure', prefix + failure)
    execute('native-failure-control', failure, expected=False)
    print('PASS: native-OOM harness negative control')
    (work / 'main.zen').write_text((ROOT / 'tests/library/pool-alloc/storage.zen').read_text())
    subprocess.run([str(args.zen.resolve()), 'build', str(work), '--emit-c', '-o', str(work / 'storage.c')], env=env, check=True, timeout=120)
    storage = (work / 'storage.c').read_text()
    execute('storage', storage)
    if args.ubsan:
        execute('storage-ubsan', storage, ('-fsanitize=undefined',))
    (work / 'main.zen').write_text((ROOT / 'tests/library/pool-alloc/snapshot_actor.zen').read_text())
    subprocess.run([str(args.zen.resolve()), 'build', str(work), '--emit-c', '-o', str(work / 'snapshot-actor.c')], env=env, check=True, timeout=120)
    execute('snapshot-actor', (work / 'snapshot-actor.c').read_text(), ('-pthread',))
