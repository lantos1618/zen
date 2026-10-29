# What to test

The format and runner are in COMPILER.md E.2. A test catches one bug. Its first comment says which one, as the one-line compiler change that would break it. Each checklist line below should have at least one test in `tests/run` (program) or `tests/fail` (must-fail). Topics in parentheses are directories.

**Coverage rule:** every diagnostic code (E.1), every trap code, and every limit in Appendix J has at least one test that triggers it.

## Lexing and parsing (lex, parse)
- [ ] Integer literals: leading zero refused, the largest u64 accepted, one past it refused
- [ ] Escapes: each valid escape; an unknown escape refused; EOF inside an escape
- [ ] Unterminated string, char and block comment, each at its opening position
- [ ] Multi-line `"""` strings: indentation checked; text after the opening refused
- [ ] Bit operators beside other operators need parentheses
- [ ] `;` ends statements and declarations take none; a binding is never a block's value
- [ ] The `() i32` return-type ambiguity in expression position
- [ ] Nesting at the depth limit passes; one past it gives `ResourceLimit`, not a crash
- [ ] Error positions point at the token, not the line start

## Names and modules (modules, imports)
- [ ] Unknown name, duplicate in one scope, shadowing in a nested scope
- [ ] Missing import: the error names the fix
- [ ] Private name imported from another module refused; re-export through `*`
- [ ] Import cycles; a module named by its folder; no prelude
- [ ] Mutual recursion across declarations (collect before bodies)

## Types and fit (sema, generics, trait-bound)
- [ ] A literal fits any type whose range holds it; one out of range refused
- [ ] Mixed-type arithmetic (`i32 + usize`) refused, naming both conversions
- [ ] Overloads: none fits, exactly one, two fit (ambiguous)
- [ ] Generic inference from arguments; a written type argument; `i32` / `i64` literal default
- [ ] An error in an uninstantiated generic body is still reported
- [ ] The same generic instance from two modules is one type
- [ ] Bounds: a missing member, a computed field, a sealed member overridden
- [ ] Construction by name; defaults; omitted `Res<T>` is `None`; an unknown field

## Mutability and ownership (own, ownership-*)
- [ ] Writing through a `:` binding or a `:` path is refused; `::` on every field of the path
- [ ] A `::` parameter is the caller's storage: the caller sees the write
- [ ] Use after `.consume()`; consume in a loop body; consume on one branch only
- [ ] Drop runs exactly once: normal exit, `h.break`, `h.next`, `.try()`, early return
- [ ] Defers run in reverse, per scope, on every exit; none on a trap
- [ ] A maybe-moved local is dropped only on the paths where it wasn't moved (drop flag)
- [ ] A trait value or a handle can't outlive the storage it points at

## Control flow (match-*, loop-*, closures-capture)
- [ ] Match is exhaustive per level; a missing variant is named; `_` covers the rest
- [ ] An unreachable arm is refused
- [ ] Ranges: both bounds, the half-open end, empty ranges
- [ ] Nested patterns: outer and inner tag both tested; payloads bound correctly
- [ ] All four bool forms and `.then` give the same branch; `.then` gives `Ok`/`None`
- [ ] Loops: zero iterations, `break` value, `next`, a nested `break` exits only the inner loop
- [ ] Fold: accumulator type, an early `break` result
- [ ] A local closure reads live captures and writes a captured `::=`
- [ ] Inlining at the depth limit; a self-reaching closure gives `ResourceLimit`

## Definite initialization and must-use (flow)
- [ ] `label :: str;` assigned on one branch only, then read: refused
- [ ] Assigned inside a loop, read after it: the first-iteration path is refused
- [ ] A dropped failing `Res` is refused; `.ignore()` accepts it
- [ ] A failing `Res` bound and unused on one path is refused

## Errors (errors-*)
- [ ] The three `Res` forms; `.try()` on `Err` and on `None`
- [ ] A `None` never becomes an `Err` without `ok_or`
- [ ] `main` returning `Err` exits 1; `Ok(n)` exits n

## Arithmetic and traps (traps, div-mod-traps, integer-widening, casts-conversions, bitwise)
- [ ] For every width: MIN, MAX, and MAX + 1 trapping for `+ - *`, signed and unsigned
- [ ] `+% -% *%` wrap at every width
- [ ] `/ %` by zero; `MIN / -1` and `MIN % -1`
- [ ] Shifts: a count ≥ width; signed versus logical shift right
- [ ] Checked conversions at each boundary; float to integer NaN, ±inf, 2^63
- [ ] Narrow types are kept normalized after spills and calls
- [ ] A provable trap (`i32.MAX + 1`, a literal index past the end) is a compile error
- [ ] Trap message format: exact `file:line:col` for frontend checks; exit 134

## Values and layout (struct-*, arrays, enum-*, vec)
- [ ] Field order, padding and nested offsets; a copy is independent of its source
- [ ] Return by value, small and large; `a = a` self-assignment
- [ ] Array bounds: the last index works, one past it traps
- [ ] Enum tag and payload offsets; a unit-only enum in a register

## Calls and ABI (codegen, bindings)
- [ ] More arguments than registers (stack arguments); mixed int and float arguments
- [ ] Left-to-right evaluation with side effects in arguments and both sides of a binary operation
- [ ] Recursion and mutual recursion; values live across calls
- [ ] C calls in both directions; a `callback` passed to C

## Floats (math)
- [ ] NaN compares; ±0; subnormals; printing round-trips

## Text and printing (string-*, printing, fmt)
- [ ] `str` is bytes: length, equality, UTF-8 as bytes
- [ ] Format: `{}`, `{name}`, `{{`; a bad format refused at compile time

## Comptime and meta (meta)
- [ ] A field walk over a struct; typecase arms; the step limit; an `Env` use refused

## Environment (env, env-args, stdin, file-io, cli)
- [ ] args, stdin bytes exactly, files, exit codes
- [ ] A CLI type: a positional `:`, an option `::`, an unknown flag, a missing positional

## Memory and actors (T2, when `std/actor` exists; MEMORY_AND_ACTORS.md)
- [ ] A value from a dropped arena can't be stored or returned past it (`REGION`)
- [ ] Send rule: plain, `str`, `val` and a consumed `Region` pass; a `Vec` in the sender's arena, a `Ptr` or a trait value is refused with the fix named
- [ ] A send to a full mailbox answers `Full` and never waits; a send to a stopped actor answers `Closed`
- [ ] `ask`: answered, `Timeout`, `Closed` (receiver ended or dropped its `Reply`), `Cycle` (A asks B asks A)
- [ ] A late reply after a timeout is dropped and never writes into the returned frame
- [ ] `@scope.deadline` and `cancel_on`: a pending wait returns `Cancelled`/`Timeout` and the scope's defers run
- [ ] Stack-checked profile: deep recursion in an actor traps `StackOverflow` and ends only that actor; the same depth behaves the same in `main`
- [ ] A trap in one actor: its watchers get `failed`, its arena and pool are freed, other actors keep running
- [ ] The same function run with `main`'s `Env` and an actor's `Env` gives the same result
- [ ] A C callback with an `Env` parameter is refused; an `Env` can't be sent or stored in another actor
- [ ] Seeded schedules: every test above passes under several `ZEN_ACTOR_SEED` values, and a failure names its seed
- [ ] `Pool`: a long-lived actor that churns stays at a stable size

## Build and packages (when `src/build` exists)
- [ ] A lock mismatch is an error; no network when the lock covers the graph
- [ ] A dependency's `build` never runs; only products import
- [ ] Minimal version selection picks the highest minimum; a major-version conflict names both requirers

## Whole compiler
- [ ] Determinism: same input, byte-identical output (C, assembly, Ir dump)
- [ ] Self-host: C(stage 2) == C(stage 3) (Appendix K)
- [ ] IR level: the E.2 rows (differential fuzzing and mutations) once `src/ir` and `src/back` exist
