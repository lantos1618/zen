#!/usr/bin/env python3
"""The scoreboard: one command that measures the compiler, so progress is a number.

    tools/score.py            print the score
    tools/score.py --record   also append it to bench/history.tsv (commit that file)

Fails (exit 1) when a unit check fails, or when fewer tests or checks pass than in the last
recorded row; a run that got worse is not recorded.

What it measures:
    size    tokens per stage and in total (tools/budget.py); non-blank source lines
    tests   tests/run and tests/fail on our compiler (tests/fresh.sh) and on stage 0
    units   every std.test suite under src/ (passed and failed checks)
    build   seconds to build our compiler with stage 0, and the binary's size
"""
import datetime
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import budget  # noqa: E402

HISTORY = ROOT / "bench" / "history.tsv"
COLUMNS = ["date", "commit", "tokens", "lines", "run_ours", "fail_ours", "run_stage0", "fail_stage0",
           "units_passed", "units_failed", "build_s", "binary_kb"]


def sh(*args: str) -> str:
    return subprocess.run(args, cwd=ROOT, capture_output=True, text=True).stdout


def size() -> dict:
    tokens = lines = 0
    stages = {}
    for part in budget.BUDGETS:
        path = ROOT / part
        n, l = budget.size(path) if path.exists() else (0, 0)
        tokens, lines = tokens + n, lines + l
        if n:
            stages[part] = n
    return {"tokens": tokens, "lines": lines, "stages": stages}


# "run 7 / 7" and "fail 6 / 6" from tests/run.py.
def tests(adapter: str) -> tuple[str, str]:
    out = sh("python3", "tests/run.py", "--compiler", adapter)
    found = dict(re.findall(r"^(run|fail)\s+(\d+ / \d+)", out, re.M))
    return found.get("run", "0 / 0"), found.get("fail", "0 / 0")


def units() -> tuple[int, int, list]:
    passed = failed = 0
    report = []
    for suite in sorted(ROOT.glob("src/**/*.zen")):
        if "Suite(" not in suite.read_text():
            continue
        entry = str(suite.relative_to(ROOT / "src"))
        m = re.search(r"(\d+) passed, (\d+) failed", sh("tools/zen0.sh", entry))
        p, f = (int(m.group(1)), int(m.group(2))) if m else (0, 1)
        passed, failed = passed + p, failed + f
        report.append((entry, p, f))
    return passed, failed, report


def build() -> tuple[float, int]:
    start = time.time()
    sh("tools/zen0.sh", "-o", "build/zen", "main.zen")
    binary = ROOT / "build" / "zen"
    return round(time.time() - start, 1), (binary.stat().st_size // 1024 if binary.exists() else 0)


# What got worse since the last recorded row: fewer tests or unit checks passing.
def regressions(now: dict) -> list:
    if not HISTORY.exists():
        return []
    last = dict(zip(COLUMNS, HISTORY.read_text().splitlines()[-1].split("\t")))
    passed = lambda v: int(str(v).split(" / ")[0])
    return [f"{k}: {last[k]} -> {now[k]}" for k in ["run_ours", "fail_ours", "run_stage0", "fail_stage0",
            "units_passed"] if passed(now[k]) < passed(last[k])]


def main() -> int:
    s = size()
    build_s, binary_kb = build()                     # first: the test adapter runs this binary
    run_ours, fail_ours = tests("tests/fresh.sh")
    run_stage0, fail_stage0 = tests("tests/stage0.sh")
    units_passed, units_failed, suites = units()

    print(f"size     {s['tokens']} tokens, {s['lines']} lines")
    for part, n in s["stages"].items():
        print(f"           {part:20} {n:6}")
    print(f"tests    ours:    run {run_ours}, fail {fail_ours}")
    print(f"         stage 0: run {run_stage0}, fail {fail_stage0}")
    print(f"units    {units_passed} passed, {units_failed} failed")
    for entry, p, f in suites:
        print(f"           {entry:32} {p} passed, {f} failed")
    print(f"build    {build_s} s, binary {binary_kb} KiB")

    commit = sh("git", "rev-parse", "--short", "HEAD").strip()
    row = [datetime.date.today().isoformat(), commit, s["tokens"], s["lines"], run_ours, fail_ours,
           run_stage0, fail_stage0, units_passed, units_failed, build_s, binary_kb]
    worse = regressions(dict(zip(COLUMNS, row)))
    for w in worse:
        print(f"WORSE    {w}")
    if "--record" in sys.argv and not worse:
        HISTORY.parent.mkdir(exist_ok=True)
        new = not HISTORY.exists()
        with HISTORY.open("a") as h:
            if new:
                h.write("\t".join(COLUMNS) + "\n")
            h.write("\t".join(str(v) for v in row) + "\n")
        print(f"recorded in {HISTORY.relative_to(ROOT)}")
    return 0 if units_failed == 0 and not worse else 1


if __name__ == "__main__":
    sys.exit(main())
