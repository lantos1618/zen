# Zen

**Performance is locked down, not hoped for.** Benches live next to tests (take a `Bencher` like tests take a `Tester`), budgets are project build policy, and a regression fails the build. That includes the build itself: a 20 minute build is a bug, and bugs fail CI. **Not implemented:** `BenchStats` and `Budget` exist, but the root `build.zen` currently describes build targets only; no benchmark runner enforces budgets yet.

**Pipeline:** `mod_resolver -> lexer -> parser -> sema -> codegen`

One stage per module, and modules are `<folder>/<folder>.zen` — a folder carries its root beside its children, so `src/gen/gen.zen` is module `gen` and `src/std/ast/ast.zen` is module `std.ast`.

```
build.zen              // this project's own build graph
src/zen/zen.zen        // thin cli: build / check / fmt / test / lsp
src/std/ast/ast.zen    // THE ast. the compiler, @meta and gen_c all consume these nodes
src/std/lex/lex.zen
src/std/parse/parse.zen
src/sema/sema.zen
src/gen/gen.zen        // backend-shared plumbing
src/gen/gen_c/gen_c.zen  // the c backend
src/zen/zen_build.zen  // the build driver behind `zen build`
src/std/...            // the stdlib specified below. ~34 modules.
```

`src/std/ast/ast.zen` is the keystone: one AST with three consumers, which is what makes `@meta` a view onto the compiler's own nodes rather than a parallel universe.

**The full tree — including the seed, the test corpora, and which stage each piece appears at — lives in `PLAN.md`.** It is the authority; this sketch shows only the shape.

---

# How the compiler gets built

The original Python frontend bootstrap is retired. The maintained build path is
**C compiler → committed `seed/zen.c` → seed Zen executes `build.zen` → `./zen`**.
`make build` and `make bootstrap` use the same path. Make owns only compiling the
seed; the Zen project builder owns the source graph, C generation, native tool
invocation, and publication. An existing `./zen` can run `./zen build --release .`
to build its own replacement. The compiler target has no unconditional network/TLS link
dependencies. Python remains a test tool, not a compiler build orchestrator.

**`build.zen` is planned, not executed.** The driver type-checks it against
`std.build`, then evaluates the `build` function's target registrations over
values known while planning: string and path literals, lists, locals,
`std.build` enum values, `b.mode()`, `b.os`, `b.arch`, `b.target()` and `.match`
over any of them. A written target field that the planner cannot evaluate, or
an unknown field name, stops the build with the field named; nothing falls back
to a default silently. Calls into project code are refused at their position,
because the project is not compiled yet.

**The build mode** is chosen on the command line — `--mode debug|release|small`,
with `--release` for `release` — and defaults to `debug`, so an edit-run cycle
pays only for an unoptimized C compile. Debug compiles at `-O0`, release at
`-O2`, and small at `-Oz` (`-Os` for GCC) with unreferenced sections dropped at
link time (`-Wl,-dead_strip` on macOS, `--gc-sections` elsewhere) and the
executable stripped. A target can choose for itself:

```zen
{ Builder, BuildError, Optimize, Cc } = std.build

build = (b :: Builder) Res<BuildError> {
    b.exe("app", {
        src: Path("src/main.zen"),
        deps: [],
        optimize: b.mode().match({ Debug => Optimize.Debug, _ => Optimize.Size }),
        strip: b.mode().match({ Debug => false, _ => true }),
        cc: b.os.match({ Macos => Cc.Clang, _ => Cc.Gcc }),
        cflags: ["-Wno-unused"],
        defines: ["APP_NAME=app"],
        libs: ["m"],
    }).try();
}
```

`optimize` is `Optimize.Debug | Speed | Size` and `cc` is
`Cc.Clang | Gcc | Tcc | Custom(Path)`, so a misspelled choice is a compile
error. `--cc` and then `CC` override `cc`, and `CFLAGS` words follow `cflags`.
On macOS the `/usr/bin` compiler shims are resolved once, through xcrun, to the
clang and SDK they select, and that answer is kept in `build/.zen/toolchain`.
`zen build --target TRIPLE` cross-compiles with clang; such a target is not run.

**Unchanged work is skipped.** Each native target records, beside its
generated C, the inputs of its last successful compile — the compiler
executable, the compilation words, every source file read (by length and
content hash) and every module-path probe answer — and its last link command
with the generated C's hash. A build whose records still match skips the front
end, the C compiler, or both, and leaves the executable untouched, which also
spares macOS from verifying a new binary before its first run. Records are
removed before work starts and written only after success. Targets with C
imports always recompile, and targets with extern C sources or C imports always
relink, because their headers are not recorded; neither are system headers or
libraries found through search paths, so deleting a target's executable forces
a relink.

Native project builds lock their generated workspace, link to a candidate
beside the requested executable, and rename it into place after success. A
failed frontend or native command preserves the previous executable, including
one currently running. Inherited lock descriptors keep the workspace protected
if a C compiler outlives the Zen driver. The driver starts no helper processes
of its own: the host platform comes from the compiler's predefined macros, and
directories and renames go through `Env.fs` and `std.fs.posix`.

**The grammar is written first, not extracted later.** It is the stage-0 artifact anyway, and writing the rules rather than more examples is what surfaces the ambiguities — the first one already found is that `Alias = Shape` is indistinguishable from a one-variant enum unless the grammar says which.

Two properties designed in rather than discovered:

- **`gen_c` is deterministic.** Same input, byte-identical output. Otherwise every seed regeneration is a noisy diff nobody reviews, and the fixpoint test below is worthless.
- **Regenerate, then commit.** Commit-then-regenerate ships a seed one change stale, and nothing but a full feature test catches it.

**The seed subset was the real constraint.** The bootstrapper had to implement every feature the compiler itself used, so the compiler is written in a subset that avoids `@meta`. `@meta` is a feature user code gets from day one; the compiler may adopt it now that the bootstrapper is gone.

**The cheapest strong oracle:** because `gen_c` is deterministic, "the compiler compiles itself to byte-identical C" is a fixpoint test that catches an enormous class of bugs and costs one script. Pair it with a corpus of programs with expected output.

### The order

LSP, formatter, and race checker are the visible goals, and **two of those three are not tools.** The race checker is the type system (`self :: @Self`, `consume`, `iso`) — sound from the start or never sound. The formatter is the parser plus a printer, one grammar, not two. Only the LSP is a genuinely separate program, and even it is a thin server over compiler internals.

So four decisions, all made in week one, all brutal to retrofit:

1. **Every AST node carries a `file` plus a half-open `start..end` span,** each end a `line:col` with a 1-based byte column, from the lexer up. A point is not enough: without an end, the formatter cannot reprint a node and the LSP cannot select one.
2. **Trivia — comments and whitespace — is attached to nodes, not discarded.** Then the formatter is `parse |> print` and can never disagree with the compiler about what the language is.
3. **Sema is memoized queries, not monolithic passes.** `type_of(node)`, `defs_of(name)`. This is the *same machinery* as comptime memoization — build it once.
4. **The compiler is a library; the `zen` CLI is a thin `main`.** `zen build` / `zen fmt` / `zen lsp` are entry points into one artifact, so they cannot drift.

| stage | what | why here |
|---|---|---|
| 0 | Python bootstrapper, minimal subset | the grammar exists first; deleted after stage 2 |
| 1 | **self-host** | everything after this is cheaper; nothing before it matters |
| 2 | formatter + CI gate | do it *at* self-host, before the tree grows, or you get a flag day |
| 3 | ownership / sendability checker | `self :: @Self`, `consume`, `iso` |
| 4 | LSP | falls out of (1)–(4) above |
| 5 | actors + runtime | orthogonal; constrains nothing in the compiler |

**Ship the ownership *syntax* at stage 0** even though nothing checks it. `self :: @Self` and `consume` cost nothing to parse and ignore. Defer the syntax and every line of stdlib written before stage 3 has to be revised; defer only the enforcement and nothing is lost.

**So read the Ownership section below as law, and check the tree before reading
it as behaviour.** The formatter's layout rules and unit-return normalization live in
`src/fmt/` and are held by `tests/corpus/fmt/`; token-moving match-arm rules
remain owed. Its `faithful` guard re-lexes the result and refuses token changes except
AST-identified redundant unit returns on named functions and methods with bodies.
Bodiless signatures, function types, callback return constraints and unit values
remain explicit. Other formatting passes still preserve every token. Ownership checks cover receiver mutation, consume/use-after-move,
copies and partial moves of `Drop` values, and `@scope` exits. Actor lowering
and a bounded-mailbox runtime have landed, but deep `iso` sendability remains
law rather than implemented behaviour. What is checked refuses; what is not
still compiles.

**Bootstrap scope:** C remains the full-language bootstrap backend. Optional scalar JavaScript and assembly generators now have an explicit support boundary; see [Code generation](BACKENDS.md). Whole-language shared lowering, an LLVM renderer, and optimization passes remain separate work.

**Compilation is whole-program.** One merged module graph; `gen_c` emits each generic instantiation exactly once. Separate compilation would have to decide which object file owns `Vec<Circle>` when `Vec` and `Circle` come from different modules, and every language that tries pays for that forever. The cost is that build time scales with the tree, which is exactly what `b.budget` exists to watch.


`zen check <root> [--entry <file>] [--std <path>] [--ffi]` uses the same module
loader and semantic checker as source emission. It accepts a library without
`main`, writes no generated artifacts, returns zero for a clean check and one
for source diagnostics. Invalid command arguments return two. Emission and
output flags are rejected by this command. The programmatic CLI parser takes
an explicit caller allocator: `cli(env, alloc, argv)`.

---

# The laws

Everything below follows from these. When two rules seem to conflict, the law wins.

1. **No ambient allocator.** Ordinary library allocation takes an `Alloc`.
   Runtime capabilities may own the storage their contract names.
2. **No ambient authority.** All authority flows from the `Env` `main` receives — io, net, page allocation, threads, spawning.
3. **Satisfy requirements, never impl storage.** Layout is fixed at declaration and never depends on which impls are linked.
4. **Failure stays visible.** Only success lifts into `Res`. `Err` and `None` are always written. A reason is never invented.
5. **`Res` is for failure a caller can act on. A trap is for a bug.**
6. **`*` means this name crosses a module boundary** — and therefore its type is written, not inferred.
7. **The signature answers the question.** Does it allocate, does it mutate, can it fail, does it escape — read the signature.

**Primitive conversions have one standard-library owner.** Lossless widening
returns a value; checked conversion returns `Res<T>` and refuses out-of-range
values with `None`. Only validated declarations in `std.core.num` acquire
compiler-provided conversion behavior. A local bodyless `to_<primitive>`
declaration cannot manufacture a cast. See [numeric conversions](NUMERIC_CONVERSIONS.md)
for the supported surface and compiler boundary.

---

# Lexical rules

A scanner cannot abstain. Every one of these was going to be decided by whoever wrote the first one, so they are decided here instead — that is the difference between a language and an implementation with a manual.

The shape of every rule below is the same: **reject rather than reinterpret.** A scanner that silently picks a reading is how a language ends up with a specification nobody can write down, and the readings it picks are always the ones that hide the bug (`010` meaning 8, `"\q"` meaning `q`). Rejecting costs the author one keystroke. Reinterpreting costs a reader an afternoon.

**Escapes.** The set is `\n \t \r \v \f \0 \\ \' \"` and nothing else. An unknown escape is an error, never a silent literal character: `"\q"` does not mean `q`.

**A `"…"` string or character literal does not span lines.** The newline is the error, and the diagnostic points at the **opening quote** — pointing at end-of-file names no useful location, because end-of-file is not where the mistake is. The diagnostic names the form that may span lines.

**Multi-line strings are written `"""` … `"""`.** Text that has lines is written as lines, not as `\n` escapes on one line:

```zen
USAGE: str = """
    usage: zen <command>

    commands:
        build   compile a project
        run     build and run it
    """
```

The rules, each chosen so that what the eye sees on the page is the value:

- **The text starts on the line after the opening `"""`.** Nothing else may follow the opening `"""` on its line; text there is an error at its first byte. There is no one-line `"""text"""` form — a one-line string is `"text"`.
- **The closing `"""` is the first text on its own line**, and the whitespace before it is the literal's **indentation**. Text before the closing `"""` on its line is an error.
- **The indentation is removed from every line.** So the literal sits at the code's indentation and a deeper line keeps only its extra indentation. Every line of text must begin with exactly the indentation's bytes — compared byte for byte, so a tab is not four spaces — or be whitespace only; a line that starts left of the closing `"""` is an error at its first byte of text, never a guess at what to strip. A whitespace-only line shorter than the indentation is an empty line.
- **Neither delimiter's line break is text.** The line break after the opening `"""` and the one before the closing line are not part of the value, so the example above ends in `it`, not in a newline. A value that ends in a newline ends with an empty line before the closing `"""`. With no line between the delimiters, or one empty line, the value is `""`.
- **Line breaks in the value are LF**, whatever the file was saved with: a CR before a line break is not text.
- **Escapes are the one-line set and mean the same bytes.** `"` and `""` need no escape; `\"""` writes three quotes without closing the literal. An escaped `\n` is a byte of text, not a line of the literal. A backslash does not continue a line.
- **It is a string literal**: type `str`, usable wherever `"…"` is — as a `println` or `String` format string, and as a match pattern.

The scanner reads the whole literal as one token, and the parser keeps its value as the equivalent one-line literal, so every later phase and every backend reads one form. The formatter prints the literal's source bytes; no layout rule reaches inside it.

**A character literal holds exactly one byte.** `str` is bytes, so `''` and `'ab'` are both errors. `'é'` is two bytes and therefore not a character literal.

**Integers are decimal or hexadecimal (`0x`/`0X`); floats are decimal.** A digit may not be followed by an identifier character: `1abc` is an error, not a number beside a name. There are no type suffixes — a literal's type comes from its context, which is the same rule the rest of the language runs on.

- **A leading zero is rejected.** Zen has no octal, so `010` cannot quietly mean 8. Python 3 made this exact call for this exact reason.
- **`12.` is an error**; a float has digits on both sides of the point. The gain is that a number literal is never the base of a member access, so `1.max` needs no lookahead to disambiguate from a malformed float.
- **A hexadecimal literal needs at least one hexadecimal digit.** `0x` and `0xG` are errors. Hexadecimal literals are integers; signs remain prefix operators rather than part of the token.

**Identifiers are ASCII** — `[A-Za-z_][A-Za-z0-9_]*`. Widening a character set later is compatible; narrowing it is not, so v1 takes the narrow end.

**Block comments do not nest.** `/* a /* b */` is closed.

**A BOM is stripped only at offset 0.** Anywhere else it is an ordinary invalid byte sequence, and saying so beats a file that parses differently depending on where an editor left a marker.

**`@` is closed.** The namespace is exactly `@Self`, `@meta`, `@scope` — adding a fourth is a design change, not an implementation detail. So `@foo` is a lexical error at the `@`, and never an unresolved name later: one mistake, one diagnostic, anchored where the fix goes.

---

# Declarations

**Conventions settled:** fields mirror bindings: `name: T` is set at construction and never reassigned, `name :: T` is mutable, and `= default` makes a field optional at construction. `*` on a field means readable outside the module; mutation only ever goes through exported methods.

**Locals mirror fields too, and `::` means mutable wherever it is written.** A local is `name = value` or, when it may be reassigned, `name :: [T] = value` with the type optional — `name ::= value` is the same binding without the space and without a type. An immutable local may write its type the same way, `name: T = value`. `c :: Circle = Circle(r: 2.0)` and `count ::= 0` are the two mutable spellings; there is no third.

**A local may be declared before it has a value.** `name :: T;` declares a mutable local and `name: T;` an immutable one; a later `name = value;` assigns it. The compiler proves definite assignment over the control flow the language actually has: every read, `consume` or capture of the local must follow an assignment on **every** path to it — a match's arms are joined, `bool.then` may not run its body, a loop body may run any number of times (and its entry state includes every way back to it), `h.break()` leaves for the point after its loop, and `.try()` leaves the function. An immutable one is assigned exactly once: an assignment on a path that may already have assigned it is refused. A declared local that nothing assigns at all is refused at its declaration, even if it is never read. Each fault is one diagnostic, at the read or the assignment, naming the local. A closure that is not called where it is written (a local function, a lambda held as a value) is checked as if it ran any number of times from where it is written, and an assignment it makes is not counted for the code after it.

**`name: T ::= value` is not a binding.** It was the typed mutable local before `::` took that job; it is refused with a diagnostic naming `name :: T = value`.

**A DEFAULT IS WRITTEN `name :: T = value`, AND ONLY THERE.** Inside a struct body `name: T = value` is already taken: it is a **constant on the type**, one value per type, read as `Type.NAME` — the form `i32.MAX` is declared with. The two are the same syntax down to the one character that elsewhere means mutability, so one of them has to lose, and the constant wins because it has no other spelling while a default has `::`. **The price is that an immutable field with a default is unspellable**, and it is written here rather than left in a grammar comment: a field you may supply and may omit, and that never changes after, is written `::` and kept immutable by the rule above it — mutation only ever goes through exported methods, and a type that exports none has none.

A field the construction omits **is its default**, not zero. `Cursor()` on a `Cursor` whose every field declares a value is that value in every field, and the same is true of the fields a partial construction leaves out.

**A field written `Res<T>` with no default may be omitted, and omission supplies `None`**, never the `Ok` of a zero: `Foo(name: 1)` on `Foo = { name: i32, a: Res<i32> }` has `a` equal to `None`. It is the field form of the trailing `Res<T>` parameter rule, with the same limit: a failing `Res` — `Res<R>` with R an Error, or `Res<T, E>` — is required, because failure is not absence. Every other field with no default is required.

**The values in a list run left to right.** A call's arguments, a construction's field values, and an array literal's elements evaluate in the order they are written — `three(a.tick(), b.tick())` runs the left tick first, `Pair(x: d.tick(), y: d.tick())` reads for `x` before it reads for `y`, and `[a.tick(), b.tick()]` runs the left element first. C leaves both questions open — a call's arguments are unordered (C11 6.5.2.2p10) and a compound literal's initialiser expressions are indeterminately sequenced (C11 6.7.9p23) — so the backend holds each side-effecting value in a temporary of its own and never asks the C compiler. A Zen program means one thing; which C compiler builds its output is nobody's business but the build's.

**Method rules**, everywhere. Export (`*`) and overridability (`=` / `::=`) are orthogonal: exported-but-final is `name* = sig {..}`, and on methods `::=` means impls may rebind, not runtime mutation.

| form | meaning |
|---|---|
| `name*` | exported from the module (same `*` as types) — **module level and struct members only** |
| `= sig` | required: impl must provide it |
| `= sig {..}` | sealed: provided, cannot be overridden |
| `::= sig {..}` | default: provided, impl may rebind it |
| `::= sig` | optional hook: impl may provide it |

**`*` is a module-level and struct-member marker, and nowhere else.** Law 6 says `*` means the name crosses a module boundary. A binding inside a function body cannot cross one — it does not outlive the call — so `*` on it means nothing, and a marker that means nothing is a marker someone will read as meaning something. `helper* = (a: i32) i32 {..}` inside a body is rejected by name, not by accident.

The corner this closes is sharp and was found by a parser: `*` is also multiplication, so a statement beginning `n *` has to be either an exported declaration or a product, and the parser cannot ask which until it has read further. Restricting `*` to the two places it has meaning removes the fork entirely at body level, which is the only place the ambiguity is reachable.

**Sum types are written with `|`. Braces make an enum; without them `|` joins existing types into a union.**

```groovy
Shape = { Circle: Circle | Rect: Rect | Unit }  // an enum, with payloads
Error = AllocError | IoError | ArgError         // a union of existing types
AllocError* = { | OutOfMemory }                 // one variant: the bar leads
Alias = Shape                                   // no bar, so an alias. unambiguous.
```

**A body's separator decides its kind.** Inside braces, `|` joins an enum's variants and `,` joins a struct's fields, and a body mixing them is rejected. A variant's payload is written like a field, `Circle: Circle`; a variant takes no `::`, because it is not a binding; and `= n` gives it a discriminant. After the `,` that ends the variants come the enum's methods and constants, exactly as in a struct body, so an enum's behaviour travels with it the way a struct's does:

```groovy
Permutation* = {
    Natural | Reverse | Rotate: usize,
    index* = (self: @Self, n: usize, i: usize) usize { .. }
}
```

**Why braces and not one syntax for both.** An earlier rule used one spelling: `A | B` was a union when every name was a type in scope and an enum otherwise. That made **an import in one module able to change what a declaration in another means** — writing `DefKind = Struct | Enum | ..` in a module that imports `std.ast` silently turned the enum into a union of `std.ast`'s types. Braces remove the question: an enum says so where it is written, and a bare `|` whose names are not all types is an error naming the braced form as the fix. Inside a body a top-level `|` always separates variants, so a union-typed field or payload is declared under a name first (`Num = u32 | i64`).

**An alias is the type, not a name that forwards to it.** `Alias = Shape` binds `Alias` to `Shape` itself, so `Alias.Circle` is `Shape.Circle` and a value of one is a value of the other — there is no conversion, because there are not two types. This is what makes the pair above observably different: under the alias reading `Alias.Circle` exists, and under the one-variant-enum reading it does not.

**A union is its members. Order and spelling are not part of its identity.** `WriteError = IoError | AllocError` and `Error = AllocError | IoError` are the same type, and so is the `IoError | AllocError` an inferred error set arrives at with no declaration behind it at all. This is not a new rule; it is the two above read together. A bare `|` declaration *is* a union of those types, not a fresh nominal type wrapping them — and the alias rule says a name does not create identity. A union of the same members, however it was spelled or in whatever order, is one type.

The consequence is a layout rule, and it is the reason to state this explicitly rather than leave it derivable: **a union's tags are numbered by a canonical order over its members, never by declaration order.** Number them by declaration and two spellings of one set get different tags, so `.try()` from one into the other needs a runtime map to renumber — a per-member switch at every widening site, for a difference that the type system says does not exist. Canonical numbering makes the widening a copy. The tag is internal either way: a program matches variants by name and can no more observe a tag's value than it can observe a struct's padding.

Enums are unaffected. `Signal = { Start | Stop }` is not a union, its variants name no types, and there is no second spelling of it to agree with — so it is numbered by declaration order, which is the order its author wrote and the order its exhaustiveness diagnostics read best in.

**A nominal enum may assign integer discriminants for a wire or file format.** Every known variant writes one unique compile-time integer. A final payload variant both preserves unassigned values and states the external domain; a closed represented enum uses `u64`:

```groovy
FrameType* =
    | Data = 0x0
    | Headers = 0x1
    | Ping = 0x6
    | Unknown(u8)
```

`kind.discriminant()` returns the catch-all's `u8`, and `FrameType.from_discriminant(byte)` reconstructs the enum. With a catch-all the latter is total; without one it returns `Res<FrameType>`. The catch-all cannot be constructed directly, because `Unknown(0)` would give the known `Data` byte two in-memory values. Represented enums are nominal, non-generic, and their known variants carry no payload. Mixed payload types remain the ordinary `Foo = | Bar(i32) | FooBar(f32)` form; they are values, not integer discriminants. External numbers never replace the compiler's dense internal tags.

The leading bar on a one-variant enum is the whole point: without it `AllocError = OutOfMemory` and `Alias = Shape` are the same three tokens, and `TestError = Failed(str)` and `Circle1 = AddFoo(Circle)` are the same five. With it, a parser needs no lookahead, no position rule, and no guess — and an enum may be declared anywhere, not only at module level.

**One declaration form:** there are no traits, only structs. A struct whose fields happen to be functions, used as a bound, is what other languages call a trait — nothing marks it special, because nothing needs to. `A.impl(B, {..})` supplies a value for every field `B` declares: an `f64` field takes an `f64`, a function-typed field takes a function. One rule, no second mechanism — which is why the method table above and the field rules are the same table.

**You satisfy requirements; you never impl storage.** A field a type declares for itself is storage. A field an impl supplies is computed, and is re-evaluated on read, so it can never go stale. Layout never depends on which impls are linked. When two impls declare the same name, the bound in scope selects which is in view; with no bound to disambiguate it is an error — never file order.

A computed field is **read-only and non-addressable**: there is no storage, so there is nothing to take the address of and nothing to assign into. Mutation goes through exported methods, as it always does.

```groovy fragment
c = Circle(radius: 1.0);
p = &c.width;     // ERROR: computed field, no address exists
c.width = 5.0;    // ERROR: nothing to assign to
```

The residue worth knowing: an impl may supply something expensive, and reading it in a loop hides real work behind a dot. The *simple* case should be held by a pair of budgets — if these two ever stop matching, uniform access is not free and we want to know. The benchmark runner is not implemented yet; these are the intended project-policy entries:

```groovy fragment
budgets: [
    Budget(name: "stored_field_read",   ns_op: 2, allocs_op: 0, bytes_op: 0),
    Budget(name: "computed_field_read", ns_op: 2, allocs_op: 0, bytes_op: 0),
]
```

```groovy
Rect* = {
    width: f64,          // Rect's own fields: storage
    height: f64,

    area* ::= (self: @Self) f64 { self.width * self.height }
}

Circle* = { radius: f64 }

// width and height are f64, so the impl supplies f64 EXPRESSIONS —
// the same `name: value` form used at construction. Circle stays
// one f64 wide; these are computed on read, never stored. area
// comes along free, it only ever needed a width and a height
Circle.impl(Rect, {
    width: self.radius * 2.0,
    height: self.radius * 2.0,
})

// a bound is just "which struct's shape do I need"
scale* = <T: Rect>(shape: T, k: f64) f64 { shape.area() * k }
```

**An impl lives with the type, not with the trait.** `A.impl(B, {..})` belongs in the module that declares `A`, which imports `B`. `str.impl(Eq, ..)` is in `std.text`, not `std.core.eq`; `Vec.impl(Display, ..)` is in `std.collections`, not `std.core.display`.

This is not a taste rule, it is what keeps dependencies pointing down. A trait sits below the types that satisfy it — `Eq` cannot know about `str` — so putting the impl with the trait forces the lower layer to import the upper one, and the module graph inverts. The reading test is the one in `STYLE.md`: write the impl's one-line summary, and whichever type it names is the module it belongs to.

The consequence worth stating: **there are no orphan impls.** A module may not impl a trait it does not own for a type it does not own, because there is no third module for that impl to live in.

**A trait value is a fat value.** Since a "trait" is an ordinary struct, a trait *value* is an ordinary record: a receiver pointer plus one function pointer per method, copied by value. `shape.as(Display)` builds that record on the stack; storing it in a `Vec<Display>` copies it inline. No `dyn`, no vtable concept, no boxing, **no allocation** — so the Alloc law is satisfied rather than side-stepped. This is the same shape as `Alloc` itself. The one thing it costs: the record points at the receiver, so the receiver must outlive it — the ordinary rule for any pointer stored in a collection.

```groovy fragment
printers ::= alloc.Vec<Display>();
printers.add(circle.as(Display)).try();   // 2 words copied in, no alloc
```

**`Display.toString` writes into a `Sink`, not into a `String`.** This is forced, and it was found by trying to implement the obvious thing. `println("{}", shape)` has to route through `toString`; if `toString` writes into a `String`, then printing needs a `String`, a `String` needs an `Alloc` to grow, and `println` has no `Alloc` parameter — so printing a value would either allocate behind the caller's back, breaking law 1, or `println` would grow an allocator parameter and hello-world would need an arena.

A `Sink` dissolves it. A console is a sink, a `String` is a sink, and `println` hands `toString` the console it already holds — so **printing does not allocate at all**, and nesting still writes into the one buffer that is already open. It is the same move as `Alloc`: name the capability, pass it as a fat value, and let the caller decide what is behind it.

**`Sink` has two members, not one.** `write_byte` looks redundant beside `write` and is not. The integer writers build a number a digit at a time, and a digit has no `str` to point at — `str` borrows bytes, and the only way to obtain something to borrow is a `Ptr` from an `Alloc`. So a sink that accepts bytes but not *a* byte makes printing an integer allocate, which is the one thing this whole design exists to prevent. The alternatives are worse: formatting digits in the C runtime moves the format rules out of `text_fmt.zen` and splits the single implementation in two, and a static digit table needs a `u64`→`usize` conversion the numeric surface does not have.

`Sink.write` returns `WriteError`, the union, and that is the part worth arguing about. Writing to a console fails with `IoError` and writing to a growable `String` fails with `AllocError`; there is no `From`, so a single sink type cannot pretend those are one error. The union is the honest type — which is exactly the reason `WriteError` was introduced. **Cost to accept knowingly:** a caller writing into a `String` must handle an `IoError` that a `String` can never produce, and a caller writing to a console must handle an `AllocError` it can never produce. `.try()` merges either into the caller's set for free, so the cost is paid only where someone actually matches on the error.

**The format language, in full.** `{}` is a hole, filled by the next argument through its `toString`. `{name}` is a hole too, filled by the binding `name` has where the hole is written. `{{` writes a literal `{` and `}}` writes a literal `}`, so `{{}}` writes `{}` — the conventional doubling, and the only escape. A `{` followed by none of `}`, `{` or an identifier character is a literal brace, and so is a lone `}`; `Display.dump` relies on that, writing `out.fmt("{} {", ..)` and expecting the trailing `{` to print. There is no width, no precision and no argument index. The walk is left to right and never backs up, which is what settles the two shapes that could read either way: `{}}` is a hole then a literal `}`, and `{{}` is a literal `{` then a literal `}` — and a doubled brace is classified before a name is ever looked for, so `{{name}}` is a `{`, the bytes `name`, and a `}`.

**A named hole consumes no argument, so the two spellings mix freely.** `fmt("{a} of {}", n)` passes the one argument its one positional hole wants. Counting a named hole would make that call claim two.

**A format hole is not an expression language, and the refusal is the design.** `{name}` holds an identifier and nothing else: no field read, no call, no operator. Each of those would give a format string a second parser with its own precedence and diagnostics, and none is bought by the syntax it saves. What makes the refusal statable rather than a special case is that **a `{` followed by an identifier character always meant a hole** — so `{p.x}` is a compile error naming its own position, and cannot fall back to printing itself, which is the wrong answer nobody reads twice. `{{p.x}` is the escape at such a site.

**A format string is read at compile time.** Both hole spellings are expanded where they are *written* — the compiler steps the format at the call site, emits one byte write per literal run and one writer call per hole, and resolves `{name}` in the frame it is standing in, exactly as it resolves a bare identifier. So there is no runtime format state and no allocation for either; a computed format is not a format at all; a name with no binding is a compile error at the hole's own position rather than a `?` in the output; and a hole count that disagrees with the argument count is a compile error too. This is also why the escape has a cost worth stating: a plain byte writer such as `String.add` reads no format meaning, so `s.add("]}}")` writes two braces where `s.fmt("]}}")` writes one. Converting a byte writer into a format call is therefore a change of output wherever the bytes hold a doubled brace.

---

# Control flow

**Control flow is one thing:** `.match`, a method — exactly as `loop` is a function. No `if`, no ternary, no `?` operator. Arms are `pattern => expr`, comma-separated, no leading `|`; `=>` already separates, so the bar is noise. Payloads bind in the pattern: `Ok(n) => n`. **Match is always exhaustive**, in every position: cover every case or write `_`. There is no partial form, so a missing arm is never ambiguous between "deliberate" and "forgot". When you really do want one side only, `bool.then` says so out loud — and being a different word, it cannot be a typo. Guards inside loops are usually a missing loop word (`find`, `filter`), not a conditional at all.

**A statement ends with `;`. A declaration does not.** That is the whole rule, and it holds without a lexer that counts newlines:

**A function type may not be written where a value is expected.** `f = (a: i32) () i32` and "returns unit, and the next member is named `i32`" are the same tokens — a signature always writes its return type, so `()` in return position and `()` as an empty parameter list cannot be told apart by looking left. The tree-sitter grammar dodges it with a declared GLR conflict; a recursive-descent parser has no such move, so the rule is: after a `)`, a `(` or a `<` never begins a return type in **expression** position. A zero-parameter function type is therefore written only in *parameter* position — `cond: () bool`, `body: () Res<T, E>` — where the following token is a `,` or a `)` and nothing is ambiguous. Every one in the standard library already sits there, so this costs nothing today; it is written down because it is a restriction the parser enforces and no reader could derive.

**A trailing `Res<T>` parameter may be omitted; omission supplies `None`.** Thus `known_header("accept")` and `known_header("accept", None)` are the same call. Several trailing `Res<T>` parameters may be omitted from the right. Omission never skips a parameter, and a failing `Res` — `Res<R>` with R an Error, or `Res<T, E>` — remains required because failure is not absence. A present bare `T` still uses the ordinary hoisting rule, so `known_header(":method", "GET")` is identical to passing `Ok("GET")`. Two overloads may not accept the same call after this rule is applied.

```groovy fragment
Vec*<T> = { .. }                 // declaration: struct. no semicolon.
Shape = { Circle: Circle | Unit }  // declaration: enum. no semicolon.
area* = (c: Circle) f64 { .. }   // declaration: function with a body. no semicolon.

v ::= alloc.Vec<i32>();          // statement. semicolon.
n :: usize = 0;                  // a typed mutable binding. semicolon.
label :: str;                    // declared now, assigned before any read. semicolon.
Circle1 = AddFoo(Circle);        // a binding inside a body is a statement. semicolon.
println("done");                 // statement. semicolon.
```

**A binding or assignment is a statement, so it can never be a block's trailing value** — there is no assignment *expression* to produce one from. `() { x = 1; }`, never `() { x = 1 }`. The compiler used to answer the second form with "expected expression", which names a thing the author did not want; it now names the rule that was broken.

Optional semicolons were the alternative and they carry a real hazard, not an aesthetic one: a statement ending in an expression, followed by a line beginning `(` or `[`, silently becomes a call or an index of the previous line. Newline sensitivity was the other alternative, and it breaks the leading-dot continuation this doc already uses in `build.zen`.

**Non-local exit** is one mechanism, not two special cases:

> A non-escaping closure may return through its caller. `.try()` and `h.break()` are both this. Escaping closures may not — they have no caller frame to return through.

`.try()` unwraps `Ok` or returns the `Err` from the enclosing function; that is a jump out through a frame boundary, exactly what `h.break(v)` does. There is no coherent position where one is fine and the other is exotic. So `loop` stays a genuinely ordinary function — `break` is a general language feature that `loop` merely uses, not a privilege the compiler grants it.

**A block is a value too.** `@scope` stands for the enclosing block, exactly as `h: LoopHandle` stands for the enclosing loop — the same idea, one level down. It nests, and each block gets its own:

```groovy fragment
{
    outer = @scope;
    {
        inner = @scope;                              // the inner block
        inner.defer(() { println("inner cleanup") });
    }                                                // inner's defers run, inner dies
    outer.defer(() { println("outer cleanup") });
}                                                    // outer's defers run
```

This is where `defer` lives, and it is why `defer` needs no keyword and no ambient authority: the block owns its own stack of closures. It is also why `Env` does not — `Env` outlives every block inside `main`, so a defer stack on `Env` would be storage in the wrong place.

**`@scope` is non-escaping.** It may be passed *inward*, so a helper can register cleanup on its caller's block, but it can never be stored in a struct, returned, or captured by an escaping closure. Same escaping/non-escaping distinction as above, now doing a third job.

**A closure registered on a scope keeps its captures in that scope's own storage**, and this is what non-escaping buys. A deferred closure outlives the frame that wrote it — `register(@scope, env)` returns long before its cleanup runs — so its captures cannot live in the caller's frame, and a general escaping closure would need a heap record, which law 1 forbids without an `Alloc`. But the block it is registered on outlives it by construction, so the block's own defer stack is exactly the right storage: sized at compile time, freed at block exit, no allocator. `defer` therefore needs no escaping-closure machinery at all — it needs the one guarantee `@scope` already makes. That is why the restriction is a feature and not a limitation.

**A function declared in a body is a local closure.** Inside a body, `succ = (x: i32) i32 { x + 1 }` declares a local function exactly as the same line declares one at module level — a declaration, so it states its parameter types and takes no `;` — and `succ(2)` calls it. What it is follows from non-escaping, with no new machinery:

- *Captures are the frame's own bindings, read live.* The body sees every binding visible where it was written and nothing written later; each call reads their current values, and a store to a captured `::=` binding writes the enclosing frame's storage. There is no closure record, no copy, and no allocation — the same guarantee a lambda passed to a function-typed parameter has, because a local function is lowered the same way: inlined at each call site in the frame that wrote it.
- *Non-local exit goes to the writer.* `.try()` inside the body returns from the enclosing function, as it does in any non-escaping closure. The declared result type types the body's tail.
- *It may run any number of times*, so it may not `consume` a captured binding — refused as it is in a loop body.
- *It is not a value.* It has no storage, so it is only ever called by name: it cannot be copied into another binding, returned, stored, or captured by an escaping closure. Passing it to a function-typed parameter is not supported yet.
- *It is plain.* No `*` (nothing outside the body can name it), no type parameters of its own (it may use the enclosing function's), a body, and no recursion — its name is bound after its body, so a call to itself is an undefined name.

Rebinding a function (`op ::= add_i32` in the example program at the end of this document) needs function values, which are not implemented. The native (IR) backends refuse local functions with "nested declarations".

---

# Errors

**Errors are values, and a type is an error because it implements std.core's `Error` bound.** Never because of its name: `Fault`, `ParseError` and `Late` are errors when an impl beside them says so, and a type called `Error` is not one unless it does. A union is an error when each of its members is one. `Error` has one member, `message`, whose default writes the name of the variant the value holds; an impl rebinds it when the payload has more to say.

```groovy
Jam = { Paper | Ink }
Jam.impl(Error, {})
```

**`Res` reads by what its arguments are**, and the reading is fixed where `Res<…>` is written:

| Written | V or R | Means |
|---|---|---|
| `Res<V>` | V does not implement Error | `Ok(V) \| None` — absence |
| `Res<R>` | R implements Error | `Ok \| Err(R)` — a unit success or a failure |
| `Res<V, R>` | any | `Ok(V) \| Err(R)` |

`Res<R>` is the same type as `Res<(), R>`, which stays legal. An unconstrained type parameter is never an error, whatever it is instantiated with, so `Res<T>` in generic code always means absence; generic failure is written `<E: Error>` and `Res<E>`, or as the second argument of `Res<V, E>`. An `Err` offered where a one-argument `Res` means absence is refused as such, with a hint to implement Error or write `Res<V, E>`.

**A unit payload is written without parentheses.** A variant whose payload is `()` is constructed and matched bare: `Ok` is `Ok(())`, `Shape.Empty` is `Shape.Empty(())`, and the pattern `Ok =>` matches it.

**A unit result lifts to `Ok`.** This is the hoisting rule — a bare T lifts when exactly one variant carries T — applied to `()`. A body returning `Res<R>` (or `Res<(), R>`) may end in a statement, and a `()`-valued arm beside a `Res` arm of a match is that `Res`'s `Ok`:

```groovy fragment
print_page = (n: i32) Res<Jam> {
    feed(n).try();
    println("printed {}", n);          // the body succeeds
}

first_even = (n: i32) Res<Jam> {
    (n % 2 == 0).match({
        true  => println("even {}", n),  // Ok
        false => Err(Jam.Ink),
    })
}
```

Only `()` lifts this way. Where the success is a value, a body that ends in a statement or a binding has left it out, and is refused as a missing success value rather than returning a zeroed one.

**Error sets.** The error type of a `Res` is a union, and propagation merges sets. `A | B` is an anonymous enum of two variants — a structural enum, not a new kind of type — so `Res<T, E>` never changes shape and a single error type is a set of one.

```groovy
read_cfg  = (p: Path) Res<Cfg, _>                       // internal: inferred from the body
read_cfg* = (p: Path) Res<Cfg, IoError | ParseError>    // exported: written out

Error = AllocError | IoError | ArgError
main  = (env: Env) Res<i32, Error>
```

Inference inside a module, explicit at the boundary — law 6. A private refactor never ripples through signatures; a public one always lands in review.

**There is no `From`, and no implicit error conversion.** An error does not change identity because the compiler found a conversion somewhere. That is the same principle as law 4, one level up.

**A `None` never becomes an `Err`.** You name the reason:

```groovy fragment
row = table.get("ada").try();                        // ERROR: Res<User> is not Res<User, E>
row = table.get("ada").ok_or(Error.NotFound).try();  // required form
```

**A failure is handled or discarded in writing.** A failing `Res` (`Res<R>` or `Res<T, E>`) that a statement computes and nothing reads — or that is the tail of a block whose value is `()`, such as a unit function's body or a `.loop` body — is refused, and the diagnostic names the three ways out: `.try()`, `.match`, or `.ignore()` when dropping it is the decision. A `Res<V>` that reads as absence is not a failure, so `v.pop();` stays legal; one that holds a failure (a `.then` whose body produced one) is refused at the failure.

```groovy fragment
out.fmt("{}\n", n);           // ERROR: this `Res<WriteError>` is dropped
out.fmt("{}\n", n).try();     // propagate
out.fmt("{}\n", n).ignore();  // a best-effort write, dropped on purpose
```

---

# The failure model

`Res` is for failure a caller can do something about — a file is missing, input is malformed. A bug is not that, and routing bugs through `Res` would put `.try()` on every arithmetic expression in the compiler and destroy the signal that makes `.try()` readable. So:

- `+ - *` **trap** on overflow. `+% -% *%` wrap, for when wrapping is the intent.
- Bit operations `& | ^ ~ << >>` never trap. They act on unsigned words only; a shift discards the bits it moves out, and a count at or above the width yields zero (see "Unsigned bit operations").
- `/ %` **trap** on a zero divisor, and on `i32.MIN / -1` — which is an overflow wearing division's clothes, and faults identically on x86.
- `buf[i]` on a fixed array is **bounds-checked and traps**. **The count is part of the type** — `[u8, 64]` and `[u8, 65]` are different types — which is what makes the check possible with no length stored beside the bytes, and what lets a literal index past a known length be the compile error below rather than a runtime trap. `Vec.get` still returns `Res<T>` — a lookup that can legitimately miss is not a bug.
- A trap **aborts the process**: it prints `file:line:col: trap: <what>` to stderr and exits `134`. The three whats are `integer overflow`, `divide by zero`, `index out of bounds`, and the position is the **operator** token. Column is a 1-based byte offset.
- **`Ptr` is outside this model, and `Vec.ptr` is the door onto it.** `p.read(i)` is C's `p[i]`: no bounds are held anywhere, nothing traps, and nothing at a call site distinguishes it from a checked lookup — the raw floor has no marker, so a collection that exports its storage exports silence. `Vec.ptr*` is exactly that export (its two std callers — `String.view`, which builds a `str` over another module's storage, and `Stdin.read`'s fill of a buffer's spare capacity — need the address itself, which no checked door hands out); every other collection keeps its storage unexported and answers lookups through checked doors. Reading past a length through it is that type's documented behaviour, not a violated guarantee. Two consequences worth writing down because both run against intuition: the arena never reuses a byte (`mem_arena.zen`), so an overread walks into **other live objects** — a neighbour's contents come back verbatim, not garbage; and an arena run never leaves its malloc block, so **no sanitizer will flag it**. The compiler's own ~49 `.ptr().read(i)` sites are in-tree users of this floor.
- Overflow traps for **unsigned** types too. "A trap is for a bug" does not have a signedness exception, and a `u8` reaching 256 is the same bug a `i8` reaching 128 is.
- A trap the compiler can **prove** will fire — `i32.MAX + 1`, a constant zero divisor, a literal index past a known length — is a **compile error**, not a runtime trap. It is a bug, and it is a bug that was visible without running the program.

One constraint this puts on the backend, stated here because it is a correctness requirement and not an implementation detail: **signed overflow is undefined behaviour in C**, so `gen_c` may not emit `a + b` and inspect the result afterwards — the optimizer is entitled to delete that check, and will. The test happens before the operation, or through `__builtin_add_overflow` and friends.

Killing only the offending actor is the Pony-shaped alternative, and it needs a supervision story that does not exist yet. It can be added later without changing any of the above.

---

# Ownership

Three questions, one checker: *what is this binding allowed to do?*

**There is no implicit receiver.** A method is a UFCS function whose first parameter happens to be named `self`, and that parameter is written out like every other one — a name and a type, never bare.

This is a rule about **declarations**, not about every parameter list. A closure passed to a function whose signature is already known infers its parameter types from that signature, so `items.loop((h, v) { .. })` needs no annotations — `h` and `v` each have exactly one possible type. Annotate a closure parameter only to disambiguate, as the fold body does with `acc: i32`. A declaration states types because someone reads it without context; a closure does not, because the context is the call.

`@Self` is the type being declared, supplied by the compiler inside a struct or impl body. The `@` says exactly that: like `@meta`, it is not a name you could have written yourself.

```groovy fragment
add* = (self :: @Self, value: T) Res<AllocError> { ... }   // mutates
get* = (self: @Self, i: usize) Res<T> { ... }                  // does not

v = alloc.Vec<i32>();    v.add(1);   // ERROR: add needs a mutable receiver
w ::= alloc.Vec<i32>();  w.add(1);   // ok
```

`@Self` is spelled `Vec<T>` when you write the same function outside the body — the two forms are the same function, and the second is what the first means:

```groovy fragment
Vec*<T> = { add* = (self :: @Self, value: T) Res<AllocError> { ... } }
add*    = (v :: Vec<T>, value: T) Res<AllocError> { ... }   // identical
```

So `::` on a receiver means the method mutates it, and it is not a receiver rule at all — it is the ordinary binding marker doing its ordinary job on the ordinary first parameter. One function form, one binding rule, nothing added.

The rule therefore holds at **every** `::` parameter, not only the first: `bump(counter)` against `bump = (c :: Counter)` needs `counter` — and every field on the path to it — to be `::`, exactly as `counter.bump()` does. There is no copy-in: a `::` parameter is the caller's storage, and a `:` binding lent to one would either be written behind its declaration or have the write silently dropped. A value that is not a place (a call, a construction, a literal) may still be passed; it is a fresh temporary no one else can see.

This is **shallow**: `::` means the method writes the receiver's *own bytes*, and nothing more. So **a handle's methods are `:`, even when they change the world.** `Alloc.raw` is `self: @Self` — allocating changes the arena behind the handle, not the two words of the handle. Same for `@scope.defer` (the closure stack lives in the block), `Ref` behavior calls (the mailbox is behind the address), and `Env.spawn`.

That is not a nicety, it is what makes the system consistent. `Vec.alloc` is a `:` field, and `Vec.grow` calls `self.alloc.realloc(..)` through it. If `realloc` demanded `:: Alloc`, that call would be illegal and every collection would need a mutable allocator field — the shallowness would buy nothing. It compiles precisely because `realloc` writes the arena, not the handle. Same reason `foo.receive_msg(..)` is legal on a `foo = env.spawn(..).try()`.

The test, when a signature is unclear: **would a bitwise copy of the receiver see the change?** If yes, the change was to its own bytes and the method is `::`. If the copy sees it too — because both point at the same thing — the method is `:`.

It is not inferred from the body. An inferred receiver requirement changes when the body changes, so adding one `self.x = ..` would silently break callers in other modules. Explicit keeps it a promise instead of a consequence.

**`consume` moves.** The compiler calls `drop` exactly once, so `g = f` on a `Drop` type cannot copy — both would drop. There is no `Clone` trait: want a second one, construct a second one.

Copying `Ptr.read` and `Ptr.copy_from` operations reject values containing inline
`Drop` owners, including generic instances checked during lowering. Consequently,
`Vec.get`, `require`, and value iteration cannot duplicate those owners. A raw
`Ptr.take(index)` transfers an initialized slot without clearing its bytes; the
caller must retire or overwrite that slot before another read or destruction.
`Vec.take` manages that retirement and compacts the initialized prefix. This is
not a checked raw-pointer lifetime or aliasing system. Factories may still return
fresh owners. LSP document queries use owner-free views whose lifetime ends when
the corresponding document is retired.

Vec replacement destroys the displaced slot before returning success. Owning
collection storage remains an unchecked boundary: borrowed insertion and
refusal cleanup do not yet satisfy this contract.
The maintained failing cases are in `tests/library/ownership-storage`; owning
lookup checks must not be presented as end-to-end container ownership safety.

Four consequences worth stating; three are places the rule looks like it bites and does not, and one is a place it does:

- **A handle is not a `Drop` value.** `Alloc` is an interface, so an `Alloc` value is a fat value pointing at an arena. The *arena* is `Drop`; the handle is two words and copies freely. That is why `Vec` can store `alloc: Alloc` by value and why `fill(alloc, v)` is not an illegal copy.
- **A handle built from a concrete value points at that value's storage.** Passing an `Arena` or any other implementor where an `Alloc` (or any interface) is wanted builds the handle over the argument's address: a local, this body's copy of a by-value parameter, or a temporary. That handle — and anything that keeps it, such as a `Vec` made from it — may be used inside the body and passed inward, but may not be returned or stored through a `::` parameter, and a value that keeps it may not follow the owner when the owner is moved. Take the interface type as the parameter, so the caller that owns the value builds the handle; a place reached through a `::` parameter is the caller's own storage and may be handed back, but may not then be moved out from under the handle. Values that only drew on the handle — a `str` or `Ptr` allocated through it — point at the allocator's memory, not at the handle, and are unaffected; so is an implementor with no storage, which has nothing to point at.
- **Passing a `Drop` value to a parameter is a borrow, not a move.** `v.add(1)` does not consume `v`, and a receiver is just the first parameter — so nothing else could be true. A move is spelled `consume` at the call site, and only there.
- **The compiler-inserted `drop` is exempt from the receiver rule.** `drop` is declared `(self :: @Self)`, but scope exit runs it on `:` bindings too. Destroying a value is not mutating it through a binding.

A source-written standard destructor call on a local owner must explicitly
consume that concrete owner: `(consume value).drop()` or
`Type.drop(consume value)`. Consuming an interface handle does not transfer
ownership of the concrete resource behind it. Calls merely named `drop` on
unrelated types or requirements do not carry this destruction contract.
Fields still require owner-managed destruction and reinitialization; the
compiler does not yet prove those field lifetimes.

```groovy fragment
f = alloc.File("x.txt").try();
g = consume f;                  // move, stated at the use site. f is dead after
f.read();                       // ERROR: f was consumed
g = alloc.File(f.path).try();   // want another? construct it
```

**Reference capabilities**, the lite set. The problem they solve: two actors run at once and both hold the same `Vec`; one writes while the other reads. Locks solve it at runtime, types solve it at compile time.

| | can you write? | how many refs exist? | can you send it? |
|---|---|---|---|
| `ref` | yes | many, all inside one actor | **no** |
| `val` | never, ever | many, anywhere | yes |
| `iso` | yes | exactly one, program-wide | yes — and you lose it |

`val` is deeply immutable *forever* — not "you may not write it" but "no writer exists", so any number of actors may read at once. Literals are `val`. `iso` is unique: you may write through it precisely *because* you hold the only reference in the program. So **only `val` and `iso` cross actors** means *share what nobody can change, or hand over what only you have*. Both make races impossible by construction, and there are no locks anywhere in the language.

**None of `ref`, `val`, `iso` is ever written.** There is no capability syntax, and that is deliberate: a behavior's parameters are sendable *by definition* — it is a behavior — so marking them would restate what the declaration already says. The constraint lives on the **argument**, and it is checked where the argument is passed. The checker proves one of two things at every send: the value is deeply immutable (`val`), or it is uniquely owned and handed over (`iso`), which you spell `consume`. The only thing you write is the `consume`.

Sending an `iso` is the same `consume`, tracked the same way:

```groovy fragment
buf ::= alloc.Vec<u8>();
worker.process(consume buf);
buf.add(2).try();              // ERROR: buf was consumed
```

**Data races are compile errors** — not deep copies at runtime.

---

# Modules

**Module paths are `<folder>/<folder>.zen`.** A bare `src/std/std.zen` is module `std`; a folder carries its root beside its children, so `src/gen/gen.zen` is module `gen`. Deliberately not Rust's `mod.rs` (twenty editor tabs all reading `mod.rs` is a real cost) and not Zig's raw path imports (no module concept at all).

Names are qualified by path, imports bind locally, and two modules may define the same top-level name without colliding.

**An import is a binding, in one of two forms.** `pick = one.pick` names one thing by its path: the last segment is the item, everything before it is the module, and the left side is the local name — so `choose = one.pick` renames it. `{ Bag, reseat } = shape` destructures several names out of a module, each bound under its own name. The braces are what make it a destructure; `a, b = m` without them is rejected, so one name and several names can never mean different things by count alone. A path can also name a module: `mem = std.mem` binds the module when `std` exports no item `mem`, and `mem.Alloc` then reads through it. An exported item wins over a module of the same path, so adding a module never changes what an existing import binds. A single bare name on the right aliases a root module (`sh = shape`) or a type (`Alias = Shape`). A name that a module both imports and declares is an error rather than one hiding the other.

**A module-qualified name reads an export.** After `Controller = controller`, `Controller.run(..)` calls the module's exported function, `Controller.Config(..)` constructs its exported struct, and `Controller.ATTACH_PATH` is its exported constant — the same value, folded in the declaring module, that a bare import of `ATTACH_PATH` would give, and usable anywhere a constant is, including inside another constant's value. A name without `*` is refused through the qualifier exactly as it is through an import. A module-qualified *function* is only called, never read as a value.

**A name that is not imported is not visible, and there is no prelude.** `Res`, `Ok`, `Vec`, `String`, `Env` and `println` are ordinary declarations in `std`, and a module that names one imports it like any other name. Everything else needs its import too, and this is not a formality — a compiler that resolves any exported top-level name program-wide makes "two modules may define the same top-level name" impossible, which is the property the flat namespace exists to provide. A whole-program name table also hides missing imports until the day two modules disagree, which is the worst day to find out. An implicit prelude is the same hiding on a smaller scale: a name that appears from nowhere, whose meaning depends on what a list in another file happens to hold.

**What is built in, and nothing else.** These need no import, because they are the language rather than its library:

| built in | what it is |
|---|---|
| `i8` `i16` `i32` `i64` `u8` `u16` `u32` `u64` `u128` `usize` `f32` `f64` `bool` `str` `()` | the primitive types, by spelling |
| `true` `false` | the two `bool` values |
| `consume` | hands over a unique value |
| `@Self` `@meta` `@scope` | the enclosing type, compile-time reflection, the enclosing block |
| `.match` `.try` | the conditional and the early return, which are syntax on any value |
| `std` | the root every standard import starts from |
| `main` | the entry point the build looks for |

The C ABI integers (`c_int` and the rest) and the SIMD vectors (`u8x16` and the rest) are also primitive types the compiler knows by spelling; they belong with the `std.c` bindings and the `std.simd` operations, which are the only code that uses them, and whether naming one should require that import is still open. A primitive's members — `i32.MAX`, `s.len`, `b.then(..)` — are declared in `std.core` and its submodules, in the primitive's own body, so they come with the primitive: `std.core` is part of every program for that reason, but loading it binds no name.

Everything else is imported, with the binding syntax every import uses:

```zen
{ Res, Ok, Err, None } = std.core     // results, Range, Eq, Hash, Display, IoError, Drop, Scope ...
{ Alloc, AllocError } = std.mem
{ Vec, Map } = std.collections
{ String } = std.text
{ Env } = std.env
{ println, print } = std.io
```

Each name is imported from the module that owns it: `std.core` for what is declared under `std/core`, and the folder root otherwise. `std.core` still re-exports `Vec`, `String`, `Env` and the rest, so `{ Vec } = std.core` also resolves, but the owning module is the one the compiler suggests and the one written in this tree. There is no wildcard import and no "common names" line: a reader learns where a name comes from by reading the top of the file, and a module's imports are the list of what it depends on.

**A standard name used without its import is an error that names the fix.**

```
main.zen:3:16: missing import: `Vec` is not imported; add `{ Vec } = std.collections`
```

The diagnostic is reported once per module and name, and the name then resolves as that import would, so one omission is one error rather than a cascade. `Res`, `Ok`, `Err` and `None` are covered exactly like `Vec`: the compiler still recognises them by declaration, but a module that writes one must import it. So is a member of a union of types, `Fail = AllocError | IoError` — a member naming an unimported type would otherwise become an enum variant in silence, which is the worst kind of wrong. A name that no standard module exports is still `undefined name`. `tools/imports` (`zen-imports`) applies these diagnostics to a tree: it asks the compiler which imports each file is missing and writes them.

**The dot does not relax that rule. A type brings what its body declares, and nothing else.** `x.f(..)` finds the members written in `x`'s type — its body's methods and associated functions, its impls, and its bounds' methods — and otherwise the free functions this module already sees: its own declarations, its imports, and the prelude. A free function declared in another module is not reachable until it is imported, however its first parameter is typed. Nothing is gathered program-wide, so two modules may both export `size` for the same first parameter without colliding: a module that imports one calls that one, and a module that imports both has an ordinary overload set that must tell them apart.

The two questions have different answers. A bare name asks "what is `Vec` here", which this module's imports answer. `x.get(0)` asks "what can this value do", which `x`'s type answers for its members and this module's imports answer for everything else — so what a call means is always readable from two files, the type's and the caller's.

**Where behavior lives follows from that rule, and there is no third form.** A fact every consumer asks of a type — a member's name, its exportedness — is a struct-body method, written once, in the type's file. An operation one consumer owns is a free function in that consumer's file, *called on* its receiver: the dot finds the calling module's own names whether they are exported or not, so the call reads `c.check_args(..)` while the declaration never leaves the module that owns the operation. There is deliberately **no out-of-line `impl Member { .. }`** — no block that adds methods to a type from another file, the mechanism Rust scatters a type's surface across a crate with — because the dot already gives the call its method shape without moving the declaration, and `A.impl(B, {..})` exists only to satisfy a bound and lives with `A`. The dividing rule: a fact two modules would both write belongs on the type; an operation one module owns stays in that module and is dot-called. **Cost to accept knowingly:** a type's full callable surface is not readable from its file — what `x` can do depends on what the calling module has in scope — which is the same scatter Rust has, resolved by import rather than aggregated crate-wide, and without a second declaration form to learn.

**Three gaps a `time` module makes unavoidable, named here so they are decided rather than worked around.**

*There is no operator overloading.* `==` through `Eq` is the only operator that dispatches to an impl, so `a + b` on a `Duration` is not writable and a module that wants it writes `add`. Whether arithmetic operators should dispatch is a real question — it is the difference between a `Duration` reading like a number and reading like a record — but it is a language decision, and until it is made, a comment promising `+ - * /` on a struct is describing a language this is not.

*And this document does not say what `a + b` means when `a` and `b` have
different types.* The current compiler accepts this program:

```groovy
f = (a: i32, b: str) i32 { a + b }
```

The emitted C then fails to compile — `incompatible type for argument 2 of 'zg_add_i32'` — so the user's first news of a type error in the most common expression in any language is a C diagnostic naming a mangled internal function.

**The implemented rule is: a binary operator takes its left operand's type,
and the right operand is not checked against it.** The return check can hide the
gap when the left operand already matches the declared result. The bitwise
operators are the exception: `& | ^` check that both operands have the same
unsigned type, and a shift checks that its count is unsigned (see "Unsigned bit
operations").

This remains a language decision, not a C-backend workaround: choose implicit
numeric widening, explicit conversions only, or a rule between them, then add
a sema refusal and focused regression before changing lowering.

*There is no `Ord`.* `std.core` has `Eq` and `Hash` and nothing that orders. Adding one is not a fifth trait beside them: **`Ord` and `Eq` must agree**, exactly as `Eq` and `Hash` must, and a type where `eq` says equal while `compare` says less is a sorted container that loses rows. Whichever is sealed in terms of the other, the relationship is the design.

*A clock is authority and a duration is not.* `Duration`, `Instant`, `Timestamp` and a broken-down civil time are values — no `Env`, constructible in a test, no capability. A `Clock` that reads one, and the timers it schedules, need `Ref` and `Context` and therefore the actor runtime. They do not belong in the same module: `std.core` sits below everything, and a `Clock` declared there would make `std.core` depend on stage 5. It is also what makes "comptime has no clock" true by construction rather than by convention — comptime has no `Env`, and now no import path to one.

**Live process output and periodic work are capability operations.**
`env.proc.run_argv_into(alloc, cwd, argv, out, err)` drains both child pipes
into caller-chosen `Sink` implementations before the child exits. The method
returns its exit code, propagates sink errors, and kills and reaps the direct
child on failure. Sinks receive borrowed chunks valid during `write`; retain a
copy if needed. The method blocks the calling thread, and child-side buffering
still controls when bytes enter the pipes. Buffered `run` and `run_argv` use
the same pipe-drainage implementation.

`std.proc` implements argument validation, NUL-terminated argument storage,
capture buffers, stream scheduling, and child cleanup in Zen using the caller's
allocator. The C backend emits a small POSIX ABI floor for pipe creation,
spawn file actions, polling, reading, waiting, and signalling. Platform types
and constants remain in that floor; emitted C links without a separate process
runtime source. macOS uses `pipe` plus close-on-exec flags, while Linux uses
`pipe2` for atomic close-on-exec setup.

`env.threads.every(alloc, milliseconds, target)` runs a `Tick` receiver on one
worker thread. Returning false from `target.tick()` stops the worker; callers
must `join<i32>()` before releasing captured resources. A target may send actor
messages so that progress state remains mailbox-owned while another thread is
blocked on model or process I/O. This is periodic work with an interval after
each callback, not a real-time deadline guarantee. `env.out.error` writes and
flushes stderr without adding a newline, allowing byte chunks to retain their
original layout.

**`zen build` takes an explicit entry, and `Fs` gets no directory listing.** The driver finds the entry by probing `main.zen` and the root's own name, which cannot find a single-file program named anything else — and the obvious fix, listing the directory, is the wrong one. `std.env.Fs` has five members and its header says why: "There is no open handle, no seek, no listing and no permission surface… Every member added here is a member the self-hosted compiler has to keep working forever." A listing is also authority to enumerate, which is a bigger capability than reading a path you were given.

The information already exists at the call site: whoever invokes the compiler knows which file is the entry. So `zen build <root> --entry <file>` is the answer, and the capability surface does not grow. A build is still a root — the entry names where to start inside it, and everything else follows imports as it always did.

**A constructor belongs to the type it constructs, and that is the hole associated functions fill.** A free `seconds(n: u64) Duration` takes a `u64`, so by the rule above `{ Duration } = std.core.time` gives you every method and no way to make one until `seconds` is imported too. The two obvious answers are both wrong: listing the constructors in every import is noise, and making them visible wherever a `u64` is puts `.seconds()`, `.minutes()` and every other module's `u64`-taking function on every integer in every program, because `u64` is a primitive every program has.

The answer is that a struct body may bind a **function**, read as `Type.name(..)` — `Duration.seconds(60)`. This is the existing "a struct body may bind a name to a value, read as `Type.NAME`" rule plus the fact that a function *is* a value here, and it puts the constructor in the one namespace that is already exactly right: the type it constructs. A name that is neither a variant nor a receiverless member is still refused rather than guessed at — `src/gen/gen_c/gen_c_member.zen` raises a positioned `codegen does not lower this yet`, because a backend that emits C for a form it does not understand turns one diagnostic into a C compiler's.

**`std.core`'s declaration of a primitive's name IS that primitive.** `str` and `i32` are declared as ordinary structs that `std.core` re-exports — `str` in `std.text.text_str` carrying `len`, `get`, `index` and `slice`; `i32` in `std.core.num` carrying `MIN`, `MAX` and `BITS` — and the members they declare belong to the primitive the compiler already knows. They are not a second nominal type that shadows it. Getting this wrong is not a small error: it mints a `str` beside the `str` every literal has, and then every literal, every trap check and every standard-library signature disagrees about which one they meant.

**Re-export is an import whose bindings are starred.** No `export`, no `from` — `*` doing the same job it does everywhere else, and `=` being the binding it already is:

```groovy fragment
// src/std/core/core.zen
{ Res, Ok, None } = std.core.result     // imported, local to this module
{ Res*, Ok*, None* } = std.core.result  // imported AND re-exported
{ str*, String* } = std.text.string     // a type brings its body's methods and its impls
```

A folder root is then just a file of starred bindings, which is why re-export is what makes folders work — and why `std.core` can span several files instead of being one enormous one.

## Printing

`println` and `print` are declarations in `std.io`, imported like anything else:

```zen
{ println } = std.io

main = () i32 {
    println("hello, {}", "world");
    0
}
```

They are bodyless declarations whose bodies the compiler supplies, recognised by **declaration identity**: sema validates them where `std.io` declares them and records each as a printer, and every backend lowers a call that selected one. A `println` imported from any other module is that module's function and nothing more. A leading string literal is read as a format at compile time exactly as `Sink.fmt` reads one — holes, `{name}` lookups and the hole count are checked at the call — and any other first argument is written as a value.

**They answer `()`, and a failed write is not reported.** A closed pipe ends the process with `SIGPIPE`; any other failure loses the bytes. The alternative, `Res<IoError>`, puts a `.try()` or `.ignore()` on every diagnostic line a program prints, and a result that is ignored everywhere teaches readers to ignore results — the opposite of what a must-use `Res` is for. Output whose arrival matters goes through `env.out`, whose `println` returns `Res<IoError>`, and a function that should be handed its output rather than reach for it takes a `Console` or a `Sink`.

**This is the one ambient effect in the standard library.** `Env` carries every other authority, so a function's signature says what it can touch. Standard output is exempt because hello-world should not need a capability parameter, and the exemption is visible: a module that prints this way says `{ println } = std.io` at the top.

---

# Scalar mathematics

`std.math` exports `cos`, `sin`, `sqrt`, `log10`, and `round` for `f64`.
Trigonometric inputs use radians; `round` resolves halfway values away from
zero. These operations allocate nothing and preserve the native math library's
NaN/infinity behavior for domain and range errors. They do not return `Res`.

```groovy fragment
{ cos, sin, sqrt } = std.math
magnitude = sqrt(real * real + imaginary * imaginary);
```

The current backend uses private header-backed `math.h` declarations inside
`std.math`. Application libraries import this standard API instead of repeating
native declarations. Targets with a separate math library must link `m` in
the executable build dependencies. This scalar API does not add SIMD types.

# Explicit native bindings

Native functions can be declared in a Zen namespace associated with a system
header:

```groovy fragment
C* = c.bind("unistd.h", {
    getpid* = () c_int
    close* = (fd: c_int) c_int
})
```

A call such as `C.getpid()` is checked against the Zen signature and lowers to
`getpid()` with `#include <unistd.h>`. There is no generated forwarding wrapper
or duplicate native prototype. The C compiler sees the actual header. Bindings
can live in ordinary Zen modules and be imported by name (for example,
`{ C, VERSION } = posix` when `posix.zen` exports both). Library and framework linking remains a project build
dependency; the header expression does not infer link flags.

An optional second literal selects a native symbol independently of the Zen
member name: `c.bind("stdlib.h", "abs", { absolute* = (v: c_int) c_int })`.
This form calls the symbol through a function-pointer cast with the declared
signature. Every member of that namespace targets the same symbol. This is
useful for runtime dispatch such as Objective-C's `objc_msgSend`, but the author
must supply the correct ABI for every call, including platform-specific return
conventions. A cast does not prove ABI compatibility or ownership safety.

These are explicit declarations, not automatic C header parsing. The binding
namespace cannot be constructed as a runtime object. Its body accepts
non-generic function signatures without bodies and immutable, explicitly typed
integer constants:

```groovy fragment
Socket = c.bind("sys/socket.h", {
    AF_INET6*: i32
    SOCK_CLOEXEC*: i32 = 0
})
```

Required constants may name a macro or enum. An optional nonnegative integer
literal supplies a fallback only when the name is not defined as a C macro;
this presence test does not detect enum-only names. Values come from the target
header, not Zen compile-time evaluation, and cannot size compile-time arrays.
Fallbacks must fit the declared integer type, checked against the target ABI.
The C backend enables its GNU/POSIX feature surface before including native
headers, including in programs that do not use process operations.

`c.record` binds a header-owned record without duplicating its layout:

```groovy fragment
Timespec = c.record("time.h", "struct timespec", {
    tv_sec: c_long,
    tv_nsec: c_long,
})
```

Field names must match the header. Construction uses native designated fields,
zero-initializes omitted native fields, and pointer arithmetic uses the actual
native size. A declaration may expose a subset of fields. Records are nongeneric
and support scalar and pointer fields without defaults. The C backend checks
exact scalar type compatibility against the header, preventing a mutable field
reference from using a wider scalar than the native field. Pointer pointee types,
lifetimes and ownership remain the binding author's explicit FFI responsibility.
Unions, bitfields, packed records and nested record fields are unsupported.

Opaque native type declarations and automatic header imports are not implemented.
An inline binding expression passed to
`b.lib` is also not implemented: put bindings in a Zen module and declare build
dependencies separately. The current implementation validates header and symbol
names when a call is emitted; unused bindings do not cause includes.

`std.native.callback` exposes a named Zen function to a native callback API:

```groovy fragment
{ callback } = std.native
compare = (left: Ptr<()>, right: Ptr<()>) i32 {
    left.to<i32>().read(0) - right.to<i32>().read(0)
}
// Pass callback(compare) to a native function-pointer parameter.
```

It returns a raw `Ptr<()>` containing the function address. The C backend accepts
only one named, nongeneric free function with a body, explicitly typed immutable
scalar or pointer parameters, and a scalar, pointer, or unit result. An omitted
return annotation on a function body means unit and is accepted here too. It rejects
capturing lambdas, local function values, aggregates (including `str`), and
capability values. A native callback has no hidden `Env` or closure context;
use the native API's explicit user-data pointer. The caller must supply the
correct native signature and keep referenced storage alive until the native API
has stopped invoking it. Thread affinity and synchronization remain the
caller's responsibility. Raw function/data pointer conversion uses the native
C toolchain convention supported by the POSIX targets, not a portable ISO C
guarantee. Objective-C blocks and automatic closure capture are separate features.

# Comptime and `@meta`

**`@` is the compiler's namespace.** A leading `@` marks something the compiler supplies that no user code could have written — `@Self` (the type being declared), `@meta` (the ast node for a value or type), `@scope` (the enclosing block). It is not a sigil with meaning of its own and it is not a macro marker; it is one flat namespace, deliberately small, and everything in it is documented here. Anything without an `@` is an ordinary binding you could have written yourself.

`@meta` **builds and reads**, and it does not get a parallel node type — it gets the compiler's own. It has two forms, and both reflect a value's TYPE, never its expression. `@meta(name: Type)` — a labelled binding, `@meta`-specific syntax rather than a call argument, because the right side is a type and the whole thing binds a name — yields Type's declaration payload: the `Struct` value itself for a struct type, which is why `.name` and `.fields()` are real members, and it binds `name` as the runtime receiver that projections like `name.at(field)` read from. `@meta(v)` yields the `Decl` of v's type; `.kind` is its `DeclKind`, and matching it is a comptime typecase whose arms bind v with its type refined per arm. Either way what comes back is the same `Struct` / `Enum` / `Function` values from `std.ast` that `DumpAst` walks and `gen_c.zen` consumes. One AST, three consumers. Building a type is constructing those nodes and returning them.

**Identity: type-returning comptime calls are memoized on their arguments.**

| question | answer |
|---|---|
| does `Circle` itself change? | no — nodes are values; `AddFoo` returns a new one |
| two calls to `AddFoo(Circle)` — one type or two? | one, memoized on (function, args) |
| identity across module boundaries? | the generating call, which is module-independent |
| can it nest? | yes — `AddFoo(AddFoo(Circle))` is just another call to memoize |
| what does the C backend see? | one emitted struct per distinct call, same as a generic |
| what if it escapes its block? | nothing special; identity is the call, not the scope |

Declared types stay **nominal** — `Circle = {radius: f64}` and `Sphere = {radius: f64}` are different types, and an impl on one is not an impl on the other. Only *generated* types are identified by their generating call.

**What runs at comptime:** the language minus io and actors. Comptime code **may allocate** (`@meta`-driven serialization has to build strings) and may loop, but the evaluator counts steps and fails the build rather than hanging. **No file reads in v1** — that is the fastest route to a build that is not reproducible.

---

# Constants on a type

A struct body may bind a name to a **value** rather than a field, and it is read as `Type.NAME`. That access form already exists — `Shape.Unit`, `Os.Macos` — so this adds a spelling, not a concept:

```groovy
i32* = {
    MAX*: i32 = 2147483647,     // starred: a constant crossing a module
    MIN*: i32 = -2147483648,    // boundary obeys law 6 like everything else
    BITS*: usize = 32,
}
```

and read back, in a body:

```groovy fragment
x = i32.MAX;              // a constant, resolved at comptime
buf: [u8, i32.BITS]       // usable wherever a comptime value is
```

The distinction from a field: a field declares storage per value, a constant declares one value per type. `MAX: i32 = 2147483647` inside `i32` is the second, because `i32` has no instances to give it storage in. Every primitive numeric type carries `MIN`, `MAX`, and `BITS` from `std.core.num`, with no import.

**The spelling is what decides, and it decides everywhere.** `name: T = value` in a struct body is a constant whether or not the type has instances; `name :: T = value` is storage with a default. That is the whole rule, and the "Declarations" section above prices what it costs.

**A constant is one value per type, so it folds wherever it is read.** `Limits.WIDTH` and `j.WIDTH` for a `j: Limits` are the same one value — a constant takes no storage, so there is nothing in `j` for the second to read and the type arriving on the left of the dot cannot change the answer.

---

# Ranges and sequences

**`Range<T>` is the integers from `start` up to, but not including, `end`, of one integer type `T`** — signed or unsigned, any width. `T` is the bounds' type and the type of every value a loop over the range visits, so a sum over `Range(0, 100)` is i32 arithmetic and a walk over `Range(0, v.len)` visits usize positions. `Range(end)` is `Range(0, end)`. A range whose end is not past its start is empty, and stepping never overflows: the last value is `end - 1`.

```zen
sum: i32 = Range(0, 100).loop(0, (h, i, v, acc: i32) { acc + v }).value_or(0)

Range(10).loop((v) { .. })                 // 0 through 9, i32
to: usize = 10;
Range(0, to).loop((v) { .. })              // usize: the literal takes `to`'s type
a: i32 = -3; b: i32 = 3;
Range(a, b).loop((h, i, v) { .. })         // i = 0..5 (passes, usize), v = -3..2 (i32)
r: Range<u8> = Range(0, 200);              // the written type settles the literals
Range<i64>(0, 5).loop((v) { .. })          // or the call writes it
```

**The bounds' type is read off the bounds, as any literal's type is read off its context.** A typed bound decides it and a literal bound takes that type; with only literals, a written binding type (`r: Range<u8> = Range(0, 200)`) or written type arguments (`Range<usize>(0, 4)`) decide it, and otherwise the literal default, i32, does. Two typed bounds of different types are an error at the second, naming both types and the conversion that makes them one — `Range(a, b)` with an i32 `a` and a usize `b` says to write `.to_i32()` on `b` or `.to_usize()` on `a`. There is no implicit widening between them, the same rule arithmetic follows. The rule is not Range's: every generic construction reads its type arguments off its field values this way.

**`Seq<T>` is what a loop walks.** `loop`, `find`, `map`, `filter` and `is_in` take any `R: Seq<T>`: a type with usize positions `start` up to `end` and an `at` that maps a position to its value, `None` ending the walk early. A collection implements it — `Vec.impl(Seq<T>, { start: 0, end: self.len, at ::= .. })` — and a fixed array and a `Range` are Seqs of their elements and values without an impl: the compiler walks those directly, a range's counter running in `T` itself.

Before this split, `Range<T>` was both: a usize index interval and the bound whose `at` mapped an index to a `T`. So `Range(0, 100)` always walked usize, an i32 sum over it was a type mismatch, `Range(a, b)` refused i32 bounds, and `r: Range<i32> = Range(0, 1)` produced two different C types. The migration is mechanical:

```zen
// before                                  // after
X.impl(Range<T>, { start: .., at ::= .. }) X.impl(Seq<T>, { start: .., at ::= .. })
walk = <R: Range<T>, T>(r: R) ..           walk = <R: Seq<T>, T>(r: R) ..
Range(0, 4).loop((i) { p.write(i, 0) })    Range<usize>(0, 4).loop((i) { p.write(i, 0) })
Range(0, v.len).loop((h, i) { .. })        unchanged: v.len is usize
```

Only a range whose bounds are all literals and whose values are used as usize changes, and the compiler names each one.

---

# Overloading

Resolution is on **declared parameter types and arity**, and a closure's type is its full signature. There is no carve-out: `loop` overloads on `(value: T)`, `(h: LoopHandle, value: T)`, and `(h: LoopHandle, index: usize, value: T)` for exactly the reason `toString` overloads on a buffer versus an allocator.

**Parameter names are documentation, not identity.** `(a: i32, b: i32) i32` and `(x: i32, y: i32) i32` are the same type, and overload resolution never sees names. Two candidates that differ only in parameter names are the same signature, and declaring both is an error at the declaration site — named for both declarations, when the generic is instantiated.

Function types must name their parameters: `(i32, i32) i32` says nothing about which `i32` is which. `() ()` has nothing to name and stays as it is.

One consequence worth stating: an unconstrained generic parameter swallows a concrete one, so `fold`'s `(init: A, body: ..)` and a hypothetical `(alloc: Alloc, body: ..)` cannot be overloads. The allocating variant gets its own name, `map` — which is honest anyway, since it is the one that allocates.

A generic bound can prove that a structurally matching concrete parameter is
excluded. For example, `R: Seq<T>` excludes a concrete boolean condition when
the substituted bound is known. An unresolved type or bound is not proof of
disjointness. The current check is conservative for optional tails and does
not attempt general logical reasoning between generic constraints.

---

`str.split_once` accepts a byte or string separator and returns borrowed
`before`/`after` views, or `None` when the separator is absent. `str.lines()`
returns a borrowed cursor: LF and CRLF terminate lines, interior empty lines
remain, and empty input or a final terminator adds no extra line. A lone CR
remains data. `next()` advances the cursor; its three `loop` callback forms
start from the beginning without advancing that cursor. These operations do
not allocate or extend the input's lifetime. `Lines` currently supports direct
`next`/`loop` traversal, not the generic indexed `Seq` consumer APIs.

```groovy // just using this for highlighting
// std.text.string

// borrowed view of text: pointer + length, no alloc, no growth,
// no allocator. string literals are str, living in static memory.
// (* is reserved for exports, so raw pointers are Ptr<T>)
//
// str is BYTES. len is a byte count, indexing yields u8, == is
// bytewise. utf-8 is functions over bytes — s.codepoints(),
// s.validate_utf8() — paid for only where the guarantee is wanted
str* = {
    data: Ptr<u8>,
    len*: usize,      // * so a byte count is readable outside std.text
}

// owned, growable text. Vec already carries len, capacity, and
// the Alloc it grows with, so String adds nothing on top: it IS
// the buffer. there is no separate StringBuffer type
String* = {
    data :: Vec<u8>,

    add* = (self :: @Self, fmt: str, args: ...) Res<WriteError>
    view* = (self: @Self) str
}

// anything bytes can be written to. a String is one and a console
// is one, which is what lets `{}` format into either without the
// format machinery knowing which it has
Sink* = {
    write* = (self :: @Self, bytes: str) Res<WriteError>

    // a sink that takes bytes but not A byte forces every integer
    // writer to allocate, which is the exact cost this design
    // exists to avoid: digits are produced one at a time, `str`
    // BORROWS bytes, and the only way to get a `str` to borrow is
    // a `Ptr` from an Alloc. so one byte is its own member
    write_byte* = (self :: @Self, byte: u8) Res<WriteError>
}

String.impl(Sink, {
    write      = (self :: @Self, bytes: str) Res<WriteError> { .. }
    write_byte = (self :: @Self, byte: u8) Res<WriteError> { .. }
})

Display* = {
    // sealed (=): the mechanical debug dump. @meta walk over
    // the fields, "Name { field: value, .. }". always there,
    // for every type, never overridden. fields() is the
    // member-filtered view of members; self.at(field) is the
    // comptime-substituted projection — this instance's value
    // for that field
    dump* = (self: @Self, out :: Sink) Res<WriteError> {
        out.fmt("{} {", @meta(self: @Self).name);
        @meta(self: @Self).fields().loop((h, field) {
            out.fmt(" {}: {},", field.name, self.at(field));
        });
        out.fmt(" }");
        Ok;
    }

    // outlined only (::=, no body): the pretty representation,
    // impls define THIS one. format machinery routes {} through
    // it, falling back to dump when a type hasn't defined one.
    // writes into a sink the CALLER owns, so nesting never
    // allocates and printing never allocates at all
    toString* ::= (self: @Self, out :: Sink) Res<WriteError>

    // sealed overload (=): the allocating form, derived from
    // the sink form, so the two can never diverge. overload
    // resolution picks by what you pass: a sink or an allocator
    toString* = (self: @Self, a: Alloc) Res<String, WriteError> {
        sb ::= a.String().try();
        self.toString(sb).try();
        Ok(sb);
    }
}


// std.core: imported like any module, `{ Res, Ok, Err, None } = std.core`

Res*<T> = { Ok: T | None }

Res*<T, E> = { Ok: T | Err: E }

// hoisting: a bare T lifts into Res<T> wherever a Res is
// expected, so the obvious thing just works:
//   Foo = { bar: Res<i32> }
//   foo = Foo(bar: 32)       // lifted to Ok(32)
//   foo = Foo(bar: Ok(32))   // identical, explicit
// same in returns: `0;` closes a Res<i32, E> function like
// `Ok(0);` does. hoisting only fires when exactly ONE variant
// carries the type; ambiguous cases require the explicit form.
// only success lifts: Err and None are always written, failure
// stays visible, and a None never becomes an Err

// error propagation: .try() unwraps Ok, or returns the Err /
// None from the ENCLOSING function. it is the non-local-exit
// intrinsic, not a method on Res — same mechanism as h.break:
//   sb ::= alloc.String().try();
//   self.toString(sb).try();

// the one-sided conditional. match is ALWAYS exhaustive, so there is
// no partial form to hide a dropped case in: when you genuinely want
// nothing on the false side, you write .then and it is visible in the
// source. lands in Res, so it composes with .try() and match like
// anything else — Ok(v) when true, None when false.
// a plain ufcs function: first param is bool, so it calls as a method
then* = <T>(b: bool, f: () T) Res<T>

// boolean preconditions: absence or a caller-chosen error
ensure* = (b: bool) Res<()>
ensure* = <E>(b: bool, reason: E) Res<(), E>
// ready.ensure().try() returns None from an optional-result function.
// ready.ensure(Error.NotReady).try() propagates the named failure.

// RAII: the compiler calls drop when a binding leaves scope,
// reverse declaration order, exactly once. exactly-once is why
// `consume` exists: a Drop value cannot be copied. Allocators
// are the flagship user: mem.alloc() returns an arena, and
// dropping the arena frees everything ever allocated from it
Drop* = {
    drop = (self :: @Self) ()
}

// @scope is the enclosing block, as a value — what LoopHandle is
// to a loop, one level down. non-escaping: it may be passed
// INWARD so a helper can register cleanup on its caller's block,
// but never stored, returned, or captured by an escaping closure
Scope* = {
    // runtime cleanup, for the ad-hoc cases Drop doesn't cover.
    // registers a closure on THIS block; they run LIFO at block
    // exit, BEFORE drops. a stack of closures, not a map: order
    // matters, and the stack lives with the block that owns it.
    //
    // capped at 32 per block: the 33rd registration on one block
    // is a runtime trap (`too many deferred closures on one
    // block`), not a program bug you could have caught earlier —
    // the limit is the language's. a defer written INSIDE a loop
    // body lands on the body's own block, fresh each iteration,
    // and never hits it; capturing an ENCLOSING block's Scope and
    // registering on it across iterations is where the cap bites.
    defer* = (self: @Self, f: () ()) ()
}


// the capability root. main receives one, and ALL authority
// flows from it, pony-style: no ambient net, threads, files or
// page allocation. The one ambient effect is standard output
// through std.io's println and print, and a module declares it
// by importing them (see "Printing" below)
ArgError* = { Missing: str   // required field absent; names the field
          | Parse: str }   // value present but not the field's type

// the disk. Each member earns its place: a compiler reads a whole
// file at once, never streams and never seeks, so there is no
// handle and no `open`. A module tree is <folder>/<folder>.zen and
// is COMPUTED rather than discovered, so nothing needs a listing --
// but a walk still has to tell a folder from a file before opening
// it, and ruling a candidate path out should cost a stat rather
// than reading a megabyte to learn nothing. Hence exactly is_dir
// and exists beside read. And write arrived with `-o`, remove with
// #757: a program that can create state must be able to retire it.
//
// `read` takes an Alloc because it allocates, returns Res because a
// missing file is a caller's problem and not a bug, and is `:`
// because a handle's methods are `:` -- a bitwise copy of an Fs sees
// the same filesystem.
FsError* = { NotFound | Denied | IsDir | Failed | OutOfMemory }

Fs* = {
    read*   = (self: @Self, a: Alloc, path: str) Res<String, FsError>
    write*  = (self: @Self, path: str, bytes: str) Res<FsError>
    remove* = (self: @Self, path: str) Res<bool, FsError>
    exists* = (self: @Self, path: str) bool
    is_dir* = (self: @Self, path: str) bool
}

// OutOfMemory is a member of FsError only because the seed subset has
// no error unions and no From, and `read` allocates. When unions
// arrive the signature becomes Res<String, FsError | AllocError> and
// the variant goes.
//
// `write` arrived the moment it had a caller and not before: `zen build
// src -o stage2.c` cannot honour its own `-o` without one, so the
// fixpoint could not complete. No append, no mode, no handle — the
// compiler writes one file once. It takes no Alloc because it allocates
// nothing: the bytes are the caller's and stay the caller's.

Env* = {
    argv: Vec<str>,       // raw argv; argv.get(0) is the program path
    out: Console,         // stdout / stderr
    mem: Mem,             // page authority: env.mem.alloc() makes an arena
    fs: Fs,               // the disk. `read` is the whole file at once
    net: Net,             // named and empty until something needs it
    threads: Threads,     // the thread escape hatch, no longer ambient

    // one environment variable, by name. NOT a `vars: Map<str, str>`
    // field, which is what this said until it was tried: the Env is
    // built before `main` is entered and the only allocator door is
    // `env.mem.alloc()` inside it, so the map could only ever be the
    // zeroed one — and a zeroed map answers None for every key that IS
    // exported, which is a wrong answer that looks like a right one.
    // A capability instead, floored on `getenv`. No Alloc: the bytes
    // are the process's environment block, borrowed for its lifetime
    // exactly as an argv row is. Res<str> because unset is an absence
    // and not a failure with a reason
    var* = (self: @Self, name: str) Res<str>

    // typed args: declare a schema struct, @meta walks its
    // fields and fills them. each field maps to --flag and its
    // SCREAMING env var, flag wins. Res<T> fields may be absent
    // (None), fields with defaults are optional, everything
    // else is required and errors by name. this IS the cli story
    args* = <T>(self: @Self) Res<T, ArgError>

    spawn* = <A: Actor>(self: @Self, actor: A) Res<Ref<A>, ActorStartError>
}

// equality and hashing, same shape as Display: one overridable
// core with an @meta default, sealed laws around it
Eq* = {
    // default (::=): field-wise comparison via @meta walk;
    // override for custom equality
    eq* ::= (self: @Self, other: @Self) bool { /* @meta field-wise */ }

    // sealed law: ne is always !eq, they can never diverge
    ne* = (self: @Self, other: @Self) bool { !self.eq(other) }
}

Hash* = {
    // default (::=): feeds every field through the hasher
    hash* ::= (self: @Self, hasher :: Hasher) u64 { /* @meta field-wise */ }
}


// std.mem.zen
// the law: there is NO ambient allocator. ordinary library allocation
// takes an Alloc. runtime capabilities may own the storage named by
// their contract (actor mailboxes and arenas are the current example)

AllocError* = | OutOfMemory

// the allocator interface. everything that allocates takes one.
// implementations: arena (mem.alloc()), fixed buffer, c malloc.
// only raw is required; the typed conveniences are defaults.
// Alloc is itself the fat-value shape every trait value has:
// a receiver plus function pointers, passed by value
Alloc* = {
    raw* = (self: @Self, size: usize, align: usize) Res<Ptr<u8>, AllocError>
    realloc* = <T>(self: @Self, p: Ptr<T>, count: usize) Res<Ptr<T>, AllocError>
    free* ::= <T>(self: @Self, p: Ptr<T>) ()    // arenas no-op this

    // one typed convenience, a default built on raw:
    create* ::= <T>(self: @Self) Res<Ptr<T>, AllocError>
}

// Vec, Map and String are NOT members of Alloc. each is a ufcs
// function declared beside its OWN type, taking an Alloc first:
//
//     Vec*    = <T>(a: Alloc) Vec<T>                 // std.collections
//     Map*    = <K, V>(a: Alloc) Map<K, V>           // std.collections
//     String* = (a: Alloc, fmt: str, args: ...) Res<String, AllocError>
//
// the call surface is identical — `alloc.Vec<i32>()` either way,
// because a free function whose first parameter is the type is
// callable as a method. what changes is the direction of the
// dependency. as members they would put Vec-shaped defaults inside
// std.mem, which cannot see Vec's unexported fields, and mem and
// collections would have to import each other.
//
// Vec and Map return a bare value: an empty one owns no pages yet, so
// construction cannot fail. the first add allocates, and THAT returns
// Res. String takes a format and must hold the result, so it allocates
// at once and says so.

// Alloc is an INTERFACE, so an Alloc value is a fat value: a receiver
// pointer plus function pointers. It is a handle, it is freely copied,
// and it is NOT Drop. Copying it copies two words, never ownership.
//
// the concrete allocator behind it owns the memory and is what Drop
// applies to. env.mem.alloc() hands back an Arena; the Arena impls
// both, and passing it where an Alloc is wanted builds the handle
Arena* = {
    // pages, free lists, whatever the arena needs. owns them.
}

Arena.impl(Alloc, { ... })

Arena.impl(Drop, {
    drop = (self :: @Self) { /* release every page at once */ }
})


// std.collections.zen
// everything here is sealed (=): collections are not extension
// points, and sealed methods compile to direct, inlinable calls

// fixed-size arrays are [type, count]: comptime length, lives
// on the stack, no alloc. [0, 1, 2] literals infer [i32, 3].
// indexing is bounds-checked and TRAPS: a fixed array has no
// Res escape hatch, and an out-of-range index is a bug
//   buf: [u8, 64]
//   primes = [i32, 4](2, 3, 5, 7)

Vec*<T> = {
    data :: Ptr<T>,
    len* :: usize,      // * is readable outside; mutation still only via methods
    capacity :: usize,
    alloc: Alloc,       // : set once at construction

    // `self :: @Self` — mutates the receiver. @Self is Vec<T> here.
    // the handle
    // in self.alloc stays usable: `:` is shallow, it protects
    // the field's own bytes, not what it points at
    add* = (self :: @Self, value: T) Res<AllocError> {
        (self.len == self.capacity).then(() { self.grow().try() });
        self.data.write(self.len, value);
        self.len = self.len + 1;
        Ok;
    }

    // moves an element OUT, leaving the vec one shorter. without this a
    // Vec<T> of Drop values can be filled and never emptied
    take* = (self :: @Self, i: usize) Res<T>

    get* = (self: @Self, i: usize) Res<T> {
        (i < self.len).then({Ok(self.data.read(i)),
        });
    }

    grow = (self :: @Self) Res<AllocError> {
        cap = (self.capacity == 0).match({
            true => 8,
            false => self.capacity * 2,
        });
        self.data = self.alloc.realloc(self.data, cap).try();
        self.capacity = cap;
        Ok;
    }
}

// internal: no *, not visible outside std.collections
Entry<K, V> = {
    hash: u64,
    key: K,
    value: V,
}

// bounds: K must be Eq + Hash. the hash finds the bucket fast,
// eq confirms the key: comparing hashes alone returns wrong
// values on collision
Map*<K: Eq + Hash, V> = {
    entries :: Vec<Entry<K, V>>,

    set* = (self :: @Self, key: K, value: V) Res<AllocError> {
        h = key.hash(Hasher());
        // probe: overwrite where hash matches AND key.eq, else:
        self.entries.add(Entry(hash: h, key: key, value: value)).try();
    }

    get* = (self: @Self, key: K) Res<V> {
        h = key.hash(Hasher());
        self.entries.loop((hd, e) {
            ((e.hash == h) && e.key.eq(key)).then(() { hd.break(e.value) });
        });
    }
}


// std.test.zen
// no test keyword, and no discovery baked into the compiler:
// build.zen walks the module tree itself (b.module) and
// registers Tester-taking functions as the test target. the
// function name IS the test name. Reflection-based registration remains
// proposed. Today `zen test` runs explicit Builder.exe_test(Exe) targets, and
// std.test.Suite supplies per-callback arenas and assertion reporting.

TestError* = { | Failed: str }

Tester* = {
    env: Env,
    alloc: Alloc,   // per-test arena: dropped after each test,
                    // so leaks are contained and reported

    expect* = (self: @Self, cond: bool) Res<TestError>

    // dumps both sides via Display.dump on failure
    expect_eq* = <T: Eq>(self: @Self, a: T, b: T) Res<TestError>
}

// benchmarking: same discovery shape, take a Bencher instead.
// because ALL allocation goes through Alloc (the law), the
// bencher counts allocs and bytes per op for free, with zero
// instrumentation
Bencher* = {
    env: Env,
    alloc: Alloc,

    // runs f until timing stabilizes
    iter* = (self: @Self, f: () ()) BenchStats
}

BenchStats* = {
    ns_op: u64,
    allocs_op: u64,
    bytes_op: u64,
}


// std.build.zen

BuildError* = NotFound
     | FetchFailed
     | VersionConflict
     | HashMismatch

// a dependency, hash-locked: the url and version say what you
// asked for, the hash pins what you actually got
Package* = {
    url: str,
    version: str,
    hash: str,
}

// build.zen runs in the middle of a three-phase build:
//   parse every module  ->  run build.zen  ->  compile
// so b.module can READ any module's declarations (that is how
// test discovery works) but build.zen may never CALL code from
// the tree it configures — that would need the tree compiled
// before the thing that says how to compile it
Builder* = {
    os: Os,        // Macos, Linux, Windows
    arch: Arch,    // X86_64, Arm64
    env: Env,
    alloc: Alloc,  // build-time arena
    exe: Exe,
    lib: Lib,

    // the parsed module graph, as the same ast.zen nodes DumpAst
    // walks. build programs can inspect their own project: this
    // is how test discovery is WRITTEN in build.zen instead of
    // baked into the compiler
    module* = (self: @Self, path: Path) Module

    // packages are declared in build.zen itself (build files
    // are programs, no separate manifest format). fetched into
    // a content-addressed cache, verified against hash
    add* ::= (self :: @Self, name: str, pkg: Package) Res<Dep, BuildError>
    remove* ::= (self :: @Self, name: str) Res<BuildError>

    // build-time budget: total and per-target compile times are
    // tracked against a rolling median
    budget* = (self :: @Self, d: Duration) ()
}

// a locked expectation for one bench.
//
// allocs_op and bytes_op are DETERMINISTIC — identical on every
// machine — so exceeding them FAILS THE BUILD. ns_op and the
// build-time budget are wall clock, which varies 2-5x on shared
// ci, so they are tracked against a rolling median and fail only
// on a sustained shift. a flaky gate gets switched off, and it
// would take the honest gates down with it
Budget* = {
    name: str,
    ns_op: u64,
    allocs_op: u64,
    bytes_op: u64,
}
```

```groovy
// ~/zen/src/loop.zen
// one construct. the compiler picks the variant by signature —
// the ordinary overload rule, with a closure's type being its
// full parameter list. no carve-out for closures
//
// loops NEVER allocate: bodies are stack closures inlined at
// the call site, index and acc thread by value, and a fold
// compiles to a plain C for-loop. the one variant that can
// allocate is map, and it is a different NAME rather than an
// overload — a generic `init: A` would swallow `alloc: Alloc`,
// so they could not be told apart. the traversal itself needs
// no allocation; a callback may use its own allocation capability

// while true
loop*<T> = (body: (h: LoopHandle) ()) Res<T>

// while true, with iteration counter
loop*<T> = (body: (h: LoopHandle, index: usize) ()) Res<T>

// while cond
loop*<T> = (cond: () bool, body: (h: LoopHandle) ()) Res<T>
loop*<T> = (cond: bool, body: (h: LoopHandle) ()) Res<T>

// ranged / collection iteration: value, control, or control and index
loop*<R: Seq<T>, T> = (range: R, body: (value: T) ()) Res<T>
loop*<R: Seq<T>, T> = (range: R, body: (h: LoopHandle, value: T) ()) Res<T>
loop*<R: Seq<T>, T> = (range: R, body: (h: LoopHandle, index: usize, value: T) ()) Res<T>

// fold: init seeds acc; natural completion returns Ok(acc).
// at(None) exhausts a supplied range. h.break() returns None;
// h.break(value) returns that value instead of the accumulator.
loop*<R: Seq<T>, T, A> = (range: R, init: A, body: (value: T, acc: A) A) Res<A>
loop*<R: Seq<T>, T, A> = (range: R, init: A, body: (h: LoopHandle, value: T, acc: A) A) Res<A>
loop*<R: Seq<T>, T, A> = (range: R, init: A, body: (h: LoopHandle, index: usize, value: T, acc: A) A) Res<A>

// map: collect one value per element in caller-chosen storage.
// The handle forms can skip an element or stop with the values made so far.
map*<R: Seq<T>, T, U> = (range: R, alloc: Alloc, body: (value: T) U) Res<Vec<U>, AllocError>
map*<R: Seq<T>, T, U> = (range: R, alloc: Alloc, body: (h: LoopHandle, value: T) U) Res<Vec<U>, AllocError>
map*<R: Seq<T>, T, U> = (range: R, alloc: Alloc, body: (h: LoopHandle, index: usize, value: T) U) Res<Vec<U>, AllocError>

// find borrows; filter collects accepted elements in order.
find*<R: Seq<T>, T> = (range: R, pred: (value: T) bool) Res<T>
filter*<R: Seq<T>, T> = (range: R, alloc: Alloc, pred: (value: T) bool) Res<Vec<T>, AllocError>

// key/value containers
loop*<K, V> = (map: Map<K, V>, body: (h: LoopHandle, key: K, value: V) ()) Res<()>

// LoopHandle controls flow, via the same non-local-exit
// mechanism as .try():
//   h.next()        continue
//   h.break()       break, loop evaluates to None
//   h.break(value)  break with value, loop is an expression
```

The collecting APIs return typed allocation failures. Older callers that
matched `None` from `map` or `filter` must now handle `Err(error)`; no matches
still produce `Ok` containing an empty vector. A `.try()` written in a callback
returns through the function where that callback was written. The helper's own
allocation `.try()` returns its allocation error to the helper's caller.

Written parameter and return annotations on a nongeneric callback constrain
generic inference before ordinary argument inference. For example, `acc: usize`
can contextualize a literal fold seed. Explicit type arguments retain priority,
and an incompatible already-typed argument is still rejected.

```groovy
// ~/zen/src/std/actor.zen
// actors are the primary shared-concurrency model. Threads is an
// explicit Env escape hatch for FFI and batch work.
//
// a behavior is any method in an Actor impl (lifecycle hooks
// aside). calling a behavior on a Ref enqueues a message and
// returns immediately: calling IS sending. the message enum
// behind the behaviors is emitted from their signatures by gen_c_actor.
//
// three guarantees replace every lock:
//   one message at a time per actor -> actor state is single-threaded
//   causal ordering                 -> A's messages to B arrive in send order
//   payload checking                -> unsafe graphs are refused
//
// Direct consumed Vec<u8> payloads are deep-copied into receiver-backed
// storage before admission succeeds; borrowed and nested vectors are refused.
// General deep val/iso sendability and unique graph handoff are still owed.
//
// Callers may stop and join a Ref. Concurrent join callers pin the actor
// record; shutdown drains accepted work, closes workers, waits for pins and
// detaches the registry before freeing records. Concurrent/repeated shutdown
// waits for the same completion. Retired Ref operations check registration
// before dereferencing: sends report Closed; stop/join return. Message data
// preserves the allocator's 16-byte alignment.
// Records are retained until runtime shutdown, including stopped actors.
// This does not provide bounded actor churn or checked raw-pointer lifetimes.

ActorError* = { Closed | Full }

// the address of an actor. freely sendable. behavior calls on
// a Ref are messages. every Ref also carries:
//   stop* ::= (self: @Self) ()  // delivers stopped after the mailbox drains
//   join* ::= (self: @Self) ()  // waits until draining and stopped complete
Ref*<A> = {
    id: u64,
}

Context* = {
    env*: Env,      // authority flows from Env, no ambient globals

    // per-actor arena (pony's per-actor heap, minus the GC),
    // rooted in the RUNTIME, not in main's arena: an actor
    // draining its mailbox after main returns still has memory.
    // drops when the actor stops, freeing everything it made
    alloc*: Alloc,
}

// Marker bound. gen_c recognizes optional `started` and `stopped`
// methods by name in an Actor impl.
Actor* = {}

// on Env, the capability root:
// spawn* = <A: Actor>(self: @Self, actor: A) Res<Ref<A>, ActorStartError>
```

```groovy
// ~/zen/src/std/thread.zen
// an explicit escape hatch for ffi and batch work. Actors currently
// own one worker each, so blocking a behavior stalls that actor;
// scheduler policy and enforcement remain owed.
//
// a thread is authority — the one kind that can outlive its
// creator — so it hangs off Env like io and pages do. there is
// no ambient thread.spawn

ThreadError* = { SpawnFailed | Panicked }

Thread* = {
    id: u64,

    // block until the body finishes, yields its result
    join* = <T>(self: @Self) Res<T, ThreadError>
}

Threads* = {
    // body is a closure; it captures its scope. an escaping
    // closure needs memory, so it says so: the Alloc law does
    // not stop at collections
    spawn* = <T>(self: @Self, a: Alloc, body: () Res<T, ThreadError>) Res<Thread, ThreadError>

    sleep* = (self: @Self, ms: u64) ()
}
```

# Example Zen Code

```gitignore
# ~/example_zen/.gitignore

*.exe
*.dll
*.so
*.dylib
*.lib
*.obj
*.pdb
*.exp
*.def
build/
```

```c
// ~/example_zen/src/extern_add.c

int add(int a, int b) {
    return a + b;
}

// ~/example_zen/src/extern_add.h

int add(int a, int b);
```

```groovy
// ~/example_zen/build.zen
// build files are zen programs; b is the Builder from std.build.
// b is `::` because b.add / b.exe / b.test mutate the graph

// Design sketch, not the implemented package API: see BUILD_PACKAGES.md.
// package declarations are plain data at module level, build()
// wires them into the graph. hash-locked, and the cli edits
// these lines for you: `zen add json` / `zen remove json`
json_pkg = Package(
    url: "https://github.com/zen-pkgs/json",
    version: "0.3.1",
    hash: "sha256:9f2a...",
)

build = (b :: Builder) Res<BuildError> {

    // and build programs can branch on the target, match on
    // b.os right here, no cfg annotations, no ifdef
    lib_paths = b.os.match({
        Macos => ["/opt/homebrew/lib"],
        Linux => ["/usr/local/lib"],
        Windows => ["C:/sodium/lib"],
    });

    json = b.add("json", json_pkg);

    libsodium = b.lib("libsodium", {
        src: Path("src/extern.c"),
        libs: ["sodium"],
        paths: lib_paths,
    });

    extern_add = b.extern("extern_add", {
        src: Path("src/extern_add.c"),
        libs: ["add"],
        paths: lib_paths,
    });

    // per-os executable suffix
    ext = b.os.match({
        Windows => ".exe",
        _ => "",
    });

    // deps are wired per target, swift-style: main.zen may only
    // import through `deps.` what this list declares. out defaults to
    // build/{os}-{arch}/{name} if omitted; gitignore covers build/
    b.exe("example_zen", {
        src: Path("src/main.zen"),
        deps: [json, libsodium, extern_add],
        out: Path("build/{}-{}/example_zen{}", b.os, b.arch, ext),
    });

    // test discovery is just code, not compiler magic: walk the
    // PARSED module tree, keep every function whose single
    // parameter is a Tester. Function-target execution is still proposed;
    // the current `zen test` runs explicitly registered Exe targets. change the filter, change what a test is
    tests ::= b.alloc.Vec<Function>();
    b.module(Path("src")).functions.loop((h, f) {
        (f.params.len == 1 && f.params.get(0).try().type == Tester)
            .then(() { tests.add(f).try() });
    });

    b.test("example_zen_tests", {
        tests: tests,
        deps: [json, libsodium, extern_add],
    });

    // benches: same walk, different filter. this is the "change
    // the filter, change what a test is" promise, kept
    benches ::= b.alloc.Vec<Function>();
    b.module(Path("src")).functions.loop((h, f) {
        (f.params.len == 1 && f.params.get(0).try().type == Bencher)
            .then(() { benches.add(f).try() });
    });

    // budgets live HERE, in code, reviewed like code. allocs_op
    // and bytes_op are deterministic, so over budget FAILS the
    // build. ns_op is wall clock, tracked against a rolling median
    b.bench("example_zen_bench", {
        benches: benches,
        budgets: [
            Budget(name: "vec_add", ns_op: 40, allocs_op: 1, bytes_op: 64),
        ],
    });

    // and the build budgets itself: per-target compile times are
    // tracked, so a build never quietly grows to 20 minutes
    b.budget(Duration.seconds(60));
}
```

```groovy
// ~/example_zen/src/main_test.zen
// tests live next to code. no annotations: build.zen's walk
// finds these because their single parameter is a Tester
{ Res, Ok } = std.core
{ Tester, TestError, Bencher } = std.test

vec_grows* = (t: Tester) Res<TestError> {
    v ::= t.alloc.Vec<i32>();
    v.add(1).try();
    v.add(2).try();
    t.expect_eq(v.len, 2).try();
}

shape_prints* = (t: Tester) Res<TestError> {
    s = Shape.Unit;
    out = t.alloc.String("{}", s).try();
    t.expect_eq(out.view(), "unit").try();
}

// a bench: found by the Bencher filter in build.zen
vec_add* = (bn: Bencher) Res<TestError> {
    bn.iter(() {
        v ::= bn.alloc.Vec<i32>();
        v.add(1);
    });
}
```

```groovy
// ~/example_zen/src/main.zen

// imports are just bindings, with three roots: a project folder,
// `std`, and `deps`. deps holds exactly what build.zen's `deps`
// list granted THIS target; any other name under deps is an error,
// and a dependency is never reachable by its bare name.
//
// importing a type brings what its body declares: its methods,
// its associated functions, and its impls. a free function over
// the type is imported by name, like any other function.
// * is the one gate — it means "this name crosses a module
// boundary" — so Vec brings add/get but never grow or Entry.
// nothing else is implicit: every name below that this file does
// not declare is on one of these lines
{ Res, Ok, Err, None, Display, Sink, WriteError, IoError } = std.core
{ Alloc, AllocError } = std.mem
{ Vec } = std.collections
{ String } = std.text
{ Env, ArgError, ThreadError } = std.env
{ Actor, Context, Ref } = std.actor
{ println } = std.io
json = deps.json
sodium = deps.libsodium

Circle = {
    radius: f64,
}

// ufcs: a free function whose first param is Circle calls like a
// method in any module that declares or imports it.
// this IS the method form — a method is a ufcs function whose
// first parameter is named self and whose type is inferred
area* = (c: Circle) f64 {
    c.radius * c.radius * 3.14159
}

Rect = {
    width: f64,
    height: f64,
}

// variants carry payload types; a default payload and a
// discriminant are different things and are written apart
Shape = { Circle: Circle | Rect: Rect | Unit }

Shape.impl(Display, {
    // defining the outlined toString: pretty output for {}.
    // dump stays available for free alongside it
    toString ::= (self: @Self, out :: Sink) Res<WriteError> {
        self.match({
            Circle(circle) => out.fmt("circle: {}", circle.radius),
            Rect(rect) => out.fmt("rect: {} {}", rect.width, rect.height),
            Unit => out.fmt("unit"),
        });
    }
})

DumpAst = (sb :: String, n: Enum) Res<AllocError> {
    sb.fmt("Enum {}", n.name);
    n.variants.loop((h, variant) {
        sb.fmt("{}: {}", variant.name, variant.payload);
    });
}

DumpAst = (sb :: String, n: Struct) Res<AllocError> {
    sb.fmt("Struct {}", n.name);
    n.fields().loop((h, field) {
        sb.fmt("{}: {}", field.name, field.value);
    });
}

DumpAst = (sb :: String, n: Function) Res<AllocError> {
    sb.fmt("Function {}", n.name);
    n.params.loop((h, param) {
        sb.fmt("{}: {}", param.name, param.value);
    });
}

DumpAst = (sb :: String, n: Other) Res<AllocError> {
    sb.fmt("Other {}", n.name);
}

// generic entry: comptime match on the declaration of n's type.
// @meta(n) is that Decl; kind is DeclKind — an ordinary enum —
// so the arm BINDS n with its type refined, and overload
// resolution just works, no casts, no as_* anything. these are
// ast.zen's own nodes — the same ones gen_c consumes
DumpAst<T> = (sb :: String, n: T) Res<IoError> {
    @meta(n).kind.match({
        Enum(e) => DumpAst(sb, e),
        Struct(s) => DumpAst(sb, s),
        Function(f) => DumpAst(sb, f),
        _ => (),
    });
}

// @meta BUILDS as well as reads: this returns a new ast node.
// building is arena calls — add_expr makes the default's ExprId,
// then a real Field (name an Ident, value the id) goes on
// members, the Vec a Struct actually has; fields() is the read
// view. the builder helpers land with the build milestone.
// two calls to AddFoo(Circle) are ONE type, memoized on the
// call and its arguments
AddFoo<T> = (a :: Ast, n: T) Res<T, Error> {
    @meta(n).kind.match({
        Struct(s) => {
            one = a.add_expr(int_expr(a, 1)).try();
            s.members.add(field_member(a, "foo", one));
        },
        _ => Err(Error("Invalid node type")),
    });
    Ok(n);
}


// actor example, pony-style: behaviors are async methods
Foo = {}

Foo.impl(Actor, {
    // optional lifecycle hooks
    started ::= (self :: @Self, ctx: Context) {
        println("actor started") 
    }
    stopped ::= (self :: @Self, ctx: Context) {
        println("actor stopped") 
    }

    // behaviors: calling one on a Ref<Foo> enqueues a message
    // and returns immediately. Direct str bytes and consumed Vec<u8> buffers
    // are copied; other allocator-backed payloads are refused;
    // gen_c_actor emits the message record from this signature
    receive_msg = (self :: @Self, ctx: Context, data: str) {
        println("actor has received {}", data)
    }

    // request/response the pony way: the request carries the
    // reply ADDRESS, and the response is just another behavior
    // call. no promise, no await, no second concept
    compute = (self :: @Self, ctx: Context, n: i32, reply: Ref<Collector>) {
        reply.result(n + 1);
    }
})

Collector = {}

Collector.impl(Actor, {
    result = (self :: @Self, ctx: Context, v: i32) {
        println("got {}", v)
    }
})


// what this program expects: a schema, not string fishing.
// fields are bindings, so defaults use the same syntax as any
// typed binding. a field with a default is optional; no
// default and no Res means required
Opts = {
    name: Res<str>,          // --name or NAME, optional, may be absent
    verbose :: bool = false, // --verbose or VERBOSE, defaults false
}

Error = AllocError
    | IoError
    | ArgError
    | ThreadError

// main receives the capability root. it is not named `self`:
// main is not a method on Env
main = (env: Env) Res<i32, Error> {

    // Env fills the schema via @meta; missing required fields
    // error by name before your logic ever runs
    opts = env.args<Opts>().try();

    name = opts.name.match({
        Ok(n) => n,
        None  => "world",
    });

    opts.verbose.then(() { println("hello, {}", name) });

    Circle1 = AddFoo(Circle); // memoized on the call: one type
    c1 = Circle1(radius: 1.0, foo: 1);
    a = c1.area();           // ufcs: free function, method syntax

    // arena allocator: page authority comes from Env, nothing
    // ambient. implements Drop, so everything allocated from it
    // frees in one shot when alloc leaves scope at end of main
    alloc ::= env.mem.alloc();

    // functions are just bindings of lambdas, so they're values.
    // function types name their parameters — names are
    // documentation, not identity, and resolution never sees them
    add_i32 = (a: i32, b: i32) i32 { a + b }
    apply = (f: (a: i32, b: i32) i32, a: i32, b: i32) i32 { f(a, b) }
    nine = apply(add_i32, 4, 5);

    // ::= makes the function itself rebindable
    op ::= add_i32;
    op = (a: i32, b: i32) i32 { a * b }

    // closures capture their scope. this one does not escape,
    // so it needs no Alloc
    base = 10;
    add_base = (x: i32) i32 { x + base }

    // actors, pony-style: foo IS the address, calling a
    // behavior IS sending a message. async is visible right
    // here: each call below returns IMMEDIATELY, the prints
    // happen later, on foo's turn, in send order (causal)
    foo = env.spawn(Foo()).try();
    Range(0, 5).loop((h, v) {
        foo.receive_msg("hello world!").try();
    });
    println("sent all five");   // may print BEFORE any receive

    // request/response without promises: send our collector's
    // address, the reply lands in its mailbox as a message
    bar = env.spawn(Collector()).try();
    foo.compute(41, bar).try(); // returns immediately
                                // "got 42" prints when bar runs

    foo.stop();   // stopped runs after foo's mailbox drains
    foo.join();   // wait until draining and stopped complete

    // threads, the escape hatch: authority from Env, never
    // ambient. blocking in a behavior stalls that actor today. the body
    // escapes, so it takes an Alloc — the law does not bend
    t = env.threads.spawn(alloc, () Res<i32, ThreadError> {
        Ok(21 * 2);   // imagine ffi or heavy batch work here
    }).try();
    t.join().match({
        Ok(v)  => println("thread says {}", v),
        Err(e) => println("thread failed: {}", e),
    });

    // fixed arrays: [type, count], comptime size, stack, no alloc.
    // indexing is bounds-checked and traps — no Res here
    primes = [i32, 4](2, 3, 5, 7);

    // collections come from the arena; .try() propagates errors,
    // and the error sets merge into main's Error union
    names ::= alloc.Vec<str>();
    names.add("ada").try();

    ages ::= alloc.Map<str, i32>();
    ages.set("ada", 36).try();

    // ad-hoc cleanup: registered on THIS block, runs LIFO at
    // block exit, before drops. @scope is the block itself
    @scope.defer(() { println("goodbye") });

    // fold variant: 0 seeds acc, loop evaluates to the final
    // acc. stack array, by-value acc, capture-free body: this
    // compiles to a plain for-loop, zero allocations
    sum = [0, 1, 2].loop(0, (h, i, v, acc: i32) {
        acc + v
    });

    // {} routes through toString, or dump if a type has none;
    // sum.toString(alloc) is the same thing via the sealed overload
    alloc.String("{}", sum).match({
        Ok(s)  => println(s),
        Err(e) => println("error: {}", e),
    });


    const_val_implicit = 1;
    const_val_explicit : i32 = 1;
    mutable_val_implicit ::= 1;
    mutable_val_explicit :: i32 = 1;

    // arithmetic traps on overflow. want wrapping? say so
    wrapped = const_val_implicit +% 255;


    // one conditional form: .match, a method, exactly like loop is a
    // function. no if, no ternary, no ? operator. every case covered,
    // always — in statement position too
    label = (const_val_implicit == 0).match({
        true => "zero",
        false => "nonzero",
    });

    // want one side only? say it. .then cannot be mistaken for a
    // forgotten arm, because it is a different word
    (const_val_implicit == 0).then(() { println("const_val_implicit is 0") });


    some_static_string = "hello";                        // str: borrowed bytes
    some_dynamic_string = alloc.String("{}!", "hello").try(); // owned, arena-backed

    Ok(0);
    // scope ends: defers run first, then drops in reverse order,
    // alloc last, freeing every String this arena handed out
}
```

---

# Still open

- **Operator overloading.** `==` through `Eq` is the only operator that dispatches to an impl, so `a + b` on a `Duration` is not writable and a module that wants it writes `add`. Whether arithmetic should dispatch is the difference between a `Duration` reading like a number and one reading like a record, and it is a language decision nobody has made.
- **`Ord`.** `std.core` has `Eq` and `Hash` and nothing that orders. The open question is not whether to add a trait: `Ord` and `Eq` must agree exactly as `Eq` and `Hash` must, so which of the two is sealed in terms of the other is the design.
- **Supervision.** A trap aborts the process. Killing only the offending actor is the Pony answer and needs a supervision story that does not exist yet.
- **`env.threads.spawn` vs `env.blocking.run`.** If the only legitimate use of a thread is running blocking work off the scheduler, the honest capability is `blocking.run` — it makes the misuse unrepresentable rather than merely discouraged.
- **Comptime file reads.** Excluded from v1 for reproducibility. `@embed_file` is the feature people will ask for.

## Unsigned bit operations

`std.core.num` exports `bit_xor(self: W, other: W) W`, `bit_and`, `bit_or`,
`shift_left(self: W, count: usize) W` and `shift_right` for unsigned words
W = u8, u16, u32, u64, u128 or usize, plus `rotate_left` and `rotate_right`
for u32 and u64. All support free-function and receiver-call syntax. Binary
operands must use the same word type. Rotation reduces the count modulo the
word width; zero and width multiples preserve the input. Logical shifts fill
with zero; counts greater than or equal to the width return zero (including
usize.MAX). The C backend guards shifts and masks rotation counts to avoid
undefined C shifts, and casts u8/u16 results back after C's int promotion.

`& | ^` (and, or, xor), `<<` and `>>` (logical shifts), and prefix `~`
(complement) are the syntax for these named operations: `a & b` is
`a.bit_and(b)`, `a | b` is `a.bit_or(b)`, `a ^ b` is `a.bit_xor(b)`,
`a << n` is `a.shift_left(n)` and `a >> n` is `a.shift_right(n)`; `~a` flips
every bit of its word, as `a.bit_xor(W.MAX)` does. They take the same words,
`u8`, `u16`, `u32`, `u64`, `u128` and `usize`, compile to the same code and
fall under the same secret discipline. Signed integers, floats and `bool` are
refused; convert a signed value explicitly, and use `&&`, `||` and `!=` on
booleans. `>>` never applies to a signed word: the arithmetic shift below is
spelled `shift_right` only.

- `a & b`, `a | b` and `a ^ b` require both operands to have the same unsigned
  type, which is the result's type. There is no implicit widening: `u32 | u64`
  is an error naming both types. A literal takes the other operand's type and
  must fit it.
- `~a` has `a`'s type.
- `word << count` and `word >> count` shift an unsigned word; the result has
  the word's type. The count may be any unsigned type, independent of the
  word's (the named form takes a `usize`); a literal count is checked against
  `usize`. Signed and float counts are errors.
- An expression whose operands are all literals — `1 << 4`, `~0`,
  `0xF0 | 0x0F`, or a literal word shifted by a typed count — takes its width
  from the expected type: an annotated binding or constant, a parameter, a
  return type or a field. It folds at that width, so `lost: u8 = 1 << 8` is
  `0` and `all: u8 = ~0` is `255`, and each literal operand must fit it. A
  `u128` expression is not folded; it is computed at run time. With
  no expected type (`x = 1 << 4`), or a type that is not unsigned
  (`x: i32 = 1 << 4`), it is an error.

Shifts are bit operations, not arithmetic, and never trap. Bits moved out of
the word are discarded, `>>` fills with zero, and a count greater than or
equal to the width yields zero, including `usize.MAX`. No backend may expose
the underlying machine's shift behaviour: the C backend guards every count and
converts narrow results back to their type, and constant folding computes the
same values at the node's width. The JavaScript and assembly backends do not
lower the operators yet: each is refused by name (``unsupported by this
backend: the `&` operator``), never lowered as some other operation. A secret
shift count is refused at `<<` and `>>` as at `shift_left` and `shift_right`
(see "Secret values").

**A bitwise operator never relies on precedence.** Beside any different binary
operator — comparison, arithmetic, logical, or another bitwise operator — the
bitwise operand must be parenthesized, and shifts do not chain:

```groovy fragment
set  = flags & mask != 0;      // ERROR: write `(flags & mask) != 0`
bits = a | b & c;              // ERROR: write `(a | b) & c` or `a | (b & c)`
next = a << 2 + 1;             // ERROR: write `a << (2 + 1)` or `(a << 2) + 1`
far  = a << 1 << 2;            // ERROR: write `(a << 1) << 2`
all  = a | b | c;              // ok: one associative operator
low  = ~a & b;                 // ok: `~` is a prefix operator, `(~a) & b`
```

The diagnostic spells out the parenthesized form. Chains of one associative
operator — `a | b | c`, `a & b & c`, `a ^ b ^ c` — need no parentheses.

**`<<` and `>>` are two adjacent angle tokens.** The lexer produces `<` and `>`
only; in operator position the parser reads two of the same angle with no byte
between them as a shift, so `Res<Ptr<u8>>` still closes two type-argument
lists and `a > > b` is not a shift. A `<` immediately followed by another `<`
never opens type arguments.

**`|` is bitwise or only in an expression.** Type unions and enum variant lists
keep their bars. Where a declaration and a binding share a shape, a run of
`Name` or `Name(..)` joined by bars is a variant list unless it ends at `;` or
an operator, or a bar is followed by something only an expression begins with:
`mask = low | high;` in a body binds a value, while `Kind = Low | High`
declares an enum. At module level an untyped `NAME = A | B` declares an enum;
a written type makes it a constant, since an enum never writes one:
`MASK: u8 = LOW | HIGH`. A represented enum's discriminant ends at the bar
before the next variant, so a bitwise or there is parenthesized.

`&` in prefix position is still the address-of operator; `&&` and `||` remain
the short-circuit operators.

## Signed arithmetic shift

`shift_right(self: S, count: usize) S` is also exported for signed words
S = i8, i16, i32 or i64, where it is the arithmetic shift: vacated high bits
copy the sign bit, so a negative value stays negative and rounds toward
negative infinity (`-7` shifted by 1 is `-4`). A count at or above the width
yields 0 for a non-negative value and -1 for a negative one, the limit of
shifting one bit at a time. The C backend never shifts a negative value
(implementation-defined in C): it shifts the complement and complements back.
Other bit operations remain unsigned-only; convert explicitly to mix them.

These allocation-free compiler primitives evaluate operands once in source
order. Only validated exported, nongeneric, immutable-parameter declarations
with these exact signatures in `std.core.num` acquire primitive behavior.
User functions with bodies may use the same names normally. Neither the
operators nor the primitives add a crypto dependency or a constant-time
compiler guarantee.

## Wide integers and truncation

`u128` is a fixed-width unsigned primitive. It supports the ordinary checked
and wrapping arithmetic, comparisons, `Eq`, the bit operations above,
lossless `to_u128` from every narrower unsigned word, and checked
`to_u64(self: u128) Res<u64>`. Literals remain limited to the u64 range and
there is no decimal printer: print `truncate_u64()` and a shifted high half.
The C backend lowers it to `unsigned __int128` and refuses a C compiler
without it with `#error`; every supported 64-bit GCC/Clang target has it.
Checked `*` on u128 guards by division; hot paths use `*%` or `mul_wide`.

`mul_wide(self: u64, other: u64) u128` returns the exact product and never
traps. `truncate_u8/u16/u32/u64(self: W) T` keep the low bits of a strictly
wider unsigned W; they are the one spelled way to discard high bits and never
fail, unlike the checked `to_` conversions. Validation is by declaration
identity exactly as for conversions (`sema_prim`); a bodyless `mul_wide` or
`truncate_*` elsewhere is rejected. JS and assembly refuse these types
through the scalar lowering's existing type check.

`add_carry(self: u64, other: u64, carry: u64) [u64, 2]` returns the sum and
the carry out (0 or 1) of `self + other + carry`, and `sub_borrow` the
difference and borrow out of `self - other - borrow`; only the low bit of
the incoming carry or borrow is read, so neither has a precondition or a
trap. They are the spelled way to write a multi-word addition chain: the C
backend lowers them to `__builtin_addcll`/`__builtin_subcll` (Clang, GCC
14), `_addcarry_u64`/`_subborrow_u64` (older GCC on x86-64) or u128
arithmetic, and Clang keeps a chain of them in the flags (ADC/SBB on
x86-64, ADCS/SBCS on arm64). A u128 sum of three terms, the usual
alternative, often leaves the carry in a register instead: OpenSSL's
ecp_nistz256 Montgomery multiplication written with u128 took 68 cycles on
a Zen 3 core, and with these operations 37. `tools/ct/isa.zen` checks the
instructions each compiler selects.

## SIMD vectors

`u8x16`, `u8x32`, `u32x4`, `u32x8`, `u64x2` and `u64x4` are primitive
vectors of unsigned lanes. They have no operators, no `Eq` and no printer;
`std.simd` supplies every operation as a validated bodyless declaration:

| Operation | Meaning |
| --- | --- |
| `splat_V(value: E)`, `lanes_V(l0.., lN-1: E)` | construct (lanes_ for N <= 8) |
| `load_V(bytes: Ptr<u8>, offset: usize)` | unaligned native-order load |
| `v.store(bytes: Ptr<u8>, offset: usize)` | unaligned native-order store |
| `v.lane(i)`, `v.with_lane(i, x)` | read / replace one lane; traps at i >= N |
| `add_wrap`, `sub_wrap`, `mul_wrap`, `bit_xor`, `bit_and`, `bit_or` | lane-wise, wrapping |
| `shift_left`, `shift_right(count: usize)` | same count per lane; zero at >= lane width |
| `rotate_left`, `rotate_right(count: usize)` | count modulo lane width |
| `v.shuffle(pattern: [usize, N])` | lane i = v[pattern[i] mod N] |
| `v.shuffle2(w, pattern: [usize, N])` | lane i = (v ++ w)[pattern[i] mod 2N] |

Every supported target is little-endian, so a load of `u32x4` reads four
little-endian words. A shuffle whose pattern is an array literal of integer
literals lowers to one `__builtin_shufflevector` (GCC 12+/Clang; older GCC
uses `__builtin_shuffle`); any other pattern is evaluated once and selects
lane by lane with the same modulo rule, so both paths agree. The C backend
emits GNU vector-extension typedefs, capped at 16-byte alignment because
arena storage guarantees no more; 32-byte vectors compile to two 16-byte
registers unless their function is compiled for a wider target. Lane
arithmetic never traps: vector code states wrapping by name. Vector
operations evaluate operands once in source order. JS and assembly refuse
vector types through the scalar lowering's type check.

## Volatile access, compiler barriers and forced inlining

`Ptr<T>` has `read_volatile(index)` and `write_volatile(index, value)`. Each
is performed exactly once and in order with other volatile accesses; the C
backend lowers them through a `volatile T *`. `std.mem.compiler_barrier()`
prevents the compiler from moving memory accesses across it or treating
earlier stores as dead (an empty `asm volatile` with a memory clobber); it
emits no instruction and is not a CPU fence. `std.mem.wipe(bytes, count)`
zeroes a span with volatile stores followed by a barrier. It erases only
that span: copies in registers, spills or other buffers are not reached, so
it is one part of a secret-lifetime contract, not the whole.

A module-level function declared `name = inline (..) T { .. }` must be
inlined into every caller. `inline` is contextual, not a keyword and not a
new `@` name: it is recognized only directly before a function value in a
declaration, so `inline(x)` elsewhere remains a call of a binding named
`inline`. The C backend emits `static inline __attribute__((always_inline))`
in single-file output. Split output gives functions external linkage and
calls cross translation units, so there the request is dropped rather than
turned into a C error. Inlining changes no semantics: evaluation order,
traps and ownership are those of an ordinary call. A recursive `inline`
function is a C compiler error, which the backend does not yet diagnose.

## Target features and runtime dispatch

A CPU feature is a capability, in the same sense as the authority `Env`
carries: `std.simd` declares `Avx2`, `Ssse3`, `Bmi2`, `Adx`, `Aes`, `Clmul`,
`Neon`, `ShaNi`, `ArmSha2` and `ArmSha512`, and only `std.simd` may construct
one (`ForgedCapability` otherwise). The detection functions `avx2()`,
`ssse3()`, `bmi2()`, `adx()`, `aes()`, `clmul()`, `neon()`, `sha_ni()`,
`arm_sha2()` and `arm_sha512()` return `Res<Capability>` from a runtime
check: cpuid through the compiler runtime on x86 (which includes the OS's
AVX state; CPUID leaf 7 for the SHA extensions and ADX), `AT_HWCAP` on Linux
arm64 and `hw.optional.arm.*` sysctls on macOS. NEON is baseline on arm64.
`Bmi2` (x86 BMI1 and BMI2) has no instructions of its own: a function taking
it may use RORX, ANDN, MULX (for `mul_wide`) and the other BMI encodings the
C compiler picks for scalar code. `ZEN_CPU_DISABLE` (a comma list of `avx2`,
`ssse3`, `bmi2`, `adx`, `aes`, `clmul`, `neon`, `sha`, `sha512` or `all`)
makes
detection report features absent so every fallback path can be run on one
machine; `sha` covers the SHA-256 instructions of both architectures.

**The signature answers the question.** A function with a capability
parameter is compiled for that feature: the C backend emits one combined
`__attribute__((target(..)))` per feature set (Clang honours only one), and
nothing on other architectures. Because the value can exist only after
successful detection, such a function cannot run where the feature is
missing, and dispatch is an ordinary match:

```zen
avx2().match({ Ok(cpu) => blocks8(cpu, ..), None => blocks4(..) })
```

Feature instructions take the capability as an argument:
`aes_round(self: u8x16, key: u8x16, cpu: Aes)` and `aes_round_last` (x86
AESENC/AESENCLAST semantics; AESE+AESMC then xor on arm64) and
`clmul_low` / `clmul_high(self: u64x2, other: u64x2, cpu: Clmul)`
(PCLMULQDQ 0x00/0x11, PMULL/PMULL2). `cast_V` views a vector's bytes as
another vector of the same size.

The SHA instructions of x86 and arm64 compute different steps of the same
algorithm (two rounds on an ABEF/CDGH split against four rounds on
ABCD/EFGH), so neither can be written in terms of the other at native cost.
Each set therefore has its own capability, detected only on its
architecture: `sha256_rnds2`, `sha256_msg1`, `sha256_msg2` take `ShaNi`
(SHA256RNDS2/MSG1/MSG2); `sha256h`, `sha256h2`, `sha256su0`, `sha256su1`
take `ArmSha2` and `sha512h`, `sha512h2`, `sha512su0`, `sha512su1` take
`ArmSha512` (FEAT_SHA256, FEAT_SHA512; operands in the ACLE order, the
destination's incoming value first). A program with both kernels dispatches
on both detections; on the other architecture the helpers abort, which is
unreachable because the capability cannot be obtained there.

Two carry chains need two carry flags, which only x86 has: ADCX adds with
CF alone and ADOX with OF alone, and MULX multiplies without touching
either, so the low and high halves of a row of partial products accumulate
at once instead of one after the other. C has no way to say which flag an
addition uses, and neither Clang nor GCC emits ADOX, so the dual chain is a
fixed operation rather than a scheduling hint:
`mul_limbs(self: [u64, 4], other: [u64, 4], adx: Adx, bmi: Bmi2) [u64, 8]`
is the 512-bit product of two 4-limb numbers (least significant limb
first) and `square_limbs(self, adx, bmi)` the square. The C backend lowers
each to inline assembly transcribed from OpenSSL's `x25519_fe64_mul` and
`x25519_fe64_sqr` product sequences, guarded by `__x86_64__`, with no
branch and every memory operand at a fixed offset from a factor. Both flags
are clear after each row, so `mul_limbs` is two blocks split after its
second row: each needs at most twelve general registers, which leaves room
for a frame pointer and for -O0. Reductions stay ordinary code over
`add_carry` and `mul_wide`, since a single flag chain is what the C
compiler schedules well. In a microbenchmark on a Zen 3 core the product
plus an `add_carry` reduction mod 2^255 - 19 took 25.9 cycles against 29.2
for OpenSSL's `x25519_fe64_mul`. On other targets `Adx` is never detected.

32-byte vectors never cross a C call between functions compiled for
different features: x86 passes them in YMM registers only with AVX, so the
mismatch is a Clang error and a silent GCC miscompile. A call that passes or
returns a 32-byte vector between an `Avx2` function and one without the
capability is refused with a diagnostic; give the helper the capability
too (dolbeau-style code threads `cpu` through its helpers) or keep the
vector in locals. Capability arguments are ordinary values and cost nothing
once inlined. Detection results are cached per process (one cpuid or sysctl
per feature, stored with relaxed atomics), so dispatching per call is cheap.

`mul_low32(self: V, other: V) V` for V = u64x2 or u64x4 multiplies the low
32 bits of each lane into a full 64-bit product (PMULUDQ, UMULL): the
radix-2^26 limb product of vector Poly1305. A constant rotation of u32
lanes by 16 lowers to a 16-bit lane swap (REV32 on arm64).

## Constant-time arithmetic

`std.ct` is the library for code whose timing must not depend on secrets.
A comparison returns a `Choice`, a 0/1 value that is deliberately not a
`bool`: it cannot be matched, short-circuited or passed to `.then`, only
combined (`and`, `or`, `xor`, `not`), spent in a select, or made public with
`declassify_bool()`. The operations are `ct_is_zero`, `ct_eq`, `ct_ne`,
`ct_lt` and `ct_gt` for u8, u16, u32, u64, u128 and usize; `ct_select`,
`ct_cmov` and `ct_swap` on words and on spans of u8, u32 or u64 words;
`ct_memeq` and `ct_memcmp` over bytes; and `ct_lookup`, which reads a whole
table (of words, or of fixed-stride records) to return one entry. The
formulas are BoringSSL's `constant_time_*` family; the shapes follow Rust's
`subtle`, libsodium's `crypto_verify_n` and fiat-crypto's `cmovznz`.

Everything rests on `value_barrier(x)`, a primitive owned by `std.ct` for
each unsigned word. It returns `x` unchanged, and the optimizer may assume
nothing about the result. Every `Choice` and every mask made from one passes
through it, so a C compiler cannot rediscover that a mask is a boolean and
compile the select as a branch. What each backend promises:

- **C** lowers the barrier to `__asm__("" : "+r"(x))` (BoringSSL's
  `value_barrier_w`), a u128 as its two 64-bit halves. It emits no
  instruction. Source shape plus the barrier is the whole promise: the C
  compiler still chooses instructions, and a CPU instruction whose latency
  depends on its operands (division, some multipliers) is not prevented.
  The evidence for a given compiler and target is `tools/ct`, which checks
  the optimized assembly and measures timing.
- **JavaScript** gives no constant-time guarantee: engines speculate,
  specialize on observed values and represent integers differently by
  magnitude. The backend refuses `std.ct` programs through its scalar type
  check (unsigned words are outside its subset), and if that subset grows
  it must keep refusing the barrier rather than lowering it to an identity.
- **Assembly** refuses these types today. When it learns unsigned words it
  must lower `value_barrier` as an opaque register redefinition and must not
  turn the masked selects into branches: a renderer that pattern-matches
  `ct_select` into a jump would reintroduce the leak the library exists to
  prevent.

## Secret values

`std.ct.Secret<T>` marks a value whose timing must not reveal it. It is
exactly `T` (a generic alias whose target is its own parameter), so every
operation on `T` type-checks and lowers unchanged; what changes is what sema
lets the program do with it. The marker may be written on a parameter, a
local binding, a struct field or a return type (anywhere inside the written
type, so `Res<Secret<u64>>` and `[Secret<u64>, 4]` count).

A value is *secret* when it is marked, or when it is computed from a secret
value: the taint follows bindings, operators, and field, element and
pointer reads. A call's result is secret when the callee's written result
type says so, or, for the operations of `std.ct`, `std.core.num` and `Ptr`,
when an argument is; any other function is checked against its own
signature, so a public result is a promise its body must keep. A write of a secret through
a pointer or a `::` binding makes that binding secret too. `Choice` is not
secret by itself; a Choice computed from a secret is. `declassify(v)` and
`choice.declassify_bool()` are the only ways out, and are the audit points.
`declassify` takes an unsigned word (marked in the assembly, see below), a
bool, or a pointer (whose pointee becomes public).

On a secret value sema refuses, at the exact expression:

| rule | refused | instead |
|---|---|---|
| branch | `.match` scrutinee, `.then`/`.ensure` receiver, `.try()` operand | `ct_select`, `ct_cmov` |
| short circuit | an operand of `&&` or `||` | `Choice.and`/`or` |
| loop | a `loop` condition, a looped-over range or collection | public bounds |
| index | `a[i]`, `Ptr.read`/`write`/`offset`/`back` index, SIMD lane index | `ct_lookup` |
| shift | a secret count of `<<`, `>>`, `shift_*` or `rotate_*` | public counts |
| divide | either operand of `/` or `%` | Barrett/Montgomery reduction |
| trap | checked `+ - *` and checked (`Res`-returning) conversions | `+% -% *%`, `truncate_*` |
| compare | `== != < <= > >=` | `ct_eq`, `ct_lt`, ... |
| call | a secret argument to a parameter not written `Secret` | mark the callee's parameter |
| result | a secret tail value of a function whose result is not `Secret` | mark the result, or declassify |
| store | a secret written through a parameter not written `Secret` | mark the parameter |

Checked arithmetic is refused because its overflow test is itself a branch
on the value. The call, result and store rules make the discipline
modular: each function is checked alone, and a secret crosses a function
boundary only where both sides say so. Calls into `std.ct`, the
compiler-owned integer operations of `std.core.num` (bit operations,
wrapping-safe widenings, `truncate_*`, `mul_wide`), `std.simd` lanes and the
`Ptr` memory operations are accepted directly; they are either implemented
with the discipline in mind or are single machine operations. `std.ct`
itself is not checked: it is where the masks are built.

The analysis is intraprocedural and flow-insensitive: names are resolved
through block and closure scopes to the binding they denote, and once a
binding is secret it is secret throughout the function, including in
closures that capture it. Not tracked yet: values leaving a closure through `h.break(v)`,
calls through function values, globals, and a generic function instantiated
at a secret type (its parameters are not written `Secret`, so the call rule
refuses the secret argument instead). None of this reaches the C backend:
`Secret<T>` lowers as `T`, and `tools/ct` checks what the C compiler made of
it.

### Checking what the C compiler made of it

`tools/ct` holds three checks, each with leaky negative controls that must
be flagged, so a check that has stopped seeing anything fails:

- `ct-asm --c program.c` compiles a program's generated C to assembly with
  each `--cc` at `-O2` and `-O3`. The C backend writes
  `/* zen:secret zu_l3key *zu_l3out */` after the parameter list of every
  function with a Secret parameter, ending in `public-result` when the
  result is not written Secret (sema's discipline makes it public, and the
  tool checks it); the tool keeps those functions out of
  line (`noinline`, and `noipa` so GCC cannot run a clone instead), places
  their secret inputs by the SysV x86-64 or AAPCS64 convention, and runs a
  forward taint analysis over the assembly, joined at labels. Registers are
  tracked whole, vector registers included (%xmm/%ymm/%zmm n are one
  register, as are b/h/s/d/q/v n on arm64), with the vector forms that also
  read their destination (legacy-SSE two-address forms with an immediate,
  NEON accumulates and lane inserts, AESE) and vector instructions leaving
  the flags alone; MULX writes both of its destinations from its source and
  the implicit %rdx, and ADC, ADCX and ADOX read the flags (one taint bit
  covers them all); std.simd vectors passed by value arrive in XMM/YMM or V
  registers, and a by-value struct the backend lends as `const T *` holds
  its secret bytes behind the pointer. The stack is tracked byte by byte, so
  a spilled vector's lanes keep their taint when reloaded narrower; a store
  at an offset the analysis cannot place smears the stack (every later stack
  load is secret). `--manifest` names further functions and their secret
  parameters (`*p` a pointer to secret memory, `**p` a pointer to memory
  holding pointers to secret memory), for shared arithmetic whose signature
  cannot say Secret because public verification uses it too; `branches=N`
  on an entry allows N secret-dependent branches, `public-result` requires
  the result register to be public at every return, `?module` makes an
  entry optional.
  `std.ct.declassify` of a word and `Choice.declassify_bool` pass through
  `declassify_barrier`, whose asm text is `/* zen:declassify %reg */`: the
  analysis treats that register as public from there on, so a program's
  explicit declassifications are the only places its secrets may steer
  code. A call passes secrets through the integer and vector argument
  registers and stack arguments its C prototype uses. An audited callee must
  have been seeded with every secret it is passed, or the call is reported;
  only argument registers its body actually consumes count (measured on its
  own assembly for the same compiler and level), a register merely holding
  the address of secret memory counts only for a pointer parameter, and
  std.simd capability arguments, which carry no data, never count. Its
  result is public only when its audit proved it (`public-result`, which
  also forbids returning a pointer into secret memory, and for a result
  returned through a hidden pointer forbids storing a secret through it or
  handing it to a callee given secrets); otherwise the
  result, and memory behind a hidden result pointer, is secret when any
  argument is secret or points at secrets. A secret-bearing call that
  passes a writable stack address marks the one value a `::` borrow names
  (its extent is read from the mangled parameter types) or, for a Ptr<T>,
  smears the stack. A function's own hidden result pointer addresses memory
  that may hold secrets. A load through a `**` pointer yields a pointer to
  secrets only when it is pointer-sized. The stack protector's guard (from
  `%fs:40`, or `___stack_chk_guard` through the GOT) is tracked into its
  slot, which stays public when the stack is smeared, since only the
  prologue writes it. On x86-64 a byte written over a secret register
  (`sete %al`) makes only its low byte public, which is what a byte-sized
  read, spill or `bool` result sees. Calls that never return end their
  path. `CT_TRACE=<symbol>` prints the analysis instruction by
  instruction. It fails on a conditional branch,
  a memory address, a division or an indirect jump that depends on a
  secret, a secret passed to an audited callee unseeded, and a secret
  returned by a public-result function. Memory other than the stack and
  secret pointees is not modelled.
- `ct-grind` is the ctgrind method: `std.ct.ct_grind.secret_bytes` marks
  memory undefined for valgrind's memcheck, which then reports every branch
  and address computed from it; `public_bytes` is the declassification. A
  program compiled with `-DZEN_CT_GRIND` also marks every `std.ct.declassify`
  result defined (`ZG_CT_PUBLIC`, a valgrind client request next to the asm
  marker), so memcheck and the static check agree on where secrets may
  steer code.
- `ct-timing` is a dudect-style statistical test (`std.ct.ct_timing`):
  fixed against random inputs, interleaved, Welch's t over all measurements
  and over dudect's percentile crops, run under `taskset` on one core after
  the load average settles. |t| above 10 is a leak.

`make ctcheck` runs the first two on their controls; the crypto package runs
all three on its own functions.
