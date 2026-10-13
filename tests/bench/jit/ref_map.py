"""CPython reference for map/main.zen: the same keys, inserts and lookups."""
import sys

M = (1 << 64) - 1
rounds = int(sys.argv[1]) if len(sys.argv) > 1 else 16
total = 0
for r in range(rounds):
    m, x = {}, r + 1
    for i in range(4096):
        x = (x * 6364136223846793005 + 1442695040888963407) & M
        m[x >> 16] = i
    y = r + 1
    for i in range(4096):
        y = (y * 6364136223846793005 + 1442695040888963407) & M
        total = (total + m.get(y >> 16, 0) + 3 * m.get((y >> 16) + 1, 0)) & M
print(f"{rounds} rounds map {total}")
