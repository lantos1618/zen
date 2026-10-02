REV="[15, 14, 13, 12, 11, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1, 0]"
out=[]
w=out.append
w('''
// ---- Hardware path -----------------------------------------------------------
//
// Ported from OpenSSL 3.5.4's perlasm designs (Apache-2.0; see
// docs/THIRD_PARTY.md): ghash-x86_64.pl gcm_init_clmul (the "<<1 twist" of H
// and powers H^2..), clmul64x2_kernel (Karatsuba with H.lo^H.hi) and
// reduction_alg9, aggregated over eight blocks as gcm_ghash_clmul does over
// four; aesni-x86_64.pl / aesv8-armx.pl eight-block CTR interleaving.
// GHASH state is kept byte-reflected (pshufb bswap) as a u64x2 whose lane 1
// holds the high 64 bits. std.simd lowers the instructions to AESENC and
// PCLMULQDQ on x86-64 and AESE/AESMC and PMULL on arm64. Selected at run time
// from the Aes and Clmul capabilities; the constant-time software path above
// remains for CPUs without them.
Wide = { lo: u64x2, mid: u64x2, hi: u64x2 }

reflect = (block: u8x16) u64x2 {
    block.shuffle(REVPAT).cast_u64x2()
}

unreflect = (x: u64x2) u8x16 {
    x.cast_u8x16().shuffle(REVPAT)
}

// clmul64x2_kernel without the fold: accumulate a * h into three parts.
karatsuba = (cpu: Clmul, a: u64x2, h: u64x2, acc: Wide) Wide {
    am = a.bit_xor(a.shuffle([1, 0]));
    hm = h.bit_xor(h.shuffle([1, 0]));
    Wide(
        lo: acc.lo.bit_xor(a.clmul_low(h, cpu)),
        mid: acc.mid.bit_xor(am.clmul_low(hm, cpu)),
        hi: acc.hi.bit_xor(a.clmul_high(h, cpu))
    )
}

zero_wide = () Wide {
    zero = splat_u64x2(0);
    Wide(lo: zero, mid: zero, hi: zero)
}

// Karatsuba fold, then reduction_alg9's two phases.
reduce = (w: Wide) u64x2 {
    zero = splat_u64x2(0);
    mid  = w.mid.bit_xor(w.lo).bit_xor(w.hi);
    x0   = w.lo.bit_xor(mid.shuffle2(zero, [2, 0]));
    xhi  = w.hi.bit_xor(mid.shuffle2(zero, [1, 2]));
    t1   = x0.bit_xor(x0.shift_left(5));
    s    = x0.shift_left(6).bit_xor(t1).shift_left(57);
    x1   = s.shuffle2(zero, [2, 0]).bit_xor(x0);
    hi1  = xhi.bit_xor(s.shuffle2(zero, [1, 2]));
    t2   = x1.bit_xor(x1.shift_right(1));
    x2   = x1.shift_right(6).bit_xor(t2).shift_right(1);
    x2.bit_xor(hi1).bit_xor(x1)
}

// gcm_init_clmul: H<<1 with the 0x1c2 polynomial folded in on carry.
twist = (h: u64x2) u64x2 {
    lo    = h.lane(0);
    hi    = h.lane(1);
    carry = 0 -% hi.shift_right(63);
    lanes_u64x2(
        lo.shift_left(1).bit_xor(carry.bit_and(1)),
        hi.shift_left(1).bit_or(lo.shift_right(63)).bit_xor(carry.bit_and(13979173243358019584))
    )
}

// Eight AES-128 blocks in flight, as aesni_ctr32_encrypt_blocks interleaves.
Blocks8 = { b0: u8x16, b1: u8x16, b2: u8x16, b3: u8x16, b4: u8x16, b5: u8x16, b6: u8x16, b7: u8x16 }
'''.replace('REVPAT', REV))

def rounds():
    s=[]
    s.append("aes8 = (cpu: Aes, keys: Ptr<u8>, x: Blocks8) Blocks8 {")
    s.append("    k0 = load_u8x16(keys, 0);")
    for i in range(8): s.append(f"    b{i} ::= x.b{i}.bit_xor(k0);")
    s.append("    Range(1, 10).loop((r) {")
    s.append("        k = load_u8x16(keys, 16 * r);")
    for i in range(8): s.append(f"        b{i} = b{i}.aes_round(k, cpu);")
    s.append("    });")
    s.append("    k10 = load_u8x16(keys, 160);")
    s.append("    Blocks8(")
    s.append(",\n".join(f"        b{i}: b{i}.aes_round_last(k10, cpu)" for i in range(8)))
    s.append("    )")
    s.append("}")
    return "\n".join(s)
w(rounds())
w('''
aes1 = (cpu: Aes, keys: Ptr<u8>, x: u8x16) u8x16 {
    b ::= x.bit_xor(load_u8x16(keys, 0));
    Range(1, 10).loop((r) { b = b.aes_round(load_u8x16(keys, 16 * r), cpu); });
    b.aes_round_last(load_u8x16(keys, 160), cpu)
}

// Counter block i: nonce || be32(counter + i); `base` holds the nonce.
counter_block = (base: u8x16, counter: u32) u8x16 {
    swapped = counter.shift_left(24).bit_or(counter.shift_left(8).bit_and(16711680))
        .bit_or(counter.shift_right(8).bit_and(65280)).bit_or(counter.shift_right(24));
    base.cast_u32x4().with_lane(3, swapped).cast_u8x16()
}

// Round keys (176 bytes) from the software key schedule, H powers 1..8 as
// reflected u64x2 at `powers`, and the nonce block.
Hardware = { keys: Ptr<u8>, powers: Ptr<u8>, base: u8x16 }

hardware_setup = (aes_cpu: Aes, gh: Clmul, sp: Spans, key: Ptr<u8>, nonce: Ptr<u8>, powers: Ptr<u8>) Hardware {
    aes128_expand_key(key, sp.schedule);
    keys = sp.schedule.to<u8>();
    Range(0, 16).loop((i) { sp.block.write(i, 0); });
    sp.block.copy_from(nonce, 12);
    base = load_u8x16(sp.block, 0);
    h1 = twist(reflect(aes1(aes_cpu, keys, splat_u8x16(0))));
    h1.store(powers, 0);
    hk ::= h1;
    Range(1, 8).loop((i) {
        hk = reduce(karatsuba(gh, hk, h1, zero_wide()));
        hk.store(powers, 16 * i);
    });
    Hardware(keys: keys, powers: powers, base: base)
}

power = (hw: Hardware, k: usize) u64x2 { load_u64x2(hw.powers, 16 * (k - 1)) }

// GHASH over `count` bytes; a final partial block is zero padded.
ghash_hw = (gh: Clmul, hw: Hardware, x: u64x2, data: Ptr<u8>, count: usize, pad: Ptr<u8>) u64x2 {
    y  ::= x;
    at ::= 0;
    (count - at >= 128).loop((h) {
        w ::= karatsuba(gh, y.bit_xor(reflect(load_u8x16(data, at))), power(hw, 8), zero_wide());''')
for i in range(1,8):
    w(f"        w = karatsuba(gh, reflect(load_u8x16(data, at + {16*i})), power(hw, {8-i}), w);")
w('''        y  = reduce(w);
        at = at + 128;
    });
    (count - at >= 16).loop((h) {
        y  = reduce(karatsuba(gh, y.bit_xor(reflect(load_u8x16(data, at))), power(hw, 1), zero_wide()));
        at = at + 16;
    });
    (at < count).then(() {
        Range(0, 16).loop((i) { pad.write(i, 0); });
        pad.copy_from(data.offset(at), count - at);
        y = reduce(karatsuba(gh, y.bit_xor(reflect(load_u8x16(pad, 0))), power(hw, 1), zero_wide()));
    });
    y
}

xor_block = (output: Ptr<u8>, input: Ptr<u8>, at: usize, stream: u8x16) {
    load_u8x16(input, at).bit_xor(stream).store(output, at);
}

// CTR from counter block 2 (J0 + 1), eight blocks at a time.
ctr_hw = (cpu: Aes, hw: Hardware, output: Ptr<u8>, input: Ptr<u8>, count: usize, pad: Ptr<u8>) {
    at :: usize = 0;
    counter :: u32 = 2;
    (count - at >= 128).loop((h) {
        s = aes8(cpu, hw.keys, Blocks8(''')
w(",\n".join(f"            b{i}: counter_block(hw.base, counter +% {i})" for i in range(8)))
w('''        ));''')
for i in range(8):
    w(f"        xor_block(output, input, at + {16*i}, s.b{i});")
w('''        at      = at + 128;
        counter = counter +% 8;
    });
    (at < count).loop((h) {
        stream = aes1(cpu, hw.keys, counter_block(hw.base, counter));
        take   = (count - at).min(16);
        (take == 16).match({
            true  => xor_block(output, input, at, stream),
            false => {
                stream.store(pad, 0);
                Range(0, take).loop((i) { output.write(at + i, input.read(at + i).bit_xor(pad.read(i))); });
            },
        });
        at      = at + take;
        counter = counter +% 1;
    });
}

// Tag = E(K, J0) xor GHASH(aad, ciphertext, bit lengths).
tag_hw = (cpu: Aes, gh: Clmul, hw: Hardware, sp: Spans, ciphertext: Ptr<u8>, count: usize, aad: Ptr<u8>, aad_count: usize) {
    y ::= splat_u64x2(0);
    (aad_count > 0).then(() { y = ghash_hw(gh, hw, y, aad, aad_count, sp.block); });
    (count > 0).then(() { y = ghash_hw(gh, hw, y, ciphertext, count, sp.block); });
    lengths = lanes_u64x2(count.to_u64() *% 8, aad_count.to_u64() *% 8);
    y = reduce(karatsuba(gh, y.bit_xor(lengths), power(hw, 1), zero_wide()));
    mask = aes1(cpu, hw.keys, counter_block(hw.base, 1));
    unreflect(y).bit_xor(mask).store(sp.tag, 0);
}

seal_hw = (cpu: Aes, gh: Clmul, sp: Spans, output: Ptr<u8>, message: Ptr<u8>, count: usize, aad: Ptr<u8>, aad_count: usize, key: Ptr<u8>, nonce: Ptr<u8>, powers: Ptr<u8>) {
    hw = hardware_setup(cpu, gh, sp, key, nonce, powers);
    ctr_hw(cpu, hw, output, message, count, sp.block);
    tag_hw(cpu, gh, hw, sp, output, count, aad, aad_count);
}

// The tag is checked before any plaintext is written.
open_hw = (cpu: Aes, gh: Clmul, sp: Spans, output: Ptr<u8>, ciphertext: Ptr<u8>, count: usize, aad: Ptr<u8>, aad_count: usize, key: Ptr<u8>, nonce: Ptr<u8>, powers: Ptr<u8>) bool {
    hw = hardware_setup(cpu, gh, sp, key, nonce, powers);
    tag_hw(cpu, gh, hw, sp, ciphertext, count, aad, aad_count);
    difference :: u64 = 0;
    Range(0, 16).loop((i) { difference = or64(difference, sp.tag.read(i).to_u64().bit_xor(ciphertext.read(count + i).to_u64())); });
    authentic = difference == 0;
    authentic.then(() { ctr_hw(cpu, hw, output, ciphertext, count, sp.block); });
    authentic
}
''')
print("\n".join(out))
