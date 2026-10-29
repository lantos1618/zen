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

## Design lessons

- **A fault should cover the whole bad thing.** An unknown escape that ended at the escape made the closing quote open a new string: one error became two.
- **Validation is the gate for generated code.** Injected or transformed IR goes back through `validate`, so meta-programming can't break the IR's guarantees.
- **Reviews from a second model catch different things.** Gemini found a quadratic lookup the first review missed; the first found missing export and argument checks. Bundle the files: the Gemini CLI keeps only the last `-f`.
- **Formatting is about 8.7 tokens per line**, so budgets count tokens, not lines.
