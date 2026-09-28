#!/usr/bin/env python3
"""Execute typed storage policy, sanitizer, and a failing no-cache control."""
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
args = p.parse_args()
with tempfile.TemporaryDirectory(prefix='zen-actor-storage-') as folder:
    work = Path(folder)
    (work / 'main.zen').write_text((ROOT / 'tests/library/actor-storage/main.zen').read_text())
    env = dict(os.environ, ZEN_STD=str(args.std.resolve()))
    subprocess.run([str(args.zen.resolve()), 'build', str(work), '--emit-c', '-o', str(work / 'generated.c')], env=env, check=True, timeout=120)
    source = (work / 'generated.c').read_text()
    def compile_run(name, text, flags=(), expected=True):
        path = work / (name + '.c')
        path.write_text(text)
        subprocess.run(['clang', '-O1', '-g', '-Wno-parentheses-equality', *flags, str(path), '-o', str(work / name)], check=True, timeout=90)
        result = subprocess.run([str(work / name)], capture_output=True, text=True, timeout=30)
        if expected:
            print(result.stdout, end='')
            assert result.returncode == 0, result.stderr
        else:
            print(result.stdout, end='')
            assert result.returncode != 0, 'Disabled-cache negative control unexpectedly passed'
    compile_run('policy', source)
    match = re.search(r'static void (\w*4Pool4give\w*)\([^;\n]+\) \{', source)
    assert match and 'zu_l11cache_limit' in match.group()
    negative = source[:match.end()] + '\n    zu_l11cache_limit = 0;\n' + source[match.end():]
    compile_run('negative', negative, expected=False)
    print('PASS: disabled-cache allocation negative control')
    # Exercise the actual generated spawn, enqueue, worker return and teardown,
    # not a hand-constructed runtime actor with substitute allocation callbacks.
    (work / 'main.zen').write_text((ROOT / 'tests/library/actor-storage/actor.zen').read_text())
    subprocess.run([str(args.zen.resolve()), 'build', str(work), '--emit-c', '-o', str(work / 'actor.c')], env=env, check=True, timeout=120)
    actor_source = (work / 'actor.c').read_text().replace('int main(', 'int zen_original_main(')
    prefix = '''#include <stdlib.h>
#include <assert.h>
static size_t measured_allocations;
static void *measured_malloc(size_t n) {
    __atomic_add_fetch(&measured_allocations, 1, __ATOMIC_RELAXED);
    return malloc(n);
}
#define malloc measured_malloc
'''
    suffix = '''
int main(int argc, char **argv) {
    int result = zen_original_main(argc, argv);
    printf("Generated actor heap allocations for 10000 turns: %zu\\n", measured_allocations);
    fflush(stdout);
    assert(result == 0 && measured_allocations < 256);
    return result;
}
'''
    compile_run('actor-policy', prefix + actor_source + suffix, ('-pthread',))
    match = re.search(r'static void (\w*4Pool4give\w*)\([^;\n]+\) \{', actor_source)
    assert match
    actor_negative = actor_source[:match.end()] + '\n    zu_l11cache_limit = 0;\n' + actor_source[match.end():]
    compile_run('actor-negative', prefix + actor_negative + suffix, ('-pthread',), expected=False)
    print('PASS: emitted actor allocator route and per-message-allocation negative control')
    compile_run('undefined-sanitized', source, ('-fsanitize=undefined',))
    compile_run('address-sanitized', source, ('-fsanitize=address',))
