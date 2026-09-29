# OS entropy contract checks

Run `python3 tests/library/entropy/run.py --zen ./zen --ubsan`.

The nativecheck gate invokes this deterministic OS-replacement fixture.
It checks the request size, exact written span, empty/null behavior, refusal
on first/later chunks and stopping after refusal. A false success from the
injected OS function must fail. Real OS availability is separately exercised
by `tests/corpus/std/os_entropy.zen`. No random-quality statistical test or
fallback PRNG is used. The replacement is test-only and never linked into std.
