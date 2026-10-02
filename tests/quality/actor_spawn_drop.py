#!/usr/bin/env python3
"""Prove spawn transfers ownership once, including both metadata allocation failures."""
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
program = '''{ Res, Ok, Err, Drop } = std.core
{ Env } = std.env
{ Actor, Context } = std.actor
{ println } = std.io
Worker = { id: u64 }
Worker.impl(Drop, { drop = (self :: @Self) { println("drop {}", self.id); } })
Worker.impl(Actor, { ping = (self :: @Self, ctx: Context) {} })
make_worker = () Worker { println("constructed"); Worker(id: 42) }
main = (env: Env) i32 {
    SETUP
    env.spawn(ARGUMENT).match({
        Ok(actor) => { actor.stop(); actor.join(); println("joined"); },
        Err(error) => { error.match({
            OutOfMemory => println("oom"),
            Unavailable => println("unavailable"),
        }); },
    });
    0
}
'''
with tempfile.TemporaryDirectory(prefix='zen-spawn-drop-') as folder:
    work = Path(folder)
    env = dict(os.environ, ZEN_STD=str(args.std.resolve()))
    for form, setup, argument in (
        ('consumed', 'item ::= make_worker();', 'consume item'),
        ('temporary', '', 'make_worker()'),
    ):
        (work / 'main.zen').write_text(program.replace('SETUP', setup).replace('ARGUMENT', argument))
        emitted = work / (form + '.c')
        subprocess.run([str(args.zen.resolve()), 'build', str(work), '--emit-c', '-o', str(emitted)],
                       env=env, check=True, timeout=120)
        source = emitted.read_text()
        allocations = list(re.finditer(r'\([^\n;]*\)malloc\(sizeof\([^\n;]+\)\);', source))
        actor_allocations = [hit for hit in allocations
                             if 'zg_actor' in source[source.rfind('\n', 0, hit.start()):hit.end()]]
        assert len(actor_allocations) == 2, 'Expected actor record and arena state allocations'

        def run(name, text, expected, broken=False):
            path = work / (form + '-' + name + '.c')
            binary = path.with_suffix('')
            path.write_text(text)
            subprocess.run(['clang', '-O1', '-g', '-pthread', '-Wno-parentheses-equality',
                            '-fsanitize=undefined', '-fno-sanitize-recover=all',
                            str(path), '-o', str(binary)], check=True, timeout=90)
            result = subprocess.run([str(binary)], text=True, capture_output=True, timeout=20)
            valid = result.returncode == 0 and result.stdout.splitlines() == expected
            if broken:
                assert not valid, 'Missing-drop control unexpectedly passed'
            else:
                assert valid, (form, name, result.returncode, result.stdout, result.stderr)
            print('PASS:', form, name)

        run('success', source, ['constructed', 'drop 42', 'joined'])
        for index, hit in enumerate(actor_allocations):
            denied = source[:hit.start()] + 'NULL;' + source[hit.end():]
            run('allocation-' + str(index), denied, ['constructed', 'drop 42', 'oom'])
            # Remove only the emitted OOM cleanup: the semantic check must fail.
            cleanup = re.search(r'\s*\(void\)\(\w+\(&zg_actor_value\d+\)\);', denied)
            assert cleanup, 'Missing allocation-failure ownership cleanup'
            broken = denied[:cleanup.start()] + denied[cleanup.end():]
            run('missing-drop-control-' + str(index), broken,
                ['constructed', 'drop 42', 'oom'], broken=True)
        start = re.search(r'zg_actor_start\(&zg_actor_instance\d+->zg_base\)', source)
        assert start
        unavailable = source[:start.start()] + '1' + source[start.end():]
        run('start-refusal', unavailable, ['constructed', 'drop 42', 'unavailable'])
