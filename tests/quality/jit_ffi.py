#!/usr/bin/env python3
"""Exercise JIT C calls and host layout probes against real native code."""
import argparse
import os
from pathlib import Path
import platform
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
ZEN = ROOT / "zen"


@unittest.skipUnless(platform.system() == "Linux" and platform.machine() == "x86_64",
                     "JIT foreign calls require Linux x86-64")
class JitForeignCalls(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="zen-jit-ffi-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.env = {k: v for k, v in os.environ.items()
                    if k not in ("CC", "CFLAGS", "ZEN_BUILD_DIR", "ZEN_BUILD_OUTPUT",
                                 "ZEN_SYMBOL_MAP", "LD_PRELOAD")}
        self.env["ZEN_STD"] = str(ROOT / "src")
        self.source = self.root / "main.zen"

    def command(self, args, **env):
        return subprocess.run(args, cwd=self.root, env={**self.env, **env},
                              capture_output=True, text=True, timeout=90)

    def jit(self, **env):
        return self.command([str(ZEN), "build", "--backend", "jit", str(self.root),
                             "--entry", "main.zen"], **env)

    def cc(self, source, output, *flags):
        path = self.root / (output + ".c")
        path.write_text(source)
        result = self.command(["cc", *flags, str(path), "-o", str(self.root / output)])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return self.root / output

    def test_register_stack_float_variadic_and_record_pointer_calls(self):
        header = self.root / "calls.h"
        header.write_text("""
#pragma once
struct sample { long value; double fraction; };
long zen_ffi_words(long, long, long, long, long, long, long, long);
long zen_ffi_seven(long, long, long, long, long, long, long);
int zen_ffi_mixed(long, double, long, double, long, double, long, double,
                  long, double, long, double, long, double, long, double,
                  double, double);
float zen_ffi_float(float);
double zen_ffi_variadic(int, ...);
long zen_ffi_record(struct sample *);
""")
        library = self.cc('#include "calls.h"\n#include <stdarg.h>\n' + """
long zen_ffi_words(long a, long b, long c, long d, long e, long f, long g, long h) {
    return a + b*2 + c*3 + d*4 + e*5 + f*6 + g*7 + h*8;
}
long zen_ffi_seven(long a, long b, long c, long d, long e, long f, long g) {
    return ((unsigned long)__builtin_frame_address(0) & 15) ? -1 : a+b+c+d+e+f+g;
}
int zen_ffi_mixed(long a, double b, long c, double d, long e, double f,
                  long g, double h, long i, double j, long k, double l,
                  long m, double n, long o, double p, double q, double r) {
    return a == 1 && b == 2 && c == 3 && d == 4 && e == 5 && f == 6 &&
           g == 7 && h == 8 && i == 9 && j == 10 && k == 11 && l == 12 &&
           m == 13 && n == 14 && o == 15 && p == 16 && q == 17 && r == 18;
}
float zen_ffi_float(float x) { return x * 2; }
double zen_ffi_variadic(int count, ...) {
    va_list args; va_start(args, count); double sum = 0;
    for (int i = 0; i < count; ++i) sum += va_arg(args, double);
    va_end(args); return sum;
}
long zen_ffi_record(struct sample *p) { return p->value + (long)p->fraction; }
""", "calls.so", "-shared", "-fPIC")
        self.source.write_text('''
{ println } = std.io
C = c.bind("''' + str(header) + '''", {
    zen_ffi_words = (a: i64, b: i64, c: i64, d: i64, e: i64, f: i64, g: i64, h: i64) i64
    zen_ffi_seven = (a: i64, b: i64, c: i64, d: i64, e: i64, f: i64, g: i64) i64
    zen_ffi_mixed = (a: i64, b: f64, c: i64, d: f64, e: i64, f: f64, g: i64, h: f64,
                    i: i64, j: f64, k: i64, l: f64, m: i64, n: f64, o: i64, p: f64,
                    q: f64, r: f64) i32
    zen_ffi_float = (x: f32) f32
    zen_ffi_variadic = (count: i32, a: f64, b: f64, c: f64) f64
    zen_ffi_record = (p :: Sample) i64
})
Sample = c.record("''' + str(header) + '''", "struct sample", { value: i64, fraction: f64 })
main = () {
    println("{}", C.zen_ffi_words(1, 2, 3, 4, 5, 6, 7, 8));
    println("{}", C.zen_ffi_seven(1, 2, 3, 4, 5, 6, 7));
    println("{}", C.zen_ffi_mixed(1, 2.0, 3, 4.0, 5, 6.0, 7, 8.0, 9, 10.0, 11, 12.0, 13, 14.0, 15, 16.0, 17.0, 18.0));
    println("{}", C.zen_ffi_float(1.25) == 2.5);
    println("{}", C.zen_ffi_variadic(3, 1.25, 2.5, 4.0) == 7.75);
    sample ::= Sample(value: 40, fraction: 2.5);
    println("{}", C.zen_ffi_record(sample));
}
''')
        result = self.jit(LD_PRELOAD=str(library))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        generated = self.root / "oracle.c"
        emitted = self.command([str(ZEN), "build", str(self.root), "--entry", "main.zen",
                                "--emit-c", "-o", str(generated)])
        self.assertEqual(emitted.returncode, 0, emitted.stdout + emitted.stderr)
        built = self.command(["cc", str(generated), str(library), "-lm", "-o", str(self.root / "oracle")])
        self.assertEqual(built.returncode, 0, built.stdout + built.stderr)
        oracle = self.command([str(self.root / "oracle")])
        self.assertEqual(oracle.returncode, 0, oracle.stdout + oracle.stderr)
        self.assertEqual(oracle.stdout, "204\n28\n1\ntrue\ntrue\n42\n")
        self.assertEqual(result.stdout, oracle.stdout)

    def test_header_change_invalidates_answers(self):
        header = self.root / "value.h"
        self.source.write_text('{ println } = std.io\nC = c.bind("' + str(header) +
                               '", { ZEN_FFI_VALUE: i32 })\nmain = () { println("{}", C.ZEN_FFI_VALUE); }\n')
        for value in (17, 29):
            header.write_text(f"#define ZEN_FFI_VALUE {value}\n")
            result = self.jit()
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(result.stdout.strip(), str(value))

    def test_overaligned_native_records_are_refused(self):
        header = self.root / "aligned.h"
        header.write_text("struct __attribute__((aligned(64))) sample { unsigned long value; };\n")
        self.source.write_text('{ println } = std.io\nSample = c.record("' + str(header) +
                               '", "struct sample", { value: u64 })\n'
                               'main = () { value ::= Sample(value: 42); println("{}", value.value); }\n')
        result = self.jit()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("native C records aligned above 16 bytes", result.stdout)

    def test_missing_symbol_is_named(self):
        self.source.write_text("zen_ffi_nonexistent_symbol = () i32\nmain = () i32 { zen_ffi_nonexistent_symbol() }\n")
        result = self.jit()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("no library defining the C function `zen_ffi_nonexistent_symbol`", result.stdout)

    def test_wide_foreign_values_are_refused_before_calling(self):
        library = self.cc("unsigned __int128 zen_ffi_wide(unsigned __int128 x) { return x; }\n",
                          "wide.so", "-shared", "-fPIC")
        self.source.write_text("zen_ffi_wide = (n: u128) u128\nmain = () i32 { zen_ffi_wide(1); 0 }\n")
        result = self.jit(LD_PRELOAD=str(library))
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("128-bit C arguments or results", result.stdout)

    def test_calls_beyond_stack_capacity_are_refused(self):
        parameters = ", ".join(f"x{i}: i64" for i in range(23))
        arguments = ", ".join(str(i) for i in range(23))
        library = self.cc("long zen_ffi_many(void) { return 0; }\n", "many.so", "-shared", "-fPIC")
        self.source.write_text(f"zen_ffi_many = ({parameters}) i64\n"
                               f"main = () i32 {{ zen_ffi_many({arguments}); 0 }}\n")
        result = self.jit(LD_PRELOAD=str(library))
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("unsupported by the jit backend: calls of C functions", result.stdout)

    def test_host_compiler_is_only_needed_for_header_probes(self):
        self.source.write_text("main = () i32 { 0 }\n")
        result = self.jit(CC="/bin/false")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.source.write_text('C = c.bind("errno.h", { ENOENT: i32 })\nmain = () i32 { C.ENOENT }\n')
        result = self.jit(CC="/bin/false")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("the host C compiler could not answer", result.stdout)

    def test_c_calls_back_into_zen_functions(self):
        header = self.root / "callbacks.h"
        header.write_text("""
#pragma once
double zen_ffi_apply(double (*f)(long, double), long n, double x);
long zen_ffi_twice(long (*f)(long), long x);
""")
        library = self.cc('#include "callbacks.h"\n' + """
double zen_ffi_apply(double (*f)(long, double), long n, double x) { return f(n, x); }
long zen_ffi_twice(long (*f)(long), long x) { return f(f(x)); }
""", "callbacks.so", "-shared", "-fPIC")
        self.source.write_text('''
{ println } = std.io
{ callback } = std.native
{ Ptr, null_ptr, AllocError } = std.mem
{ Res, Ok } = std.core
{ Env } = std.env
C = c.bind("''' + str(header) + '''", {
    zen_ffi_apply = (f: Ptr<()>, n: i64, x: f64) f64
    zen_ffi_twice = (f: Ptr<()>, x: i64) i64
})
Sort = c.bind("stdlib.h", "qsort", {
    sort* = (base: Ptr<()>, count: usize, size: usize, compare: Ptr<()>) ()
})
scale = (n: i64, x: f64) f64 {
    println("scale {}", n);
    x * 2.0
}
step = (x: i64) i64 { x + 1 }
nested = (x: i64) i64 { C.zen_ffi_twice(callback(step), x) }
compare = (a: Ptr<()>, b: Ptr<()>) i32 {
    a.to<i32>().read(0) - b.to<i32>().read(0)
}
main = (env: Env) Res<i32, AllocError> {
    println("{}", C.zen_ffi_apply(callback(scale), 3, 1.25) == 2.5);
    println("{}", C.zen_ffi_twice(callback(step), 40));
    println("{}", C.zen_ffi_twice(callback(nested), 0));
    a ::= env.mem.alloc();
    values = a.realloc<i32>(null_ptr<i32>(), 3).try();
    values.write(0, 9);
    values.write(1, 1);
    values.write(2, 5);
    Sort.sort(values.to<()>(), 3, 4, callback(compare));
    println("{} {} {}", values.read(0), values.read(1), values.read(2));
    Ok(0)
}
''')
        result = self.jit(LD_PRELOAD=str(library))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout, "scale 3\ntrue\n42\n4\n1 5 9\n")

    def test_signal_outside_a_c_call_runs_at_the_next_safe_point(self):
        # kill is a system call the interpreter makes itself, so the handler
        # arrives while no C call is parked: the stub defers it, and the
        # interpreter runs it as the system call returns, before `after`.
        self.source.write_text('''
{ println } = std.io
{ callback } = std.native
{ Ptr } = std.mem
{ kill } = std.sys
Signals = c.bind("signal.h", {
    signal = (number: i32, handler: Ptr<()>) Ptr<()>
    SIGUSR1: i32
})
Native = c.bind("unistd.h", { getpid = () i32 })
handled = (number: i32) { println("handled {}", number == Signals.SIGUSR1); }
main = () i32 {
    Signals.signal(Signals.SIGUSR1, callback(handled));
    kill(Native.getpid(), Signals.SIGUSR1);
    println("after");
    0
}
''')
        result = self.jit()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout, "handled true\nafter\n")

    def test_errno_is_read_when_the_program_runs(self):
        self.source.write_text('''
{ println } = std.io
{ Ptr } = std.mem
Native = c.bind("unistd.h", { read = (fd: i32, bytes: Ptr<u8>, count: usize) i64 })
Errors = c.bind("errno.h", { errno: i32, EBADF: i32 })
main = () {
    count = Native.read(-1, "x".ptr(), 1);
    println("{}", count < 0 && Errors.errno == Errors.EBADF);
}
''')
        result = self.jit()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout, "true\n")

    def test_executable_mapping_refusal_is_reported(self):
        wrapper = self.cc("""
#include <errno.h>
#include <linux/filter.h>
#include <linux/seccomp.h>
#include <stddef.h>
#include <sys/mman.h>
#include <sys/prctl.h>
#include <sys/syscall.h>
#include <unistd.h>
int main(int argc, char **argv) {
    struct sock_filter filter[] = {
        BPF_STMT(BPF_LD | BPF_W | BPF_ABS, offsetof(struct seccomp_data, nr)),
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, SYS_mprotect, 0, 3),
        BPF_STMT(BPF_LD | BPF_W | BPF_ABS, offsetof(struct seccomp_data, args[2])),
        BPF_JUMP(BPF_JMP | BPF_JSET | BPF_K, PROT_EXEC, 0, 1),
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ERRNO | EACCES),
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ALLOW)
    };
    struct sock_fprog program = { sizeof(filter) / sizeof(filter[0]), filter };
    if (prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) ||
        prctl(PR_SET_SECCOMP, SECCOMP_MODE_FILTER, &program)) return 77;
    execv(argv[1], argv + 1); return 78;
}
""", "deny-exec")
        self.source.write_text("abs = (n: i32) i32\nmain = () i32 { abs(-3) }\n")
        result = self.command([str(wrapper), str(ZEN), "build", "--backend", "jit", str(self.root),
                               "--entry", "main.zen"])
        self.assertNotEqual(result.returncode, 77, "seccomp filter could not be installed")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("the stub for calls of C functions", result.stdout)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--zen", type=Path, default=ZEN)
    args, remaining = parser.parse_known_args()
    ZEN = args.zen.resolve()
    unittest.main(argv=[__file__, *remaining])
