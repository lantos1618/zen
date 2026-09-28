#!/usr/bin/env python3
"""Test returned AST/sema collections with an existing compiler, never rebuild it."""
from pathlib import Path
import os
import shutil
import subprocess

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
OUT = REPO / 'build/library-returned-values'
SOURCE = OUT / 'source'
COMPILER = Path(os.environ.get('ZEN', str(REPO / 'zen'))).resolve()
CC = os.environ.get('CC', 'clang')
OUT.mkdir(parents=True, exist_ok=True)
shutil.copytree(REPO / 'src', SOURCE, dirs_exist_ok=True)
shutil.copy2(HERE / 'main.zen', SOURCE / 'returned_values.zen')


def compile_run(name, expect_success=True, sanitizer=False):
    c_file = OUT / f'{name}.c'
    binary = OUT / name
    subprocess.run([str(COMPILER), 'build', str(SOURCE), '--entry',
                    'returned_values.zen', '--std', str(SOURCE), '--emit-c',
                    '-o', str(c_file)], check=True, timeout=120)
    flags = ['-O1', '-Wno-parentheses-equality']
    if sanitizer:
        flags += ['-g', '-fsanitize=undefined', '-fno-sanitize-recover=all']
    subprocess.run([CC, *flags, str(c_file), '-o', str(binary)], check=True, timeout=120)
    result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=30)
    if expect_success:
        assert result.returncode == 0, result.stdout + result.stderr
        assert result.stdout.count('PASS:') == 2, result.stdout
        print(result.stdout, end='')
    else:
        assert result.returncode != 0, f'{name}: broken control unexpectedly passed'
        print(f'PASS: {name} rejected')


print(f'Existing compiler: {COMPILER}; std/sema: isolated copy of {REPO / "src"}', flush=True)
compile_run('functional')
compile_run('ubsan', sanitizer=True)
ast = SOURCE / 'std/ast/ast_arena.zen'
original = ast.read_text()
controls = {
    'wrong-selection': ('keep(self.type_at(id))', 'false'),
    'wrong-allocator': ('out ::= alloc.Vec<TypeId>();', 'out ::= self.alloc.Vec<TypeId>();'),
    'extra-allocation': ('out ::= alloc.Vec<TypeId>();', 'out ::= alloc.Vec<TypeId>();\n        out.reserve(1024).try();'),
}
try:
    for name, (before, after) in controls.items():
        assert original.count(before) == 1, (name, original.count(before))
        ast.write_text(original.replace(before, after))
        compile_run(name, expect_success=False)
finally:
    ast.write_text(original)
print('PASS: same-result append baseline and returned vector each use 10 allocations for 257 ids')
