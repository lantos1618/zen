#!/usr/bin/env python3
"""Execute native integer bytes independently on x86-64 and AArch64."""
import argparse
from pathlib import Path
import platform
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
TYPES = [(bits, signed) for bits in (8, 16, 32, 64) for signed in (True, False)]
MASK = (1 << 64) - 1
PAIRS = [(0, 0), (1, 2), (-1, 1), (-128, 127), (127, 1), (255, 1),
         (-32768, -1), (32767, 1), (65535, 65536), (2**31-1, 1),
         (-2**31, -1), (2**32-1, 2), (-2**63, -1), (2**63-1, 1),
         (2**64-1, 1), (17, 5)]


def run(argv, cwd, timeout=120):
    proc = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    if proc.returncode:
        raise RuntimeError(f"{argv!r}: {proc.returncode}\n{proc.stdout}{proc.stderr}")
    return proc.stdout


def narrow(value, bits, signed):
    value &= (1 << bits) - 1
    return value - (1 << bits) if signed and value >= 1 << (bits - 1) else value


def cases():
    result = []
    for kind, (bits, signed) in enumerate(TYPES):
        low, high = (-(1 << (bits-1)), (1 << (bits-1))-1) if signed else (0, (1 << bits)-1)
        for op in range(14):
            for left, right in PAIRS:
                a, b = narrow(left, bits, signed), narrow(right, bits, signed)
                values = [a+b, a-b, a+b, a-b, a*b, a & b, a | b, a ^ b,
                          a == b, a != b, a < b, a <= b, a > b, a >= b]
                value = int(values[op])
                refused = op < 2 and not low <= value <= high
                if op < 8:
                    value = narrow(value, bits, signed)
                result.append((kind*14+op, a & MASK, b & MASK, value & MASK, int(refused)))
    for origin, (bits, signed) in enumerate(TYPES):
        for dest, (into_bits, into_signed) in enumerate(TYPES):
            for value, _ in PAIRS:
                source = narrow(value, bits, signed)
                result.append((112+origin*8+dest, source & MASK, 0,
                               narrow(source, into_bits, into_signed) & MASK, 0))
    result += [(176, 24, 0, 46368, 0), (177, 64, 0, 0, 0), (177, 256, 0, 0, 1)]
    for kind, (bits, signed) in enumerate(TYPES):
        for op in range(2):
            for left, _ in PAIRS:
                for count in (0, 1, bits-1, bits, bits+1, 63, 64, 255, 2**64-1):
                    a = narrow(left, bits, False)
                    value = (a << count if op == 0 else a >> count) if count < bits else 0
                    result.append((188+kind*2+op, narrow(left,bits,signed)&MASK, count,
                                   narrow(value,bits,signed)&MASK,0))
    for kind, bits in enumerate((32,64)):
        for left, _ in PAIRS:
            for count in (0,1,bits-1,bits,bits+1,255,2**64-1):
                a, n = narrow(left,bits,False), count % bits
                value = a if n == 0 else (a >> n) | (a << (bits-n))
                result.append((204+kind,a,count,narrow(value,bits,False),0))
    for kind, (bits,signed) in enumerate(TYPES):
        for left,_ in PAIRS:
            a=narrow(left,bits,signed)
            result.append((206+kind,a&MASK,0,int(a!=0),0))
    for kind, (bits,signed) in enumerate(TYPES):
        low,high = (-(1 << (bits-1)), (1 << (bits-1))-1) if signed else (0,(1 << bits)-1)
        for op in range(3):
            for left,right in PAIRS + [(low,-1),(low,0),(high,high),(low,low)]:
                a,b=narrow(left,bits,signed),narrow(right,bits,signed)
                value=0
                refused=False
                if op==0:
                    value=a*b
                    refused=not low<=value<=high
                else:
                    refused=b==0 or (signed and a==low and b==-1)
                    if not refused:
                        quotient=(abs(a)//abs(b)) * (-1 if (a<0)!=(b<0) else 1)
                        value=quotient if op==1 else a-quotient*b
                result.append((216+kind*3+op,a&MASK,b&MASK,value&MASK,int(refused)))
    result += [(240,17,23,115,0), (241,17,23,98,0), (242,17,23,17,0)]
    result += [(244,n,0,n%251,0) for n in (0,1,4095,4096,4097,8191)]
    for kind,bits in enumerate((8,16,32,64)):
        for left,_ in PAIRS:
            a=narrow(left,bits,True)
            refused=a==-(1 << (bits-1))
            result.append((245+kind,a&MASK,0,(-a)&MASK,int(refused)))
    result += [(249,0,0,1,0),(249,1,0,0,0)]
    return result


HARNESS = r'''
#define _GNU_SOURCE
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/mman.h>
#ifdef __APPLE__
#include <pthread.h>
#include <libkern/OSCacheControl.h>
#endif
static const unsigned char code[] = {BYTES};
static const size_t entries[] = {ENTRIES};
struct test { size_t fn; uint64_t a,b,want; int refused; };
static const struct test tests[] = {CASES};
int main(void) {
#ifdef __APPLE__
    void *image=mmap(0,sizeof(code),PROT_READ|PROT_WRITE|PROT_EXEC,MAP_PRIVATE|MAP_ANONYMOUS|MAP_JIT,-1,0);
    if (image==MAP_FAILED) return 2;
    pthread_jit_write_protect_np(0);
    memcpy(image,code,sizeof(code));
    pthread_jit_write_protect_np(1);
    sys_icache_invalidate(image,sizeof(code));
#else
    void *image=mmap(0,sizeof(code),PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);
    if (image==MAP_FAILED) return 2;
    memcpy(image,code,sizeof(code));
    if (mprotect(image,sizeof(code),PROT_READ|PROT_EXEC)) return 3;
    __builtin___clear_cache(image,(char*)image+sizeof(code));
#endif
    if (entries[178] != 0 || entries[214] != 0 || entries[215] != 0) return 4;
    for (size_t i=0; i<sizeof(tests)/sizeof(tests[0]); ++i) {
        struct test t=tests[i];
        if (!entries[t.fn]) return 5;
        uint64_t args[16]={t.a,t.b,91,92,93,94,95,96,97,98,99,100,101,102,103,104}, copy[16], out[3]={0};
        memcpy(copy,args,sizeof(args));
#if defined(__aarch64__)
        register uint64_t guard1 asm("x19")=1234567, guard2 asm("x20")=9876543;
#else
        register uint64_t guard1 asm("r12")=1234567, guard2 asm("r13")=9876543;
#endif
        asm volatile("" : "+r"(guard1), "+r"(guard2));
        ((void (*)(uint64_t*,uint64_t*))((char*)image+entries[t.fn]-1))(args,out);
        asm volatile("" : "+r"(guard1), "+r"(guard2));
        if ((out[1] != 0) != t.refused || (!t.refused && out[0] != t.want) || out[2] ||
            memcmp(copy,args,sizeof(args)) || guard1!=1234567 || guard2!=9876543) {
            fprintf(stderr,"case %zu fn %zu (%llu,%llu): got %llu refuse %llu depth %llu; want %llu refuse %d\n",
              i,t.fn,(unsigned long long)t.a,(unsigned long long)t.b,(unsigned long long)out[0],
              (unsigned long long)out[1],(unsigned long long)out[2],(unsigned long long)t.want,t.refused);
            return 1;
        }
    }
    for (size_t kind=0; kind<8; ++kind) {
        unsigned char memory[24], expected[24];
        memset(memory,0x81,sizeof(memory)); memcpy(expected,memory,sizeof(memory));
        size_t size=(size_t)1 << (kind/2);
        uint64_t value=UINT64_C(0xfedcba9876543210), old=0;
        memcpy(&old,memory+3,size);
        if (!(kind&1) && size<8 && ((old>>(size*8-1))&1)) old |= UINT64_MAX << (size*8);
        memcpy(expected+3,&value,size);
        uint64_t args[4]={(uintptr_t)memory,value,0,0}, state[3]={0};
        ((void (*)(uint64_t*,uint64_t*))((char*)image+entries[179+kind]-1))(args,state);
        if(state[0]!=old || state[1] || state[2] || memcmp(memory,expected,sizeof(memory))) return 7;
    }
    for (int attempt=0; attempt<2; ++attempt) {
        unsigned char memory[24]={0};
        uint64_t args[4]={(uintptr_t)memory,INT64_MAX,0,0}, state[3]={0}, stored;
        ((void (*)(uint64_t*,uint64_t*))((char*)image+entries[attempt ? 243 : 187]-1))(args,state);
        memcpy(&stored,memory+3,8);
        if(!state[1] || state[2] || stored!=INT64_MAX) return 8;
    }
    if (munmap(image,sizeof(code))) return 6;
    printf("%zu cases passed\n",sizeof(tests)/sizeof(tests[0]));
    return 0;
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--zen', default=str(ROOT/'zen'))
    parser.add_argument('--target', choices=('host', 'x86', 'arm', 'all'), default='host')
    args = parser.parse_args()
    host_arm = platform.machine() in ('aarch64', 'arm64')
    targets = ['arm' if host_arm else 'x86'] if args.target == 'host' else (
        ['x86', 'arm'] if args.target == 'all' else [args.target])
    tests = cases()
    with tempfile.TemporaryDirectory(prefix='zen-jit-native-') as directory:
        work = Path(directory)
        shutil.copy(ROOT/'tests/quality/fixtures/jit_native/main.zen', work/'main.zen')
        for package in ('gen', 'sema', 'zen', 'lsp', 'fmt'):
            (work/package).symlink_to(ROOT/'src'/package, target_is_directory=True)
        generated = work/'fixture.c'
        run([str(Path(args.zen).resolve()), 'build', str(work), '--entry', 'main.zen',
             '--std', str(ROOT/'src'), '--backend', 'c', '-o', str(generated)], work)
        run(['cc', '-O2', '-std=c99', str(generated), '-o', str(work/'fixture'), '-ldl']
            if platform.system() != 'Darwin' else
            ['cc', '-O2', '-std=c99', str(generated), '-o', str(work/'fixture')], work)
        publish = 'publish-darwin' if platform.system() == 'Darwin' else ('publish-arm' if host_arm else 'publish-x86')
        actual = run([str(work/'fixture'), publish], work)
        if actual != 'published true result 42 preserved true\n':
            raise RuntimeError(f'native publication failed: {actual!r}')
        if platform.system() == 'Linux':
            fail = work/'deny-execute.c'
            fail.write_text(r"""
#include <errno.h>
#include <linux/filter.h>
#include <linux/seccomp.h>
#include <stddef.h>
#include <sys/mman.h>
#include <sys/prctl.h>
#include <sys/syscall.h>
#include <unistd.h>
int main(int argc, char **argv) {
    struct sock_filter rules[] = {
        BPF_STMT(BPF_LD|BPF_W|BPF_ABS, offsetof(struct seccomp_data,nr)),
        BPF_JUMP(BPF_JMP|BPF_JEQ|BPF_K, SYS_mprotect,0,3),
        BPF_STMT(BPF_LD|BPF_W|BPF_ABS, offsetof(struct seccomp_data,args[2])),
        BPF_JUMP(BPF_JMP|BPF_JSET|BPF_K, PROT_EXEC,0,1),
        BPF_STMT(BPF_RET|BPF_K, SECCOMP_RET_ERRNO|EACCES),
        BPF_STMT(BPF_RET|BPF_K, SECCOMP_RET_ALLOW)
    };
    struct sock_fprog filter={sizeof(rules)/sizeof(rules[0]),rules};
    if(prctl(PR_SET_NO_NEW_PRIVS,1,0,0,0) || prctl(PR_SET_SECCOMP,SECCOMP_MODE_FILTER,&filter)) return 77;
    execv(argv[1],argv+1); return 78;
}
""")
            run(['cc',str(fail),'-o',str(work/'deny-execute')],work)
            denied = run([str(work/'deny-execute'),str(work/'fixture'),publish],work)
            if denied != 'published false result 0 preserved true\n':
                raise RuntimeError('failed executable protection was not refused: '+denied)
            print('host: executable protection failure refused')
        for target in targets:
            output = list(map(int, run([str(work/'fixture'), target], work).split()))
            count, *rest = output
            entries, code = rest[:count], bytes(rest[count:])
            source = HARNESS.replace('BYTES', ','.join(map(str,code))).replace('ENTRIES', ','.join(map(str,entries))).replace('CASES', ','.join(
                '{%d,UINT64_C(%d),UINT64_C(%d),UINT64_C(%d),%d}' % case for case in tests))
            cross = target == 'arm' and not host_arm
            compiler = 'aarch64-linux-gnu-gcc' if cross else 'cc'
            runner = ['qemu-aarch64'] if cross else []
            if target == 'x86' and host_arm:
                raise RuntimeError('x86 cross-execution needs an x86 runner')
            for required in [compiler, *runner]:
                if not shutil.which(required):
                    raise RuntimeError(f'required native test tool unavailable: {required}')
            if cross:
                cross_fixture = work/'fixture-arm'
                run([compiler, '-O2', '-std=c99', str(generated), '-ldl', '-o', str(cross_fixture)], work)
                published = run(['qemu-aarch64', '-L', '/usr/aarch64-linux-gnu', str(cross_fixture), 'publish-arm'], work)
                if published != 'published true result 42 preserved true\n':
                    raise RuntimeError('ARM native publication failed: ' + published)
                print('arm: native publication and cache invalidation passed under QEMU')
            cfile, binary = work/f'{target}.c', work/target
            cfile.write_text(source)
            flags = ['-static'] if cross else []
            run([compiler, '-O2', *flags, str(cfile), '-o', str(binary)], work)
            print(target + ': ' + run([*runner, str(binary)], work).strip())
            # Mutate arithmetic in the compiled body, not its depth accounting.
            before = bytes.fromhex('4801c8') if target == 'x86' else bytes.fromhex('000001ab')
            after = bytes.fromhex('4829c8') if target == 'x86' else bytes.fromhex('000001eb')
            start = entries[0]-1
            stop = entries[1]-1
            position = code.find(before,start,stop)
            if target == 'x86':
                position = code.find(before,position+len(before),stop)
            if position < 0:
                raise RuntimeError('arithmetic negative control found no instruction')
            changed = code[:position]+after+code[position+len(before):]
            cfile.write_text(source.replace(','.join(map(str,code)), ','.join(map(str,changed)),1))
            run([compiler, '-O2', *flags, str(cfile), '-o', str(binary)], work)
            mutant = subprocess.run([*runner,str(binary)],capture_output=True,text=True,timeout=120)
            if mutant.returncode != 1 or 'case ' not in mutant.stderr:
                raise RuntimeError('arithmetic oracle did not reject its mutation: '+mutant.stderr)
            print(target + ': changed-arithmetic control rejected')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
