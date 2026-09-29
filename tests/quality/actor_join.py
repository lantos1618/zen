#!/usr/bin/env python3
"""Exercise actual emitted actor lifecycle code, including failing controls."""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser()
parser.add_argument('--zen', type=Path, required=True)
parser.add_argument('--expect-baseline-failure', action='store_true')
parser.add_argument('--std', type=Path, default=ROOT / 'src')
args = parser.parse_args()

PREFIX = r'''
#include <pthread.h>
#include <assert.h>
#include <unistd.h>
#include <errno.h>
static int join_calls, join_waiters, fail_join;
static pthread_cond_t *watched_condition;
static int probe_join(pthread_t thread, void **result) {
    assert(!pthread_equal(thread, pthread_self()) && "self-join must not call pthread_join");
    if (__atomic_exchange_n(&fail_join, 0, __ATOMIC_SEQ_CST)) return EINVAL;
    assert(__atomic_add_fetch(&join_calls, 1, __ATOMIC_SEQ_CST) == 1 && "concurrent pthread_join calls");
    return pthread_join(thread, result);
}
static int probe_wait(pthread_cond_t *condition, pthread_mutex_t *lock) {
    if (condition == watched_condition)
        __atomic_add_fetch(&join_waiters, 1, __ATOMIC_SEQ_CST);
    return pthread_cond_wait(condition, lock);
}
#define pthread_join probe_join
#define pthread_cond_wait probe_wait
'''
HARNESS = r'''
#undef pthread_join
#undef pthread_cond_wait
static pthread_mutex_t gate = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t changed = PTHREAD_COND_INITIALIZER;
static int entered, released, ready, launch, self_returned;
static void *test_take(void *storage, size_t bytes) { (void)storage; return malloc(bytes); }
static void test_give(void *storage, void *value) { (void)storage; free(value); }
static zg_actor *new_actor(void) {
    zg_actor *a = calloc(1, sizeof(*a));
    assert(a);
    STORAGE_CALLBACKS
    assert(zg_actor_start(a) == 0);
    return a;
}
static void self_turn(zg_actor *a, void *data) {
    (void)data;
    zg_actor_join(a);
    pthread_mutex_lock(&a->lock);
    assert(!a->joined);
    pthread_mutex_unlock(&a->lock);
    pthread_mutex_lock(&gate);
    self_returned = 1;
    pthread_cond_broadcast(&changed);
    pthread_mutex_unlock(&gate);
}
static void blocked(zg_actor *a, void *data) {
    (void)a; (void)data;
    pthread_mutex_lock(&gate);
    entered = 1;
    pthread_cond_broadcast(&changed);
    while (!released) pthread_cond_wait(&changed, &gate);
    pthread_mutex_unlock(&gate);
}
static void *joiner(void *raw) {
    pthread_mutex_lock(&gate);
    ready++;
    pthread_cond_broadcast(&changed);
    while (!launch) pthread_cond_wait(&changed, &gate);
    pthread_mutex_unlock(&gate);
    zg_actor_join(raw);
    return NULL;
}
int main(int argc, char **argv) {
    alarm(10);
    assert(argc == 2);
    if (argv[1][0] == 'f') {
        zg_actor *a = new_actor();
        assert(zg_actor_send(a, blocked, NULL, 0, NULL, 0) == 0);
        pthread_mutex_lock(&gate);
        while (!entered) pthread_cond_wait(&changed, &gate);
        pthread_mutex_unlock(&gate);
        zg_actor_stop(a);
        fail_join = 1;
        zg_actor_join(a);
        pthread_mutex_lock(&a->lock);
        assert(!a->joined && join_calls == 0);
        JOIN_OWNER_CHECK
        pthread_mutex_unlock(&a->lock);
        pthread_mutex_lock(&gate);
        released = 1;
        pthread_cond_broadcast(&changed);
        pthread_mutex_unlock(&gate);
        zg_actor_join(a);
        assert(a->joined && join_calls == 1);
    } else if (argv[1][0] == 's') {
        zg_actor *a = new_actor();
        assert(zg_actor_send(a, self_turn, NULL, 0, NULL, 0) == 0);
        pthread_mutex_lock(&gate);
        while (!self_returned) pthread_cond_wait(&changed, &gate);
        pthread_mutex_unlock(&gate);
        assert(join_calls == 0);
        zg_actor_stop(a);
        zg_actor_join(a);
        assert(a->joined && join_calls == 1);
        zg_actor_join(a);
        assert(join_calls == 1);
    } else {
        for (int round = 0; round < 16; round++) {
            entered = released = ready = launch = 0;
            __atomic_store_n(&join_calls, 0, __ATOMIC_SEQ_CST);
            __atomic_store_n(&join_waiters, 0, __ATOMIC_SEQ_CST);
            zg_actor *a = new_actor();
            WATCH_CONDITION
            if (argv[1][0] != 'i') {
                assert(zg_actor_send(a, blocked, NULL, 0, NULL, 0) == 0);
                pthread_mutex_lock(&gate);
                while (!entered) pthread_cond_wait(&changed, &gate);
                pthread_mutex_unlock(&gate);
            }
            pthread_t callers[8];
            for (int i = 0; i < 8; i++)
                assert(pthread_create(&callers[i], NULL, joiner, a) == 0);
            pthread_mutex_lock(&gate);
            while (ready != 8) pthread_cond_wait(&changed, &gate);
            launch = 1;
            pthread_cond_broadcast(&changed);
            pthread_mutex_unlock(&gate);
            // Prove all seven non-owning callers actually waited before release.
            for (int i = 0; i < 2000 && __atomic_load_n(&join_waiters, __ATOMIC_SEQ_CST) < 7; i++)
                usleep(1000);
            assert(__atomic_load_n(&join_waiters, __ATOMIC_SEQ_CST) >= 7);
            zg_actor_stop(a);
            pthread_mutex_lock(&gate);
            released = 1;
            pthread_cond_broadcast(&changed);
            pthread_mutex_unlock(&gate);
            for (int i = 0; i < 8; i++) assert(pthread_join(callers[i], NULL) == 0);
            assert(a->joined && a->count == 0 && join_calls == 1);
            zg_actor_join(a);
            assert(join_calls == 1);
        }
    }
    zg_actor_shutdown();
    puts("PASS: actor join lifecycle");
    return 0;
}
'''
OLD_JOIN = '''static void zg_actor_join(zg_actor *a) {
    if (!a || a->joined) return;
    pthread_join(a->thread, NULL);
    a->joined = 1;
}
'''
with tempfile.TemporaryDirectory(prefix='zen-actor-join-') as folder:
    work = Path(folder)
    (work / 'main.zen').write_text((ROOT / 'tests/corpus/actor/dynamic_str_is_copied.zen').read_text())
    subprocess.run([str(args.zen.resolve()), 'build', str(work), '--emit-c', '-o', str(work / 'generated.c')],
                   env=dict(os.environ, ZEN_STD=str(args.std.resolve())), check=True, timeout=120)
    generated = (work / 'generated.c').read_text().replace('int main(', 'int zen_original_main(')
    watch = 'watched_condition = &a->joined_wake;' if 'pthread_cond_t joined_wake;' in generated else 'watched_condition = NULL;'
    owner_check = 'assert(!a->joining);' if 'int joining;' in generated else ''
    callbacks = 'a->storage = NULL; a->take = test_take; a->give = test_give;' if 'void *(*take)(void' in generated else ''
    source = PREFIX + generated + HARNESS.replace('WATCH_CONDITION', watch).replace('JOIN_OWNER_CHECK', owner_check).replace('STORAGE_CALLBACKS', callbacks)

    def compile_run(name, text, expect_failure):
        src, binary = work / f'{name}.c', work / name
        src.write_text(text)
        subprocess.run(['clang', '-O2', '-pthread', '-Werror=parentheses-equality', str(src), '-o', str(binary)],
                       check=True, timeout=90)
        for mode in ('self', 'concurrent', 'idle', 'failure'):
            result = subprocess.run([str(binary), mode], capture_output=True, text=True, timeout=15)
            if expect_failure:
                assert result.returncode != 0, f'{name}/{mode}: negative control unexpectedly passed'
            else:
                assert result.returncode == 0, f'{name}/{mode}: {result.stdout}\n{result.stderr}'
            print(f'PASS: {name}/{mode} ' + ('detected broken lifecycle' if expect_failure else 'lifecycle'))

    compile_run('generated', source, args.expect_baseline_failure)
    if not args.expect_baseline_failure:
        start = source.index('static void zg_actor_join(zg_actor *a) {')
        end = source.index('static void zg_actor_shutdown(void)', start)
        broken = source[:start] + OLD_JOIN + source[end:]
        compile_run('old-join-control', broken, True)
