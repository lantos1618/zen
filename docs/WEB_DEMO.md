# zen-ui in the browser

A zen-ui app, written in Zen, compiled by Zen's JavaScript backend, running
in a browser tab. This is the JavaScript backend's first real milestone: the
program is ordinary zen-ui code (its `View`, layout, appearance and text
state), lowered by the same shared IR lowering the assembly backend uses,
and rendered to JavaScript. There is no second AST-to-JS compiler, and no C.

## Run it

The compiler must be this branch's `./zen` (`make build`). From the zen-ui
checkout:

```sh
ZEN=../zen-web/zen
ZEN_STD=../zen-web/src $ZEN build web-counter   # build/web/app.js (JS backend)
ZEN_STD=../zen-web/src $ZEN build web-serve     # build/web-serve  (asm backend)
./build/web-serve 8765                          # then open http://127.0.0.1:8765/
```

`web-serve` is the demo's file server, itself written in Zen
(`web/serve.zen`) and built by the native assembly backend: it serves
`web/` (the page) and `build/web/` (the compiled program) side by side and
sends the cross-origin-isolation headers the page needs. Any static server
that sends `Cross-Origin-Opener-Policy: same-origin` and
`Cross-Origin-Embedder-Policy: require-corp` works too.

The encoder test runs on both backends and must print the same bytes:

```sh
ZEN_STD=../zen-web/src $ZEN build web-test && ./build/web-test
ZEN_STD=../zen-web/src $ZEN build web-test-js && node build/web-test.js
```

## The pipeline

```text
examples/web_counter.zen ─┐
src/ui.zen, src/web.zen ──┴─▶ parse ─▶ sema ─▶ gen_lower_core ─▶ gen_ir (native surface)
                                                (shared with asm)        │
                                                                         ▼
                                                        gen_verify.verify_native
                                                                         │
                                                                         ▼
                                  gen_js (renderer) + gen_js_runtime (machine half)
                                                                         │
                                                                         ▼
                                                             build/web/app.js
   browser: index.html ─▶ host.js ─▶ new Worker("app.js") ─┐
                            ▲   │                           │ runs `main`
            DOM clicks ─────┘   └── applies command packets ◀┘ (stdout)
            event packets ──────────────────────────────────▶ (stdin, blocks)
```

1. **Front end.** Nothing JS-specific: the counter is checked by sema like
   any Zen program.
2. **Shared lowering** (`src/gen/gen_lower_*`). The same lowering the
   assembly backend uses produces the native IR surface: typed slots,
   `Block` aggregates, `Load`/`Store`, checked arithmetic, `Trap`
   terminators, `System` calls. This work added `F64` to that surface
   (zen-ui's layout is all `f64`), static struct-member calls
   (`View.create(...)`), and `Ptr.take`; all three are target-neutral
   lowering, so the assembly backend gets them too (it refuses `F64` for
   now, with a reason, before rendering).
3. **Verification.** `gen_verify.verify_native`, the one verifier.
4. **Rendering** (`src/gen/gen_js.zen`). IR only, no AST or sema
   (`make archcheck`). One JS function per IR function, a `switch` over
   basic blocks. The machine model is in `docs/JS_BACKEND.md`: one linear
   heap (`ArrayBuffer` + `DataView`), `Ptr` = byte offset, 64-bit words as
   `(lo, hi)` uint32 pairs with the high half of a result in `zH`, frames on
   a heap stack, traps that report `file:line:col: trap: …` and exit 134.
5. **Runtime** (`src/gen/gen_js_runtime.zen`, emitted into every script).
   The heap and page allocator, 64-bit helpers, `%g` float printing,
   buffered stdout, the `System` call layer, and two hosts: Node (a
   process) and a browser Worker.
6. **The page** (zen-ui `web/index.html`, `web/host.js`). `host.js` is the
   only hand-written JavaScript in the demo, about 120 lines, and it makes
   no decisions: it starts `app.js` in a Worker, draws the command packets
   the program writes, and turns clicks into event packets.

### How the program talks to the page

The browser host is a *sys flavor*, not a foreign-function binding: the
Worker's standard streams are wired to the page.

- **stdout → commands.** `src/web.zen` (zen-ui's web host, in Zen) writes
  little-endian packets: one per `View` node (frame, font size, flags,
  colours, radius, alignment, id and text), a title, "ready", and later one
  per changed text. The layout is documented at the top of `src/web.zen`.
  zen-ui computes every frame; the page positions elements absolutely.
- **stdin → events.** A click on a button appends `{kind: 1, action}` (two
  u64 words) to a ring buffer in a `SharedArrayBuffer`. The runtime's `read`
  blocks in `Atomics.wait` until bytes arrive, so the Zen program is a
  plain loop:

  ```zen
  web ::= Web.open(arena, view, "Zen UI · Web Counter").try();
  running.loop((h) {
      web.next(env).match({
          Closed        => { running = false; },
          Press(action) => { /* update the View */ web.sync(view).try(); },
      });
  });
  ```

  The runtime flushes buffered stdout before it blocks on stdin, so each
  event's updates reach the page before the program waits again.
- **SharedArrayBuffer** needs a cross-origin-isolated page, hence the
  COOP/COEP headers from `web-serve`.

Because the protocol is plain bytes on standard streams, the same program
runs under Node with a file as stdin (useful for tests), and the encoders
run on the C backend too (`tests/web.zen`).

## What changed where

Compiler (`zen-web`, branch `web-backend`):

| File | Change |
| --- | --- |
| `src/gen/gen_js.zen` | New renderer of the native IR surface (replaces the scalar-only one). |
| `src/gen/gen_js_runtime.zen` | New: the JS runtime, emitted into each script. |
| `src/gen/gen.zen` | `--backend js` uses the full lowering and `verify_native`; asm refuses `F64` with a reason. |
| `src/gen/gen_ir.zen`, `gen_verify.zen` | `Scalar.F64`: IEEE arithmetic and comparisons, bit-pattern constants. |
| `src/gen/gen_lower_shape.zen`, `gen_lower_core.zen` | `f64` values; float literals to exact bits (Clinger's fast path; others refused). |
| `src/gen/gen_lower_call.zen` | Static member calls through a type; `Ptr.take`; formatting an `f64` into text refused. |
| `src/zen/zen_project.zen` | JS project targets may depend on Zen source libraries (only native libraries are refused). |
| `tests/js/main.zen` | The corpus gate stages programs like the native runner (`src`, `prog`, harness env). |
| `tests/corpus/gen/scalar_backends` | JS now runs the wide/bool-entry programs instead of refusing them. |

zen-ui (uncommitted):

| File | Change |
| --- | --- |
| `src/environment.zen` | `Platform = Macos \| Ios \| Web`. |
| `examples/main.zen` | The one exhaustive `Platform` match gains `Web`. |
| `src/web.zen` | New: the web host (`Web.open`, `next`, `sync`, packet encoders). |
| `examples/web_counter.zen` | New: the demo. |
| `tests/web.zen` | New: encoder test, run on C and JS. |
| `web/index.html`, `web/host.js` | New: the page and its DOM glue. |
| `web/serve.zen` | New: the Zen file server (asm backend). |
| `build.zen` | Targets `web-counter`, `web-test`, `web-test-js`, `web-serve`. |

## What works and what does not

Measured with `make jscheck` (every executable corpus program through
`--backend js` under Node, compared with the C oracle): **656 of 961**
programs now behave exactly like C (1 of 976 before this work), with 1
Linux-only failure, 304 refused by the shared lowering and none broken.
`docs/JS_BACKEND.md` has the breakdown.

Supported by the JS backend now: everything the shared lowering supports
(integers of every width with Zen's traps, `f64`, records, enums and `Res`,
matches, `.try()`, generics, inlined closures, loops, `Ptr`, `Alloc`/arenas
over pages, `str`/`String`/`Vec`, formatting of integers and `str`),
stdout/stderr/stdin, files through `Env.fs` under Node, argv and env,
clocks and randomness.

Not yet, in the order they block zen-ui:

- **`vararg` parameters.** zen-ui's `Elements` builder (`tree.Window(...,
  children...)`) uses them, and the shared lowering refuses them, so the
  demo builds its screen through `View` directly (`view.box`, `view.text`,
  `view.button`), which is the same layout engine.
- **Actors and threads.** The macOS/iOS hosts drive the UI from actors over
  pipes (`src/interaction.zen`, `c.bind` to `unistd.h`/`poll.h`). The
  lowering refuses actors, and `c.bind` natives have no JS mapping; the web
  host therefore uses a synchronous event loop instead of `Session`/`Pump`.
  The planned mapping (Workers + `Atomics` on a shared heap) is in
  `docs/JS_BACKEND.md`.
- **Formatting an `f64` into text** (`a.String("{}", 1.5)`): `add_f64` has
  no Zen body yet (C uses `%g`). Printing an `f64` to the console works.
- **`f32`**, float literals beyond 15 significant digits or a decimal
  exponent beyond ±22, and float match patterns.
- Sockets, `epoll`/`kqueue` and process spawning (no synchronous
  equivalent in Node or a browser).
- Text input: the host sends button presses only; editable nodes and
  keyboard events are not wired yet.
- `usize` is still 64-bit in the IR, so lengths and indices pay for pair
  arithmetic. A 32-bit `usize` on JS needs a data-layout parameter in the
  shared lowering (`NATIVE_BACKEND.md`).
