# Owning-storage regression inputs

These inputs currently expose unresolved ownership defects; they are not
passing corpus cases. See ISSUES.md. Compile each with `--entry NAME.zen`.

- `borrow.zen` must be refused: storage cannot take an ordinary borrowed owner.
  The current program prints `drop 1` twice.
- `invalid-set.zen` must destroy the consumed input exactly once on refusal.
  The current program prints nothing.

A transfer repair must also cover allocation refusal, generic forwarding and
helper calls. Destruction of borrowed parameters is not a valid repair.

Successful replacement is covered by the passing corpus regression
`tests/corpus/ownership-drop/vec_set_destroys_displaced_owners.zen`.
It verifies repeated middle-slot replacement, unchanged length, exactly-once
destruction during clear, and ordinary integer replacement. The original Vec
implementation fails this oracle by omitting both displaced destructors.
