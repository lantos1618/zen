# Native application libraries

Libraries own a capability and expose ordinary Zen values. A library is a
source module registered in `build.zen`; importing it does not require copying
its source into the app. The selected executable names its library dependencies.
Current projects use sibling checkouts with explicit paths; there is no package
registry, dependency fetching, or lockfile resolver yet.

| Library | Responsibility | Public boundary |
| --- | --- | --- |
| `std` | General memory, collections, actors, clocks and bounded sample statistics | Caller-owned storage and platform-neutral values |
| `zen-macos` | AppKit windows, Metal presentation, macOS input/audio devices | Configured window, events, borrowed samples, explicit lifecycle |
| `zen-audio` | Portable sample processing | FFT, bands, WAV encoding, caller-owned arrays |
| `zen-parakeet` | Local Parakeet inference through NVIDIA's native SDK | Mono f32 samples in; owned Zen text or errors out |
| `zen-whisper` | Optional existing Whisper CLI integration | Explicit executable/model/file paths; process output |
| `zen-voice` | Actor-owned model lifecycle and bounded dictation scheduling | Copied PCM requests and bounded transcript replies |
| `zen-tui` (Zen Code) | Application policy and presentation | Composes capture, DSP, model worker, and UI |

The model adapter must not own microphone permissions, windows, or the UI event
loop. DSP must not depend on macOS or a particular speech model. Native handles
stay inside their owner; callers receive copied text or clearly borrowed sample
views. Allocators are chosen at the operation boundary. A live native owner must
not be copied and must be closed before its allocator dies.

Native functions are declared with `c.bind` against their actual headers. The
compiler emits calls rather than handwritten forwarding implementations. The
native callback facility accepts explicitly typed nongeneric free functions;
it does not make captured Zen closures into native callbacks. Record layouts
that are currently mirrored in Zen are checked against the native SDK header.

The application and adapter code are Zen. Operating-system frameworks and the
NeMo Speech inference engine are external native dependencies. Parakeet's
weights are data stored outside Git and passed by explicit local path. Runtime
or model downloads do not belong in an imported module's initialization.

`std.math.vector` now supplies portable, allocation-free f64 `dot` and
`squared_distance` kernels written in Zen. Independent accumulators let the
existing C backend auto-vectorize them; no compiler edits, native vector ABI,
fast-math flags or handwritten C implementation are required. Apple Clang at
`-O2` emits ARM SIMD instructions for both kernels. This is an optimization
verified on one target, not a language-level guarantee on every compiler/CPU.
The pitch detector uses squared distance; the FFT remains scalar Zen.

Both borrowed input pointers must cover the requested count; they may overlap,
and null is allowed only for zero elements. There is no allocation or extra
alignment requirement. Floating-point reductions use a different addition
order from a scalar fold and are not bitwise-equivalent. Native vector types,
shuffles and explicit instruction selection remain separate future work.
Model inference already uses its native CPU/Metal backend. MLX would be an
independent numeric/model backend, not a windowing dependency.

Run `python3 tests/library/vector/run.py` for tail/aliasing/offset checks, a
broken-kernel negative control, sanitizers, ARM assembly inspection and a
704-element microbenchmark. The current benchmark driver and scalar reference are both Zen, compiled with
identical `-O2` flags. It mutates an input each iteration to prevent hoisting.
The original measurements below used a C driver with indirect calls. On Apple M2 Pro, the initial five runs measured 168–177 ns for the
std kernel versus 552–776 ns for the scalar reference (about 3.3× warm).
These are isolated kernel measurements, not application latency claims.

## Timing and threading ownership

General elapsed time uses `Env.clock.since_start()`. `std.stats` owns bounded
rolling numeric samples and nearest-rank summaries; it knows nothing about
frames, microphones, Apple APIs, or exporters. Sampling and summarizing reuse
caller-allocated storage.

Display-link callbacks, Core Animation timestamps and Metal drawables belong
in `zen-macos`. The SDK's frame metrics describe submissions, not measured
onscreen presentation or GPU execution time. Native UI handles stay on the
main run loop. The app chooses what to display and when to request inference.

`zen-voice` owns the speech worker and its current Darwin pipe reply bridge.
A future generic pollable actor-result channel belongs in std once its
lifecycle, backpressure and portability contracts are implemented and tested;
this milestone does not claim that channel exists. Do not move speech policy
or macOS run-loop behavior into the actor runtime.

The focused sanitizer run timed out on this host, including outside the sandbox;
that check remains unverified. The runner exits nonzero on sanitizer timeout
after reporting the independent assembly and benchmark checks.

`std.trace` now provides a single-owner, caller-allocated bounded buffer of
completed spans with borrowed names, explicit IDs and timestamps, and dropped
record accounting. It has no clocks or transport. `zen-otel` encodes OTLP JSON;
Zen Code opts in to shutdown-only local trace export. Automatic actor context
propagation and a network exporter remain future work.

## C emission boundary audit

Compiler C emission is not uniformly language lowering. The current backend
also emits hand-written runtime algorithms as strings. Keep that distinction
visible when claiming the system is written in Zen.

| Area | Current form | Intended ownership |
| --- | --- | --- |
| `gen_c_actor.zen` | C mailbox, copying, locks, registry and shutdown algorithms | Move policy and budgeting into a typed Zen runtime; compiler retains per-actor message/thunk generation |
| `gen_c_proc.zen` | C process capture/polling runtime | Zen process implementation over native declarations, preserving pipe/exit semantics |
| `gen_c_threads.zen` | C sleep/thread ABI and capture ownership glue | Separate native ABI/capture lowering from reusable thread policy |
| `gen_c_env.zen`, `gen_c_stdin.zen`, `gen_c_clock.zen` | Small emitted capability helpers | Review for header-bound std implementations with the same allocation contracts |
| `gen_c_runtime.zen` | Mixed traps, checked arithmetic, allocator/native runtime | Classify individually; type/layout-specific compiler operations remain lowering |
| Native app/library `src` and `tools` | Zen plus `c.bind` declarations | Keep implementations in Zen; no handwritten C implementation found by the current scan |
| ABI/allocation/assembly tests | C assertions and injected fault/probe code | Deliberate independent instrumentation, not production implementations |

The SIMD benchmark driver and scalar reference now live in
`tests/library/vector/benchmark.zen`; the Python runner no longer prints a C
benchmark implementation. Generated-C mutation remains only for negative
controls and precise assembly inspection. Grammar parser C is generated by
Tree-sitter; foreign-call example C and native header ABI tests are intentional.

Do not treat moving C strings into `.c`/`.h` files as a Zen migration. For each
runtime extraction, preserve behavior with allocator failure, payload overflow,
concurrent producer, closed/full mailbox and shutdown tests. Start actor work
with checked payload sizes and byte-budget semantics, then migrate the policy
behind the typed actor API. Layout/ABI requirements and compiler bootstrap
dependencies must be resolved before deleting the old path. The paused opaque
draft is not an available validated prerequisite.

### Actor admission hardening

The development runtime now reads `MAX_MESSAGES` (64) and
`MAX_MESSAGE_BYTES` (32 MiB) from `std.actor.actor_limits` at compiler build
time. Counts and bytes include the executing message; bytes include its header,
typed fields and copied slices. Closed/full/oversized sends reject before
allocation or copying. Size checks use remaining capacity before addition,
avoiding overflow. Allocation failure leaves counters unchanged; completed
turns release their charge. This bounds message allocations, not native model
memory, per-turn scratch or the process-wide sum across actors.

Policy constants live in Zen; queue implementation and locking remain emitted
C. The first correction keeps the existing registry-before-mailbox locks held
through allocation/copy/enqueue. This prevents a new reservation/shutdown race
but large copies can serialize unrelated actor sends. A later typed Zen runtime
migration should introduce tested reservations before optimizing this lock.

`tests/quality/actor_admission.py --zen build/dev/actor-zen` fault-injects the
actual generated runtime, covering overflow, byte/count limits, allocation
failure, four simultaneous producers, active-message charging and stop/drain.
Its negative control deliberately allocates on rejection and must fail.
The corpus includes a Zen oversized-descriptor regression.

The isolated development compiler and app integration pass focused checks.
The regular compiler binary has not been replaced. Full verification remains
blocked by missing `npx`; the HTTP/2 actor corpus case also needs `libssl`.
Seed C was generated only in the isolated source snapshot, whose `git add`
step cannot stage ignored build artifacts. No aggregate-green claim is made.

### Mailbox storage and join candidate

`std.mem.mem_pool.Pool` owns reusable raw blocks behind a native heap boundary.
Operations require external serialization and exact-owner returns. It is not
a general thread-safe Alloc, and live owners must not be copied.
`std.actor.actor_storage` selects exact-size mailbox reuse with at most 64
cached blocks and 1 MiB cached bytes including pool headers; requested blocks
over 64 KiB (excluding the pool header) are returned immediately. Message admission also charges
allocation metadata against the 32 MiB active budget. Compiler-generated
callbacks bridge actor layout to this typed Zen policy. Pool close follows
worker drain. Context.alloc retains the actor lifetime.

Concurrent Ref.join callers have one native join owner and a separate condition
variable, so they cannot consume worker wakeups. Self-join returns without
claiming completion. Failed native joins remain retryable; global teardown
refuses to free an unjoined worker. External callers must be quiescent before
process-wide teardown. This does not add a worker pool or concurrent global
shutdown support.

Actor control records and arena state still use native runtime allocation.
Spawn does not yet accept a caller-selected allocator; this change must not
be described as full allocator compliance. The global send lock still spans
allocation and copying. Header alignment supports the existing scalar payload
floor; native over-aligned vector payloads need a separate ABI design.

`make actorcheck` exercises admission, join concurrency, typed storage and
actual generated actor reuse, with deliberately broken negative controls.
It is included in `make verify`. These candidate changes require integration
before seed promotion.
