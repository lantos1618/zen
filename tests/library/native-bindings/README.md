# Native header contracts

Run `python3 tests/library/native-bindings/run.py --zen /path/to/compiler`.
The fixtures compile against a small controlled C header, then execute generated
C. They distinguish a present macro from its fallback, an absent macro from its
fallback, and an enum identifier from preprocessor macro presence. Header-backed
record construction, exact field names and mutable field writes execute too.

Invalid sources must fail in the Zen compiler before C compilation: constant
mutation, native constants used as compile-time array sizes, namespace
construction, invalid C record names, record methods, generic records and union
field layouts. The runner uses temporary build directories and no network.

An out-of-range `c_int` fallback is intentionally checked by the target C
compiler against `INT_MAX`, rather than guessed by Zen's host. The runner
requires that generated range assertion to reject an absent-macro fallback.
Normal fixed-width integer ranges remain Zen semantic checks.

A mismatched native scalar field must fail the target C type assertion. This
prevents a mutable Zen reference from writing a wider value into narrower native
storage. Pointer pointee declarations remain explicit FFI contracts.
