#!/usr/bin/env python3
"""Stage one corpus test's root exactly as tests/run.py does.

usage: stage.py <zen> <base> <dest>

<base> is the test's `.expected` path without the suffix. The staged root
is written to <dest>/src: the test's files, std, and the compiler modules
it imports, by run.py's own manifest.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import run  # noqa: E402


def main() -> int:
    zen, base, dest = sys.argv[1:4]
    expected = (run.REPO_ROOT / (base + ".expected")).resolve()
    found = run.Collection()
    run.collect(run.TESTS_DIR, found, run.CORPUS)
    test = next((t for t in found.tests if t.expected_path.resolve() == expected), None)
    if test is None:
        print(f"stage.py: no corpus test expects {expected}", file=sys.stderr)
        return 1
    tool = run.Toolchain("zen", [zen], src_root=run.REPO_ROOT / "src")
    work = Path(dest)
    work.mkdir(parents=True, exist_ok=True)
    run.stage(test, tool, work)
    return 0


if __name__ == "__main__":
    sys.exit(main())
