# Bounded completed spans

`std.trace.Buffer` stores completed `Span` values in caller-allocated storage.
`Buffer.create(alloc, capacity)` allocates that storage once; capacity zero
allocates nothing. `record` and `at` allocate nothing. This module has no clock,
actor, file, transport, sampling or OpenTelemetry dependency.

A buffer has one mutable owner. Its span storage must outlive the buffer and
all reads through it. A stored `Span.name` is a **borrowed string view**, not a
copy: the name's bytes must remain valid until every consumer has finished
reading that span. Mutating those bytes changes what readers observe. Prefer
static names or storage with the same lifetime as the buffer. Copy names into
receiver-owned storage when asynchronous transport needs a longer lifetime.
Neither copying a buffer descriptor nor sending its pointer creates independent
ownership or makes concurrent writes safe; serialize all access externally.

A valid span has a nonzero ID, a different parent ID, a nonempty name and an end
time at least its start time. The buffer does not validate UTF-8, deduplicate
IDs, require parents to be present, or convert timestamp epochs; encoders and
consumers own those policies. Equal start/end timestamps are valid.

Once full, `record` returns false without changing existing records. Invalid
spans likewise return false. Each refusal increments `dropped` up to
`usize.MAX`, then leaves it saturated. `at` returns `None` beyond the populated
count. Use `Buffer.create` for normal construction; raw construction assumes
valid caller-owned storage and coherent capacity/count values.

Run the focused gate from the compiler repository:

```sh
python3 tests/library/trace/run.py --zen build/bootstrap/zen-seed --std src
```

The gate checks invalid spans, oversized capacity, disabled storage, 10,000
full-buffer refusals, unchanged recorded values, indexed bounds, borrowed-name
visibility and dropped-counter saturation under UBSan. Test-only native
instrumentation rejects malloc/calloc/realloc throughout the record/read phase,
including disabled creation and capacity-overflow refusal. A deliberately
allocating generated `record` implementation must fail the same gate. The
instrumentation observes generated-program allocator calls, not libc internals;
it is not a proof of arbitrary pointer lifetime safety.
