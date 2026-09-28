# Returned collection regressions

Run `python3 tests/library/returned_values/run.py` from the repository root.
`ZEN` may select an existing compiler; the default is the repository's `zen`.
The runner copies current `src` into ignored `build/library-returned-values`
and compiles the harness against that copy, including the complete sema module
and its migrated call sites. It does not build a compiler or regenerate a seed.

The AST checks cover empty trees, no matches, stable id order across arena pages,
repeat queries, and refusal at every vector growth. Both the previous append
algorithm and the returned result collect the same 257 ids with exactly ten
allocation requests. This establishes allocation parity, not a timing improvement.
The caller-selected allocator is independent of the AST allocator.

The sema checks parse ordinary, valid variadic, misplaced variadic, and nested
variadic declarations and assert their diagnostic counts. Refusing every
allocation in checker construction and validation must propagate failure.
The same harness also runs with UBSan.

Three mutations are applied only to the isolated source copy and must fail:
discarding all selections, using the AST allocator instead of the supplied
allocator, and adding an unnecessary reserve. These prove that functional,
allocator-routing, and allocation-budget assertions detect regressions.
Full compiler/seed integration and aggregate verification are separate checks.
