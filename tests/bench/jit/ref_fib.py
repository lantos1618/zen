"""CPython reference for fib/main.zen: fib(24) `rounds` times, calls counted."""
import sys

def fib(n, calls):
    calls[0] += 1
    return n if n < 2 else fib(n - 1, calls) + fib(n - 2, calls)

rounds = int(sys.argv[1]) if len(sys.argv) > 1 else 64
calls, total = [0], 0
for _ in range(rounds):
    total = (total + fib(24, calls)) % (1 << 64)
print(f"{rounds} rounds fib {total} calls {calls[0]}")
