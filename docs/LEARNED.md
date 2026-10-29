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
