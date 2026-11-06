# Working on the Zen compiler

**Goal:** a small compiler that works, covers the language, reads well, and has a low attack
surface. Every change leaves it working, measured, and readable by a person in one sitting.

**Read first:** `docs/ZEN_LANGUAGE.md` (the language), `docs/COMPILER.md` (the design),
`docs/STYLE.md` (how code looks), `docs/LEARNED.md` (stage-0 quirks and lessons).

## The loop: one slice at a time

A slice is the smallest step that makes one more kind of program run.

1. **Pick the next slice** from the roadmap below. Don't start two.
2. **Write its target program and tests first:** `tests/run/<slice>/` and `tests/fail/<slice>/`.
   Each test's first comment names the compiler mistake it catches.
3. **Show a taste sample** (about 30 lines of the new code's shape) before writing volume.
4. **Implement it through every stage:** parse, check, lower, then IR and the interpreter.
5. **Pass the gates** (below).
6. **Mutation-check it:** break the new code in one place per test; each break must fail a test.
   A break that passes means the tests have a gap: add the missing case.
7. **Record:** `tools/score.py --record`, plus a `docs/LEARNED.md` entry if something was learned.
8. **Open a focused PR** with the template, then wait for review before the next slice.

## Gates: all must pass before a commit

```sh
tools/zen0.sh -o build/zen main.zen                       # our compiler builds with stage 0
python3 tests/run.py --compiler tests/fresh.sh            # no test that passed before fails now
python3 tests/run.py --compiler tests/stage0.sh           # stage 0 agrees, or the difference is explained
tools/score.py                                            # unit suites all pass; read the numbers
python3 tools/budget.py                                   # every stage within its token budget
awk 'length > 115' src/**/*.zen                           # prints nothing
```

## Rules learned in review

- **Check the language and std first.** Error unions widen through `.try()`; `impl Eq` with
  discriminants gives `==`; `i32.MAX`; constants on a type; UFCS; `ensure`, `then`, `ok_or`,
  `ignore`. A workaround or macro for something the language has is a failed change.
- **No loose helpers.** A helper is a method on the type it serves, or part of one named module.
  The same few lines twice means a shared method.
- **Closed sets are enums**, one variant per line with a leading bar, numbers as discriminants.
- **Built-in words are tokens.** No stage after the lexer compares text.
- **Errors point at the thing that's wrong**: the operand, the value, the arm.
- **Tests:** `std.test` for units, one check per test, names that state the rule.
- **Edit by exact text or line number found with `grep`**, never by a loose pattern.
- **Say what was checked.** Every commit message ends with how the change was verified.

## Roadmap

| # | Slice | Runs | Status |
|---|---|---|---|
| 1 | functions, calls, `i32` arithmetic | `sub(50, 8)` exits 42 | done |
| 2 | bool, comparisons, `.match`, bindings | max/abs exits 13 | done |
| 3 | imports, `env.out.println`, `Res<IoError>`, `.try()` | tests/run/print | next |
| 4 | loops, closures, `.then({ .. })`, `h.break` | sum of a range | |
| 5 | structs: construction, fields, copies | a point's fields | |
| 6 | enums and `.match` on variants | a shape's area | |
| 7 | `Res`, `.try()`, error unions | parsing a number | |
| 8 | provable traps refused, integer widths and casts | `i32.MAX + 1` refused | |
| 9 | `str`, `Vec`, arenas (our own `std`) | the lexer's tests | |
| 10 | self-hosting: our compiler builds itself | C(stage 2) == C(stage 3) | |

## Size

Budgets are in tokens per stage (`tools/budget.py`, COMPILER.md Appendix I). A slice should
add the least code that runs its program. If a stage nears its budget, simplify before adding.
