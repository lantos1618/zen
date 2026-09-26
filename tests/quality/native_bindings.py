#!/usr/bin/env python3
"""Compile and run explicit native namespaces using real system headers."""
import argparse
import os
import sys
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
ZEN = ROOT / "zen"

class NativeBindings(unittest.TestCase):
    def compile(self, source, success=True):
        temp = tempfile.TemporaryDirectory(prefix="zen-native-")
        self.addCleanup(temp.cleanup)
        directory = Path(temp.name)
        (directory / "main.zen").write_text(source)
        output = directory / "program.c"
        result = subprocess.run([str(ZEN), "build", str(directory), "--emit-c", "-o", str(output)],
                                env={**os.environ, "ZEN_STD": str(ROOT / "src")},
                                capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode == 0, success, result.stdout + result.stderr)
        return directory, output, result

    def run_c(self, directory, output):
        binary = directory / "program"
        cc = subprocess.run(["cc", "-std=c99", str(output), "-o", str(binary)], capture_output=True, text=True, timeout=60)
        self.assertEqual(cc.returncode, 0, cc.stderr)
        return subprocess.run([str(binary)], capture_output=True, text=True, timeout=10)

    def test_header_functions_have_no_synthetic_wrappers(self):
        directory, output, _ = self.compile('''
Ptr, null_ptr = std.mem
C = c.bind("stdlib.h", {
    malloc* = (size: usize) Ptr<()>
    free* = (value: Ptr<()>) ()
})
main = () i32 {
    p = C.malloc(64);
    missing = p.is_null();
    C.free(p);
    missing.match({true => 1, false => 0})
}
''')
        generated = output.read_text()
        self.assertIn("#include <stdlib.h>", generated)
        self.assertNotRegex(generated, r"\bextern\b[^\n]*\b(?:malloc|free)\s*\(")
        self.assertNotIn("zg_os_", generated)
        self.assertEqual(self.run_c(directory, output).returncode, 0)

    def test_explicit_symbol_uses_declared_abi(self):
        directory, output, _ = self.compile('''
C = c.bind("stdlib.h", "abs", {
    absolute* = (value: c_int) c_int
})
main = () i32 { (-17).to_c_int().match({ Ok(value) => (C.absolute(value) == 17).match({ true => 0, false => 1 }), None => 2 }) }
''')
        self.assertIn("))abs)", output.read_text())
        self.assertEqual(self.run_c(directory, output).returncode, 0)

    def test_binding_roundtrips_formatter(self):
        directory, output, _ = self.compile('''
C = c.bind("unistd.h", {
 getpid* = () c_int
})
main = () i32 { (C.getpid() > 0).match({true => 0, false => 1}) }
''')
        for args in (["fmt", str(directory / "main.zen")], ["fmt", "--check", str(directory / "main.zen")]):
            result = subprocess.run([str(ZEN), *args], capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('c.bind("unistd.h"', (directory / "main.zen").read_text())
        self.assertEqual(self.run_c(directory, output).returncode, 0)

    def test_binding_module_can_be_imported(self):
        temp = tempfile.TemporaryDirectory(prefix="zen-native-import-")
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        (root / "posix.zen").write_text('C* = c.bind("unistd.h", { getpid* = () c_int })\nVERSION*: i32 = 1\n')
        (root / "main.zen").write_text('C, VERSION = posix\nmain = () i32 { (C.getpid() > 0).match({true => 0, false => 1}) }\n')
        output = root / "program.c"
        result = subprocess.run([str(ZEN), "build", str(root), "--emit-c", "-o", str(output)],
                                env={**os.environ, "ZEN_STD": str(ROOT / "src")}, capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.run_c(root, output).returncode, 0)

    def test_calls_are_checked_against_zen_declarations(self):
        for call in ('C.abs("wrong")', 'C.abs()', 'C.abs(1, 2)'):
            with self.subTest(call=call):
                self.compile('C = c.bind("stdlib.h", { abs* = (v: c_int) c_int })\n'
                             'main = () i32 { ' + call + '; 0 }', False)

    def test_symbol_override_roundtrips_formatter(self):
        source = ('C = c.bind("stdlib.h", "abs", { magnitude* = (v: c_int) c_int })\n'
                  'main = () i32 { (17).to_c_int().match({ Ok(v) => (C.magnitude(v) == v).match({true => 0, false => 1}), None => 2 }) }\n')
        directory, _, _ = self.compile(source)
        path = directory / "main.zen"
        result = subprocess.run([str(ZEN), "fmt", str(path)], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('"abs"', path.read_text())
        second_dir, output, _ = self.compile(path.read_text())
        self.assertIn("))abs)", output.read_text())
        self.assertEqual(self.run_c(second_dir, output).returncode, 0)

    def project_fixture(self, files, registrations):
        temporary = tempfile.TemporaryDirectory(prefix="zen-native-project-")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        for name, content in files.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        (root / "build.zen").write_text(
            "Builder, BuildError = std.build\n"
            "build = (b :: Builder) Res<(), BuildError> {\n"
            + registrations + "\nOk(())\n}\n")
        environment = {key: value for key, value in os.environ.items()
                       if key not in ("CC", "CFLAGS", "ZEN_BUILD_OUTPUT", "ZEN_BUILD_DIR", "ZEN_SYMBOL_MAP")}
        environment["ZEN_STD"] = str(ROOT / "src")
        result = subprocess.run([str(ZEN), "build", str(root)], cwd=root,
                                env=environment, capture_output=True, text=True, timeout=90)
        return root, result

    def test_selected_library_resolves_arbitrary_root_and_children(self):
        for child_path in ("vendor/sdk/detail.zen", "vendor/sdk/detail/detail.zen"):
            with self.subTest(child_path=child_path):
                root, result = self.project_fixture({
                    "main.zen": "answer, VERSION = sdk\nmain = () i32 { (answer() == 42).match({true => 0, false => 1}) }\n",
                    "vendor/sdk/api.zen": "VALUE, FLAG = sdk.detail\nanswer* = () i32 { VALUE }\nVERSION*: i32 = 1\n",
                    child_path: "VALUE*: i32 = 42\nFLAG*: bool = true\n",
                }, 'sdk = b.lib("sdk", {src: Path("vendor/sdk/api.zen"), libs: [], paths: []}).try();\n'
                   'b.lib("unused", {src: Path("missing/not-present.zen"), libs: [], paths: []}).try();\n'
                   'b.exe("app", {src: Path("main.zen"), deps: [sdk], out: Ok(Path("app"))}).try();')
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                process = subprocess.run([str(root / "app")], capture_output=True, text=True, timeout=10)
                self.assertEqual(process.returncode, 0, process.stdout + process.stderr)

    @unittest.skipUnless(sys.platform == "darwin", "Apple Foundation requires macOS")
    def test_objective_c_language_and_framework_linking(self):
        root, result = self.project_fixture({
            "main.zen": 'Foundation = c.bind("Foundation/Foundation.h", { NSPageSize* = () usize })\n'
                        'main = () i32 { (Foundation.NSPageSize() > 0).match({true => 0, false => 1}) }\n',
        }, 'b.exe("app", {src: Path("main.zen"), deps: [], language: "objective-c", '
           'frameworks: ["Foundation"], out: Ok(Path("app"))}).try();')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        process = subprocess.run([str(root / "app")], capture_output=True, text=True, timeout=10)
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)

    def test_unselected_library_is_not_importable(self):
        _, result = self.project_fixture({
            "main.zen": "answer, VERSION = sdk\nmain = () i32 { answer() }\n",
            "vendor/sdk/api.zen": "answer* = () i32 { 0 }\nVERSION*: i32 = 1\n",
        }, 'b.lib("sdk", {src: Path("vendor/sdk/api.zen"), libs: [], paths: []}).try();\n'
           'b.exe("app", {src: Path("main.zen"), deps: [], out: Ok(Path("app"))}).try();')
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("nothing is at that path", result.stdout + result.stderr)

    def test_rejects_typed_or_mutable_native_namespace(self):
        for declaration in ("C: i32 =", "C ::="):
            with self.subTest(declaration=declaration):
                _, _, result = self.compile(
                    declaration + ' c.bind("unistd.h", { getpid* = () c_int })\n'
                    'main = () i32 { 0 }\n', False)
                self.assertIn("a native namespace uses an untyped immutable declaration",
                              result.stdout + result.stderr)

    def test_rejects_namespace_construction(self):
        _, _, result = self.compile(
            'C = c.bind("unistd.h", { getpid* = () c_int })\n'
            'main = () i32 { value = C(); 0 }\n', False)
        self.assertIn("constructing a native binding namespace", result.stdout + result.stderr)

    def test_rejects_bodies_generic_and_data_members(self):
        for member in ('f* = () i32 { 1 }', 'f*<T> = (value: T) T', 'value: i32'):
            with self.subTest(member=member):
                _, _, result = self.compile('C = c.bind("stdlib.h", { ' + member + ' })\nmain = () i32 { 0 }\n', False)
                self.assertIn("native bindings require", result.stdout)

    def test_rejects_header_and_symbol_injection(self):
        for source in (
            'C = c.bind("bad\\nheader", { getpid* = () c_int })\nmain = () i32 { C.getpid(); 0 }',
            'C = c.bind("stdlib.h", "abs);bad(", { f* = () c_int })\nmain = () i32 { C.f(); 0 }',
        ):
            with self.subTest(source=source):
                _, _, result = self.compile(source, False)
                self.assertIn("invalid native", result.stdout + result.stderr)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--zen", type=Path, default=ZEN)
    args, remaining = parser.parse_known_args()
    ZEN = args.zen.resolve()
    unittest.main(argv=[__file__, *remaining])
