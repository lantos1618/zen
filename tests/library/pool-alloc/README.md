# Explicit pool allocation

`std.mem` exports `Pool`, `PoolPolicy`, and `PoolAlloc`. `Pool` caches exact-size
blocks; `PoolAlloc` supplies the standard `Alloc` interface to existing code.
The caller supplies all three cache limits. There is no actor policy in this API.

```zen
Pool, PoolPolicy, PoolAlloc, Ptr, null_ptr = std.mem

use_buffer = (a: Alloc) Res<(), AllocError> {
    bytes = a.realloc<u8>(null_ptr<u8>(), 128).try();
    @scope.defer(() { a.free(bytes); });
    bytes.write(0, 42);
    Ok(())
}

main = (env: Env) Res<i32, AllocError> {
    owner = env.mem.alloc();
    pool = owner.realloc<Pool>(null_ptr<Pool>(), 1).try();
    pool.write(0, Pool());
    @scope.defer(() {
        state ::= pool.read(0);
        state.close();
        pool.write(0, state);
    });
    allocator = PoolAlloc(pool: pool, policy: PoolPolicy(
        cache_bytes: 4096, block_bytes: 512, blocks: 8
    ));
    use_buffer(allocator).try();
    Ok(0)
}
```

The adapter value must remain alive at a stable address while any `Alloc` handle
refers to it. Pool storage must outlive adapters, borrowed handles, and allocations.
Neither the pool nor its live state may be copied to make independent owners.
Calls require external serialization; this API does not supply synchronization.
Pass only this pool's live allocations to its `realloc` and `free` operations.

`cache_bytes` includes each retained block's 16-byte header; `block_bytes` limits
its payload; `blocks` limits retained count and linear-search work. Zero limits
disable caching. Use a consistent policy per pool; close its idle cache before
switching to stricter limits. A policy change does not evict existing cached blocks.
These limits constrain retained storage, not outstanding live
allocations or process-wide memory. The pool remains libc-backed, rather than
using a caller-supplied backing allocator.

`raw` accepts alignment 1, 2, 4, 8, or 16. Other alignments return `OutOfMemory`,
consistent with the current `AllocError` set. The native backend requires malloc
alignment of at least 16 bytes, as on supported Apple silicon/x86-64 targets.
The header size is checked before allocation. A zero-byte request returns a
non-null, freeable block. `realloc` retains capacity when shrinking, including
shrinking to zero. Growth allocates and copies before freeing the original;
failure leaves the original pointer and bytes untouched. `free` is null-safe.

Return all outstanding allocations, then `close` the pool. Closing reclaims the
cache and is repeatable; it does not free still-live allocations. `owned` includes
headers and all live/cached blocks, `cached` includes cached headers, and
`cached_blocks`, `allocations`, `reuses`, and `peak` expose accounting.

Run the standalone gate with a seed or candidate compiler:

```sh
python3 tests/quality/pool_alloc.py --zen build/bootstrap/zen-seed --std src --ubsan
```

The gate tests the generic `Alloc` surface, content-preserving growth, native OOM
and overflow ownership, exact-size reuse, count/byte bounds, large-block bypass,
and teardown. Negative controls remove the realloc copy and remove native OOM
injection. `--sanitize` additionally runs AddressSanitizer/UndefinedBehaviorSanitizer;
its runtime must be available on the host. This is a focused gate, not proof of
arbitrary pointer/lifetime safety or full compiler verification.
