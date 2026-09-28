# Owning lookup regression

`main.zen` inserts one consumed owner and then attempts a copying lookup.
Compilation must reject that lookup. `tests/quality/ownership_lookup.py` also
checks Vec.require/iteration, Map lookup/iteration, pointer reads and bulk copies,
generic helpers and inline owner fields. Vec.take and Ptr.take transfer ownership;
factories remain valid. Runtime controls assert exact destruction counts under
UBSan, including removing the middle element before clearing the remaining vector.

Run from the repository root:

```sh
python3 tests/quality/ownership_lookup.py --zen ./zen
```

An optional `--old-zen PATH --old-std PATH` runs the original counter-only
reproducer against a pre-fix compiler/library pair and requires two destructor
calls. That is a failing control for the ownership contract, not a supported
behavior. Ptr.take is unchecked: the caller must retire or overwrite the source
slot before reading or destroying it again. This gate does not establish general
borrow lifetimes, container-alias safety, or complete ownership soundness.
