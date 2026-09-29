#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
static size_t calls;
size_t entropy_probe_calls(void) { return calls; }
void entropy_probe_reset(void) { calls = 0; }
void zen_test_arc4random_buf(void *out, size_t count) {
    if (!out || !count) abort();
    calls++;
    uint8_t *bytes = out;
    for (size_t i = 0; i < count; i++) bytes[i] = (uint8_t)(i % 251 + 1);
}
