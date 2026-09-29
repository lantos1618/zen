# Concurrent mailbox correctness

Run from the compiler repository:

```sh
python3 tests/quality/actor_contention.py --zen build/dev/actor-observe-zen
```

The fixture spawns a real generated Zen actor with its generated typed mailbox
storage. A test-only native probe supplies eight concurrent pthread producers
to exercise the generated send ABI. It does not copy or replace the runtime or
allocation implementation.

Two rounds deliver 32,000 messages each. The probe checks per-producer order,
exactly-once delivery, copied stack payloads, count/byte bounds, complete drain,
and no more than 64 additional native allocations for the stable payload size.
A third round races stop against producers and checks that every accepted
message drains and post-stop sends return Closed. Process teardown runs only
after external producers are quiescent, as required by the runtime contract.

The same workload runs under UBSan. Deliberately disabling the generated pool
cache must violate the allocation budget; corrupting copied payloads must
violate delivery checks. The join gate separately exercises simultaneous join
callers, self-join, idle workers and failed native joins.

This is a correctness and stable-size allocation gate, not a throughput
benchmark, race-detector result or proof of arbitrary borrowed-data safety.
The runtime retains a process-wide send lock and one thread per actor.
Exact-size pool caching can retain obsolete size classes at the block-count
limit; variable-size workloads require separate churn measurements before a
cache eviction policy is chosen. ASan remains a separate unresolved gate on
hosts where its runtime fails before the program starts.
