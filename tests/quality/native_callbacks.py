#!/usr/bin/env python3
"""Exercise raw native callbacks through a real libc function."""
import argparse
from pathlib import Path
import sys
import unittest

import native_bindings


class NativeCallbacks(unittest.TestCase):
    compile = native_bindings.NativeBindings.compile
    run_c = native_bindings.NativeBindings.run_c

    def test_qsort_calls_zen_function(self):
        directory, output, _ = self.compile('''
Ptr, null_ptr = std.mem
callback = std.native
C = c.bind("stdlib.h", "qsort", {
    sort* = (base: Ptr<()>, count: usize, size: usize, compare: Ptr<()>) ()
})
compare = (a: Ptr<()>, b: Ptr<()>) i32 {
    a.to<i32>().read(0) - b.to<i32>().read(0)
}
main = (env: Env) Res<i32, AllocError> {
    a ::= env.mem.alloc();
    values = a.realloc<i32>(null_ptr<i32>(), 3).try();
    values.write(0, 9);
    values.write(1, 1);
    values.write(2, 5);
    C.sort(values.to<()>(), 3, 4, callback(compare));
    Ok((values.read(0) == 1 && values.read(1) == 5 && values.read(2) == 9).match({ true => 0, false => 1 }))
}
''')
        self.assertIn("((void *)&", output.read_text())
        self.assertEqual(self.run_c(directory, output).returncode, 0)

    def test_omitted_unit_return_callback(self):
        directory, output, _ = self.compile(r'''
Ptr = std.mem
callback = std.native
C = c.bind("stdlib.h", { atexit = (handler: Ptr<()>) i32 })
IO = c.bind("unistd.h", { write = (fd: i32, bytes: Ptr<u8>, count: usize) i64 })
finished = () {
    IO.write(1, "unit callback\n".ptr(), 14);
}
main = () i32 { C.atexit(callback(finished)) }
''')
        result = self.run_c(directory, output)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "unit callback\n")

    def test_rejects_capturing_lambda(self):
        self.compile('''
callback = std.native
main = () i32 {
    value = 4;
    callback(() i32 { value });
    0
}
''', False)

    def test_rejects_non_abi_functions(self):
        cases = [
            'f = (env: Env) {}',
            'f = (s: str) {}',
            'f = (unit: ()) {}',
            'f = () str { "not a native scalar" }',
            'f = (x :: i32) {}',
            'f = (x: i32) i32',
            'f<T> = (x: T) {}',
        ]
        for declaration in cases:
            with self.subTest(declaration=declaration):
                _, _, result = self.compile(
                    'callback = std.native\n' + declaration +
                    '\nmain = () i32 { callback(f); 0 }\n', False)
                self.assertIn('callback', result.stdout + result.stderr)

    def test_rejects_shadowing_local(self):
        self.compile('''
callback = std.native
f = (x: i32) i32 { x }
main = () i32 {
    f = (x: i32) i32 { x + 1 };
    callback(f);
    0
}
''', False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--zen', default=str(native_bindings.ZEN))
    args, rest = parser.parse_known_args()
    native_bindings.ZEN = Path(args.zen).resolve()
    unittest.main(argv=[sys.argv[0], *rest])
