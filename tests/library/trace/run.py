#!/usr/bin/env python3
"""Focused std.trace ownership/bounds gate with allocation negative control."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
ROOT = Path(__file__).resolve().parents[3]
p = argparse.ArgumentParser()
p.add_argument('--zen', type=Path, required=True)
p.add_argument('--std', type=Path, default=ROOT / 'src')
a = p.parse_args()
with tempfile.TemporaryDirectory(prefix='zen-trace-') as directory:
    work = Path(directory)
    (work / 'main.zen').write_text((Path(__file__).parent / 'main.zen').read_text())
    (work / 'trace_probe.h').write_text('''#ifndef TRACE_PROBE_H
#define TRACE_PROBE_H
#include <stdlib.h>
#include <assert.h>
static int trace_active;
static void begin(void) { trace_active = 1; }
static void end(void) { trace_active = 0; }
static void *trace_malloc(size_t n) { assert(!trace_active); return malloc(n); }
static void *trace_calloc(size_t n, size_t s) { assert(!trace_active); return calloc(n, s); }
static void *trace_realloc(void *p, size_t n) { assert(!trace_active); return realloc(p, n); }
#define malloc trace_malloc
#define calloc trace_calloc
#define realloc trace_realloc
static void leak(void) { void *p = malloc(1); free(p); }
#endif
''')
    subprocess.run([str(a.zen.resolve()), 'build', str(work), '--emit-c', '-o', str(work / 'generated.c')], env=dict(os.environ, ZEN_STD=str(a.std.resolve())), check=True, timeout=120)
    source = (work / 'generated.c').read_text()
    # Preinclude ensures allocator calls preceding the generated binding include
    # are measured too. Instrumentation is test-only and single-threaded.
    def execute(name, text, expected=True):
        file = work / (name + '.c')
        file.write_text(text)
        subprocess.run(['clang', '-O1', '-g', '-fsanitize=undefined', '-Werror=parentheses-equality', '-I', str(work), '-include', str(work / 'trace_probe.h'), str(file), '-o', str(work / name)], check=True, timeout=90)
        result = subprocess.run([str(work / name)], capture_output=True, text=True, timeout=30)
        if expected:
            assert result.returncode == 0, result.stdout + result.stderr
            assert 'runtime error:' not in result.stderr, result.stderr
            print(result.stdout, end='')
        else:
            assert result.returncode != 0, 'Record-allocation negative control unexpectedly passed'
            assert 'trace_active' in result.stderr, result.stdout + result.stderr
    execute('trace', source)
    # Negative control: a std whose Buffer.record allocates must be caught.
    std = work / 'std-allocating-record'
    shutil.copytree(a.std, std)
    trace = std / 'std' / 'trace.zen'
    text = trace.read_text()
    head = '    record* = (self :: @Self, span: Span) bool {\n'
    assert head in text, 'Buffer.record implementation not found'
    text = text.replace('Buffer* = {', 'Leak = c.bind("trace_probe.h", { leak = () () })\nBuffer* = {', 1)
    trace.write_text(text.replace(head, head + '        Leak.leak();\n', 1))
    subprocess.run([str(a.zen.resolve()), 'build', str(work), '--emit-c', '-o', str(work / 'negative.c')], env=dict(os.environ, ZEN_STD=str(std)), check=True, timeout=120)
    execute('allocating-record', (work / 'negative.c').read_text(), False)
    print('PASS: allocating-record negative control')
