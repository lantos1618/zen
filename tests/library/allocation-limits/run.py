#!/usr/bin/env python3
"""Exercise current allocator sources without rebuilding the compiler."""
from pathlib import Path
import os
import shutil
import subprocess

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
STD = Path(os.environ.get('ZEN_STD', REPO / 'src')).resolve()
COMPILER = Path(os.environ.get('ZEN', REPO / 'zen')).resolve()
OUT = REPO / 'build/library-allocation-limits'
SOURCE = OUT / 'source'
shutil.copytree(STD, SOURCE, dirs_exist_ok=True)
shutil.copy2(HERE / 'main.zen', SOURCE / 'allocation_limits.zen')


def run(name, broken=False):
    c_file = OUT / f'{name}.c'
    binary = OUT / name
    subprocess.run([str(COMPILER), 'build', str(SOURCE), '--entry',
                    'allocation_limits.zen', '--std', str(SOURCE), '--emit-c',
                    '-o', str(c_file)], check=True, timeout=120)
    subprocess.run(['clang', '-O1', '-g', '-Wno-parentheses-equality',
                    '-fsanitize=undefined', '-fno-sanitize-recover=all',
                    str(c_file), '-o', str(binary)], check=True, timeout=120)
    result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=30)
    if broken:
        assert result.returncode != 0, f'{name}: mutation escaped detection'
        print(f'PASS: rejected {name}')
    else:
        assert result.returncode == 0, result.stdout + result.stderr
        assert 'PASS:' in result.stdout, result.stdout
        print(result.stdout, end='')


run('functional')
mutations = [
    ('arena-byte-wrap', 'std/mem/mem_arena.zen',
     '(element == 0 || count <= usize.MAX / element)', 'true'),
    ('arena-header-overflow', 'std/mem/mem_arena.zen',
     '(size <= usize.MAX - null_ptr<Page>().bytes(1).align_up(ALIGN_MAX) - HEADER_BYTES - align)', 'true'),
    ('vec-length-overflow', 'std/collections/collections_vec.zen',
     '(n <= usize.MAX - self.len)', 'true'),
    ('vec-doubling-overflow', 'std/collections/collections_vec.zen',
     'false => want}', 'false => want * 2}'),
]
for name, relative, before, after in mutations:
    path = SOURCE / relative
    original = path.read_text()
    assert original.count(before) == 1, (name, original.count(before))
    try:
        path.write_text(original.replace(before, after))
        run(name, broken=True)
    finally:
        path.write_text(original)
