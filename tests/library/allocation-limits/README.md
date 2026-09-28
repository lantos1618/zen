# Allocation limit regression

Run `python3 tests/library/allocation-limits/run.py` using the existing compiler.
`ZEN` and `ZEN_STD` select the compiler and source tree; both repository
`poolcheck` targets include this regression. It never rebuilds the compiler.

The UBSan executable checks impossible element counts, allocation/page header
arithmetic, Vec length and growth overflow, preservation of live contents after
refusal, and successful retry. A refusing allocator verifies that capacities
above half the address space reach the allocator without doubling. An injected
allocation failure checks that Vec leaves its pointer, length and contents
unchanged before retry. Four isolated source mutations prove the checks reject
byte multiplication wrap, header overflow, length overflow and doubling overflow.
