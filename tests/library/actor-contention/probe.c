/* Test-only native producers exercise the generated mailbox ABI. The actor,
   allocation callbacks, pool and worker are generated from the Zen fixture. */
#include <assert.h>
#include <sched.h>
#include <unistd.h>
enum { PRODUCERS = 8, TURNS = 4000 };
typedef struct { size_t producer, sequence; } payload;
static size_t delivered[PRODUCERS], accepted[PRODUCERS], full[PRODUCERS];
static zg_actor *target;
static pthread_mutex_t launch_lock = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t launch_changed = PTHREAD_COND_INITIALIZER;
static int ready, launch, race_stop;
static void consume(zg_actor *actor, void *raw) {
    (void)actor;
    payload *p = raw;
    assert(p->producer < PRODUCERS);
    assert(p->sequence == delivered[p->producer]);
    delivered[p->producer]++;
}
static void *produce(void *raw) {
    size_t id = (size_t)raw;
    pthread_mutex_lock(&launch_lock);
    ready++;
    pthread_cond_broadcast(&launch_changed);
    while (!launch) pthread_cond_wait(&launch_changed, &launch_lock);
    pthread_mutex_unlock(&launch_lock);
    for (size_t seq = 0; seq < TURNS;) {
        payload p = {id, seq};
        int result = zg_actor_send(target, consume, &p, sizeof(p), NULL, 0);
        pthread_mutex_lock(&target->lock);
        assert(target->count <= ZG_ACTOR_CAPACITY && target->bytes <= ZG_ACTOR_BYTE_CAPACITY);
        pthread_mutex_unlock(&target->lock);
        /* Mutation proves that stack payload ownership crosses by copy. */
        p.producer = p.sequence = SIZE_MAX;
        if (result == 0) { accepted[id]++; seq++; }
        else if (result == 2) { full[id]++; sched_yield(); }
        else { assert(result == 1 && race_stop); break; }
    }
    return NULL;
}
static void exercise(void) {
    alarm(30);
    target = zg_actor_registry;
    assert(target && !target->next);
    /* Exclude asynchronous worker initialization and the fixture's first turn. */
    for (;;) {
        pthread_mutex_lock(&target->lock);
        int drained = target->count == 0;
        pthread_mutex_unlock(&target->lock);
        if (drained) break;
        sched_yield();
    }
    size_t before = __atomic_load_n(&measured_allocations, __ATOMIC_RELAXED);
    for (int round = 0; round < 3; round++) {
        ready = launch = 0;
        race_stop = round == 2;
        for (int i = 0; i < PRODUCERS; i++) delivered[i] = accepted[i] = full[i] = 0;
        pthread_t threads[PRODUCERS];
        for (size_t i = 0; i < PRODUCERS; i++) assert(pthread_create(&threads[i], NULL, produce, (void *)i) == 0);
        pthread_mutex_lock(&launch_lock);
        while (ready != PRODUCERS) pthread_cond_wait(&launch_changed, &launch_lock);
        launch = 1;
        pthread_cond_broadcast(&launch_changed);
        pthread_mutex_unlock(&launch_lock);
        if (race_stop) { usleep(1000); zg_actor_stop(target); }
        for (int i = 0; i < PRODUCERS; i++) assert(pthread_join(threads[i], NULL) == 0);
        if (race_stop) zg_actor_join(target);
        else {
            for (;;) {
                pthread_mutex_lock(&target->lock);
                int drained = target->count == 0;
                pthread_mutex_unlock(&target->lock);
                if (drained) break;
                sched_yield();
            }
        }
        size_t total = 0, refusals = 0;
        for (int i = 0; i < PRODUCERS; i++) {
            assert(accepted[i] == delivered[i]);
            if (!race_stop) assert(accepted[i] == TURNS);
            total += accepted[i];
            refusals += full[i];
        }
        pthread_mutex_lock(&target->lock);
        assert(target->count == 0 && target->bytes == 0 && !target->head && !target->tail);
        pthread_mutex_unlock(&target->lock);
        size_t allocations = __atomic_load_n(&measured_allocations, __ATOMIC_RELAXED) - before;
        assert(allocations <= 64); /* Exact bounded mailbox size class. */
        printf("PASS: round %d drained %zu accepted turns; %zu full refusals; mailbox allocations %zu\n", round, total, refusals, allocations);
        if (race_stop) assert(zg_actor_send(target, consume, NULL, 0, NULL, 0) == 1);
    }
    alarm(0);
}
