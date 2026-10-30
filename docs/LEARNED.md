# Learned while building

Short, current facts that save the next person (or agent) an hour. Delete an entry when it stops being true.

## Writing Zen for the stage-0 compiler

| Fact | So write |
|---|---|
| `.try()` returns early only on `Err`/`None`; on `Ok` it unwraps and continues | early exit = an error value; a "return this value now" is an arm of the result expression |
| `.match` as a statement is not a return | make the whole function body the `.match` expression |
| Enums have no default `Eq` | compare with `.match`, or a `code()` method mapping variants to numbers |
| `u64` has no `Hash` and is not `Ordered` | no `Map<u64, _>` or `sort` on `u64`; a small open-addressing set if needed |
| `x.to_usize()` from `u64` is fallible (`Res`) | keep counts in `u32`/`usize`; shift counts are `usize` |
| `0.to_u64()` lexes as a float | typed bindings: `total :: u64 = 0` |
| A named function can't be passed as an argument | wrap it: `(c) { is_name(c) }` |
| `.try()` inside a value-producing `.match` arm fails in the C backend | convert first (`r = x.match({ .. => Ok(..), .. => Err(..) })`), then `r.try()` on its own line |
| A variant named like a std type (`Eq`, `OutOfBounds`) is read as that type | pick another name (`Equal`, `OutOfBoundsAccess`) |
| `self.f(self.field.add(x))` passes `self` by value while writing `self.field` | hoist: `r = self.field.add(x); self.f(r)` |
| A local function declaration takes no `;` | `set = (r: RegisterId) { .. }` then the next statement |
| Char literals work as `.match` patterns on `u8` | `c.match({ '(' => .., ':' => .., _ => .. })` |
| `variant_name()` exists but bypasses the `@` rule | use it until the new compiler has `@meta(v).variant.name` |
| An alias of a generic instance (`FunctionId = Id<Function>`) is treated as a different type | write `Id<Function>` directly; a non-generic alias (`Code = DiagnosticCode`) works |
| Record payloads can't be written inline in a variant (`\| Set: { dst: .. }`) | declare the record, then `\| Set: Set` |
| `bool.then` and `bool.ensure` live in `std.core` | `cond.ensure(reason).try();` is the one-line "fail unless"; `cond.then(() { .. })` is the one-sided action |
| A line may start with `.` to continue the previous expression | `(long condition)` then `    .ensure(..).try();` on the next line |

## Design lessons

- **A fault should cover the whole bad thing.** An unknown escape that ended at the escape made the closing quote open a new string: one error became two.
- **Validation is the gate for generated code.** Injected or transformed IR goes back through `validate`, so meta-programming can't break the IR's guarantees.
- **Reviews from a second model catch different things.** Gemini found a quadratic lookup the first review missed; the first found missing export and argument checks. Bundle the files: the Gemini CLI keeps only the last `-f`.
- **Formatting is about 8.7 tokens per line**, so budgets count tokens, not lines.

## From the review of #111

- **Check std first.** The lexer re-wrote `is_digit`, `is_space`, a u64 parser and a test printer that std already had.
- **Helpers are methods or a named module, never loose.** Text reads became `Source`; integer math became `Int`; IR constructors became `ir/build.zen`. Each change also made the code using them shorter.
- **Enums carry their numbers** (`= 1`, `.discriminant()`), and a represented enum's catch-all (`Explicit`) is made only by `from_discriminant`.
- **The stage-0 `zen fmt` fights the style** (it puts enum variants on one line), so layout is by hand, by STYLE.md's rules.
- **`.try()` inside a closure leaves the enclosing function.** A `std.test` body is therefore one expression; one check per test fits that anyway.
- **Mutation checks find weak tests.** Weakening the leading-zero rule went unnoticed until a two-digit case was added.
- **A function with `Alloc` and no `Env` can't wait or do IO.** The lexer takes `Alloc` on purpose; that's the rule from MEMORY_AND_ACTORS.md, not an oversight.

## From the second review of #111

- **"I don't want to read this" is the top gate.** The validator was 53 copies of a five-line `require` block; as one `ensure` line per rule it reads as a list of rules.
- **Zen had the guard all along:** `.then` and `ensure`. Before claiming the language lacks something, look in std.
- **A table stays a table:** every arm of `check_instruction` is one call; logic lives in the named rule it calls.
- **Questions about a record belong on the record** (`Symbol.is_function`, `must_be_defined`), not repeated inline.
- **Edit by line number or exact text, never by a loose pattern.** A `sed` meant for one `Ok` line matched seven, one of them making a function call itself.

## The first program

- **Run every test on both compilers.** `tests/stage0.sh` and `tests/fresh.sh` run the same files; when they disagree, one of them, or the test, is wrong. The first disagreement found a wrong test: `2147483647 + 1` is a provable trap, so §8 makes it a compile error.
- **Not yet in our checker:** refusing provable traps at compile time (§8). Stage 0 does it.
- **A test must be able to fail.** `add(40, 2)` couldn't catch swapped arguments, because `+` doesn't care about order; `sub(50, 8)` can, and swapping operands in lowering makes it exit 214 instead of 42.

## bool and .match

- **Point at the thing that's wrong.** Stage 0 reports a type error at the offending operand or arm value, not at the whole expression; ours does the same now.
- **Boundaries again:** `<` and `<=` only differ on equal operands, so a comparison test without `2 < 2` can't tell them apart. The mutation check found it.
- **Names belong in the tree.** A binding's name is the Let node's first child; reading it back out of the source text was a hack.
- **Find a mutation's line with grep, never by memory**: a guessed line number made one check silently change nothing.

## From the review of #112

| The language already has | So write |
|---|---|
| Error unions, widened by `.try()` | `Res<T, ParseError \| CheckError>`; no wrapper enum, no `.match` per stage. Match the union by type name. |
| `impl Eq` on an enum with discriminants | `Type.impl(Eq, { eq = .. self.discriminant() == other.discriminant() })`, then `t == Type.I32` |
| Limits of the primitives | `i32.MAX`; a value fits i32 when `.to_i32()` succeeds |
| Constants grouped on a type | `Limits.PARSE_DEPTH` in `src/limits.zen`, every limit in one place (Appendix J) |
| UFCS | `kids.push(x)` for a free function whose first parameter is the list |
| `ignore` | `.ignore()` to drop a result on purpose |

- **Built-in words are tokens.** `true`, `false` and `_` lex as their own kinds, so the parser, checker and lowering never compare text; only the lexer turns words into kinds.
- **`.then` takes a body, not a value.** `.then(h.break())` would break immediately; the body has to run only when true. The spec allows `.then({ h.break() })`; stage 0 needs `() { .. }`.
- **Missing in std, for our own:** `is_ok()` on `Res` (today `.match({ Ok(_) => true, None => false })`).

## Slice 3: imports, env.out.println, Res<IoError>, .try()

| Fact | So write |
|---|---|
| There is no `return`; `.try()` is the only early exit | pick a branch with `.match({ true => self.a(..), false => self.b(..) })`, each arm a method |
| A variant named like any std name (`Env`, `Path`, `Err`) is read as that name | `EnvType`, `Module`, `Stderr`: spell it as what it is here |
| `T.from_discriminant(k)` takes a `u64` and gives `Res<T>` | loop `Range(T.FIRST, T.END)` with `FIRST*: u64` constants on the type, to look a variant up by name |
| A function on a type needs no `self` | `Library.find(name, module)`: lookups live on the closed set they search |
| Constants on a type cross modules only with `*` | `FIRST*: u64 = 1` |
| A Vec<u8> is a str through `str_at(v.ptr(), v.len)` | no copy to print a global's bytes |

- **One exit code can't mean two things.** `tests/fresh.sh` read exit 1 as "refused", so a program whose `main` returns `Err` looked refused. `zen --check` now decides refusal, and the run is separate.
- **A mutation that's caught for the wrong reason is a gap.** An unknown call resolved to the first function was "caught" only because that function took no arguments; the test now has a one-argument function first.
- **Formats are pieces, read once.** `Format.pieces()` is shared by check (holes against arguments, errors at the hole) and lower (one write per piece), so the two can't disagree about where a hole is.
