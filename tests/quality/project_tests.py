#!/usr/bin/env python3
"""Exercise executable test targets through the real Zen CLI."""
import argparse
import os
from pathlib import Path
import subprocess
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
ZEN = ROOT / "zen"


class ProjectTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="zen-project-tests-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.write("pass.zen", "main = () i32 { 0 }\n")
        self.write("fail.zen", "main = () i32 { 7 }\n")

    def write(self, name, text):
        (self.root / name).write_text(text)

    def build_file(self, registrations):
        self.write("build.zen", "Builder, BuildError, Mode, Optimize, Cc = std.build\n"
                   "Res, Ok, Path = std.core\n"
                   "build = (b :: Builder) Res<(), BuildError> {\n"
                   + registrations + "\nOk(())\n}\n")

    def run_zen(self, *args):
        return subprocess.run([str(ZEN), *args], cwd=self.root,
                              env={**os.environ, "ZEN_STD": str(ROOT / "src")},
                              capture_output=True, text=True, timeout=90)

    def test_chained_registrations_keep_order_and_select_targets(self):
        self.build_file('b.exe("app", {src: Path("fail.zen"), deps: []}).try()\n'
                        ' .exe_test("first", {src: Path("pass.zen"), deps: []}).try()\n'
                        ' .exe_test("last", {src: Path("pass.zen"), deps: []}).try();')
        result = self.run_zen("test")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("ok first\nok last", result.stdout)
        self.assertIn("2 passed, 0 failed", result.stdout)
        selected = self.run_zen("test", "last")
        self.assertEqual(selected.returncode, 0, selected.stdout + selected.stderr)
        self.assertNotIn("ok first", selected.stdout)

    def test_chaining_requires_error_propagation(self):
        self.build_file('b.exe("app", {src: Path("pass.zen"), deps: []})\n'
                        ' .exe("other", {src: Path("pass.zen"), deps: []}).try();')
        result = self.run_zen("build")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("no `exe`", result.stdout)

    def test_chained_duplicate_stops_before_execution(self):
        self.write("pass.zen", 'println = std.io\nmain = () { println("must not run"); }\n')
        self.build_file('b.exe_test("same", {src: Path("pass.zen"), deps: []}).try()\n'
                        ' .exe_test("same", {src: Path("pass.zen"), deps: []}).try();')
        result = self.run_zen("test")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertNotIn("must not run", result.stdout)

    def package_repo(self):
        repo = self.root / "source repository"
        repo.mkdir()
        self.git(repo, "init", "--quiet", "--template=")
        self.git(repo, "config", "user.email", "fixture@example.invalid")
        self.git(repo, "config", "user.name", "Package fixture")
        (repo / "sample.zen").write_text('answer* = () i32 { 42 }\nmarker* = 0\n')
        self.git(repo, "add", "sample.zen")
        self.git(repo, "commit", "--quiet", "-m", "fixture")
        return repo, self.git(repo, "rev-parse", "HEAD").strip()

    def git(self, repo, *args):
        result = subprocess.run(["git", "-c", "core.hooksPath=/dev/null", "-C", str(repo), *args],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout

    def package_manifest(self, repo, rev, src="sample.zen", used=True):
        self.write("client.zen", 'answer, marker = sample\nmain = () i32 { answer() - 42 }\n')
        target_src = "client.zen" if used else "pass.zen"
        deps = "[sample]" if used else "[]"
        self.build_file(f'sample = b.add("sample", {{url: "{repo.as_uri()}", rev: "{rev}", '
                        f'src: Path("{src}"), libs: [], paths: []}}).try();\n'
                        f'b.exe_test("client", {{src: Path("{target_src}"), deps: {deps}}}).try();')

    def test_pinned_package_builds_and_reuses_cache_offline(self):
        repo, rev = self.package_repo()
        self.package_manifest(repo, rev)
        first = self.run_zen("test", "client")
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        cache = self.root / "build/packages" / rev
        self.assertEqual(self.git(cache, "rev-parse", "HEAD").strip(), rev)
        repo.rename(repo.with_name("offline repository"))
        offline = self.run_zen("test", "client")
        self.assertEqual(offline.returncode, 0, offline.stdout + offline.stderr)

    def test_package_cache_refuses_modified_and_untracked_sources(self):
        repo, rev = self.package_repo()
        self.package_manifest(repo, rev)
        first = self.run_zen("test", "client")
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        cache = self.root / "build/packages" / rev
        original = (cache / "sample.zen").read_text()
        for filename in ("sample.zen", "untracked.zen"):
            with self.subTest(filename=filename):
                (cache / filename).write_text('answer* = () i32 { 99 }\n')
                result = self.run_zen("test", "client")
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn("cached source is modified", result.stdout)
                self.assertNotIn("ok client", result.stdout)
                if filename == "sample.zen":
                    (cache / filename).write_text(original)
                else:
                    (cache / filename).unlink()

    def test_package_refuses_wrong_origin_and_commit(self):
        repo, rev = self.package_repo()
        self.package_manifest(repo, rev)
        first = self.run_zen("test", "client")
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        cache = self.root / "build/packages" / rev
        self.git(cache, "remote", "set-url", "origin", "https://example.invalid/wrong")
        result = self.run_zen("test", "client")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("cache origin or commit", result.stdout)
        self.git(cache, "remote", "set-url", "origin", repo.as_uri())
        self.git(cache, "-c", "user.email=fixture@example.invalid", "-c", "user.name=Fixture",
                 "commit", "--allow-empty", "--quiet", "-m", "different commit")
        result = self.run_zen("test", "client")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("cache origin or commit", result.stdout)

    def test_package_rejects_floating_revisions_and_path_escape(self):
        repo, rev = self.package_repo()
        for pin, src in (("main", "sample.zen"), (rev, "../sample.zen"), (rev, "/tmp/sample.zen")):
            with self.subTest(pin=pin, src=src):
                self.package_manifest(repo, pin, src)
                result = self.run_zen("test", "client")
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn("full lowercase commit ID", result.stdout)
                self.assertFalse((self.root / "build/packages").exists())

    def test_missing_package_entry_and_commit_fail(self):
        repo, rev = self.package_repo()
        self.package_manifest(repo, rev, "absent.zen")
        result = self.run_zen("test", "client")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("source entry does not exist", result.stdout)
        self.package_manifest(repo, "0" * 40)
        result = self.run_zen("test", "client")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("fetch/verification failed", result.stdout)

    def test_unused_package_does_not_fetch(self):
        self.package_manifest(self.root / "absent repository", "0" * 40, used=False)
        result = self.run_zen("test", "client")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse((self.root / "build/packages").exists())

    def test_failures_continue_and_selection_is_explicit(self):
        self.build_file('b.exe_test("first", {src: Path("pass.zen"), deps: []}).try();\n'
                        'b.exe_test("bad", {src: Path("fail.zen"), deps: []}).try();\n'
                        'b.exe_test("last", {src: Path("pass.zen"), deps: []}).try();')
        all_tests = self.run_zen("test")
        self.assertEqual(all_tests.returncode, 1, all_tests.stdout + all_tests.stderr)
        self.assertIn("not ok bad (exit 7)\nok last", all_tests.stdout)
        self.assertIn("zen test: 2 passed, 1 failed", all_tests.stdout)
        selected = self.run_zen("test", str(self.root), "last")
        self.assertEqual(selected.returncode, 0, selected.stdout + selected.stderr)
        self.assertIn("zen test: 1 passed, 0 failed", selected.stdout)
        self.assertNotIn("not ok", selected.stdout)
        local = self.run_zen("test", "first")
        self.assertEqual(local.returncode, 0, local.stdout + local.stderr)

    def test_std_math_links_without_project_native_dependency(self):
        self.write("math.zen", 'sqrt = std.math\nmain = () i32 { (sqrt(9.0) == 3.0).match({ true => 0, false => 1 }) }\n')
        self.build_file('b.exe_test("math", {src: Path("math.zen"), deps: [], optimize: Optimize.Debug}).try();')
        checker = self.root / "check-math-link"
        checker.write_text(f"#!{sys.executable}\nimport os, sys\n"
                           'if "-lm" not in sys.argv: raise SystemExit("missing math library")\n'
                           f"os.execv({shutil.which('cc')!r}, [{shutil.which('cc')!r}, *sys.argv[1:]])\n")
        checker.chmod(0o755)
        result = subprocess.run([str(ZEN), "test", "math"], cwd=self.root,
            env={**os.environ, "ZEN_STD": str(ROOT / "src"), "CC": str(checker)},
            capture_output=True, text=True, timeout=90)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("zen test: 1 passed, 0 failed", result.stdout)

    def test_empty_and_unknown_selections_fail(self):
        self.build_file('b.exe("app", {src: Path("pass.zen"), deps: []}).try();')
        for args in (("test",), ("test", "missing")):
            result = self.run_zen(*args)
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("no matching executable test targets", result.stdout)

    def test_registered_unimported_source_is_checked_before_any_execution(self):
        self.write("pass.zen", 'println = std.io\nmain = () { println("must not run"); }\n')
        self.write("broken_test.zen", 'main = () { absent_test_function(); }\n')
        self.build_file('b.exe_test("first", {src: Path("pass.zen"), deps: []}).try();\n'
                        'b.exe_test("broken", {src: Path("broken_test.zen"), deps: []}).try();')
        result = self.run_zen("test")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("undefined name", result.stdout)
        self.assertNotIn("must not run", result.stdout)
        self.assertNotIn("zen test: 2 passed", result.stdout)

    def test_trailing_arguments_require_a_separator(self):
        self.write("args.zen", 'Env = std.env\nprintln = std.io\n'
                   'main = (env: Env) {\n'
                   'env.argv.get(1).when_ok((arg) { println("arg {}", arg); });\n}\n')
        self.build_file('b.exe_test("args", {src: Path("args.zen"), deps: []}).try();')
        result = self.run_zen("test", "--", "--help")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("arg --help", result.stdout)
        for args in (("test", "--invalid"), ("test", "args", "extra")):
            result = self.run_zen(*args)
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)

    def test_duplicate_target_names_are_rejected(self):
        self.build_file('b.exe("same", {src: Path("pass.zen"), deps: []}).try();\n'
                        'b.exe_test("same", {src: Path("pass.zen"), deps: []}).try();')
        result = self.run_zen("test")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertNotIn("zen test: 1 passed", result.stdout)

    def test_selected_targets_cannot_share_an_executable(self):
        self.build_file('b.exe_test("first", {src: Path("fail.zen"), deps: [], '
                        'out: Ok(Path("build/shared"))}).try();\n'
                        'b.exe_test("last", {src: Path("pass.zen"), deps: [], '
                        'out: Ok(Path("build/shared"))}).try();')
        result = self.run_zen("test")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("selected targets share output", result.stdout)
        self.assertNotIn("zen test: 2 passed", result.stdout)

    def test_ordinary_build_does_not_execute_or_build_test_targets(self):
        self.write("broken.zen", 'main = () { missing(); }\n')
        self.build_file('b.exe("app", {src: Path("pass.zen"), deps: []}).try();\n'
                        'b.exe_test("test", {src: Path("broken.zen"), deps: []}).try();')
        result = self.run_zen("build")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse((self.root / "build/linux-x86_64/test").exists())

    def test_init_creates_a_runnable_project_and_never_overwrites(self):
        created = self.run_zen("init", "fresh app")
        self.assertEqual(created.returncode, 0, created.stdout + created.stderr)
        self.assertIn("Next: cd fresh app && zen run", created.stdout)
        project = self.root / "fresh app"
        self.assertEqual((project / ".gitignore").read_text(), "build/\n")
        self.assertIn('b.exe("fresh-app"', (project / "build.zen").read_text())
        ran = subprocess.run([str(ZEN), "run"], cwd=project,
                             env={**os.environ, "ZEN_STD": str(ROOT / "src")},
                             capture_output=True, text=True, timeout=90)
        self.assertEqual(ran.returncode, 0, ran.stdout + ran.stderr)
        self.assertEqual(ran.stdout, "Hello, world!\n")
        (project / "src/main.zen").write_text("main = () i32 { 3 }\n")
        again = self.run_zen("init", "fresh app")
        self.assertEqual(again.returncode, 1, again.stdout + again.stderr)
        self.assertIn("already exists", again.stdout)
        self.assertEqual((project / "src/main.zen").read_text(), "main = () i32 { 3 }\n")

    def recording_compiler(self):
        """A CC that logs its arguments, then runs the real compiler."""
        compiler = self.root / "recording-cc"
        compiler.write_text(f"#!{sys.executable}\nimport os, sys\n"
                            f"open({str(self.root / 'cc.log')!r}, 'a').write(' '.join(sys.argv[1:]) + '\\n')\n"
                            f"os.execv({shutil.which('cc')!r}, [{shutil.which('cc')!r}, *sys.argv[1:]])\n")
        compiler.chmod(0o755)
        return str(compiler)

    def last_command(self):
        return (self.root / "cc.log").read_text().splitlines()[-1].split()

    def test_modes_select_optimization_and_build_zen_reads_them(self):
        self.build_file('b.exe("app", {src: Path("pass.zen"), deps: [], '
                        'defines: ["ANSWER=42"], libs: ["m"], '
                        'strip: b.mode().match({ Debug => false, _ => true })}).try();')
        compiler = self.recording_compiler()
        size = "-Oz" if sys.platform == "darwin" else "-Os"
        for words, level in ((("run",), "-O0"), (("run", "--release"), "-O2"),
                             (("run", "--mode", "small"), size), (("build", "--mode=release"), "-O2")):
            result = self.run_zen(*words, "--cc", compiler)
            self.assertEqual(result.returncode, 0, (words, result.stdout + result.stderr))
            command = self.last_command()
            self.assertIn(level, command, words)
            self.assertIn("-DANSWER=42", command)
            self.assertIn("-lm", command)
            self.assertEqual(level != "-O0", "-s" in command or "-Wl,-x" in command, words)

    def test_target_settings_are_typed_and_written_fields_must_plan(self):
        self.build_file('b.exe("app", {src: Path("pass.zen"), deps: [], optimize: Optimize.Fastest}).try();')
        typo = self.run_zen("build")
        self.assertEqual(typo.returncode, 1, typo.stdout + typo.stderr)
        self.assertIn("no `Fastest` on `Optimize`", typo.stdout)
        self.build_file('b.exe("app", {src: Path("pass.zen"), deps: [], optimise: Optimize.Size}).try();')
        unknown = self.run_zen("build")
        self.assertEqual(unknown.returncode, 1, unknown.stdout + unknown.stderr)
        self.assertIn("an executable target has no field `optimise`", unknown.stdout)
        self.build_file('b.exe("app", {src: Path("pass.zen"), deps: [], optimize: pick()}).try();')
        self.write("build.zen", (self.root / "build.zen").read_text()
                   + "pick = () Optimize { Optimize.Size }\n")
        unplanned = self.run_zen("build")
        self.assertEqual(unplanned.returncode, 1, unplanned.stdout + unplanned.stderr)
        self.assertIn("field `optimize` cannot be planned", unplanned.stdout)

    def test_cc_option_overrides_build_zen_and_verbose_traces(self):
        self.build_file('b.exe("app", {src: Path("pass.zen"), deps: [], cc: Cc.Tcc}).try();')
        compiler = self.recording_compiler()
        result = self.run_zen("build", "-v", "--cc", compiler)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(compiler, result.stderr)
        self.assertIn("compile `app`", result.stderr)

    def test_usage_errors_name_the_command_and_its_targets(self):
        self.build_file('b.exe("app", {src: Path("pass.zen"), deps: []}).try();\n'
                        'b.exe("tool", {src: Path("pass.zen"), deps: []}).try();')
        bogus = self.run_zen("run", "--bogus")
        self.assertEqual(bogus.returncode, 2)
        self.assertIn("unknown option `--bogus` for `zen run`", bogus.stderr)
        self.assertIn("Usage: zen run", bogus.stderr)
        missing = self.run_zen("run", "build.zen")
        self.assertEqual(missing.returncode, 1)
        self.assertIn("its targets are: app, tool", missing.stdout)
        for words in (("-h", "run"), ("help", "run"), ("run", "--help")):
            helped = self.run_zen(*words)
            self.assertEqual(helped.returncode, 0, words)
            self.assertTrue(helped.stdout.startswith("Build and run an executable target"), words)

    def counting_compiler(self):
        """A CC that records each invocation; it refuses while cc.fail exists."""
        compiler = self.root / "counting-cc"
        compiler.write_text(f"#!{sys.executable}\nimport os, sys\n"
                            f"open({str(self.root / 'cc.log')!r}, 'a').write(' '.join(sys.argv[1:]) + '\\n')\n"
                            f"if os.path.exists({str(self.root / 'cc.fail')!r}): raise SystemExit(1)\n"
                            f"os.execv({shutil.which('cc')!r}, [{shutil.which('cc')!r}, *sys.argv[1:]])\n")
        compiler.chmod(0o755)
        return str(compiler)

    def links(self):
        log = self.root / "cc.log"
        return len(log.read_text().splitlines()) if log.exists() else 0

    def build_with(self, compiler, cflags="", command=("build",)):
        return subprocess.run([str(ZEN), *command], cwd=self.root,
            env={**os.environ, "ZEN_STD": str(ROOT / "src"), "CC": compiler, "CFLAGS": cflags},
            capture_output=True, text=True, timeout=90)

    def exit_status(self):
        return subprocess.run([str(self.root / "build/app")], timeout=10).returncode

    def generated_mtime(self):
        return (self.root / "build/.zen/app/program.c").stat().st_mtime_ns

    def test_unchanged_build_skips_native_compiler(self):
        self.build_file('b.exe("app", {src: Path("pass.zen"), deps: [], out: Ok(Path("build/app"))}).try();')
        compiler = self.counting_compiler()
        for expected, cflags in ((1, ""), (1, ""), (2, "-g")):
            result = self.build_with(compiler, cflags)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(self.links(), expected)
        published = (self.root / "build/app").stat().st_mtime_ns
        self.build_with(compiler, "-g")
        self.assertEqual((self.root / "build/app").stat().st_mtime_ns, published)
        self.write("pass.zen", "main = () i32 { 3 }\n")
        self.build_with(compiler, "-g")
        self.assertEqual((self.links(), self.exit_status()), (3, 3))
        for words, links in ((("build", "--release"), 4), (("build", "--release"), 4), (("build",), 5)):
            self.build_with(compiler, "-g", words)
            self.assertEqual(self.links(), links, words)
        (self.root / "build/app").unlink()
        self.build_with(compiler, "-g")
        self.assertEqual((self.links(), self.exit_status()), (6, 3))

    def test_failed_link_is_relinked_on_the_next_build(self):
        self.build_file('b.exe("app", {src: Path("pass.zen"), deps: [], out: Ok(Path("build/app"))}).try();')
        compiler = self.counting_compiler()
        self.assertEqual(self.build_with(compiler).returncode, 0)
        self.write("pass.zen", "main = () i32 { 5 }\n")
        (self.root / "cc.fail").touch()
        self.assertEqual(self.build_with(compiler).returncode, 1)
        (self.root / "cc.fail").unlink()
        self.assertEqual(self.exit_status(), 0)
        self.assertEqual(self.build_with(compiler).returncode, 0)
        self.assertEqual((self.links(), self.exit_status()), (3, 5))

    def test_unchanged_sources_skip_the_front_end(self):
        (self.root / "util").mkdir()
        self.write("util/util.zen", "value* = () i32 { 4 }\n")
        self.write("pass.zen", "util = util\nmain = () i32 { util.value() }\n")
        self.build_file('b.exe("app", {src: Path("pass.zen"), deps: [], out: Ok(Path("build/app"))}).try();')
        compiler = self.counting_compiler()
        self.assertEqual(self.build_with(compiler).returncode, 0)
        generated = self.generated_mtime()
        self.assertEqual(self.build_with(compiler).returncode, 0)
        self.assertEqual((self.generated_mtime(), self.links(), self.exit_status()), (generated, 1, 4))
        # A new flat module shadows the folder module without changing any
        # file the previous build read.
        self.write("util.zen", "value* = () i32 { 6 }\n")
        self.assertEqual(self.build_with(compiler).returncode, 0)
        self.assertNotEqual(self.generated_mtime(), generated)
        self.assertEqual((self.links(), self.exit_status()), (2, 6))
        self.write("util.zen", "value* = () i32 { 7 }\n")
        self.assertEqual(self.build_with(compiler).returncode, 0)
        self.assertEqual((self.links(), self.exit_status()), (3, 7))

    def test_failed_compile_is_not_reused(self):
        self.build_file('b.exe("app", {src: Path("pass.zen"), deps: [], out: Ok(Path("build/app"))}).try();')
        compiler = self.counting_compiler()
        self.assertEqual(self.build_with(compiler).returncode, 0)
        self.write("pass.zen", "main = () i32 { missing() }\n")
        for _ in range(2):
            self.assertEqual(self.build_with(compiler).returncode, 1)
        self.write("pass.zen", "main = () i32 { 0 }\n")
        result = self.build_with(compiler)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.exit_status(), 0)

    def test_suite_rejects_empty_and_reports_assertions(self):
        self.write("suite.zen", 'Suite = std.test\nRes, IoError = std.core\nEnv = std.env\n'
                   'main = (env: Env) Res<i32, IoError> {\n'
                   'suite ::= Suite(env: env);\nsuite.finish()\n}\n')
        self.build_file('b.exe_test("suite", {src: Path("suite.zen"), deps: []}).try();')
        empty = self.run_zen("test")
        self.assertEqual(empty.returncode, 1, empty.stdout + empty.stderr)
        self.assertIn("0 passed, 0 failed", empty.stdout)
        self.write("suite.zen", 'Suite = std.test\nRes, IoError = std.core\nEnv = std.env\n'
                   'main = (env: Env) Res<i32, IoError> {\n'
                   'suite ::= Suite(env: env);\n'
                   'suite.run("first", (t) { t.expect(false) }).try();\n'
                   'suite.run("last", (t) { t.expect_eq(2, 2) }).try();\n'
                   'suite.finish()\n}\n')
        failed = self.run_zen("test")
        self.assertEqual(failed.returncode, 1, failed.stdout + failed.stderr)
        self.assertIn("not ok first: expectation was false", failed.stdout)
        self.assertIn("ok last", failed.stdout)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zen", type=Path, default=ZEN)
    args, remaining = parser.parse_known_args()
    ZEN = args.zen.resolve()
    unittest.main(argv=[__file__, *remaining])
