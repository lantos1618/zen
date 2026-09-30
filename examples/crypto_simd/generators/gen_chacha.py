# Generates the vector ChaCha20 block functions (libsodium dolbeau u4/u8).
def qr_lines(a,b,c,d):
    return [
        f"x{a} = x{a}.add_wrap(x{b}); x{d} = x{d}.bit_xor(x{a}).rotate_left(16);",
        f"x{c} = x{c}.add_wrap(x{d}); x{b} = x{b}.bit_xor(x{c}).rotate_left(12);",
        f"x{a} = x{a}.add_wrap(x{b}); x{d} = x{d}.bit_xor(x{a}).rotate_left(8);",
        f"x{c} = x{c}.add_wrap(x{d}); x{b} = x{b}.bit_xor(x{c}).rotate_left(7);",
    ]
def round_seq(qs):
    # VEC8_ROUND_SEQ: line k of every quarter round before line k+1.
    lines=[qr_lines(*q) for q in qs]
    out=[]
    for k in range(4):
        for l in lines: out.append(l[k])
    return out
col=[(0,4,8,12),(1,5,9,13),(2,6,10,14),(3,7,11,15)]
diag=[(0,5,10,15),(1,6,11,12),(2,7,8,13),(3,4,9,14)]

def gen(V, N, name, token):
    splat=f"splat_{V}"
    I="    "
    o=[]
    tok = f"cpu: {token}, " if token else ""
    o.append(f"{name} = (")
    if token: o.append(f"    cpu     : {token},")
    o.append("    j       : Ptr<u32>,")
    o.append("    output  : Ptr<u8>,")
    o.append("    input   : Ptr<u8>,")
    o.append("    offset  : usize,")
    o.append("    counter : u32")
    o.append(") {")
    for w in range(16):
        if w==12:
            lanes=", ".join(str(i) for i in range(N))
            o.append(f"{I}o12 = {splat}(counter).add_wrap(lanes_{V}({lanes}));")
        else:
            o.append(f"{I}o{w} = {splat}(j.read({w}));")
    for w in range(16):
        o.append(f"{I}x{w} ::= o{w};")
    o.append(f"{I}Range(0, 10).loop((round) {{")
    for l in round_seq(col)+round_seq(diag):
        o.append(f"{I}{I}{l}")
    o.append(f"{I}}});")
    for w in range(16):
        o.append(f"{I}x{w} = x{w}.add_wrap(o{w});")
    # transpose: 4x4 within each 128-bit half.
    if N==4:
        lo32="[0, 4, 1, 5]"; hi32="[2, 6, 3, 7]"; lo64="[0, 1, 4, 5]"; hi64="[2, 3, 6, 7]"
    else:
        lo32="[0, 8, 1, 9, 4, 12, 5, 13]"; hi32="[2, 10, 3, 11, 6, 14, 7, 15]"
        lo64="[0, 1, 8, 9, 4, 5, 12, 13]"; hi64="[2, 3, 10, 11, 6, 7, 14, 15]"
    for q in range(4):
        a,b,c,d=4*q,4*q+1,4*q+2,4*q+3
        o.append(f"{I}t{a} = x{a}.shuffle2(x{b}, {lo32}); t{b} = x{c}.shuffle2(x{d}, {lo32});")
        o.append(f"{I}t{c} = x{a}.shuffle2(x{b}, {hi32}); t{d} = x{c}.shuffle2(x{d}, {hi32});")
        o.append(f"{I}y{a} = t{a}.shuffle2(t{b}, {lo64}); y{b} = t{a}.shuffle2(t{b}, {hi64});")
        o.append(f"{I}y{c} = t{c}.shuffle2(t{d}, {lo64}); y{d} = t{c}.shuffle2(t{d}, {hi64});")
    if N==4:
        # y{4q+k} = block k, words 4q..4q+3 -> offset + 64k + 16q
        for q in range(4):
            for k in range(4):
                off=64*k+16*q
                o.append(f"{I}xor_store_{V}(output, input, offset + {off}, y{4*q+k});")
    else:
        # ONEOCTO: pair word group q (words 4q..) with group q+1 (words 4q+4..):
        # low halves -> block k (32 bytes at 64k + 16q*... ) ; high halves -> block k+4.
        lo128="[0, 1, 2, 3, 8, 9, 10, 11]"; hi128="[4, 5, 6, 7, 12, 13, 14, 15]"
        for q in (0,2):
            for k in range(4):
                a=4*q+k; b=4*(q+1)+k
                off=64*k+16*q
                o.append(f"{I}xor_store_{V}(output, input, offset + {off}, y{a}.shuffle2(y{b}, {lo128}));")
                o.append(f"{I}xor_store_{V}(output, input, offset + {off+256}, y{a}.shuffle2(y{b}, {hi128}));")
    o.append("}")
    return "\n".join(o)

print(gen("u32x8", 8, "blocks8", "Avx2"))
print()
print(gen("u32x4", 4, "blocks4", None))
