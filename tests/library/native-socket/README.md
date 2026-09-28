# Native socket and header ABI regression checks

Run from the repository root with a compiler supporting `c.record` and typed
immutable constants in `c.bind`:

```sh
python3 tests/library/native-socket/run.py --zen ./zen
python3 tests/library/native-socket/run.py --zen ./zen --ubsan
```

`--std PATH` selects another standard library. The runner compiles the fixtures
using that library, then compiles generated C against the installed host headers.
It creates only local IPv4/IPv6 loopback connections; no external DNS or server is
used. IPv6 is required rather than silently skipping a failing platform path.

The production socket implementation remains Zen. `probe.h` is test-only native
instrumentation: descriptor flags/counts, SIGPIPE disposition, and balanced
`getaddrinfo`/`freeaddrinfo` calls. The Python file coordinates peers and compilation;
it is not a runtime dependency or a replacement implementation of std.net.

Covered contracts:

- A native record with deliberately different field order and hidden bytes has
  native construction, zero initialization, field access and array stride.
- Typed header macro and enum constants resolve to their header values. An
  optional present macro takes precedence over its fallback; an absent macro
  uses its explicit fallback.
- Literal IPv4 and IPv6 resolution preserves numeric text and family.
- Both loopback families carry a partial-read/full-write handshake.
- Sockets carry FD_CLOEXEC; explicit repeated close and automatic scope drop close
  their descriptor. Descriptor counts remain stable after 100 refused connects.
- Closed-peer high-level and raw writes return errors with SIGPIPE at its default
  disposition; the process must survive.
- Caller allocator failures are swept from allowance zero through successful DNS
  allocation. Native addrinfo lists and socket descriptors remain balanced.

Bounds and limitations: descriptor counting scans descriptors 0–1023 because this
fixture opens only a handful of low-numbered descriptors. Counting addrinfo lists
checks ownership balance, not individual libc heap blocks. CLOEXEC flag checks do
not prove atomic close-on-exec setup against concurrent process spawning. These
are focused host checks, not an ASan or whole-repository pass. Refusal checks use
a freshly released ephemeral port because Darwin does not immediately reject a
bound non-listening port; unexpected concurrent port reuse fails the test. The current socket
bindings target Darwin/Linux hosts with 64-bit `ssize_t` and 32-bit `int`; these
tests do not establish compatibility with 32-bit operating-system ABIs.
