#!/usr/bin/env python3
"""Stress actual generated actor storage with native concurrent producers."""
import argparse
import os
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser()
parser.add_argument('--zen', type=Path, required=True)
parser.add_argument('--std', type=Path, default=ROOT / 'src')
args = parser.parse_args()
fixture = ROOT / 'tests/library/actor-contention'
with tempfile.TemporaryDirectory(prefix='zen-actor-contention-') as folder:
    work = Path(folder)
    (work / 'main.zen').write_text((fixture / 'main.zen').read_text())
    (work / 'probe.h').write_text('static void exercise(void);\n')
    subprocess.run([str(args.zen.resolve()), 'build', str(work), '--emit-c', '-o', str(work / 'generated.c')],
                   env=dict(os.environ, ZEN_STD=str(args.std.resolve())), check=True, timeout=120)
    source = (work / 'generated.c').read_text()
    prefix = '''#include <stdlib.h>
static size_t measured_allocations;
static void *measured_malloc(size_t n) {
    __atomic_add_fetch(&measured_allocations, 1, __ATOMIC_RELAXED);
    return malloc(n);
}
#define malloc measured_malloc
'''
    harness = (fixture / 'probe.c').read_text()

    def check(name, generated, flags=(), failure=False):
        path = work / f'{name}.c'
        path.write_text(prefix + generated + harness)
        subprocess.run(['clang', '-O1', '-g', '-pthread', '-Werror=parentheses-equality', *flags,
                        '-I', str(work), str(path), '-o', str(work / name)], check=True, timeout=90)
        result = subprocess.run([str(work / name)], capture_output=True, text=True, timeout=40)
        if failure:
            assert result.returncode != 0, f'{name}: broken control unexpectedly passed'
            print(f'PASS: {name} rejected')
        else:
            assert result.returncode == 0, f'{name}: {result.stdout}\n{result.stderr}'
            print(result.stdout, end='')

    check('contention', source)
    check('undefined-sanitized', source, ('-fsanitize=undefined', '-fno-sanitize-recover=all'))
    match = re.search(r'static void (\w*4Pool4give\w*)\([^;\n]+\) \{', source)
    assert match, 'No generated typed pool give found'
    broken = source[:match.end()] + '\n    zu_l11cache_limit = 0;\n' + source[match.end():]
    check('no-cache-control', broken, failure=True)
    assert 'if (size) memcpy(m->data, data, size);' in source
    broken = source.replace('if (size) memcpy(m->data, data, size);',
                            'if (size) memset(m->data, 0, size);', 1)
    check('payload-corruption-control', broken, failure=True)
