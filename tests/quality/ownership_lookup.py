#!/usr/bin/env python3
"""Owning reads are rejected; explicit extraction destroys each owner once."""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser()
parser.add_argument('--zen', type=Path, required=True)
parser.add_argument('--std', type=Path, default=ROOT / 'src')
parser.add_argument('--old-zen', type=Path)
parser.add_argument('--old-std', type=Path)
args = parser.parse_args()
HEADER = '''Owner = { id: i32 }
Owner.impl(Drop, { drop = (self :: @Self) { println("drop {}", self.id); } })
'''

def program(body, extra=''):
    return HEADER + extra + '\nmain = (env: Env) Res<i32, AllocError> {\n' + body + '\nOk(0)\n}\n'

VEC = '''v ::= env.mem.alloc().Vec<Owner>();
item ::= Owner(id: 1);
v.add(consume item).try();
'''
POINTER = '''p = env.mem.alloc().create<Owner>().try();
item ::= Owner(id: 1);
p.write(0, consume item);
'''
REJECT = {
    'vec-get': program(VEC + 'copy = v.get(0).ok_or(AllocError.OutOfMemory).try(); v.clear();'),
    'vec-require': program(VEC + 'copy = v.require(0); v.clear();'),
    'vec-loop': program(VEC + 'v.loop((value) { println("{}", value.id); }); v.clear();'),
    'ptr-read': program(POINTER + 'copy = p.read(0);'),
    'ptr-copy-run': program(POINTER + 'q = env.mem.alloc().create<Owner>().try(); q.copy_from(p, 1);'),
    'generic-read': program(POINTER + 'copy = copied(p);',
                            'copied = <T>(p: Ptr<T>) T { p.read(0) }\n'),
    'nested-read': program('p = env.mem.alloc().create<Box>().try(); copy = p.read(0);',
                           'Box = { value: Owner }\n'),
    'map-get': program('m ::= env.mem.alloc().Map<str, Owner>(); copy = m.get("key");'),
    'map-pairs': program('m ::= env.mem.alloc().Map<str, Owner>(); m.pairs((h, k, value) { println("{}", value.id); });'),
}
PASS = {
    'vec-take': (program(VEC + 'taken = v.take(0).ok_or(AllocError.OutOfMemory).try(); v.clear(); println("taken {}", taken.id);'), 'taken 1\ndrop 1\n'),
    'ptr-take': (program(POINTER + 'taken = p.take(0); println("taken {}", taken.id);'), 'taken 1\ndrop 1\n'),
    'factory': (program('value = make_owner(); println("made {}", value.id);',
                        'make_owner = () Owner { Owner(id: 7) }\n'), 'made 7\ndrop 7\n'),
    'middle-take': (program('''v ::= env.mem.alloc().Vec<Owner>();
a ::= Owner(id: 1); b ::= Owner(id: 2); c ::= Owner(id: 3);
v.add(consume a).try(); v.add(consume b).try(); v.add(consume c).try();
value = v.take(1).ok_or(AllocError.OutOfMemory).try(); v.clear(); println("taken {}", value.id);'''),
                    'drop 3\ndrop 1\ntaken 2\ndrop 2\n'),
    'plain-lookup': (program('''v ::= env.mem.alloc().Vec<i32>(); v.add(42).try();
println("{}", v.get(0).ok_or(AllocError.OutOfMemory).try()); v.clear();'''), '42\n'),
}

def emit(compiler, work, name, source, std=None):
    folder = work / name
    folder.mkdir()
    (folder / 'main.zen').write_text(source)
    output = folder / 'out.c'
    result = subprocess.run([str(compiler.resolve()), 'build', str(folder), '--emit-c', '-o', str(output)],
                            env=dict(os.environ, ZEN_STD=str((std or args.std).resolve())),
                            capture_output=True, text=True, timeout=120)
    return result, output


def execute(path):
    binary = path.with_suffix('')
    subprocess.run(['clang', '-O1', '-g', '-Wno-parentheses-equality', '-fsanitize=undefined',
                    '-fno-sanitize-recover=all', str(path), '-o', str(binary)],
                   capture_output=True, text=True, check=True, timeout=90)
    return subprocess.run([str(binary)], capture_output=True, text=True, timeout=20)


with tempfile.TemporaryDirectory(prefix='zen-owning-lookup-') as folder:
    work = Path(folder)
    for name, source in REJECT.items():
        result, _ = emit(args.zen, work, name, source)
        diagnostic = result.stdout + result.stderr
        assert result.returncode != 0 and 'cannot copy a Drop owner through Ptr' in diagnostic, (name, diagnostic)
        print('PASS reject:', name, flush=True)
    for name, (source, expected) in PASS.items():
        result, path = emit(args.zen, work, name, source)
        assert result.returncode == 0, (name, result.stdout, result.stderr)
        run = execute(path)
        assert run.returncode == 0 and run.stdout == expected, (name, run.returncode, run.stdout, run.stderr)
        print('PASS UBSan:', name, flush=True)
    if args.old_zen:
        source = (ROOT / 'tests/library/ownership-lookup/main.zen').read_text()
        result, path = emit(args.old_zen, work, 'old-compiler-control', source, args.old_std)
        assert result.returncode == 0, (result.stdout, result.stderr)
        run = execute(path)
        assert run.returncode == 0 and run.stdout.count('drop 1\n') == 2, (run.stdout, run.stderr)
        print('PASS negative control: old compiler duplicates one destruction', flush=True)
