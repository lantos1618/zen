#!/usr/bin/env python3
"""Force actor join/teardown overlap and reject retired addresses before access."""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
p = argparse.ArgumentParser()
p.add_argument('--zen', type=Path, required=True)
p.add_argument('--std', type=Path, default=ROOT / 'src')
p.add_argument('--sanitizer', choices=['none', 'undefined', 'address', 'thread'], default='undefined')
args = p.parse_args()
PREFIX = r'''
#include <pthread.h>
#include <stdlib.h>
static int probe_unlock(pthread_mutex_t *);
static int probe_wait(pthread_cond_t *, pthread_mutex_t *);
static void probe_free(void *);
#define pthread_mutex_unlock probe_unlock
#define pthread_cond_wait probe_wait
#define free probe_free
'''
HARNESS = r'''
#undef pthread_mutex_unlock
#undef pthread_cond_wait
#undef free
#include <assert.h>
#include <stdint.h>
#include <unistd.h>
#include <sched.h>
static zg_actor *target;
static pthread_mutex_t gate = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t changed = PTHREAD_COND_INITIALIZER;
static pthread_t watched;
static int watching, parked, resume_join, shutdown_waiting, freed, delivered;
static int probe_unlock(pthread_mutex_t *lock) {
    int pause = __atomic_load_n(&watching, __ATOMIC_ACQUIRE) && lock == &target->lock && pthread_equal(pthread_self(), watched)
        && target->joined;
    int result = pthread_mutex_unlock(lock);
    if (pause) {
        pthread_mutex_lock(&gate);
        parked = 1;
        pthread_cond_broadcast(&changed);
        while (!resume_join) pthread_cond_wait(&changed, &gate);
        parked = 0;
        pthread_mutex_unlock(&gate);
    }
    return result;
}
static int probe_wait(pthread_cond_t *condition, pthread_mutex_t *lock) {
    if (condition == &zg_actor_registry_idle && zg_actor_borrowers) {
        pthread_mutex_lock(&gate);
        shutdown_waiting = 1;
        pthread_cond_broadcast(&changed);
        pthread_mutex_unlock(&gate);
    }
    return pthread_cond_wait(condition, lock);
}
static void probe_free(void *p) {
    if (p == target) {
        pthread_mutex_lock(&gate);
        assert(!parked && "teardown freed a record while join still accesses it");
        assert(!freed && "actor record freed twice");
        freed = 1;
        pthread_mutex_unlock(&gate);
    }
    free(p);
}
static void *take_block(void *storage, size_t bytes) { (void)storage; return malloc(bytes); }
static void give_block(void *storage, void *block) { (void)storage; free(block); }
static void turn(zg_actor *actor, void *data) {
    (void)actor;
    assert((uintptr_t)data % 16 == 0 && "mailbox payload alignment");
    assert(*(long double *)data == 3.0L);
    delivered++;
}
static void *joiner(void *unused) {
    (void)unused;
    watched = pthread_self();
    __atomic_store_n(&watching, 1, __ATOMIC_RELEASE);
    zg_actor_join(target);
    return NULL;
}
static void *shutdown_caller(void *unused) { (void)unused; zg_actor_shutdown(); return NULL; }
int main(void) {
    alarm(15);
    target = calloc(1, sizeof(*target));
    assert(target);
    target->take = take_block;
    target->give = give_block;
    assert(zg_actor_start(target) == 0);
    long double value = 3.0L;
    assert(zg_actor_send(target, turn, &value, sizeof(value), NULL, 0) == 0);
    zg_actor_stop(target);
    pthread_t join_thread, shutdown_threads[2];
    assert(pthread_create(&join_thread, NULL, joiner, NULL) == 0);
    pthread_mutex_lock(&gate);
    while (!parked) pthread_cond_wait(&changed, &gate);
    pthread_mutex_unlock(&gate);
    for (int i = 0; i < 2; i++) assert(pthread_create(&shutdown_threads[i], NULL, shutdown_caller, NULL) == 0);
    pthread_mutex_lock(&gate);
    while (!shutdown_waiting) pthread_cond_wait(&changed, &gate);
    assert(!freed);
    resume_join = 1;
    pthread_cond_broadcast(&changed);
    pthread_mutex_unlock(&gate);
    assert(pthread_join(join_thread, NULL) == 0);
    for (int i = 0; i < 2; i++) assert(pthread_join(shutdown_threads[i], NULL) == 0);
    assert(freed && delivered == 1 && !zg_actor_registry && !zg_actor_pending && !zg_actor_borrowers);
    for (int i = 0; i < 1000; i++) {
        assert(zg_actor_send(target, turn, &value, sizeof(value), NULL, 0) == 1);
        zg_actor_stop(target);
        zg_actor_join(target);
    }
    zg_actor_shutdown();
    puts("PASS: join pin, concurrent/idempotent shutdown, retired addresses and aligned payload");
    return 0;
}
'''
with tempfile.TemporaryDirectory(prefix='zen-actor-shutdown-') as folder:
    work = Path(folder)
    (work / 'main.zen').write_text((ROOT / 'tests/corpus/actor/dynamic_str_is_copied.zen').read_text())
    emitted = work / 'generated.c'
    subprocess.run([str(args.zen.resolve()), 'build', str(work), '--emit-c', '-o', str(emitted)],
                   env=dict(os.environ, ZEN_STD=str(args.std.resolve())), check=True, timeout=120)
    source = PREFIX + emitted.read_text().replace('int main(', 'int zen_original_main(') + HARNESS
    flags = [] if args.sanitizer == 'none' else ['-fsanitize=' + args.sanitizer, '-fno-sanitize-recover=all']
    controls = [('generated', source, False)]
    wait = '    while (zg_actor_borrowers) pthread_cond_wait(&zg_actor_registry_idle, &zg_actor_registry_lock);'
    assert wait in source
    controls.append(('no-pin-wait-control', source.replace(wait, '', 1), True))
    aligned = 'm->turn(a, m->data);'
    assert aligned in source
    controls.append(('misaligned-control', source.replace(aligned, 'm->turn(a, m->data + 1);', 1), True))
    for name, text, broken in controls:
        path = work / (name + '.c')
        binary = work / name
        path.write_text(text)
        subprocess.run(['clang', '-std=c11', '-O1', '-g', '-pthread', '-Wno-parentheses-equality',
                        *flags, str(path), '-o', str(binary)], check=True, timeout=90)
        result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=20)
        if broken:
            assert result.returncode != 0, name + ': broken control passed'
            assert 'teardown freed' in result.stderr or 'mailbox payload alignment' in result.stderr or 'misaligned address' in result.stderr, (name, result.returncode, result.stderr)
            print('PASS:', name, 'detected', flush=True)
        else:
            assert result.returncode == 0, (name, result.returncode, result.stdout, result.stderr)
            print(result.stdout, end='', flush=True)
