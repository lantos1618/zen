#!/usr/bin/env python3
"""Exercise the native page header boundary without making huge allocations."""
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
program = '''{ Page, AllocError, Ptr, null_ptr } = std.mem
{ Res, Ok, Err } = std.core
{ Env } = std.env
Native = c.bind("stdbool.h", { aligned* = (p: Ptr<u8>) bool })
main = (env: Env) Res<i32, AllocError> {
    errors ::= 0;
    [usize.MAX, usize.MAX - 31].loop((size) {
        env.mem.page(size, null_ptr<Page>()).match({
            Err(_) => { errors = errors + 1; },
            Ok(page) => { env.mem.release(page); },
        });
    });
    (errors == 2).ensure(AllocError.OutOfMemory).try();
    page = env.mem.page(16, null_ptr<Page>()).try();
    env.mem.release(page);
    arena = env.mem.alloc();
    bytes = arena.raw(16, 16).try();
    Native.aligned(bytes).ensure(AllocError.OutOfMemory).try();
    Ok(0)
}
'''
prefix = '''#include <stdlib.h>
#include <stdio.h>
#include <stdint.h>
#include <stdbool.h>
static bool aligned(const unsigned char *p) { return ((uintptr_t)p & 15u) == 0; }
static size_t page_allocations;
static void *counted_malloc(size_t n) {
    page_allocations++;
    return n < 24 ? NULL : malloc(n);
}
#define malloc counted_malloc
'''
suffix = '''
int main(int argc, char **argv) {
    int result = zen_original_main(argc, argv);
    if(result || page_allocations != 4) { fprintf(stderr, "result=%d allocations=%zu\\n", result, page_allocations); return 1; }
    puts("PASS: overflowing page headers rejected before allocation; ordinary page and aligned Arena allocation succeed");
    return 0;
}
'''
with tempfile.TemporaryDirectory(prefix='zen-page-allocation-') as folder:
    work = Path(folder)
    (work / 'main.zen').write_text(program)
    generated = work / 'generated.c'
    subprocess.run([str(args.zen.resolve()), 'build', str(work), '--emit-c', '-o', str(generated)],
                   env=dict(os.environ, ZEN_STD=str(args.std.resolve())), check=True, timeout=120)
    source = prefix + generated.read_text().replace('int main(', 'int zen_original_main(') + suffix
    for name, text, passing in (
        ('checked', source, True),
        ('unaligned-control', re.sub(r'\(sizeof\(([^)]+)\) \+ 15u\) & ~\(size_t\)15u', r'sizeof(\1)', source), False),
        ('unchecked-control', re.sub(r'\(zg_t\d+ > SIZE_MAX - zg_page_header\d+\) \? NULL : ', '', source), False),
    ):
        if not passing:
            assert text != source, 'Page guard not found'
        path = work / (name + '.c')
        path.write_text(text)
        binary = work / name
        subprocess.run(['clang', '-O1', '-g', '-Wno-parentheses-equality',
                        '-fsanitize=undefined', '-fno-sanitize-recover=all',
                        str(path), '-o', str(binary)], check=True, timeout=90)
        result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=20)
        assert (result.returncode == 0) == passing, (name, result.stdout, result.stderr)
        print(result.stdout, end='')
        if not passing:
            print('PASS:', name, 'detected')
