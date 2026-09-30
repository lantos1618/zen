def gen(L):
    V=f"u64x{L}"; tok = "cpu: Avx2, " if L==4 else ""
    cap = "cpu, " if L==4 else ""
    sfx = f"{L}"
    o=[]
    w=o.append
    lanes="lanes_"+V
    # multiply-reduce: A = A * R (limbs a0..a4 vectors, r0..r4, s1..s4 vectors)
    w(f"""// poly1305_sse2.c-style lanes: {L} blocks per step in radix 2^26, lane j
// holding blocks j, j+{L}, ... with r^{L} per step; the lanes are finally
// multiplied by r^{L}..r^1 and summed. Products use the low 32 bits of each
// 64-bit lane (PMULUDQ/UMULL); every operand is below 2^30.
Lanes{sfx} = {{ a0: {V}, a1: {V}, a2: {V}, a3: {V}, a4: {V} }}

mul32_{sfx} = ({tok}a: {V}, b: {V}) {V} {{ a.mul_low32(b) }}

// A * R, partially reduced: every limb below 2^26 except a1 (< 2^27).
mulr{sfx} = ({tok}x: Lanes{sfx}, r: Lanes{sfx}) Lanes{sfx} {{
    m26 = splat_{V}(67108863);
    s1 = r.a1.mul_wrap(splat_{V}(5)); s2 = r.a2.mul_wrap(splat_{V}(5));
    s3 = r.a3.mul_wrap(splat_{V}(5)); s4 = r.a4.mul_wrap(splat_{V}(5));""")
    rr=['r.a0','r.a1','r.a2','r.a3','r.a4']; ss=[None,'s1','s2','s3','s4']
    for k in range(5):
        terms=[]
        for i in range(5):
            j=k-i
            f = rr[j] if j>=0 else ss[j+5]
            terms.append(f"mul32_{sfx}({cap}x.a{i}, {f})")
        expr=terms[0]
        for t in terms[1:]:
            expr=f"{expr}.add_wrap({t})"
        w(f"    d{k} ::= {expr};")
    w(f"""    c ::= d0.shift_right(26); t0 ::= d0.bit_and(m26);
    d1 = d1.add_wrap(c); c = d1.shift_right(26); t1 = d1.bit_and(m26);
    d2 = d2.add_wrap(c); c = d2.shift_right(26); t2 = d2.bit_and(m26);
    d3 = d3.add_wrap(c); c = d3.shift_right(26); t3 = d3.bit_and(m26);
    d4 = d4.add_wrap(c); c = d4.shift_right(26); t4 = d4.bit_and(m26);
    t0 = t0.add_wrap(c.mul_wrap(splat_{V}(5))); c = t0.shift_right(26); t0 = t0.bit_and(m26);
    Lanes{sfx}(a0: t0, a1: t1.add_wrap(c), a2: t2, a3: t3, a4: t4)
}}
""")
    # message limbs for L consecutive blocks
    if L==4:
        load=f"""    x = load_u64x4(m, offset); y = load_u64x4(m, offset + 32);
    lo = x.shuffle2(y, [0, 2, 4, 6]); hi = x.shuffle2(y, [1, 3, 5, 7]);"""
    else:
        load=f"""    x = load_u64x2(m, offset); y = load_u64x2(m, offset + 16);
    lo = x.shuffle2(y, [0, 2]); hi = x.shuffle2(y, [1, 3]);"""
    w(f"""// Blocks offset .. offset + {16*L} as lanes, with the 2^128 bit.
message{sfx} = ({tok}m: Ptr<u8>, offset: usize) Lanes{sfx} {{
    m26 = splat_{V}(67108863);
{load}
    Lanes{sfx}(
        a0: lo.bit_and(m26),
        a1: lo.shift_right(26).bit_and(m26),
        a2: lo.shift_right(52).bit_or(hi.shift_left(12)).bit_and(m26),
        a3: hi.shift_right(14).bit_and(m26),
        a4: hi.shift_right(40).bit_or(splat_{V}(16777216))
    )
}}

add{sfx} = ({tok}x: Lanes{sfx}, y: Lanes{sfx}) Lanes{sfx} {{
    Lanes{sfx}(a0: x.a0.add_wrap(y.a0), a1: x.a1.add_wrap(y.a1), a2: x.a2.add_wrap(y.a2), a3: x.a3.add_wrap(y.a3), a4: x.a4.add_wrap(y.a4))
}}
""")
    # driver
    splatl = lambda n: f"splat_{V}(r{n}.l{{}})"
    lanes_r = lambda k: "lanes_"+V+"(" + ", ".join(f"q{L-j}.l{k}" for j in range(L)) + ")"
    w(f"""// count is a nonzero multiple of {16*L}.
poly_lanes{sfx} = ({tok}p: Ptr<u64>, m: Ptr<u8>, count: usize) {{
    r1 = limbs26(p.read(0), p.read(1), p.read(2));""")
    for k in range(2, L+1):
        w(f"    r{k}w = mulmod(p, {'r%dw' % (k-1) if k>2 else 'Wide3(w0: p.read(0), w1: p.read(1), w2: p.read(2))'});")
    for k in range(2, L+1):
        w(f"    r{k} = limbs26_carried(r{k}w.w0, r{k}w.w1, r{k}w.w2);")
    w(f"    q1 = r1;")
    # rename for lanes_r convenience
    for k in range(2, L+1): w(f"    q{k} = r{k};")
    w(f"    step = Lanes{sfx}(a0: splat_{V}(r{L}.l0), a1: splat_{V}(r{L}.l1), a2: splat_{V}(r{L}.l2), a3: splat_{V}(r{L}.l3), a4: splat_{V}(r{L}.l4));")
    w(f"    tail = Lanes{sfx}(a0: {lanes_r(0)}, a1: {lanes_r(1)}, a2: {lanes_r(2)}, a3: {lanes_r(3)}, a4: {lanes_r(4)});")
    w(f"""    h = limbs26_carried(p.read(3), p.read(4), p.read(5));
    first = message{sfx}({cap}m, 0);
    acc ::= Lanes{sfx}(
        a0: first.a0.with_lane(0, first.a0.lane(0) +% h.l0),
        a1: first.a1.with_lane(0, first.a1.lane(0) +% h.l1),
        a2: first.a2.with_lane(0, first.a2.lane(0) +% h.l2),
        a3: first.a3.with_lane(0, first.a3.lane(0) +% h.l3),
        a4: first.a4.with_lane(0, first.a4.lane(0) +% h.l4)
    );
    offset: usize ::= {16*L};
    (offset < count).loop((loop) {{
        acc    = add{sfx}({cap}mulr{sfx}({cap}acc, step), message{sfx}({cap}m, offset));
        offset = offset + {16*L};
    }});
    acc = mulr{sfx}({cap}acc, tail);
    store_limbs(p, {" +% ".join(f"acc.a0.lane({j})" for j in range(L))}, {" +% ".join(f"acc.a1.lane({j})" for j in range(L))}, {" +% ".join(f"acc.a2.lane({j})" for j in range(L))}, {" +% ".join(f"acc.a3.lane({j})" for j in range(L))}, {" +% ".join(f"acc.a4.lane({j})" for j in range(L))});
}}
""")
    return "\n".join(o)

common = '''
// ---- Poly1305 lanes support ---------------------------------------------------
Wide3 = { w0: u64, w1: u64, w2: u64 }
Limbs26 = { l0: u64, l1: u64, l2: u64, l3: u64, l4: u64 }

// a * r mod p in radix 2^44 (poly1305_donna64.h blocks without a message).
mulmod = (p: Ptr<u64>, a: Wide3) Wide3 {
    r0 = p.read(0); r1 = p.read(1); r2 = p.read(2);
    s1 = r1 *% 20; s2 = r2 *% 20;
    d0 ::= a.w0.mul_wide(r0) +% a.w1.mul_wide(s2) +% a.w2.mul_wide(s1);
    d1 ::= a.w0.mul_wide(r1) +% a.w1.mul_wide(r0) +% a.w2.mul_wide(s2);
    d2 ::= a.w0.mul_wide(r2) +% a.w1.mul_wide(r1) +% a.w2.mul_wide(r0);
    c ::= d0.shift_right(44).truncate_u64(); h0 ::= d0.truncate_u64().bit_and(MASK44);
    d1 = d1 +% c.to_u128(); c = d1.shift_right(44).truncate_u64(); h1 = d1.truncate_u64().bit_and(MASK44);
    d2 = d2 +% c.to_u128(); c = d2.shift_right(42).truncate_u64(); h2 = d2.truncate_u64().bit_and(MASK42);
    h0 = h0 +% c *% 5; c = h0.shift_right(44); h0 = h0.bit_and(MASK44);
    Wide3(w0: h0, w1: h1 +% c, w2: h2)
}

// Radix 2^44 (h1 fully carried first) to five 26-bit limbs.
limbs26 = (h0: u64, h1: u64, h2: u64) Limbs26 {
    m26: u64 = 67108863;
    Limbs26(
        l0: h0.bit_and(m26),
        l1: h0.shift_right(26).bit_or(h1.shift_left(18)).bit_and(m26),
        l2: h1.shift_right(8).bit_and(m26),
        l3: h1.shift_right(34).bit_or(h2.shift_left(10)).bit_and(m26),
        l4: h2.shift_right(16)
    )
}

limbs26_carried = (h0: u64, h1: u64, h2: u64) Limbs26 {
    c = h0.shift_right(44);
    k1 = h1 +% c;
    limbs26(h0.bit_and(MASK44), k1.bit_and(MASK44), h2 +% k1.shift_right(44))
}

// Five 26-bit limb sums back to the radix 2^44 state, partially reduced.
// Limb fields are added, not or-ed, after masking where they straddle words.
store_limbs = (p: Ptr<u64>, a0: u64, a1: u64, a2: u64, a3: u64, a4: u64) {
    m26: u64 = 67108863;
    c ::= a0.shift_right(26); l0 ::= a0.bit_and(m26);
    k1 = a1 +% c; c = k1.shift_right(26); l1 = k1.bit_and(m26);
    k2 = a2 +% c; c = k2.shift_right(26); l2 = k2.bit_and(m26);
    k3 = a3 +% c; c = k3.shift_right(26); l3 = k3.bit_and(m26);
    k4 = a4 +% c; c = k4.shift_right(26); l4 = k4.bit_and(m26);
    l0 = l0 +% c *% 5; c = l0.shift_right(26); l0 = l0.bit_and(m26);
    k5 = l1 +% c;
    h0 = l0 +% k5.bit_and(262143).shift_left(26);
    h1 ::= k5.shift_right(18) +% l2.shift_left(8) +% l3.bit_and(1023).shift_left(34);
    h2 = l3.shift_right(10) +% l4.shift_left(16) +% h1.shift_right(44);
    p.write(3, h0); p.write(4, h1.bit_and(MASK44)); p.write(5, h2);
}
'''
print(common)
print(gen(4))
print(gen(2))
