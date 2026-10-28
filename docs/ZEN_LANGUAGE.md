# Zen — the language on one page

A small, statically typed systems language with explicit allocation, capabilities
passed in through `Env`, errors as values, and one control-flow construct.
Distilled from `docs/DESIGN.md`. Each section is tagged with the compiler pass that owns it
and a **tier**: **T0** the compiler needs to build itself, **T1** everyday programs,
**T2** later or optional.

```text
 lex/parse ─► collect ─► fit ─► resolve ─► cull ─► lower ─► Ir ─► flow ─► C | native
 syntax       names,     shapes,  pin names  reach   to §1    validated  init, moves,
              signatures qualifiers          main    Ir       once       must-use
```

## 1. Laws (everything follows from these)

1. **No ambient allocator.** Allocation takes an `Alloc`.
2. **No ambient authority.** IO, net, pages, threads, spawning: all come from the `Env` that `main` receives. (One exception: `println`.)
3. **Satisfy requirements, never impl storage.** Layout is fixed at declaration.
4. **Failure stays visible.** Only success lifts into `Res`; `Err` and `None` are always written.
5. **`Res` is for failures a caller can act on; a trap is for a bug.**
6. **`*` means the name crosses a module boundary**, so its type is written, not inferred.
7. **The signature answers the question**: allocates? mutates? fails? escapes?

## 2. Lexical — *lex/parse, T0*

Reject rather than reinterpret: no `010` (leading zeros), no unknown escapes, integer literals must fit u64.
`;` ends a statement; a declaration has no `;`. Comments `//`. Multi-line strings `"""…"""` with checked indentation.
Bit operators beside other operators need parentheses: `(a & b) == c`.

## 3. Bindings and functions — *fit, T0*

```zen
x = 1                    // immutable
y: i64 = 2               // immutable, typed
n ::= 0                  // mutable
c :: Circle = Circle(radius: 2.0)
label :: str;            // declared now, assigned before any read (flow checks)

add  = (a: i32, b: i32) i32 { a + b }       // tail expression is the result
log  = (msg: str) { println(msg) }           // unit function
add* = (a: i32, b: i32) i32 { a + b }        // exported: types must be written
```

A function declared inside a body is a **local closure**: inlined where it is called, it reads the frame's bindings live, and it cannot be stored or returned.

## 4. Types — *collect + fit, T0*

| Kind | Spelling |
|---|---|
| Primitives | `bool` `i8..i64` `u8..u64` `u128` `usize` `f32` `f64` `str` (borrowed bytes) `()` |
| Fixed arrays | `[u8, 64]`: the count is part of the type, and indexing is bounds-checked |
| Struct | `Point = { x: i32, y :: i32, z :: i32 = 0 }`: `:` set once, `::` mutable, `= v` default |
| Constant on a type | `Limits = { WIDTH: usize = 80 }`, read as `Limits.WIDTH` |
| Enum | `Shape = { Circle: f64 \| Rect: Rect \| Unit }`, one-variant form `{ \| Only }` |
| Union of types | `Error = AllocError \| IoError`: identity is the member set, not its order |
| Alias | `Alias = Shape`: the same type |
| Generic | `Box<T> = { value: T }`, `Vec<T>`, `Res<V, E>` |
| Function type | `(a: i32, b: i32) i32`: parameters are named |
| Raw pointer | `Ptr<T>`: outside the safety model (`p.read(i)` is C's `p[i]`) |

Construction is by name: `Point(x: 1, y: 2)`. Omitted fields take their default. Omitted `Res<T>` fields are `None`.

## 5. Control flow: `.match` is the only conditional — *fit + lower, T0*

```zen
n.match({ 0 => "zero", 1 => "one", _ => "many" })      // exhaustive, always
shape.match({ Circle(r) => r * r, Rect(w) => w.area(), Unit => 0.0 })

b.match({ true => a, false => c })    // arms
b.match({ a }, { c })                 // positional (T, F) bodies
b.match({ a })                        // F omitted == b.then({ a })
b.then({ a })                         // one-sided: Ok(a) / None
// `() { a }` closures are accepted anywhere `{ a }` is
```

There is no `if`, no ternary and no `?`. All four bool forms lower to one `Branch`.

## 6. Loops and early exit — *lower, T0*

```zen
Range(0, 10).loop((i) { .. })                    // i32 from the literals
items.loop((h, i, v) { (v == 0).then({ h.break(i) }) })   // handle: break(v) / next()
total = Range(0, 100).loop(0, (h, i, v, acc: i32) { acc + v }).value_or(0)   // fold
```

`loop` is an ordinary function. Its closure is inlined, and `h.break` / `h.next` are jumps. `Seq<T>` (`start`, `end`, `at`) is what a loop walks; arrays and `Range` are built in.
`.try()` is the same non-local exit: it returns `Err`/`None` from the enclosing function.

## 7. Errors — *fit + flow, T0*

| Written | Means |
|---|---|
| `Res<V>` (V not an Error) | `Ok(V) \| None`: absence |
| `Res<R>` (R implements `Error`) | `Ok \| Err(R)`: unit success or failure |
| `Res<V, E>` | `Ok(V) \| Err(E)` |

```zen
read_cfg  = (p: Path) Res<Cfg, _>                      // inferred inside a module
read_cfg* = (p: Path) Res<Cfg, IoError | ParseError>   // written at the boundary
row = table.get("ada").ok_or(Error.NotFound).try()     // a None never becomes an Err
out.fmt("{}\n", n).ignore()                            // dropping a failure is written down
```

There is no `From` and no implicit conversion. A dropped failing `Res` is a compile error (must-use, checked in flow).
A type is an error because `T.impl(Error, {..})` says so, never because of its name.

## 8. The failure model (traps) — *lower, T0*

`+ - *` trap on overflow (signed and unsigned); `+% -% *%` wrap. `/ %` trap on zero and on `MIN / -1`.
`[i]` on fixed arrays traps out of bounds. A trap prints `file:line:col: trap: <what>` and exits 134.
A trap the compiler can **prove** (`i32.MAX + 1`, a literal index past the end) is a compile error.
Bit operations `& | ^ ~ << >>` work on unsigned words only and never trap.

## 9. Ownership — *fit (qualifiers) + flow (paths), T0*

```zen
get* = (self: @Self, i: usize) Res<T>              // reads
add* = (self :: @Self, value: T) Res<AllocError>   // writes its own bytes
v ::= alloc.Vec<i32>();  v.add(1).try();           // a `:` binding could not call add

g = f.consume();      // move, written at the use; f is dead afterwards
@scope.defer({ cleanup() })                         // runs at block exit, then drops in reverse
```

- **No implicit receiver.** A method is a function whose first parameter is `self`.
- **`::` is shallow.** It means "writes my own bytes". A handle's methods (`Alloc`, `Ref`) are `:` even when they change the world behind the handle.
- **Passing is borrowing; `consume` moves.** A `Drop` value cannot be copied. There is no `Clone`.
- **As type qualifiers in `fits()`:** `::` (MUT), `Secret<T>`, values bound to `@scope`, an arena or a frame (SCOPED / REGION / FRAME), move-only kinds.
- **Path-sensitive, in flow:** use-after-move, definite assignment, must-use.
- **Across actors only `val` (deeply immutable) or `iso` (unique, via `.consume()`).** No capability syntax: it's proven at each send. Data races are compile errors.

## 10. Bounds and impls (no traits, only structs) — *collect + fit, T0*

```zen
Rect = { width: f64, height: f64, area* ::= (self: @Self) f64 { self.width * self.height } }
Circle = { radius: f64 }
Circle.impl(Rect, { width: self.radius * 2.0, height: self.radius * 2.0 })   // computed fields
scale* = <T: Rect>(shape: T, k: f64) f64 { shape.area() * k }
d = shape.as(Display)        // trait value = receiver pointer + fn pointers, no allocation
```

Member forms: `= sig` required, `= sig {..}` sealed, `::= sig {..}` default, `::= sig` optional hook.
An impl lives with the type, so there are no orphan impls. Overloads resolve on parameter types and arity, never names; two that both fit is an error.

## 11. Modules — *collect, T0*

```zen
{ Res, Ok, Err, None } = std.core     // destructure
pick = one.pick                       // one item, renamable
mem  = std.mem                        // a module, read as mem.Alloc
{ Res*, Ok* } = std.core.result       // re-export = starred import
```

`<folder>/<folder>.zen` is module `folder`. There is no prelude and no wildcard: a name used without its import is an error that names the fix.
Built in, with no import: primitives, `true` `false`, `consume`, `@Self` `@meta` `@scope`, `.match` `.try`, `std`, `main`.
Dot calls find the type's own members, then free functions this module already sees. Nothing is resolved program-wide.

## 12. Entry and capabilities — *lower + runtime, T0*

```zen
main = (env: Env) Res<i32, Error> {
    a ::= env.mem.alloc();                 // arena from the page capability
    text = env.fs.read(a, "in.txt").try();
    env.out.println("{} bytes", text.len).try();
    Ok(0)
}
```

`main = () {}`, `() i32`, or `(env: Env) Res<i32, E>` (exit with the Ok value; an Err exits 1).
`println` (from `std.io`) is the one ambient effect. Formats are read at compile time: `{}`, `{name}`, `{{`.

## 13. Native bindings — *lower, T1*

```zen
C* = c.bind("unistd.h", { getpid* = () c_int, close* = (fd: c_int) c_int, AF_INET6*: i32 })
Timespec = c.record("time.h", "struct timespec", { tv_sec: c_long, tv_nsec: c_long })
{ callback } = std.native        // callback(f): a named, non-capturing fn as a C function pointer
```

These are explicit declarations checked against the real header. There is no header parsing and no inferred link flags.

## 14. Comptime and `@meta` — *fit + lower, T1*

`@meta(n: T).fields().loop((h, field) { .. n.at(field) .. })` walks a type's fields at compile time. `@meta(v).kind` is a typecase.
Comptime is the language without IO or actors. It may allocate, it is step-limited, and it has no file reads.

## 15. Command lines are types — *lower, T1*

```zen
BuildArgs = { verbose :: bool = false, jobs :: u32 = 2, out :: Res<Path>, input: Path }
BuildArgs.impl(Cli, { about: "Build one input", verbose: Spec(short: 'v') })
args = env.args<BuildArgs>().try()
```

A `:` field is positional and a `::` field is an option. The impl is the table, checked against the type.

## 16. Concurrency — *lower + runtime, T2*

Actors: `Ref<A>`, behaviours are sends, there is one-shot request/reply, and payloads are sendable (`val`/`iso`). Threads come from `env.threads` (`spawn`, `every`, `join`). Doors: process and stream capabilities.

## 17. Low-level and security extras — *T2*

`Secret<T>` and constant-time operations (`std.ct`): a secret can't drive a branch, a match or an index.
SIMD (`u8x16`…), wide multiply / carry ops, explicit truncation, volatile access, target features.

## Open language decisions (from DESIGN.md)

- **Mixed-type arithmetic** (`i32 + usize`): today the left type wins unchecked; v07 refuses it. Choose widening or explicit-only.
- **Operator overloading:** only `==` (via `Eq`) dispatches. Should `+` on `Duration`?
- **Ordering:** there is no `Ord`. It must agree with `Eq`.

## Minimal compiler profile (marrying with the v0.7 design)

| Tier | Language | Compiler pieces |
|---|---|---|
| **T0** | §2–§12 | lex/parse, collect, fit (+ qualifiers), resolve, cull, lower (App. C), Ir §1 + validate, flow, C route + one native target |
| **T1** | §13–§15 | `c.bind`/`c.record`/callback, `@meta`, CLI derive |
| **T2** | §16–§17 | actors and threads runtime, Secret/ct, SIMD, extra targets, JIT |

Acceptance: `tests/corpus` (1141) and `tests/must-fail` (617), scored with `v07/score/score.py` and `v07/flow/mustfail.py`.
