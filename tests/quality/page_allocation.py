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
prefix = '''#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include <sys/types.h>
bool aligned(const unsigned char *p) { return ((uintptr_t)p & 15u) == 0; }
static size_t page_maps;
#define mmap counted_mmap
#define main zen_main
'''
suffix = '''
#include <stdio.h>
#undef mmap
#undef main
void *mmap(void *, size_t, int, int, int, off_t);
void *counted_mmap(void *at, size_t n, int prot, int flags, int fd, off_t off) {
    page_maps++;
    return mmap(at, n, prot, flags, fd, off);
}
int main(int argc, char **argv, char **envp) {
    int status = zen_main(argc, argv, envp);
    if(status || page_maps != 3) { fprintf(stderr, "status=%d maps=%zu\\n", status, page_maps); return 1; }
    puts("PASS: overflowing page headers rejected before mapping; ordinary page and aligned Arena allocation succeed");
    return 0;
}
'''


def header_guard(text):
    # The page header size `h` is followed by the refusal limit `usize.MAX - h`.
    return re.search(r'= \(uint64_t\)INT64_C\((\d+)\);\n  (v\d+) = \(uint64_t\)INT64_C\(-(\d+)\);\n  (v\d+) = (v\d+) > \2;', text)


def unaligned(text):
    pattern = r'= \(uint64_t\)INT64_C\((\d+)\);\n(  v\d+ = \(uint64_t\)INT64_C\(-\d+\);\n  v\d+ = v\d+ > v\d+;)'
    return re.sub(pattern, lambda m: f'= (uint64_t)INT64_C({int(m.group(1)) - 8});\n{m.group(2)}', text)


def unchecked(text):
    found = header_guard(text)
    text = text.replace(found.group(0), found.group(0).replace(f'{found.group(4)} = {found.group(5)} > {found.group(2)};', f'{found.group(4)} = 0;'), 1)
    return text.replace('  if (bytes > SIZE_MAX - 16) return 0;\n', '', 1)


with tempfile.TemporaryDirectory(prefix='zen-page-allocation-') as folder:
    work = Path(folder)
    (work / 'main.zen').write_text(program)
    generated = work / 'generated.c'
    subprocess.run([str(args.zen.resolve()), 'build', str(work), '--emit-c', '-o', str(generated)],
                   env=dict(os.environ, ZEN_STD=str(args.std.resolve())), check=True, timeout=120)
    source = prefix + generated.read_text() + suffix
    assert header_guard(source), 'Page header guard not found'
    for name, text, passing in (
        ('checked', source, True),
        ('unaligned-control', unaligned(source), False),
        ('unchecked-control', unchecked(source), False),
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
