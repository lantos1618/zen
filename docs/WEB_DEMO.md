# zen-ui in the browser

A zen-ui app, written in Zen, compiled by Zen's JavaScript backend, running
in a browser tab. The app, zen-ui's layout, and the web host that turns a
zen-ui `View` into DOM elements are all Zen. The only JavaScript that is not
compiled Zen is what `gen_js` itself emits: the runtime and one small stub
per `js.bind` member signature. There is no second AST-to-JS compiler and
no C.

## Run it

The compiler is unified-rooms' `./zen` (`make build` in ../zen-unified). From the zen-ui
checkout:

```sh
ZEN_STD=../zen-unified/src ../zen-unified/zen build web-counter   # build/web/ (JS backend)
ZEN_STD=../zen-unified/src ../zen-unified/zen build web-serve     # build/web-serve (asm backend)
./build/web-serve 8765                                            # open http://127.0.0.1:8765/
```

`web-counter` is declared in zen-ui's `build.zen` with `backend: Codegen.Js,
web: true, out: Ok(Path("build/web"))`. Without a project, the same output
comes from:

```sh
zen build <root> --entry main.zen --backend js --target js-browser -o build/web
```

`web-serve` is a tiny file server written in Zen (`web/serve.zen`) and built
by the native assembly backend; any static file server works. Screenshots
from the verification run are in zen-ui `build/web-screenshots/`.

## The `js-browser` layout

`--target js-browser -o DIR` (or `web: true` on a project executable) writes
three files. The layout is stable: a `zen serve` dev server builds and serves
this directory.

| File | What it is |
| --- | --- |
| `index.html` | A fixed page: loads `runtime.js`, then `app.js`, with an empty `<body>`. The program builds its own DOM. |
| `runtime.js` | The JS backend's runtime (`src/gen/gen_js_runtime.zen`): heap, 64-bit helpers, traps, output, the `js.bind` boundary, the event queue and the page host. The same for every program. |
| `app.js` | The program: `js.bind` stubs, one function per IR function, constants, and `zmain(entry)`. |

Without `--target js-browser`, `--backend js -o FILE` still writes one
self-contained script (runtime and program) for Node.

## The pipeline

```text
examples/web_counter.zen ─┐
src/ui.zen ───────────────┤
src/web_host.zen (js.bind)┴─▶ parse ─▶ sema ─▶ gen_lower_core ─▶ gen_ir (native surface,
                                               (shared with asm)   plus Host and Wait)
                                                                        │
                                                        gen_verify.verify_native
                                                                        │
                                   gen_js: functions, generators, stubs ▼
                                                 build/web/{index.html, runtime.js, app.js}

 page load ─▶ runtime.js ─▶ app.js: zmain(main)
     main lays out the View (zen-ui) and builds the DOM (js.bind calls),
     then page.next() ─▶ std.js.wait() suspends the program
 click ─▶ listener queues the handler id ─▶ runtime resumes main ─▶ Zen
     updates the View ─▶ page.sync() sets textContent ─▶ wait() suspends again
```

1. **Front end.** Nothing JavaScript-specific. `js.bind` parses into the same
   native-namespace declaration `c.bind` does (a struct of bodiless
   signatures, marked as a host object), so sema checks its calls like any
   other native call.
2. **Shared lowering** (`src/gen/gen_lower_*`). The lowering the assembly
   backend uses, extended target-neutrally: `F64` values, static
   struct-member calls (`View.create(...)`), `Ptr.take`, and two IR
   instructions: `Host`, a `js.bind` call that records how each argument
   crosses (number, bool, `str`, handle or handler), and `Wait`.
3. **Verification.** `gen_verify.verify_native` also checks each `Host`
   argument against its boundary form.
4. **Rendering** (`src/gen/gen_js.zen`; IR only, per `make archcheck`). One
   JS function per IR function. A function that can reach `Wait` renders as
   a generator (`function*`) and its callers resume it with `yield*`, so the
   Zen program stays synchronous while the page's event loop runs. Each
   distinct `js.bind` signature gets one stub:

   ```js
   function zj6(a0, a1) {
     const t = zobj(a0);
     return (t["textContent"] = zstr(a1), 0);
   }
   ```

5. **Runtime** (`src/gen/gen_js_runtime.zen`). Besides the machine model in
   `docs/JS_BACKEND.md`: the handle table (`zref`, `zobj`), UTF-8 decoding
   of `str` slices (`zstr`), listeners that queue handler ids (`zhandler`),
   and the driver that resumes a suspended program when an id is queued.

### `js.bind`

```zen
{ Ref, Handler, wait } = std.js

Document = js.bind("document", {
    createElement* = (tag: str) Ref
    get_body* = () Ref
    set_title* = (title: str) ()
})
Element = js.bind("Element", {
    append* = (this: Ref, child: Ref) ()
    set_textContent* = (this: Ref, text: str) ()
    addEventListener* = (this: Ref, kind: str, handler: Handler) ()
})
StyleNumber = js.bind("Element.style", {
    setProperty* = (this: Ref, name: str, value: f64) ()
})
```

- The string is an object path. Without a receiver it starts at
  `globalThis` (`"document"`, `"Math"`). When the first parameter is
  `this: Ref`, the member applies to that object and the path after the
  first segment is followed from it (`"Element.style"` reaches `this.style`);
  the first segment only names the kind of object.
- `set_x` assigns property `x`, `get_x` reads it, and any other member is a
  method call of the same name. These are JavaScript's names, so they do not
  follow Zen naming. Names must be plain identifiers; anything else becomes
  a stub that throws.
- Marshalling is explicit and closed. Integers, `f64` and `bool` cross as
  numbers. `str` crosses as a UTF-8 slice of Zen's heap (pointer and
  length) that the stub decodes; `std.js.Bytes` crosses as a `Uint8Array`
  view of heap bytes, valid for the call. Host objects cross as `Ref`, a
  u32 id in the runtime's handle table: 0 is `null`/`undefined`, and the
  same live object always has the same id. The table holds each object
  until the program calls `release()` on its Ref; a released id traps if
  it is used again. `std.js.copy` copies an `ArrayBuffer` or typed array
  into heap bytes in one call. `Handler`, a u32 id, crosses as a listener
  that queues that id. Nothing else may cross, and a `str`, `Bytes` or
  `Handler` never comes back.
- Events never call into Zen from JavaScript. `std.js.wait()` suspends the
  program until a handler fires and answers its id (0 when no event can
  arrive, as under Node).
- The C backend refuses `js.bind` members, and the asm backend refuses
  programs that use them before rendering.

**Overlap with native packages.** `js.bind` is meant to share its
declaration and check machinery with the native-packages work
(`zen-native-pkgs`, `docs/proposals/NATIVE_PACKAGES.md`). Today `js.bind`
and `c.bind` already parse into one kind of declaration and pass through the
same sema paths. Under that proposal the string would become a declared
native, for example `js.bind(js.native.dom.object("document"), {..})` with
`dom` declared by a `b.native` whose availability is per target
(`js-browser` provides `dom`; Node would provide `node:fs`). The proposal's
resolution and visibility rule (a library may bind only natives in its
dependency closure) and its target gating would then apply to host objects
unchanged, and the marshalling table above is the JavaScript counterpart of
its C ABI type check. Nothing here waits on that work.

### The zen-ui web host (`src/web_host.zen`)

`Page.open(arena, view, title)` walks the View and creates one element per
node: a `<button>` for buttons and a `<div>` for text and boxes. zen-ui's
computed frame, font size, colours and corner radius are set as CSS custom
properties with `style.setProperty(name, f64)`, and one stylesheet (Zen
strings appended to a `<style>` element) maps them onto `left`, `top`,
`width`, `height`, `background`, `color` and `border-radius`. Numbers cross
as numbers and the browser formats them, so no float formatting happens in
Zen. Each button registers `Handler(id: node index + 1)` for `"click"`.

`page.next(view)` waits for a handler and answers `Press(action)` for that
node; `page.sync(view)` redraws the text of every node whose
`text_revision` moved. The demo (`examples/web_counter.zen`) is an ordinary
loop over `next`, `view.set_text` and `sync`.

## What changed where

Compiler (`zen-web`, branch `web-backend`, on `unified-rooms` after the
native-asm-backend merge):

| File | Change |
| --- | --- |
| `src/gen/gen_js.zen` | Renderer of the native IR surface; generators for suspending functions; `js.bind` stubs; `emit_js` (Node script) and `emit_app`, `emit_runtime`, `PAGE` (page layout). |
| `src/gen/gen_js_runtime.zen` | The JS runtime, including the `js.bind` boundary and the page and Node hosts. |
| `src/gen/gen.zen` | `--backend js` uses the full lowering and `verify_native`; the `js-browser` layout; asm refuses `F64` and host instructions with a reason. |
| `src/gen/gen_ir.zen`, `gen_verify.zen` | `Scalar.F64`; `Host(HostCall)` with `Marshal`; `Wait`. |
| `src/gen/gen_lower_shape.zen`, `gen_lower_core.zen` | `f64` values; float literals to exact bits (Clinger's fast path; others refused). |
| `src/gen/gen_lower_call.zen` | `js.bind` calls; `std.js.wait`; static member calls through a type; formatting an `f64` into text refused. |
| `src/std/js/js.zen` | New: `Ref`, `Handler`, `wait`, and the `js.bind` contract. |
| `src/std/parse/parse_decl.zen`, `src/std/ast/ast_node.zen` | `js.bind(path, {..})` parses to a native namespace with `native_host`. |
| `src/gen/gen_c/gen_c_assoc.zen` | C refuses `js.bind` members. |
| `src/zen/zen_build.zen`, `zen_cli.zen` | `--target js-browser -o DIR`. |
| `src/std/build/build.zen`, `src/zen/zen_build_plan.zen`, `zen_project.zen` | Project executables take `web: true`; JS targets may depend on Zen source libraries. |
| `tests/js/main.zen`, `tests/js/cases/` | The gate stages programs like the native runner and also runs JavaScript-only `js.bind` cases. |
| `tests/corpus/gen/scalar_backends` | JS now runs the wide and bool-entry programs instead of refusing them. |

zen-ui (uncommitted):

| File | Change |
| --- | --- |
| `src/environment.zen` | `Platform = Macos \| Ios \| Web`. |
| `examples/main.zen` | The one exhaustive `Platform` match gains `Web`. |
| `src/web_host.zen` | New: the web host in Zen (`Page.open`, `next`, `sync`) over `js.bind`. |
| `examples/web_counter.zen` | New: the demo. |
| `web/serve.zen` | New: the Zen file server (asm backend). |
| `build.zen` | Targets `web-counter` (`web: true`) and `web-serve`. |

## What works and what does not

`make jscheck` compiles every executable corpus program with `--backend js`,
runs it under Node and compares it with the C oracle: **661 of 977**
programs now behave exactly like C (1 of 976 before this work), none emit
broken JavaScript, and the remaining failures and refusals are in the shared
lowering (`docs/JS_BACKEND.md` has the breakdown).

Not yet, in the order they block zen-ui:

- **`vararg` parameters.** zen-ui's `Elements` builder (`tree.Window(...,
  children...)`) uses them and the shared lowering refuses them, so the demo
  builds its screen through `View` directly (`view.box`, `view.text`,
  `view.button`), which is the same layout engine.
- **Actors and threads.** The macOS and iOS hosts drive the UI from actors
  over pipes (`src/interaction.zen`, `c.bind` to `unistd.h` and `poll.h`).
  The lowering refuses actors, so the web host is a synchronous loop over
  `std.js.wait` instead of `Session` and `Pump`.
- **Formatting an `f64` into text** (`a.String("{}", 1.5)`): `add_f64` has
  no Zen body yet (C uses `%g`). Printing an `f64` works.
- **Text input and keys.** The web host registers clicks only; editable
  nodes, keyboard, pointer drags and scroll offsets are not wired yet.
- `f32`, float literals beyond 15 significant digits or a decimal exponent
  beyond ±22, float match patterns; sockets, `epoll`/`kqueue` and process
  spawning.
- `usize` is still 64-bit in the IR, so lengths and indices pay for pair
  arithmetic. A 32-bit `usize` on JS needs a data-layout parameter in the
  shared lowering.
