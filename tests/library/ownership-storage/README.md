# Owning-storage regression inputs

These inputs currently expose unresolved ownership defects; they are not
passing corpus cases. See ISSUES.md. Compile each with `--entry NAME.zen`.

- `borrow.zen` must be refused: storage cannot take an ordinary borrowed owner.
  The current program prints `drop 1` twice.
- `replace.zen` must destroy both owners exactly once. The current program only
  prints `drop 2`, losing the replaced owner.
- `invalid-set.zen` must destroy the consumed input exactly once on refusal.
  The current program prints nothing.

A transfer repair must also cover allocation refusal, generic forwarding and
helper calls. Destruction of borrowed parameters is not a valid repair.
