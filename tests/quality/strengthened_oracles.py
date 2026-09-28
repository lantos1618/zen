#!/usr/bin/env python3
"""Check strengthened test oracles against explicit generated-C faults.

These simulate bad lowering; they do not measure all compiler-source mutations.
Every clean and faulty variant must compile. A killed control must terminate and
produce a mismatching result, so compile failures cannot inflate the count.
"""
import argparse
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]
CASES = {
    'codegen/transitive_type_closure_reaches_deepest_record': ('5touchO', 'constant return instead of nested field read'),
    'sema/nominal_generic_types_validate_open_and_closed': ('6closedO', 'zeroed generic return instead of input'),
    'actor/multiple_actor_types_keep_distinct_c_names': ('5First4pingO', 'first actor handler omitted'),
    'own/consume_in_every_match_arm': ('3Buf4dropO', 'owner destructor omitted'),
    'std/create_calls_the_dynamic_allocator': (None, 'create requests insufficient alignment'),
}


def mutate(code, selector):
    if selector is None:
        code, count = re.subn(r'(\.zu_m3raw\([^;\n]*sizeof\(int32_t\), )16(\);)', r'\g<1>1\2', code)
    else:
        pattern = re.compile(r'(^static (\w+) [^\n]*' + re.escape(selector) + r'[^\n]*\([^\n]*\) \{\n).*?^}', re.M | re.S)
        def replace(match):
            typ = match.group(2)
            returned = 'return;' if typ == 'void' else ('return 0;' if typ == 'int32_t' else 'return (' + typ + '){0};')
            return match.group(1) + '    ' + returned + '\n}'
        code, count = pattern.subn(replace, code)
    if count != 1:
        raise RuntimeError(f'Expected one fault site, found {count}')
    return code


def command(argv):
    result = subprocess.run(argv, capture_output=True, text=True, timeout=90)
    if result.returncode:
        raise RuntimeError('Command failed: ' + ' '.join(map(str, argv)) + '\n' + result.stderr[-2500:])
    return result


def check(tree, label, compiler, output):
    records = []
    for case, (selector, fault) in CASES.items():
        source = tree / 'corpus' / (case + '.zen')
        expected = source.with_suffix('.expected').read_text()
        folder = output / label / source.stem
        folder.mkdir(parents=True, exist_ok=True)
        generated = folder / 'clean.c'
        command([str(compiler), 'build', str(source.parent), '--entry', source.name,
                 '--std', str(ROOT / 'src'), '--emit-c', '-o', str(generated)])
        faulty = folder / 'fault.c'
        faulty.write_text(mutate(generated.read_text(), selector))
        outcomes = {}
        for variant in (generated, faulty):
            binary = variant.with_suffix('')
            command(['clang', '-std=c11', '-O0', '-Werror=return-type', str(variant), '-o', str(binary)])
            result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=15)
            outcomes[variant.stem] = dict(exit=result.returncode, stdout=result.stdout,
                                          matches=result.returncode == 0 and result.stdout == expected)
        if not outcomes['clean']['matches']:
            raise RuntimeError(f'Clean fixture failed: {label} {case}: {outcomes}')
        if label == 'after' and outcomes['fault']['matches']:
            raise RuntimeError(f'Fault survived strengthened fixture: {case}')
        record = dict(test_id='corpus/' + case, phase=label, fault=fault, outcomes=outcomes)
        records.append(record)
        print(label, case, 'DETECTED' if not outcomes['fault']['matches'] else 'SURVIVED', flush=True)
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--zen', type=Path, default=ROOT / 'zen')
    parser.add_argument('--baseline-tests', type=Path)
    parser.add_argument('--out', type=Path, default=ROOT / 'build/source_health/jev-test-review/oracle-controls')
    args = parser.parse_args()
    out = args.out.resolve()
    if not out.is_relative_to(ROOT / 'build/source_health'):
        parser.error('Write reports under build/source_health')
    records = []
    if args.baseline_tests:
        records += check(args.baseline_tests.resolve(), 'before', args.zen.resolve(), out)
    records += check(ROOT / 'tests', 'after', args.zen.resolve(), out)
    (out / 'results.json').write_text(json.dumps(records, indent=2) + '\n')


if __name__ == '__main__':
    main()
