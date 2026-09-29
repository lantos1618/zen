# OS entropy contract checks

Run `python3 tests/library/entropy/run.py --zen ./zen --ubsan`.

The nativecheck gate invokes this deterministic OS-replacement fixture.
It checks that one OS call receives exactly the requested span, the bytes
around it stay untouched, and empty/null spans make no OS call. A short fill
from the injected OS function must fail. `arc4random_buf` has no error result,
so there is no OS-refusal path to inject. Real OS availability is separately exercised
by `tests/corpus/std/os_entropy.zen`. No random-quality statistical test or
fallback PRNG is used. The replacement is test-only and never linked into std.
