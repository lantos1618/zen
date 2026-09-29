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
it does not make captured Zen closures into native callbacks. `c.record` uses
the native header's layout and checks scalar field types. `std.net` uses this
for `addrinfo` and typed header constants for platform flags; socket ownership,
allocation and cleanup remain Zen. Native pointer lifetimes remain explicit
FFI responsibilities. Existing mirrored application records need migration
before they can claim this header-owned layout contract.

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

## Bounded binary cursors

`std.bytes.ByteReader` and `ByteWriter` borrow a caller-owned `Ptr<u8>` and
length. `open` accepts a null pointer only for zero length. They allocate
nothing and do not extend memory lifetimes; the caller must supply a live
region of the declared size, with writable storage for a writer.

Readers expose `read_be(width)`, `read_le(width)` and `take(count)`;
writers expose `write_be(value, width)` and `write_le(value, width)`.
Widths are 1–8 bytes; decoded values are u64. A write rejects a value that
cannot fit in the requested width. Invalid widths/values produce `Invalid`;
insufficient remaining storage produces `Truncated`. Failure leaves the
cursor position and destination bytes unchanged. `remaining`, `consumed`
and `written` expose progress without allocation. `take` returns a borrowed
`str` byte view; it does not validate UTF-8. These cursors are independent
values, so copying one copies its position, not its storage.

Integer/endian/cursor behavior belongs in std. SHA, AEAD, TLS transcript
state and cryptographic key schedules remain in zen-crypto. Algorithm-specific
fixed-size block loops need not be generalized solely to move them into std.

## Operating-system entropy

`std.entropy.fill_random(output, count)` fills a caller-owned writable byte span
using the operating system's cryptographic random source. It allocates nothing,
retains no pointer or PRNG state, and has no predictable fallback. Supply a live
span of `count` bytes. A null pointer is accepted only when count is zero;
empty calls perform no OS operation. Nonempty null spans return `Invalid`.

On macOS 10.12+ and Linux with glibc 2.25+, the header-backed `getentropy`
binding requests at most 256 bytes per call; chunking and errors are handled in
Zen. The operation may block during OS entropy initialization. Any OS refusal
returns `Unavailable`; earlier chunks may already have overwritten the output,
so callers must discard the entire result on failure. No secure-erasure claim
is made. This is distinct from `std.core.rand`, which must not generate keys.

TLS algorithms remain in zen-crypto. Public handshake randomness and ephemeral
private keys require separate calls: never expose private bytes by reusing them
as the public ClientHello/ServerHello random. OS entropy availability does not
replace protocol validation, secret ownership or side-channel review.

The corpus checks real OS success and buffer guards. `tests/library/entropy`
uses a deterministic test-only OS replacement to cover 256-byte chunking,
zero/null spans, failure on the first and a later call, and stopping after
failure. A deliberately false OS-success result must fail its assertions.
These checks do not attempt to establish entropy quality through statistics.

Reference: [getentropy](https://man7.org/linux/man-pages/man3/getentropy.3.html).
The macOS SDK declares the same interface in `sys/random.h`.
