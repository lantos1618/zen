# Actor runtime benchmarks and stress scenarios

Each program is one scenario from `reports/actors/PLAN.md`'s targets or the
stress campaign (`zen-experiments/actors/stress`), built for the C and the
native backend by `build.zen`. Parameters come from the environment; every
program prints one `bench=...` line of `key=value` numbers.

| Program | What it measures | Parameters |
|---|---|---|
| `spawn` | ns per spawn, resident bytes per idle actor | `N` |
| `pingpong` | round-trip ns, messages/s | `PAIRS`, `ROUNDS` |
| `ring` | ns per hop | `NODES` |
| `fanin` | 10k senders into one actor: loss, order, starvation, items/s | `SENDERS`, `PER` |
| `parked` | 1M clients waiting on one gate: bytes each, time to resume | `N` |
| `overload` | producers outrunning consumers: loss, order, throughput, RSS | `PRODUCERS`, `DURATION`, `WORK` |
| `churn` | actors spawned and stopped: each finalised once, rate | `TOTAL` |
| `preempt` | CPU-bound turns beside latency probes, with and without sysmon | `HOGS`, `PROBES`, `DURATION`, `TURN_MS` |
| `soak` | everything at once for `DURATION` s, a line per `INTERVAL` s | `DURATION`, `INTERVAL` |
| `chatter` | random gossip graph under backpressure: wedges, conservation, latency, RSS | `PEERS`, `FANOUT`, `DURATION`, `MAX_BURST`, `FORWARD`, `SLOW`, `DIE` |

Runtime settings: `ZEN_ACTOR_WORKERS`, `ZEN_ACTOR_SYSMON_US` (0 turns
preemption off), `ZEN_ACTOR_WATCHDOG_MS` (0 turns the stuck-runtime
report off), `ZEN_ACTOR_TRACE=<file>` (every message's path, written
at exit; see docs/ACTOR_RUNTIME.md), `ZEN_ACTOR_CHECKED=1` (one mapping
per block, for sanitizer runs).

On dev-box, from this directory:

```sh
zen build . --release
CPUS=9-12 WORKERS=4 REPS=3 bin/c/run          # medians, load-gated
```

`run` waits before each run until the pinned CPUs are at least 90% idle.
Run `churn` under AddressSanitizer with `ZEN_ACTOR_CHECKED=1` (build its C
with `zen build --emit-c` and `clang -fsanitize=address`).
