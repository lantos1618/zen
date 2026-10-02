#!/usr/bin/env python3
"""Exercise the real Zen project builder and its seed-only Make bootstrap."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[2]
ZEN = ROOT / "zen"


class SelfBuildTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="zen-self-build-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.environment = {k: v for k, v in os.environ.items()
                            if k not in ("CC", "CFLAGS", "ZEN_BUILD_OUTPUT", "ZEN_BUILD_DIR", "ZEN_SYMBOL_MAP")}
        self.environment["ZEN_STD"] = str(ROOT / "src")
        self.source = self.root / "chosen.zen"
        self.source.write_text("main = () i32 { 3 }\n")
        self.output = self.root / "chosen"
        self.write_graph()

    def write_graph(self, extra=""):
        (self.root / "build.zen").write_text(
            "{ Builder, BuildError } = std.build\n"
            "build = (b :: Builder) Res<(), BuildError> {\n"
            'b.exe("chosen", { src: Path("chosen.zen"), deps: [], '
            'out: Ok(Path("chosen")) }).try();\n' + extra + "\nOk(())\n}\n")

    def build(self, success=True, **environment):
        result = subprocess.run([str(ZEN), "build", "."], cwd=self.root,
                                env={**self.environment, **environment}, capture_output=True,
                                text=True, timeout=90)
        self.assertEqual(result.returncode == 0, success, result.stdout + result.stderr)
        return result

    def status(self, executable=None):
        return subprocess.run([str(executable or self.output)], capture_output=True, timeout=10).returncode

    def wrapper(self, body, name="compiler"):
        path = self.root / name
        path.write_text("#!/bin/sh\nset -eu\n" + body)
        path.chmod(0o755)
        return str(path)

    def test_fresh_make_bootstrap_uses_build_graph_without_python(self):
        # No ./zen, Python driver, src/ tree or generated C units exist here,
        # so the standard library is named on the make command line.
        # The graph deliberately selects an entry different from src/zen/zen.zen.
        (self.root / "seed").mkdir()
        shutil.copyfile(ROOT / "seed/zen.c", self.root / "seed/zen.c")
        shutil.copyfile(ROOT / "Makefile", self.root / "Makefile")
        make = ["make", "build", "PY=/no-python-for-building", "CFLAGS=-O0 -std=c99", "CACHE="]
        result = subprocess.run([*make, f"ZEN_STD={ROOT / 'src'}"], cwd=self.root,
                                env=self.environment, capture_output=True, text=True, timeout=180)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue((self.root / "build/bootstrap/zen-seed").is_file())
        self.assertEqual(self.status(), 3)
        # With a src/ tree of its own, the checkout's library wins over a
        # ZEN_STD the shell exports for other work, even one naming no tree.
        (self.root / "src").symlink_to(ROOT / "src", target_is_directory=True)
        self.source.write_text("main = () i32 { 5 }\n")
        result = subprocess.run(make, cwd=self.root, capture_output=True, text=True, timeout=180,
                                env={**self.environment, "ZEN_STD": str(self.root / "no-such-std")})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.status(), 5)
        self.source.write_text("main = () i32 { 8 }\n")
        result = self.build()
        self.assertEqual(self.status(), 8)
        self.assertFalse((self.root / "zen").exists())

    def test_frontend_and_partial_native_failure_preserve_executable(self):
        self.build()
        published = self.output.read_bytes()
        self.source.write_text("main = () i32 { missing(); }\n")
        self.build(success=False)
        self.assertEqual(self.output.read_bytes(), published)
        self.source.write_text("main = () i32 { 7 }\n")
        compiler = self.wrapper('while [ "$#" -gt 0 ]; do\n'
                                '  if [ "$1" = -o ]; then shift; printf broken > "$1"; exit 9; fi\n'
                                '  shift\ndone\nexit 10\n')
        self.build(success=False, CC=compiler)
        self.assertEqual(self.output.read_bytes(), published)
        self.assertFalse(Path(str(self.output) + ".zen-next").exists())
        self.build()
        self.assertEqual(self.status(), 7)

    def test_running_executable_survives_replacement(self):
        self.source.write_text('getchar = () i32\nmain = (env: Env) Res<i32, IoError> {\n'
                               'env.out.println("ready").try(); env.out.flush().try();\n'
                               'getchar(); Ok(3)\n}\n')
        self.build()
        child = subprocess.Popen([str(self.output)], stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE, text=True)
        try:
            self.assertEqual(child.stdout.readline(), "ready\n")
            self.source.write_text("main = () i32 { 9 }\n")
            self.build()
            self.assertIsNone(child.poll())
            self.assertEqual(self.status(), 9)
            child.communicate("\n", timeout=10)
            self.assertEqual(child.returncode, 3)
        finally:
            if child.poll() is None:
                child.kill()
            child.wait(timeout=10)

    def test_compiler_words_flags_and_isolated_output(self):
        compiler = self.wrapper('[ "$1" = sentinel ]; shift\n'
                                'printf "%s\\n" "$@" > flags.log\nexec cc "$@"\n',
                                "compiler with spaces")
        self.build(CC='"' + compiler + '" sentinel', CFLAGS='-O0 -DNAME="two words"',
                   ZEN_BUILD_OUTPUT="dev/compiler", ZEN_BUILD_DIR="dev/work")
        self.assertFalse(self.output.exists())
        self.assertEqual(self.status(self.root / "dev/compiler"), 3)
        self.assertTrue((self.root / "dev/work/.zen/chosen/program.c").is_file())
        self.assertIn("-DNAME=two words\n", (self.root / "flags.log").read_text())
        self.build(success=False, CC='"unterminated')
        self.assertFalse(self.output.exists())
        self.write_graph('b.exe("other", {src: Path("chosen.zen"), deps: []}).try();')
        self.build(success=False, ZEN_BUILD_OUTPUT="shared")
        self.assertFalse((self.root / "shared").exists())

    def test_foreign_symbol_text_does_not_link_unused_libraries(self):
        self.source.write_text('main = () { println("SSL_read_ex"); }\n')
        self.build()
        result = subprocess.run([str(self.output)], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "SSL_read_ex\n")

    def test_external_header_changes_are_observed(self):
        (self.root / "value.h").write_text("#define VALUE 4\n")
        (self.root / "native.c").write_text('#include "value.h"\nint answer(void) { return VALUE; }\n')
        self.source.write_text("answer = () i32\nmain = () i32 { answer() }\n")
        (self.root / "build.zen").write_text(
            "{ Builder, BuildError } = std.build\nbuild = (b :: Builder) Res<(), BuildError> {\n"
            'native = b.extern("native", {src: Path("native.c"), libs: [], paths: []}).try();\n'
            'b.exe("chosen", {src: Path("chosen.zen"), deps: [native], '
            'out: Ok(Path("chosen"))}).try(); Ok(())\n}\n')
        self.build()
        self.assertEqual(self.status(), 4)
        (self.root / "value.h").write_text("#define VALUE 6\n")
        self.build()
        self.assertEqual(self.status(), 6)

    def test_orphaned_compiler_retains_workspace_lock(self):
        compiler = self.wrapper('echo ready > compiler-started\n'
                                'while [ ! -f compiler-release ]; do sleep 0.05; done\n'
                                'exec cc "$@"\n')
        with (self.root / "build.log").open("w+") as log:
            parent = subprocess.Popen([str(ZEN), "build", "."], cwd=self.root,
                                      env={**self.environment, "CC": compiler}, stdout=log, stderr=log)
            try:
                deadline = time.monotonic() + 30
                while not (self.root / "compiler-started").exists():
                    if parent.poll() is not None or time.monotonic() > deadline:
                        log.seek(0)
                        self.fail("compiler did not reach gate: " + log.read())
                    time.sleep(0.05)
                parent.kill()
                parent.wait(timeout=5)
                locked = self.build(success=False)
                self.assertIn("workspace is locked", locked.stdout)
            finally:
                (self.root / "compiler-release").touch()
                if parent.poll() is None:
                    parent.kill()
                parent.wait(timeout=5)
            # The surviving C compiler holds the same descriptor until exit.
            deadline = time.monotonic() + 30
            while True:
                result = subprocess.run([str(ZEN), "build", "."], cwd=self.root,
                                        env=self.environment, capture_output=True, text=True, timeout=30)
                if result.returncode == 0:
                    break
                self.assertIn("workspace is locked", result.stdout)
                self.assertLess(time.monotonic(), deadline)
                time.sleep(0.1)
        self.assertEqual(self.status(), 3)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zen", type=Path, default=ZEN)
    args, remaining = parser.parse_known_args()
    ZEN = args.zen.resolve()
    unittest.main(argv=[__file__, *remaining])
