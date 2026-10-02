#!/usr/bin/env python3
"""Exercise header constants and records through compiler diagnostics and C."""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def invoke(args, **kwargs):
    return subprocess.run(args, capture_output=True, text=True, timeout=90, **kwargs)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--zen', type=Path, default=ROOT / 'zen')
    parser.add_argument('--case', help='Run one named fixture')
    args = parser.parse_args()
    good = {'constants', 'record', 'fallback-range', 'signed-size', 'scalar-mismatch', 'posix-record'}
    cases = sorted(HERE.glob('*.zen'))
    assert len(cases) >= 9, 'missing native-binding fixtures'
    if args.case:
        cases = [case for case in cases if case.stem == args.case]
        assert cases, 'unknown fixture'
    for fixture in cases:
        with tempfile.TemporaryDirectory(prefix='zen-native-contract-') as tmp:
            work = Path(tmp)
            source = fixture.read_text().replace('@HEADER@', str(HERE / 'constants.h'))
            (work / 'main.zen').write_text(source)
            output = work / 'program.c'
            result = invoke([str(args.zen.resolve()), 'build', str(work), '--emit-c', '-o', str(output)],
                            env={**os.environ, 'ZEN_STD': str(ROOT / 'src')})
            diagnostic = result.stdout + result.stderr
            if fixture.stem not in good:
                assert result.returncode != 0, f'{fixture.name}: accepted invalid source'
                assert 'diagnostic(s)' in diagnostic, f'{fixture.name}: no compiler diagnostic: {diagnostic}'
                expected = {
                    'comptime': 'array count must be a compile-time constant',
                    'mutation': 'immutable',
                    'namespace-construction': 'construction names a constant',
                    'invalid-record-name': 'invalid native record',
                    'record-union': '`|` joins an enum',
                    'record-function': 'native records require',
                    'record-generic': 'cannot be generic',
                }[fixture.stem]
                assert expected in diagnostic, diagnostic
                assert not any(word in diagnostic for word in ['Segmentation fault', 'Assertion failed']), diagnostic
            else:
                assert result.returncode == 0, f'{fixture.name}: {diagnostic}'
                built = invoke(['cc', '-std=c99', str(output), '-o', str(work / 'program')])
                if fixture.stem in {'fallback-range', 'scalar-mismatch'}:
                    assert built.returncode != 0, 'C accepted an invalid native ABI declaration'
                    expected = '_range' if fixture.stem == 'fallback-range' else 'zg_native_scalar_field_type_mismatch'
                    assert expected in built.stderr, built.stderr
                    print(f'PASS {fixture.stem} (target C ABI check)')
                    continue
                assert built.returncode == 0, f'{fixture.name}: {built.stderr}'
                ran = invoke([str(work / 'program')])
                assert ran.returncode == 0, f'{fixture.name}: runtime {ran.returncode}: {ran.stderr}'
                if fixture.stem == 'constants':
                    text = output.read_text()
                    assert '#ifdef ZEN_PRESENT_CONSTANT' in text
                    assert '#ifdef ZEN_ABSENT_CONSTANT' in text
                    assert 'ZEN_ENUM_CONSTANT' in text
            print(f'PASS {fixture.stem}')
    print(f'{len(cases)} native-binding contracts passed')


if __name__ == '__main__':
    main()
