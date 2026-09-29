# Native application libraries

Libraries own a capability and expose ordinary Zen values. A library is a
source module registered in `build.zen`; importing it does not require copying
its source into the app. The selected executable names its library dependencies.
Projects can register sibling checkouts with `b.lib`, or use pinned Git sources
with `b.add`. The manifest itself contains the commit lock. There is no registry,
semantic-version solver, transitive manifest execution, or `zen add` editor yet.
See [project dependencies](BUILD_PACKAGES.md) for the implemented API.

`std.fs.posix` owns streaming file descriptors for POSIX targets. `open_read`
and `create_temporary` take caller-selected allocation; descriptor `read_exact`
and `write_all` perform complete transfers without allocating, retrying EINTR.
`size` preserves the cursor on seekable files. Handles have explicit `close`
lifetimes, and `Fs.remove` removes temporary paths. The pointer-taking read
requires caller-provided capacity; this is a native boundary, not a checked
buffer or compiler-enforced descriptor ownership API. The temporary-file
operation uses `mkstemps` (Darwin/Linux). Rooms owns its upload protocol,
attachment limits, progress text and preview allowlist; those are not std APIs.

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

### Actor byte-buffer transfer

A direct `Vec<u8>` behavior argument requires `consume`. Admission copies its
live bytes into a private arena backed by the receiver's `Env.mem`, replaces
the vector's allocator and capacity, and publishes only after allocation
succeeds. A refused allocation returns `ActorError.Full` and frees partial
transfer storage. Closed/count/byte-limit refusals happen before preparation. Admission reserves
count, bytes and pending work before releasing runtime locks for allocator
callbacks. Stop waits for those reservations; a stop during preparation rejects
the send and releases its private storage before running stopped.
Nested vectors, other element types and borrowed vectors remain rejected.
The shared `Env.mem` provider and its userdata must outlive the actor and support
allocation/release from sender and worker threads. Each transfer arena itself
has one mutator at a time.

The transfer allocator has a stable address and remains live through subsequent
turns, `stopped`, and actor destruction. The receiver can retain and grow even an
initially empty vector. Each accepted buffer message currently retains a private
arena until actor shutdown; this uses ordinary arena page granularity and is not
a claim of bounded total actor-state memory. Message bytes remain subject to the
mailbox admission limit. The transfer does not change general owning collection
storage's unresolved borrow and invalid-set issues.

`tests/quality/actor_buffers.py` exercises the generated runtime under UBSan,
including corruption/lifetime negative controls, refusal at each preparation
allocation, refused-allocation cleanup, closed admission without allocation, reentrant callbacks, and stop during
preparation.

The buffer gate also forces eight native producers to overlap inside preparation,
checks 512 delivered buffers and each producer's order, grows each receiver buffer,
and tracks complete reclamation of preparation allocations at shutdown.

## JSON object inspection

`Jsons.member_count(id)` and `Jsons.member(id, index)` expose stored object
members without allocation or serialization. Enumeration preserves duplicate
keys and their stored order; `field(id, name)` continues to return the last
matching value. Keys are decoded borrowed text and share the tree's storage
lifetime. Non-object values return zero members / `None`; out-of-range member
indices return `None`. Invalid `JsonId` values retain `at`'s trapping contract.

This capability was extracted from agentfleet's resource-schema validation.
Agent commands, RPC framing, extension environment variables and package policy
remain application concerns. General process cancellation, bounded execution
and atomic filesystem publication need independent lifecycle and portability
contracts before being added to std; the former agentfleet `proc.c` patch must
not be applied over the current Zen-owned process implementation.

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

## HTTP is a package dependency

HTTP/1 and HTTP/2 are maintained in [zen-http](https://github.com/lantos1618/zen-http).
`std.net.http`, `std.net.http2`, their top-level `std` re-exports, and
`env.net.http()` have been removed. This is a breaking source change; there is
no compatibility facade or hidden package download. The compiler bootstrap
and standard library have no dependency on zen-http or zen-openssl.

Applications import `HttpClient`, response/error types and `H2Client` from
`http`, and construct `HttpClient()` explicitly. Register the package and its
TLS backend in the application's build graph; the package README documents
its current sibling-checkout and OpenSSL build requirements. HTTP-specific
regression coverage is maintained with the package rather than duplicated
inside compiler std tests. The native PSK client is an explicit package API;
ordinary certificate-verified HTTPS continues to use zen-openssl.

Socket, readiness, TCP, DNS and other shared OS primitives remain in std.
The reserved `Net` capability retains its empty shape; it no longer constructs
an HTTP client.
