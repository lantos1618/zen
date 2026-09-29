/* Native producers exercise the generated typed transfer callback, not a
   second implementation of the actor runtime or Vec allocator. */
#include <assert.h>
#include <sched.h>
enum { PRODUCERS = 8, TURNS = 64 };
static pthread_mutex_t rendezvous = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t all_preparing = PTHREAD_COND_INITIALIZER;
static size_t prepared, delivered[PRODUCERS];
static int stress;
static _Thread_local int first_preparation = 1;
static zg_actor *target;
static int PREPARE(zg_actor *actor, void *raw, zg_actor_owned **pending) {
    if (stress && first_preparation) {
        first_preparation = 0;
        pthread_mutex_lock(&rendezvous);
        prepared++;
        pthread_cond_broadcast(&all_preparing);
        while (prepared != PRODUCERS) pthread_cond_wait(&all_preparing, &rendezvous);
        pthread_mutex_unlock(&rendezvous);
    }
    preparing = 1;
    int result = PREPARE_impl(actor, raw, pending);
    preparing = 0;
    return result;
}
static void *produce(void *raw) {
    size_t producer = (size_t)raw;
    for (size_t accepted = 0; accepted < TURNS;) {
        uint8_t bytes[2] = {(uint8_t)producer, (uint8_t)accepted};
        MESSAGE message = {0};
        message.zg_arg0.zu_m4data = bytes;
        message.zg_arg0.zu_m3len = 2;
        message.zg_arg0.zu_m8capacity = 2;
        zg_actor_slice slice = {
            offsetof(MESSAGE, zg_arg0.zu_m4data),
            offsetof(MESSAGE, zg_arg0.zu_m3len), bytes, 2
        };
        int result = zg_actor_send_owned(target, TURN, &message, sizeof(message), &slice, 1, PREPARE);
        bytes[0] = 255; bytes[1] = 255;
        if (result == 0) accepted++;
        else { assert(result == 2); sched_yield(); }
    }
    return NULL;
}
static void exercise(void) {
    pthread_mutex_lock(&zg_actor_registry_lock);
    target = zg_actor_registry;
    assert(target && !target->next);
    pthread_mutex_unlock(&zg_actor_registry_lock);
    stress = 1;
    pthread_t threads[PRODUCERS];
    for (size_t i = 0; i < PRODUCERS; i++) assert(pthread_create(&threads[i], NULL, produce, (void *)i) == 0);
    for (size_t i = 0; i < PRODUCERS; i++) assert(pthread_join(threads[i], NULL) == 0);
    pthread_mutex_lock(&target->lock);
    assert(target->preparing == 0 && target->count <= ZG_ACTOR_CAPACITY && target->bytes <= ZG_ACTOR_BYTE_CAPACITY);
    pthread_mutex_unlock(&target->lock);
}
static void recorded(uint8_t byte, uint8_t sequence) {
    assert(byte < PRODUCERS);
    assert(delivered[byte] == sequence);
    delivered[byte]++;
}
static void completed(void) {
    for (size_t i = 0; i < PRODUCERS; i++) assert(delivered[i] == TURNS);
    puts("PASS: concurrent buffer reservations drained 512 messages");
}
