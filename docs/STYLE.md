# Style and layout

Goals, in order: **small, works, elegant, low attack surface.** When two rules pull apart, the earlier goal wins.

## 1. File layout

```text
docs/        ZEN_LANGUAGE  COMPILER  BUILD_AND_PACKAGES  STYLE  TESTING
src/
  main.zen                 driver: argv -> stages -> exit code; nothing else
  front/
    parse/   lex.zen  parse.zen  ast.zen                    bytes -> Ast           (I: 2,000)
    collect/ collect.zen                                    Ast -> Decls           (1,000)
    check/   fit.zen  types.zen  resolve.zen  cull.zen      Decls -> Checked       (4,000)
    lower/   lower.zen  match.zen  inline.zen  cleanup.zen  Checked -> Ir (App C)  (5,000)
    flow/    flow.zen                                       Ir -> Ir + errors      (800)
  ir/        ir.zen (§1.1)  builder.zen  validate.zen  interp.zen (App B)  dump.zen   (2,000)
  back/      target.zen  ops.zen  steps.zen  alloc.zen  write.zen                       (3,000)
             int.zen  float.zen  convert.zen  memory.zen  call.zen  control.zen  (App H)
  c/         write_c.zen (App D)                                                        (1,500)
  build/     manifest.zen  graph.zen  mvs.zen  lock.zen  fetch.zen  ffi.zen            (1,800)
  std/       core/  mem/  seq/  text/  collections/  io/   (App L)                      (4,000)
runtime/     zen_rt.c                                                                   (200)
tests/       run/<topic>/  fail/<topic>/  run.py  stage0.sh  baseline-*.txt
tools/       budget.py
```

- **One stage per directory.** The numbers are line budgets; `tools/budget.py` fails past them.
- **Dependencies point one way:** `main → front → ir ← back, c`. `ir` imports nothing from the compiler, and `back` and `c` never import `front`. `std` imports only `std`.
- **No `util`, `helpers`, `common`, `misc` or `part2`.** A file has one subject you can name.
- **A folder exists** only when it has more than one file.

## 2. Code

**Shape**
- **The pseudocode in COMPILER.md is the code.** Use the same record names and the same function names (`lower`, `alloc`, `write`, `validate`). If they disagree, fix one of them in the same commit.
- **Closed sets are enums:** token kinds, opcodes, diagnostics, targets, trap codes. Use exhaustive `.match`, never an integer constant per kind.
- **Tables over code.** Templates, instruction descriptors and spellings are data indexed by enum (Appendix H).
- **Stages return new values.** Nothing mutates its input; no global state.
- **Refuse early.** The failing path leaves first, and the success path isn't nested.
- **Linear passes.** No quadratic loops over a function or a module; v07 had to fix three of them.

**Signatures say allocates, mutates, fails, escapes**
- **Allocation** takes an `Alloc` or uses an allocator-backed receiver.
- **`self :: @Self`** writes the receiver's bytes; `:` doesn't.
- **`Res`** is for failures a caller can act on. A trap is for a broken invariant.
- **No boolean parameters that switch the operation.** Use an enum or two functions.
- **Parameters that always travel together** become one record.

**Names**
- Types are nouns, functions are verbs, predicates are questions (`is_empty`).
- No `get_` or `do_`. Use `add` for one and `add_all` for many.
- Established abbreviations only: `alloc`, `len`, `ptr`, `env`, `ir`, `ast`, `reg`. Never `blk`, `nd` or `tp`.
- Rename before you comment a name.

## 3. Comments

Write comments for the next person changing the code. Keep:
- a contract;
- an invariant the code can't state;
- an ABI or format rule;
- why the simpler-looking change is wrong.

Never keep:
- chronology, plans or audit notes;
- a paraphrase of the next line;
- what an earlier version did.

A paragraph-long comment usually means a missing name or function.

## 4. Std and memory

- **One way to do each job.** No aliases and no wrappers.
- **One memory model:** `Alloc` is the interface and `Arena` the only T0 implementation. No global heap, no reference counting.
- **Each std module is under 400 lines.** Split by job when one grows past that.

## 5. Agents and commits

- **One stage or one std module per change**, gated by `tests/run.py --baseline` and `tools/budget.py`.
- **A change may add passes and may not lose one.** A budget overrun is a failed change, not a reason to raise the budget.
- **Before trusting a new check, break its target on purpose and watch it fail.**
- **No generated code is committed** except the bootstrap seed (Appendix K).

## 6. Review checklist

1. Can you say what it's about in one line without the module's name? If not, it lives elsewhere.
2. Does an existing type, table or std function already do it?
3. Is it a closed set written as constants or strings instead of an enum?
4. Does a dependency point the wrong way?
5. Is any pass worse than linear?
6. Which test proves this change, and did that test fail before the change?
7. Did the line count go down or stay level for the same behaviour?
