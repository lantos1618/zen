#!/usr/bin/env python3
"""Fail when a part of the compiler grows past its line budget (COMPILER.md H, I, L).

Counts non-blank lines in every .zen file under each budgeted directory.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

BUDGETS = {                       # directory -> lines
    "src/front/parse": 2_000,     # lex + parse
    "src/front/collect": 1_000,
    "src/front/check": 4_000,     # fit + types + resolve + cull
    "src/front/lower": 5_000,
    "src/front/flow": 800,
    "src/ir": 2_000,              # records, builder, validate, interpreter
    "src/back": 3_000,            # native: templates, alloc, write (both ISAs)
    "src/c": 1_500,               # C route
    "src/build": 1_800,           # build.zen, packages, FFI (BUILD_AND_PACKAGES.md 9)
    "src/std": 4_000,
    "runtime/zen_rt.c": 200,      # C: entry, traps, Env glue
    "runtime/actor": 400,         # C: threads, mailboxes, stack switch (T2)
}
TOTAL = 25_000


def lines(path: Path) -> int:
    files = [path] if path.is_file() else [*path.rglob("*.zen"), *path.rglob("*.c"), *path.rglob("*.h")]
    return sum(1 for f in files for l in f.read_text().splitlines() if l.strip())


def main() -> int:
    over, total = 0, 0
    for part, budget in BUDGETS.items():
        path = ROOT / part
        n = lines(path) if path.exists() else 0
        total += n
        mark = "OVER" if n > budget else "ok"
        over += n > budget
        print(f"{part:20} {n:6} / {budget:6}  {mark}")
    print(f"{'total':20} {total:6} / {TOTAL:6}  {'OVER' if total > TOTAL else 'ok'}")
    return 1 if over or total > TOTAL else 0


if __name__ == "__main__":
    sys.exit(main())
