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

SIMD belongs below these APIs: eventual `std.simd` vector operations and compiler
lowering should be reusable by DSP and numeric libraries. Model inference
already uses the native runtime's CPU/Metal implementations. The current FFT
is scalar Zen with numerical tests; it is not represented as SIMD-optimized.
Measure its cost before adding vector APIs. MLX is a possible independent
numeric/model backend, not a dependency of windowing or generic sample buffers.

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
