#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
static size_t calls;
static int mode;
size_t entropy_probe_calls(void) { return calls; }
void entropy_probe_mode(int selected) { mode = selected; calls = 0; }
int zen_test_getentropy(void *out, size_t count) {
    if (!out || !count || count > 256) abort();
    calls++;
    if (mode == 1 || (mode == 2 && calls == 2)) return -1;
    uint8_t *bytes = out;
    for (size_t i = 0; i < count; i++) bytes[i] = (uint8_t)(calls + 7);
    return 0;
}
