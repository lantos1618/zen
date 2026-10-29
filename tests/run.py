#!/usr/bin/env python3
"""Run tests/run (programs) and tests/fail (must-fail) against any compiler.

    tests/run.py --compiler CMD [--jobs N] [--baseline FILE [--update]] [PATH ...]

CMD is called as `CMD <test> <exe>`, where <test> is a .zen file or a directory
holding main.zen (or <dir>.zen). Exit 0 means <exe> was built; anything else
means the program was refused, with diagnostics on stderr.

A test states what it expects in `//!` lines at the end of its entry file:

    //! out: <line>        stdout, one line each, exact      //! out-no-eol
    //! exit: <code>       exit status (default 0)
    //! err: <text>        stderr contains <text>
    //! stdin: <line>      program input, one line each      //! stdin-no-eol
    //! arg: <word>        program argument
    //! env: KEY=VALUE     program environment
    //! error: L:C         must-fail: a diagnostic at L:C (or file.zen:L:C, or `any`)
    //! hint: <text>       what the diagnostic should say (not checked)
"""
import argparse, os, re, subprocess, sys, tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TIMEOUT = 30


def entry_of(test: Path) -> Path:
    if test.is_file():
        return test
    for name in ("main.zen", test.name + ".zen"):
        if (test / name).is_file():
            return test / name
    raise FileNotFoundError(f"{test}: no main.zen or {test.name}.zen")


def directives(test: Path) -> dict[str, list[str]]:
    d: dict[str, list[str]] = {}
    for line in entry_of(test).read_text().splitlines():
        m = re.match(r"//! ([a-z-]+):? ?(.*)$", line)
        if m:
            d.setdefault(m.group(1), []).append(m.group(2))
    return d


def lines_to_bytes(d, key):
    if key not in d:
        return b""
    return ("\n".join(d[key]) + ("" if f"{key}-no-eol" in d else "\n")).encode()


def check(compiler: list[str], test: Path) -> str | None:
    """None when the test passes, else one line saying why not."""
    d = directives(test)
    must_fail = "error" in d
    with tempfile.TemporaryDirectory() as tmp:
        exe = Path(tmp) / "a.out"
        try:
            built = subprocess.run([*compiler, str(test), str(exe)], capture_output=True,
                                   timeout=TIMEOUT)
        except subprocess.TimeoutExpired:
            return "compiler timed out"
        diag = built.stderr.decode("utf-8", "replace")
        if must_fail:
            if built.returncode == 0:
                return "accepted a program that must fail"
            wanted = [p for p in d["error"] if p != "any"]
            if wanted and not any(re.search(rf"(^|[^\d]){re.escape(p)}([^\d]|$)", diag) for p in wanted):
                return f"refused, but not at {' or '.join(wanted)}: {first_line(diag)}"
            return None
        if built.returncode != 0 or not exe.is_file():
            return f"refused: {first_line(diag)}"
        env = {"PATH": os.environ.get("PATH", ""), **dict(e.split("=", 1) for e in d.get("env", []))}
        try:
            ran = subprocess.run([str(exe), *d.get("arg", [])], input=lines_to_bytes(d, "stdin"),
                                 capture_output=True, timeout=TIMEOUT, env=env, cwd=tmp)
        except subprocess.TimeoutExpired:
            return "program timed out"
    want_code = int(d.get("exit", ["0"])[0])
    if ran.returncode != want_code:
        return f"exit {ran.returncode}, wanted {want_code}: {first_line(ran.stderr.decode('utf-8', 'replace'))}"
    if ran.stdout != lines_to_bytes(d, "out"):
        return f"stdout differs: got {first_line(ran.stdout.decode('utf-8', 'replace'))!r}"
    err = ran.stderr.decode("utf-8", "replace")
    missing = [e for e in d.get("err", []) if e not in err]
    return f"stderr lacks {missing[0]!r}" if missing else None


def first_line(text: str) -> str:
    return next((l for l in text.splitlines() if l.strip()), "(nothing)")[:160]


def collect(paths: list[Path]) -> list[Path]:
    """A path is a test, a topic (tests/run/<topic>), or a tree holding topics."""
    tests = []
    for base in paths:
        if base.suffix == ".zen" or base.parent.parent.name in ("run", "fail"):
            tests.append(base)
            continue
        topics = [base] if base.parent.name in ("run", "fail") else sorted(
            p for p in base.rglob("*") if p.is_dir() and p.parent.name in ("run", "fail"))
        for topic in topics:
            tests += [i for i in sorted(topic.iterdir()) if i.suffix == ".zen" or i.is_dir()]
    return tests


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--compiler", required=True, help="command called as CMD <test> <exe>")
    ap.add_argument("--jobs", "-j", type=int, default=os.cpu_count() or 1)
    ap.add_argument("--baseline", type=Path, help="file of passing test ids to compare against")
    ap.add_argument("--update", action="store_true", help="rewrite --baseline with this run's passes")
    ap.add_argument("--verbose", "-v", action="store_true", help="print every failure")
    ap.add_argument("paths", nargs="*", type=Path, default=[ROOT / "run", ROOT / "fail"])
    args = ap.parse_args()

    compiler = args.compiler.split()
    tests = collect([p.resolve() for p in args.paths])
    with ThreadPoolExecutor(args.jobs) as pool:
        results = list(pool.map(lambda t: (t, check(compiler, t)), tests))

    ident = lambda t: str(t.relative_to(ROOT))
    passed = {ident(t) for t, why in results if why is None}
    for kind in ("run", "fail"):
        mine = [ident(t) for t, _ in results if ident(t).startswith(kind + "/")]
        if mine:
            print(f"{kind:5} {sum(i in passed for i in mine):5} / {len(mine)}")
    if args.verbose:
        for t, why in results:
            if why:
                print(f"FAIL {ident(t)}: {why}")

    if not args.baseline:
        return 0 if len(passed) == len(results) else 1
    if args.update:
        args.baseline.write_text("".join(f"{i}\n" for i in sorted(passed)))
        print(f"baseline: {len(passed)} passing ids written to {args.baseline}")
        return 0
    before = set(args.baseline.read_text().split()) if args.baseline.is_file() else set()
    ran = {ident(t) for t, _ in results}
    lost = sorted((before & ran) - passed)
    gained = sorted(passed - before)
    why = {ident(t): w for t, w in results}
    for i in lost:
        print(f"REGRESSED {i}: {why[i]}")
    print(f"baseline: {len(gained)} newly passing, {len(lost)} regressed")
    return 1 if lost else 0


if __name__ == "__main__":
    sys.exit(main())
