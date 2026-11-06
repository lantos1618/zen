#!/usr/bin/env python3
"""Fail when a part of the compiler grows past its budget (COMPILER.md H, I, L).

Size is counted in tokens, not lines, so formatting never changes it: comments,
whitespace and line breaks are free; every name, literal, operator and bracket
counts. Test files (`*test*`) are not compiler size.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# directory -> tokens. Each is the earlier line budget times 10. Measured on src/ir
# (2026-10-29): formatted Zen is about 8.7 tokens per non-blank line.
BUDGETS = {
    "src/front/parse": 20_000,     # lex + parse
    "src/front/collect": 10_000,
    "src/front/check": 40_000,     # fit + types + resolve + cull
    "src/front/lower": 50_000,
    "src/front/flow": 8_000,
    "src/ir": 20_000,              # records, builder, validate, interpreter
    "src/back": 30_000,            # native: templates, alloc, write (both ISAs)
    "src/c": 15_000,               # C route
    "src/build": 18_000,           # build.zen, packages, FFI (BUILD_AND_PACKAGES.md 9)
    "src/std": 40_000,
    "runtime/zen_rt.c": 2_000,     # C: entry, traps, Env glue
    "runtime/actor": 6_000,        # C: workers, stealing, poller, monitor, stack switch (T2)
}
TOTAL = 250_000

TOKEN = re.compile(r'"""[\s\S]*?"""|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|[A-Za-z_][A-Za-z0-9_]*|\d[\w.]*|::=|::|=>|->|[+\-*%]%|[<>=!]=|&&|\|\||\S')
COMMENT = re.compile(r"//[^\n]*|/\*[\s\S]*?\*/")


def tokens(text: str) -> int:
    return len(TOKEN.findall(COMMENT.sub(" ", text)))


def size(path: Path) -> tuple[int, int]:
    files = [path] if path.is_file() else [*path.rglob("*.zen"), *path.rglob("*.c"), *path.rglob("*.h")]
    product = [f for f in files if "test" not in f.stem]
    texts = [f.read_text() for f in product]
    return sum(tokens(t) for t in texts), sum(1 for t in texts for l in t.splitlines() if l.strip())


def main() -> int:
    over, total = 0, 0
    print(f"{'part':20} {'tokens':>8} / {'budget':>7}  {'lines':>6}")
    for part, budget in BUDGETS.items():
        path = ROOT / part
        n, lines = size(path) if path.exists() else (0, 0)
        total += n
        over += n > budget
        print(f"{part:20} {n:8} / {budget:7}  {lines:6}  {'OVER' if n > budget else 'ok'}")
    print(f"{'total':20} {total:8} / {TOTAL:7}          {'OVER' if total > TOTAL else 'ok'}")
    return 1 if over or total > TOTAL else 0


if __name__ == "__main__":
    sys.exit(main())
