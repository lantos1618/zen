#!/usr/bin/env python3
"""Fault-inject generated actor ABI: no copied C runtime implementation here."""
import argparse, os, subprocess, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
p=argparse.ArgumentParser();p.add_argument('--zen',type=Path,required=True);p.add_argument('--std',type=Path,default=ROOT/'src');args=p.parse_args()
with tempfile.TemporaryDirectory(prefix='zen-actor-budget-') as folder:
    work=Path(folder)
    (work/'main.zen').write_text((ROOT/'tests/corpus/actor/dynamic_str_is_copied.zen').read_text())
    subprocess.run([str(args.zen.resolve()),'build',str(work),'--emit-c','-o',str(work/'generated.c')],env=dict(os.environ,ZEN_STD=str(args.std.resolve())),check=True,timeout=120)
    source=(work/'generated.c').read_text()
    # Instrument only allocator calls. Huge synthetic slices must be rejected
    # before either allocating or reading their intentionally invalid pointers.
    prefix='''#include <stdlib.h>
#include <pthread.h>
#include <unistd.h>
static int idle_waits;
static pthread_cond_t *watched_idle;
static int probe_wait(pthread_cond_t *condition, pthread_mutex_t *lock) { if(condition == watched_idle) __atomic_add_fetch(&idle_waits,1,__ATOMIC_RELAXED); return pthread_cond_wait(condition,lock); }
#define pthread_cond_wait probe_wait
static int wake_signals;
static int probe_signal(pthread_cond_t *condition) { __atomic_add_fetch(&wake_signals,1,__ATOMIC_RELAXED); return pthread_cond_signal(condition); }
#define pthread_cond_signal probe_signal
static int denied, allocations;
static void *probe_malloc(size_t n) { __atomic_add_fetch(&allocations,1,__ATOMIC_RELAXED); return denied ? NULL : malloc(n); }
#define malloc probe_malloc
'''
    source=source.replace('int main(', 'int zen_original_main(')
    harness=r'''
#include <assert.h>
/* Deliberate native test allocator: isolate admission/failure semantics from
   the separately executed typed Zen cache policy. No runtime fallback. */
static void *test_take(void *storage, size_t n) {
    (void)storage; return malloc(n + ZG_ACTOR_STORAGE_OVERHEAD);
}
static void test_give(void *storage, void *block) { (void)storage; free(block); }
static void test_storage(zg_actor *a) { a->storage=NULL; a->take=test_take; a->give=test_give; }
#define CHARGE (sizeof(zg_actor_msg) + ZG_ACTOR_STORAGE_OVERHEAD)
static pthread_mutex_t gate = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t changed = PTHREAD_COND_INITIALIZER;
static int entered, released, turns;
static void blocked(zg_actor *a, void *data) {
    (void)a; (void)data; pthread_mutex_lock(&gate); entered=1; pthread_cond_signal(&changed);
    while(!released) pthread_cond_wait(&changed,&gate);
    turns++; pthread_mutex_unlock(&gate);
}
static void noop(zg_actor *a, void *data) { (void)a;(void)data; }
static int idle_turns;
static void idle_turn(zg_actor *a, void *data) { (void)a;(void)data; __atomic_add_fetch(&idle_turns,1,__ATOMIC_RELAXED); }
static void *producer(void *raw) {
    zg_actor *a=raw;
    for(int i=0;i<32;i++) { int result=zg_actor_send(a,noop,NULL,0,NULL,0); assert(result==0 || result==2); }
    return NULL;
}
int main(void) {
    zg_actor a={0}; test_storage(&a); pthread_mutex_init(&a.lock,NULL); a.open=1;
    zg_actor_slice huge={0,0,(const unsigned char*)1,SIZE_MAX};
    int before=allocations;
    assert(zg_actor_send(&a,noop,NULL,0,&huge,1)==2);
    assert(zg_actor_send(&a,noop,(void*)1,SIZE_MAX,NULL,0)==2);
    assert(allocations==before && a.count==0 && a.bytes==0);
    a.open=0; assert(zg_actor_send(&a,noop,NULL,0,NULL,0)==1);
    a.open=1; a.count=ZG_ACTOR_CAPACITY;
    assert(zg_actor_send(&a,noop,NULL,0,NULL,0)==2);
    a.count=0; a.bytes=ZG_ACTOR_BYTE_CAPACITY;
    assert(zg_actor_send(&a,noop,NULL,0,NULL,0)==2);
    assert(allocations==before);
    a.bytes=0; denied=1;
    assert(zg_actor_send(&a,noop,NULL,0,NULL,0)==2);
    assert(a.count==0 && a.bytes==0); denied=0;
    pthread_mutex_destroy(&a.lock);
    zg_actor *live=calloc(1,sizeof(*live)); test_storage(live); assert(zg_actor_start(live)==0);
    assert(zg_actor_send(live,blocked,NULL,0,NULL,0)==0);
    pthread_mutex_lock(&gate); while(!entered)pthread_cond_wait(&changed,&gate); pthread_mutex_unlock(&gate);
    pthread_mutex_lock(&live->lock);
    assert(live->count==1 && live->bytes==CHARGE);
    pthread_mutex_unlock(&live->lock);
    int signals_before = wake_signals;
    pthread_t producers[4];
    for(int i=0;i<4;i++)assert(pthread_create(&producers[i],NULL,producer,live)==0);
    for(int i=0;i<4;i++)assert(pthread_join(producers[i],NULL)==0);
    pthread_mutex_lock(&live->lock);
    assert(live->count==ZG_ACTOR_CAPACITY && live->bytes==ZG_ACTOR_CAPACITY*CHARGE);
    pthread_mutex_unlock(&live->lock);
    assert(wake_signals - signals_before == 1);
    before=allocations;
    assert(zg_actor_send(live,noop,NULL,0,NULL,0)==2 && allocations==before);
    zg_actor_stop(live);
    assert(zg_actor_send(live,noop,NULL,0,NULL,0)==1 && allocations==before);
    pthread_mutex_lock(&gate);released=1;pthread_cond_signal(&changed);pthread_mutex_unlock(&gate);
    zg_actor_join(live);
    assert(turns==1 && live->count==0 && live->bytes==0);
    /* Exercise the byte cap with real copied allocations, independently of
       the 64-message cap. The first blocked turn remains charged. */
    entered=0;released=0;
    zg_actor *bulk=calloc(1,sizeof(*bulk)); test_storage(bulk); assert(zg_actor_start(bulk)==0);
    assert(zg_actor_send(bulk,blocked,NULL,0,NULL,0)==0);
    pthread_mutex_lock(&gate);while(!entered)pthread_cond_wait(&changed,&gate);pthread_mutex_unlock(&gate);
    size_t payload_size=1024*1024;
    void *payload=calloc(1,payload_size); assert(payload);
    size_t accepted=0;
    while(accepted<ZG_ACTOR_CAPACITY) {
        int result=zg_actor_send(bulk,noop,payload,payload_size,NULL,0);
        if(result==2)break;
        assert(result==0);accepted++;
    }
    assert(accepted==(ZG_ACTOR_BYTE_CAPACITY-CHARGE)/(payload_size+CHARGE));
    assert(accepted+1<ZG_ACTOR_CAPACITY);
    pthread_mutex_lock(&bulk->lock);
    assert(bulk->bytes==CHARGE+accepted*(payload_size+CHARGE));
    pthread_mutex_unlock(&bulk->lock);
    before=allocations;
    assert(zg_actor_send(bulk,noop,payload,payload_size,NULL,0)==2 && allocations==before);
    free(payload);zg_actor_stop(bulk);
    pthread_mutex_lock(&gate);released=1;pthread_cond_signal(&changed);pthread_mutex_unlock(&gate);
    zg_actor_join(bulk);assert(bulk->bytes==0 && bulk->count==0);
    zg_actor *idle=calloc(1,sizeof(*idle)); test_storage(idle);
    watched_idle=&idle->wake; assert(zg_actor_start(idle)==0);
    for(int i=0;i<128;i++) {
        for(int spin=0;spin<2000 && __atomic_load_n(&idle_waits,__ATOMIC_RELAXED)<=i;spin++) usleep(1000);
        assert(__atomic_load_n(&idle_waits,__ATOMIC_RELAXED)>i);
        assert(zg_actor_send(idle,idle_turn,NULL,0,NULL,0)==0);
    }
    zg_actor_stop(idle);zg_actor_join(idle);
    assert(idle_turns==128);
    zg_actor_shutdown();
    puts("PASS: overflow, count/byte limits, allocation failure, active charge, concurrent producers, stop/drain and no allocation on rejection");
    return 0;
}
'''
    (work/'probe.c').write_text(prefix+source+harness)
    subprocess.run(['clang','-O2','-pthread','-Werror=parentheses-equality',str(work/'probe.c'),'-o',str(work/'probe')],check=True,timeout=90)
    subprocess.run([str(work/'probe')],check=True,timeout=20)

    # Negative control: prove rejected-send allocation checks detect regressions.
    probe=(work/'probe.c').read_text()
    signature='static int zg_actor_send(zg_actor *a, zg_actor_turn turn, const void *data, size_t size, const zg_actor_slice *slices, size_t slice_count) {'
    assert signature in probe
    (work/'negative.c').write_text(probe.replace(signature, signature + '\n void *unexpected=malloc(1); free(unexpected);',1))
    subprocess.run(['clang','-O2','-pthread','-Werror=parentheses-equality',str(work/'negative.c'),'-o',str(work/'negative')],check=True,timeout=90)
    control=subprocess.run([str(work/'negative')],capture_output=True,timeout=20)
    assert control.returncode != 0, 'Negative allocation control unexpectedly passed'
    print('PASS: rejected-send allocation negative control')

    # Restoring per-message notifications must fail the queue-transition check.
    transition = 'if (was_empty) pthread_cond_signal(&a->wake);'
    assert transition in probe
    (work/'wake-negative.c').write_text(probe.replace(transition, 'pthread_cond_signal(&a->wake);',1))
    subprocess.run(['clang','-O2','-pthread','-Werror=parentheses-equality',str(work/'wake-negative.c'),'-o',str(work/'wake-negative')],check=True,timeout=90)
    control=subprocess.run([str(work/'wake-negative')],capture_output=True,timeout=20)
    assert control.returncode != 0, 'Redundant-wakeup control unexpectedly passed'
    print('PASS: one wake signal for 63 queued messages; redundant-wakeup control detected')
