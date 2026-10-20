#!/usr/bin/env python3
"""Numeric comparison operands retain element width, with a bool-spill control."""
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
with tempfile.TemporaryDirectory(prefix='zen-comparison-operands-') as folder:
    work = Path(folder)
    fixture = ROOT / 'tests/corpus/ptr/comparisons_preserve_element_types.zen'
    (work / 'main.zen').write_text(fixture.read_text())
    emitted = work / 'generated.c'
    subprocess.run([str(args.zen.resolve()), 'build', str(work), '--emit-c', '-o', str(emitted)],
                   env=dict(os.environ, ZEN_STD=str(args.std.resolve())), check=True, timeout=120)
    source = emitted.read_text()
    spill = re.search(r'uint8_t (zg_s\d+);\n\s*\1 = \([^\n]+\)\[0\];', source)
    if spill:
        broken = source[:spill.start()] + source[spill.start():].replace('uint8_t ', 'bool ', 1)
    else:
        # IR-C declares every value at the top of its function and reads
        # bytes through `za_uint8_t`; take the first read after the 199 store.
        stored = source.find('= (uint8_t)INT64_C(199);')
        assert stored >= 0, 'Expected the first byte store'
        held = re.compile(r'\n\s*(v\d+) = \*\(const za_uint8_t \*\)'
                          r'\(\(const unsigned char \*\)\(uintptr_t\)v\d+ \+ 0u\);').search(source, stored)
        assert held, 'Expected held byte-pointer read'
        decl = f'ZR_U uint8_t {held.group(1)} ZR_Z;'
        at = source.rfind(decl, 0, held.start())
        assert at >= 0, 'Expected the held read to be declared as a byte'
        broken = source[:at] + f'ZR_U _Bool {held.group(1)} ZR_Z;' + source[at + len(decl):]
    for name, text, passing in (('typed', source, True), ('bool-spill-control', broken, False)):
        path = work / (name + '.c')
        binary = path.with_suffix('')
        path.write_text(text)
        subprocess.run(['clang', '-O1', '-g', '-Wno-parentheses-equality',
                        '-fsanitize=undefined', '-fno-sanitize-recover=all',
                        str(path), '-o', str(binary)], check=True, timeout=90)
        result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=20)
        valid = result.returncode == 0 and result.stdout == 'comparisons preserve numeric elements\n'
        assert valid == passing, (name, result.returncode, result.stdout, result.stderr)
        print('PASS:', name)
