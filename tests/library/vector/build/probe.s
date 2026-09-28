	.section	__TEXT,__text,regular,pure_instructions
	.build_version macos, 26, 0	sdk_version 26, 2
	.section	__TEXT,__literal8,8byte_literals
	.p2align	3, 0x0                          ; -- Begin function main
lCPI0_0:
	.long	0                               ; 0x0
	.long	1                               ; 0x1
	.section	__TEXT,__text,regular,pure_instructions
	.globl	_main
	.p2align	2
_main:                                  ; @main
	.cfi_startproc
; %bb.0:
	sub	sp, sp, #384
	stp	d9, d8, [sp, #272]              ; 16-byte Folded Spill
	stp	x28, x27, [sp, #288]            ; 16-byte Folded Spill
	stp	x26, x25, [sp, #304]            ; 16-byte Folded Spill
	stp	x24, x23, [sp, #320]            ; 16-byte Folded Spill
	stp	x22, x21, [sp, #336]            ; 16-byte Folded Spill
	stp	x20, x19, [sp, #352]            ; 16-byte Folded Spill
	stp	x29, x30, [sp, #368]            ; 16-byte Folded Spill
	add	x29, sp, #368
	.cfi_def_cfa w29, 16
	.cfi_offset w30, -8
	.cfi_offset w29, -16
	.cfi_offset w19, -24
	.cfi_offset w20, -32
	.cfi_offset w21, -40
	.cfi_offset w22, -48
	.cfi_offset w23, -56
	.cfi_offset w24, -64
	.cfi_offset w25, -72
	.cfi_offset w26, -80
	.cfi_offset w27, -88
	.cfi_offset w28, -96
	.cfi_offset b8, -104
	.cfi_offset b9, -112
	cmp	w0, #1
	b.lt	LBB0_4
; %bb.1:
	mov	x20, x1
	mov	x21, x0
	ubfiz	x0, x21, #4, #32
	bl	_malloc
	mov	x19, x0
	cbz	x0, LBB0_5
; %bb.2:
	mov	w21, w21
	add	x22, x19, #8
LBB0_3:                                 ; =>This Inner Loop Header: Depth=1
	ldr	x0, [x20], #8
	stur	x0, [x22, #-8]
	bl	_strlen
	str	x0, [x22], #16
	subs	x21, x21, #1
	b.ne	LBB0_3
	b	LBB0_5
LBB0_4:
	mov	x19, #0                         ; =0x0
LBB0_5:
	movi.2d	v0, #0000000000000000
	stp	q0, q0, [sp, #240]
	stp	q0, q0, [sp, #208]
	stp	q0, q0, [sp, #176]
	stp	q0, q0, [sp, #144]
	stp	q0, q0, [sp, #112]
	stp	q0, q0, [sp, #80]
	stp	q0, q0, [sp, #48]
	stp	q0, q0, [sp, #16]
	str	q0, [sp]
	mov	w0, #48                         ; =0x30
	bl	_malloc
	cbz	x0, LBB0_39
; %bb.6:
	mov	x20, x0
	ldur	q0, [sp, #56]
	ldur	q1, [sp, #72]
	stp	q0, q1, [x0]
	mov	x25, x0
	str	xzr, [x25, #32]!
	str	xzr, [x0, #40]
	bl	_zu_f5_3std3mem9mem_arena5Arena3rawO3_t4_3std3mem9mem_arena5Arenab5usizeb5usize
	mov	w22, w1
	ands	x8, x0, #0xffffffff
	csel	x21, x1, x22, eq
	cbz	x8, LBB0_10
; %bb.7:
	ldr	x0, [x25]
	cbz	x0, LBB0_14
LBB0_8:                                 ; =>This Inner Loop Header: Depth=1
	ldr	x22, [x0]
	bl	_free
	mov	x0, x22
	cbnz	x22, LBB0_8
; %bb.9:
	mov	w23, #0                         ; =0x0
	mov	x22, x21
	b	LBB0_38
LBB0_10:
	mov	x0, x20
	bl	_zu_f5_3std3mem9mem_arena5Arena3rawO3_t4_3std3mem9mem_arena5Arenab5usizeb5usize
	mov	w22, w1
	ands	x8, x0, #0xffffffff
	csel	x24, x1, x22, eq
	cbz	x8, LBB0_15
; %bb.11:
	ldr	x0, [x25]
	cbz	x0, LBB0_14
LBB0_12:                                ; =>This Inner Loop Header: Depth=1
	ldr	x21, [x0]
	bl	_free
	mov	x0, x21
	cbnz	x21, LBB0_12
; %bb.13:
	mov	w23, #0                         ; =0x0
	mov	x22, x24
	b	LBB0_38
LBB0_14:
	mov	w23, #0                         ; =0x0
	b	LBB0_38
LBB0_15:
	sub	x8, x24, x21
	cmp	x8, #64
	b.hs	LBB0_17
; %bb.16:
	mov	x8, #0                          ; =0x0
	b	LBB0_19
LBB0_17:
	add	x9, x24, #32
	movi.2s	v0, #2
	movi.2s	v1, #4
Lloh0:
	adrp	x8, lCPI0_0@PAGE
Lloh1:
	ldr	d2, [x8, lCPI0_0@PAGEOFF]
	add	x10, x21, #32
	mov	w8, #1024                       ; =0x400
	movi.2s	v3, #6
	fmov.2d	v4, #0.25000000
	fmov.2d	v5, #-10.00000000
	fmov.2d	v6, #0.50000000
	fmov.2d	v7, #2.00000000
	mov	w11, #1024                      ; =0x400
	movi.2s	v16, #8
LBB0_18:                                ; =>This Inner Loop Header: Depth=1
	add.2s	v17, v2, v0
	add.2s	v18, v2, v1
	add.2s	v19, v2, v3
	ushll.2d	v20, v2, #0
	ucvtf.2d	v20, v20
	ushll.2d	v17, v17, #0
	ucvtf.2d	v17, v17
	ushll.2d	v18, v18, #0
	ucvtf.2d	v18, v18
	ushll.2d	v19, v19, #0
	ucvtf.2d	v19, v19
	mov.16b	v21, v5
	fmla.2d	v21, v4, v20
	mov.16b	v22, v5
	fmla.2d	v22, v4, v17
	mov.16b	v23, v5
	fmla.2d	v23, v4, v18
	mov.16b	v24, v5
	fmla.2d	v24, v4, v19
	stp	q21, q22, [x10, #-32]
	stp	q23, q24, [x10], #64
	mov.16b	v21, v7
	fmla.2d	v21, v6, v20
	mov.16b	v20, v7
	fmla.2d	v20, v6, v17
	mov.16b	v17, v7
	fmla.2d	v17, v6, v18
	mov.16b	v18, v7
	fmla.2d	v18, v6, v19
	stp	q21, q20, [x9, #-32]
	stp	q17, q18, [x9], #64
	add.2s	v2, v2, v16
	subs	x11, x11, #8
	b.ne	LBB0_18
LBB0_19:
	fmov	d0, #-10.00000000
	fmov	d1, #0.25000000
	fmov	d2, #2.00000000
	fmov	d3, #0.50000000
LBB0_20:                                ; =>This Inner Loop Header: Depth=1
	ucvtf	d4, w8
	fmadd	d5, d4, d1, d0
	str	d5, [x21, x8, lsl #3]
	fmadd	d4, d4, d3, d2
	str	d4, [x24, x8, lsl #3]
	add	x8, x8, #1
	cmp	x8, #1026
	b.ne	LBB0_20
; %bb.21:
	mov	x0, #0                          ; =0x0
	mov	x1, #0                          ; =0x0
	mov	x2, #0                          ; =0x0
	bl	_zu_f4_3std4math6vector3dotO3_t4_3std3mem7mem_ptr3PtrI1_b3f64t4_3std3mem7mem_ptr3PtrI1_b3f64b5usize
	fcmp	d0, #0.0
	b.ne	LBB0_23
; %bb.22:
	mov	x0, #0                          ; =0x0
	mov	x1, #0                          ; =0x0
	mov	x2, #0                          ; =0x0
	bl	_zu_f4_3std4math6vector16squared_distanceO3_t4_3std3mem7mem_ptr3PtrI1_b3f64t4_3std3mem7mem_ptr3PtrI1_b3f64b5usize
	fcmp	d0, #0.0
	cset	w26, eq
	b	LBB0_24
LBB0_23:
	mov	w26, #0                         ; =0x0
LBB0_24:
	mov	x22, #0                         ; =0x0
	add	x23, x21, #8
	add	x24, x24, #8
	b	LBB0_27
LBB0_25:                                ;   in Loop: Header=BB0_27 Depth=1
	mov	w26, #0                         ; =0x0
LBB0_26:                                ;   in Loop: Header=BB0_27 Depth=1
	add	x22, x22, #1
	cmp	x22, #1025
	b.eq	LBB0_35
LBB0_27:                                ; =>This Loop Header: Depth=1
                                        ;     Child Loop BB0_29 Depth 2
	cbz	x22, LBB0_31
; %bb.28:                               ;   in Loop: Header=BB0_27 Depth=1
	mov	x8, #0                          ; =0x0
	movi	d9, #0000000000000000
	movi	d8, #0000000000000000
LBB0_29:                                ;   Parent Loop BB0_27 Depth=1
                                        ; =>  This Inner Loop Header: Depth=2
	ldr	d0, [x23, x8, lsl #3]
	ldr	d1, [x24, x8, lsl #3]
	add	x9, x8, #1
	fmadd	d9, d0, d1, d9
	fsub	d0, d0, d1
	fmadd	d8, d0, d0, d8
	mov	x8, x9
	cmp	x22, x9
	b.ne	LBB0_29
; %bb.30:                               ;   in Loop: Header=BB0_27 Depth=1
	tbz	w26, #0, LBB0_25
	b	LBB0_32
LBB0_31:                                ;   in Loop: Header=BB0_27 Depth=1
	movi	d8, #0000000000000000
	movi	d9, #0000000000000000
	tbz	w26, #0, LBB0_25
LBB0_32:                                ;   in Loop: Header=BB0_27 Depth=1
	mov	x0, x23
	mov	x1, x24
	mov	x2, x22
	bl	_zu_f4_3std4math6vector3dotO3_t4_3std3mem7mem_ptr3PtrI1_b3f64t4_3std3mem7mem_ptr3PtrI1_b3f64b5usize
	fcmp	d0, d9
	b.ne	LBB0_25
; %bb.33:                               ;   in Loop: Header=BB0_27 Depth=1
	mov	x0, x23
	mov	x1, x24
	mov	x2, x22
	bl	_zu_f4_3std4math6vector16squared_distanceO3_t4_3std3mem7mem_ptr3PtrI1_b3f64t4_3std3mem7mem_ptr3PtrI1_b3f64b5usize
	fcmp	d0, d8
	b.ne	LBB0_25
; %bb.34:                               ;   in Loop: Header=BB0_27 Depth=1
	mov	x0, x21
	mov	x1, x21
	mov	x2, x22
	bl	_zu_f4_3std4math6vector16squared_distanceO3_t4_3std3mem7mem_ptr3PtrI1_b3f64t4_3std3mem7mem_ptr3PtrI1_b3f64b5usize
	fcmp	d0, #0.0
	cset	w26, eq
	b	LBB0_26
LBB0_35:
Lloh2:
	adrp	x21, ___stdoutp@GOTPAGE
Lloh3:
	ldr	x21, [x21, ___stdoutp@GOTPAGEOFF]
	ldr	x3, [x21]
Lloh4:
	adrp	x0, l_.str.2@PAGE
Lloh5:
	add	x0, x0, l_.str.2@PAGEOFF
	mov	w23, #1                         ; =0x1
	mov	w1, #1                          ; =0x1
	mov	w2, #55                         ; =0x37
	bl	_fwrite
Lloh6:
	adrp	x8, l_.str.11@PAGE
Lloh7:
	add	x8, x8, l_.str.11@PAGEOFF
Lloh8:
	adrp	x9, l_.str.10@PAGE
Lloh9:
	add	x9, x9, l_.str.10@PAGEOFF
	cmp	w26, #0
	csel	x0, x9, x8, ne
	mov	w8, #4                          ; =0x4
	cinc	x2, x8, eq
	ldr	x3, [x21]
	mov	w1, #1                          ; =0x1
	bl	_fwrite
	ldr	x1, [x21]
	mov	w0, #10                         ; =0xa
	bl	_fputc
	eor	w22, w26, #0x1
	ldr	x0, [x25]
	cbz	x0, LBB0_38
LBB0_36:                                ; =>This Inner Loop Header: Depth=1
	ldr	x21, [x0]
	bl	_free
	mov	x0, x21
	cbnz	x21, LBB0_36
; %bb.37:
	mov	w23, #1                         ; =0x1
LBB0_38:
	mov	x0, x20
	bl	_free
	mov	x0, x19
	bl	_free
	cmp	w23, #0
	csinc	w0, w22, wzr, ne
	ldp	x29, x30, [sp, #368]            ; 16-byte Folded Reload
	ldp	x20, x19, [sp, #352]            ; 16-byte Folded Reload
	ldp	x22, x21, [sp, #336]            ; 16-byte Folded Reload
	ldp	x24, x23, [sp, #320]            ; 16-byte Folded Reload
	ldp	x26, x25, [sp, #304]            ; 16-byte Folded Reload
	ldp	x28, x27, [sp, #288]            ; 16-byte Folded Reload
	ldp	d9, d8, [sp, #272]              ; 16-byte Folded Reload
	add	sp, sp, #384
	ret
LBB0_39:
Lloh10:
	adrp	x0, l_.str@PAGE
Lloh11:
	add	x0, x0, l_.str@PAGEOFF
Lloh12:
	adrp	x3, l_.str.1@PAGE
Lloh13:
	add	x3, x3, l_.str.1@PAGEOFF
	mov	w1, #4                          ; =0x4
	mov	w2, #17                         ; =0x11
	bl	_zg_trap
	.loh AdrpLdr	Lloh0, Lloh1
	.loh AdrpAdd	Lloh8, Lloh9
	.loh AdrpAdd	Lloh6, Lloh7
	.loh AdrpAdd	Lloh4, Lloh5
	.loh AdrpLdrGot	Lloh2, Lloh3
	.loh AdrpAdd	Lloh12, Lloh13
	.loh AdrpAdd	Lloh10, Lloh11
	.cfi_endproc
                                        ; -- End function
	.p2align	2                               ; -- Begin function zg_trap
_zg_trap:                               ; @zg_trap
	.cfi_startproc
; %bb.0:
	sub	sp, sp, #96
	stp	x24, x23, [sp, #32]             ; 16-byte Folded Spill
	stp	x22, x21, [sp, #48]             ; 16-byte Folded Spill
	stp	x20, x19, [sp, #64]             ; 16-byte Folded Spill
	stp	x29, x30, [sp, #80]             ; 16-byte Folded Spill
	add	x29, sp, #80
	.cfi_def_cfa w29, 16
	.cfi_offset w30, -8
	.cfi_offset w29, -16
	.cfi_offset w19, -24
	.cfi_offset w20, -32
	.cfi_offset w21, -40
	.cfi_offset w22, -48
	.cfi_offset w23, -56
	.cfi_offset w24, -64
	mov	x19, x3
	mov	x20, x2
	mov	x21, x1
	mov	x22, x0
Lloh14:
	adrp	x8, ___stdoutp@GOTPAGE
Lloh15:
	ldr	x8, [x8, ___stdoutp@GOTPAGEOFF]
Lloh16:
	ldr	x0, [x8]
	bl	_fflush
Lloh17:
	adrp	x23, ___stderrp@GOTPAGE
Lloh18:
	ldr	x23, [x23, ___stderrp@GOTPAGEOFF]
	ldr	x0, [x23]
	stp	x20, x19, [sp, #16]
	stp	x22, x21, [sp]
Lloh19:
	adrp	x1, l_.str.3@PAGE
Lloh20:
	add	x1, x1, l_.str.3@PAGEOFF
	bl	_fprintf
	ldr	x0, [x23]
	bl	_fflush
	mov	w0, #134                        ; =0x86
	bl	_exit
	.loh AdrpAdd	Lloh19, Lloh20
	.loh AdrpLdrGot	Lloh17, Lloh18
	.loh AdrpLdrGotLdr	Lloh14, Lloh15, Lloh16
	.cfi_endproc
                                        ; -- End function
	.p2align	2                               ; -- Begin function zu_f4_3std4math6vector3dotO3_t4_3std3mem7mem_ptr3PtrI1_b3f64t4_3std3mem7mem_ptr3PtrI1_b3f64b5usize
_zu_f4_3std4math6vector3dotO3_t4_3std3mem7mem_ptr3PtrI1_b3f64t4_3std3mem7mem_ptr3PtrI1_b3f64b5usize: ; @zu_f4_3std4math6vector3dotO3_t4_3std3mem7mem_ptr3PtrI1_b3f64t4_3std3mem7mem_ptr3PtrI1_b3f64b5usize
	.cfi_startproc
; %bb.0:
	sub	sp, sp, #192
	stp	d15, d14, [sp, #112]            ; 16-byte Folded Spill
	stp	d13, d12, [sp, #128]            ; 16-byte Folded Spill
	stp	d11, d10, [sp, #144]            ; 16-byte Folded Spill
	stp	d9, d8, [sp, #160]              ; 16-byte Folded Spill
	stp	x28, x27, [sp, #176]            ; 16-byte Folded Spill
	.cfi_def_cfa_offset 192
	.cfi_offset w27, -8
	.cfi_offset w28, -16
	.cfi_offset b8, -24
	.cfi_offset b9, -32
	.cfi_offset b10, -40
	.cfi_offset b11, -48
	.cfi_offset b12, -56
	.cfi_offset b13, -64
	.cfi_offset b14, -72
	.cfi_offset b15, -80
	cmp	x2, #4
	b.hs	LBB2_2
; %bb.1:
	mov	x8, #0                          ; =0x0
	movi	d0, #0000000000000000
	subs	x10, x2, x8
	b.hi	LBB2_10
	b	LBB2_17
LBB2_2:
	lsr	x9, x2, #2
	and	x8, x2, #0xfffffffffffffffc
	cmp	x2, #32
	b.hs	LBB2_4
; %bb.3:
	mov	x10, #0                         ; =0x0
	mov	x11, #0                         ; =0x0
	movi	d2, #0000000000000000
	movi	d3, #0000000000000000
	movi	d1, #0000000000000000
	movi	d0, #0000000000000000
	b	LBB2_7
LBB2_4:
	and	x11, x9, #0x3ffffffffffffff8
	lsl	x10, x11, #2
	add	x12, x1, #128
	add	x13, x0, #128
	movi	d2, #0000000000000000
	mov	x14, x11
	movi	d3, #0000000000000000
	movi	d1, #0000000000000000
	movi	d0, #0000000000000000
LBB2_5:                                 ; =>This Inner Loop Header: Depth=1
	sub	x15, x13, #128
	sub	x16, x13, #64
	ld4.2d	{ v16, v17, v18, v19 }, [x15]
	ld4.2d	{ v4, v5, v6, v7 }, [x16]
	add	x15, sp, #32
	st1.2d	{ v4, v5, v6, v7 }, [x15]       ; 64-byte Folded Spill
	mov	x15, x13
	sub	x16, x12, #128
	ld4.2d	{ v20, v21, v22, v23 }, [x15], #64
	ld4.2d	{ v28, v29, v30, v31 }, [x16]
	sub	x16, x12, #64
	ld4.2d	{ v8, v9, v10, v11 }, [x16]
	ld4.2d	{ v24, v25, v26, v27 }, [x15]
	mov	x15, x12
	ld4.2d	{ v12, v13, v14, v15 }, [x15], #64
	fmul.2d	v5, v16, v28
	fmul.2d	v4, v17, v29
	stp	q4, q5, [sp]                    ; 32-byte Folded Spill
	fmul.2d	v4, v18, v30
	str	q4, [sp, #96]                   ; 16-byte Folded Spill
	fmul.2d	v16, v19, v31
	add	x16, sp, #32
	ld1.2d	{ v4, v5, v6, v7 }, [x16]       ; 64-byte Folded Reload
	fmul.2d	v17, v4, v8
	fmul.2d	v18, v5, v9
	fmul.2d	v19, v6, v10
	ld4.2d	{ v28, v29, v30, v31 }, [x15]
	fmul.2d	v4, v7, v11
	fmul.2d	v5, v20, v12
	fmul.2d	v6, v21, v13
	fmul.2d	v7, v22, v14
	fmul.2d	v20, v23, v15
	fmul.2d	v21, v24, v28
	fmul.2d	v22, v25, v29
	fmul.2d	v23, v26, v30
	fmul.2d	v24, v27, v31
	ldr	q25, [sp, #16]                  ; 16-byte Folded Reload
	fadd	d2, d2, d25
	mov	d25, v25[1]
	fadd	d2, d2, d25
	ldr	q25, [sp]                       ; 16-byte Folded Reload
	fadd	d3, d3, d25
	mov	d25, v25[1]
	fadd	d3, d3, d25
	fadd	d2, d2, d17
	mov	d17, v17[1]
	fadd	d2, d2, d17
	fadd	d3, d3, d18
	mov	d17, v18[1]
	fadd	d3, d3, d17
	fadd	d2, d2, d5
	mov	d5, v5[1]
	fadd	d2, d2, d5
	ldr	q5, [sp, #96]                   ; 16-byte Folded Reload
	fadd	d1, d1, d5
	mov	d5, v5[1]
	fadd	d1, d1, d5
	fadd	d3, d3, d6
	mov	d5, v6[1]
	fadd	d3, d3, d5
	fadd	d1, d1, d19
	mov	d5, v19[1]
	fadd	d1, d1, d5
	fadd	d1, d1, d7
	mov	d5, v7[1]
	fadd	d1, d1, d5
	fadd	d0, d0, d16
	mov	d5, v16[1]
	fadd	d0, d0, d5
	fadd	d2, d2, d21
	mov	d5, v21[1]
	fadd	d2, d2, d5
	fadd	d0, d0, d4
	mov	d4, v4[1]
	fadd	d0, d0, d4
	fadd	d3, d3, d22
	mov	d4, v22[1]
	fadd	d3, d3, d4
	fadd	d0, d0, d20
	mov	d4, v20[1]
	fadd	d0, d0, d4
	fadd	d1, d1, d23
	mov	d4, v23[1]
	fadd	d1, d1, d4
	fadd	d0, d0, d24
	mov	d4, v24[1]
	fadd	d0, d0, d4
	add	x12, x12, #256
	add	x13, x13, #256
	subs	x14, x14, #8
	b.ne	LBB2_5
; %bb.6:
	cmp	x9, x11
	b.eq	LBB2_9
LBB2_7:
	sub	x9, x9, x11
	lsl	x10, x10, #3
	add	x11, x10, #16
	add	x10, x0, x11
	add	x11, x1, x11
LBB2_8:                                 ; =>This Inner Loop Header: Depth=1
	ldp	d4, d5, [x10, #-16]
	ldp	d6, d7, [x11, #-16]
	fmadd	d2, d4, d6, d2
	fmadd	d3, d5, d7, d3
	ldp	d4, d5, [x10], #32
	ldp	d6, d7, [x11], #32
	fmadd	d1, d4, d6, d1
	fmadd	d0, d5, d7, d0
	subs	x9, x9, #1
	b.ne	LBB2_8
LBB2_9:
	fadd	d2, d3, d2
	fadd	d0, d0, d1
	fadd	d0, d0, d2
	subs	x10, x2, x8
	b.ls	LBB2_17
LBB2_10:
	cmp	x10, #8
	b.hs	LBB2_12
; %bb.11:
	mov	x9, x8
	b	LBB2_15
LBB2_12:
	and	x11, x10, #0xfffffffffffffff8
	add	x9, x8, x11
	lsl	x8, x8, #3
	add	x12, x8, #32
	add	x8, x1, x12
	add	x12, x0, x12
	mov	x13, x11
LBB2_13:                                ; =>This Inner Loop Header: Depth=1
	ldp	q1, q2, [x12, #-32]
	ldp	q3, q4, [x12], #64
	ldp	q5, q6, [x8, #-32]
	ldp	q7, q16, [x8], #64
	fmul.2d	v1, v1, v5
	mov	d5, v1[1]
	fmul.2d	v2, v2, v6
	mov	d6, v2[1]
	fmul.2d	v3, v3, v7
	mov	d7, v3[1]
	fmul.2d	v4, v4, v16
	mov	d16, v4[1]
	fadd	d0, d0, d1
	fadd	d0, d0, d5
	fadd	d0, d0, d2
	fadd	d0, d0, d6
	fadd	d0, d0, d3
	fadd	d0, d0, d7
	fadd	d0, d0, d4
	fadd	d0, d0, d16
	subs	x13, x13, #8
	b.ne	LBB2_13
; %bb.14:
	cmp	x10, x11
	b.eq	LBB2_17
LBB2_15:
	sub	x8, x2, x9
	lsl	x10, x9, #3
	add	x9, x1, x10
	add	x10, x0, x10
LBB2_16:                                ; =>This Inner Loop Header: Depth=1
	ldr	d1, [x10], #8
	ldr	d2, [x9], #8
	fmadd	d0, d1, d2, d0
	subs	x8, x8, #1
	b.ne	LBB2_16
LBB2_17:
	ldp	x28, x27, [sp, #176]            ; 16-byte Folded Reload
	ldp	d9, d8, [sp, #160]              ; 16-byte Folded Reload
	ldp	d11, d10, [sp, #144]            ; 16-byte Folded Reload
	ldp	d13, d12, [sp, #128]            ; 16-byte Folded Reload
	ldp	d15, d14, [sp, #112]            ; 16-byte Folded Reload
	add	sp, sp, #192
	ret
	.cfi_endproc
                                        ; -- End function
	.p2align	2                               ; -- Begin function zu_f4_3std4math6vector16squared_distanceO3_t4_3std3mem7mem_ptr3PtrI1_b3f64t4_3std3mem7mem_ptr3PtrI1_b3f64b5usize
_zu_f4_3std4math6vector16squared_distanceO3_t4_3std3mem7mem_ptr3PtrI1_b3f64t4_3std3mem7mem_ptr3PtrI1_b3f64b5usize: ; @zu_f4_3std4math6vector16squared_distanceO3_t4_3std3mem7mem_ptr3PtrI1_b3f64t4_3std3mem7mem_ptr3PtrI1_b3f64b5usize
	.cfi_startproc
; %bb.0:
	cmp	x2, #4
	b.hs	LBB3_2
; %bb.1:
	mov	x8, #0                          ; =0x0
	movi	d0, #0000000000000000
	subs	x10, x2, x8
	b.hi	LBB3_10
	b	LBB3_17
LBB3_2:
	lsr	x9, x2, #2
	and	x8, x2, #0xfffffffffffffffc
	cmp	x2, #32
	b.hs	LBB3_4
; %bb.3:
	mov	x11, #0                         ; =0x0
	mov	x10, #0                         ; =0x0
	movi.2d	v0, #0000000000000000
	movi.2d	v1, #0000000000000000
	b	LBB3_7
LBB3_4:
	and	x10, x9, #0x3ffffffffffffff8
	lsl	x11, x10, #2
	add	x12, x1, #128
	add	x13, x0, #128
	movi	d0, #0000000000000000
	mov	x14, x10
	movi	d2, #0000000000000000
	movi	d1, #0000000000000000
	movi	d3, #0000000000000000
LBB3_5:                                 ; =>This Inner Loop Header: Depth=1
	ldp	q4, q5, [x13, #-96]
	ldp	q6, q7, [x13, #-128]
	ldp	q16, q17, [x13, #-32]
	ldp	q18, q19, [x13, #-64]
	ldp	q20, q21, [x13, #32]
	ldp	q22, q23, [x13]
	ldp	q24, q25, [x13, #96]
	ldp	q26, q27, [x12, #-128]
	fsub.2d	v7, v7, v27
	ldp	q27, q28, [x12, #-96]
	fsub.2d	v5, v5, v28
	fsub.2d	v6, v6, v26
	ldp	q26, q28, [x12, #-64]
	fsub.2d	v4, v4, v27
	fsub.2d	v19, v19, v28
	ldp	q27, q28, [x12, #-32]
	fsub.2d	v17, v17, v28
	fsub.2d	v18, v18, v26
	ldp	q26, q28, [x12]
	fsub.2d	v16, v16, v27
	fsub.2d	v23, v23, v28
	ldp	q27, q28, [x12, #32]
	fsub.2d	v21, v21, v28
	fsub.2d	v22, v22, v26
	ldp	q26, q28, [x13, #64]
	fsub.2d	v20, v20, v27
	ldr	q27, [x12, #80]
	fsub.2d	v27, v28, v27
	ldr	q28, [x12, #112]
	fsub.2d	v25, v25, v28
	ldr	q28, [x12, #64]
	fsub.2d	v26, v26, v28
	ldr	q28, [x12, #96]
	fsub.2d	v24, v24, v28
	fmul.2d	v28, v4, v4
	fmul.2d	v29, v6, v6
	fmul.2d	v5, v5, v5
	fmul.2d	v6, v7, v7
	zip2.2d	v4, v6, v5
	fmul.2d	v30, v16, v16
	fmul.2d	v31, v18, v18
	fmul.2d	v7, v17, v17
	fmul.2d	v17, v19, v19
	zip1.2d	v16, v6, v5
	zip2.2d	v5, v17, v7
	fmul.2d	v19, v20, v20
	fmul.2d	v20, v22, v22
	fmul.2d	v18, v21, v21
	fmul.2d	v21, v23, v23
	zip1.2d	v17, v17, v7
	zip2.2d	v6, v21, v18
	fmul.2d	v22, v24, v24
	fmul.2d	v23, v26, v26
	fmul.2d	v24, v25, v25
	fmul.2d	v25, v27, v27
	zip1.2d	v18, v21, v18
	zip2.2d	v7, v25, v24
	zip1.2d	v21, v25, v24
	zip2.2d	v24, v29, v28
	zip1.2d	v25, v29, v28
	zip2.2d	v26, v31, v30
	zip1.2d	v27, v31, v30
	zip2.2d	v28, v20, v19
	zip1.2d	v19, v20, v19
	zip2.2d	v20, v23, v22
	zip1.2d	v22, v23, v22
	fadd	d0, d0, d25
	mov	d23, v25[1]
	fadd	d0, d0, d23
	fadd	d0, d0, d27
	mov	d23, v27[1]
	fadd	d0, d0, d23
	fadd	d0, d0, d19
	mov	d19, v19[1]
	fadd	d0, d0, d19
	fadd	d0, d0, d22
	mov	d19, v22[1]
	fadd	d0, d0, d19
	fadd	d2, d2, d24
	mov	d19, v24[1]
	fadd	d2, d2, d19
	fadd	d2, d2, d26
	mov	d19, v26[1]
	fadd	d2, d2, d19
	fadd	d2, d2, d28
	mov	d19, v28[1]
	fadd	d2, d2, d19
	fadd	d2, d2, d20
	mov	d19, v20[1]
	fadd	d2, d2, d19
	fadd	d1, d1, d16
	mov	d16, v16[1]
	fadd	d1, d1, d16
	fadd	d1, d1, d17
	mov	d16, v17[1]
	fadd	d1, d1, d16
	fadd	d1, d1, d18
	mov	d16, v18[1]
	fadd	d1, d1, d16
	fadd	d1, d1, d21
	mov	d16, v21[1]
	fadd	d1, d1, d16
	fadd	d3, d3, d4
	mov	d4, v4[1]
	fadd	d3, d3, d4
	fadd	d3, d3, d5
	mov	d4, v5[1]
	fadd	d3, d3, d4
	fadd	d3, d3, d6
	mov	d4, v6[1]
	fadd	d3, d3, d4
	fadd	d3, d3, d7
	mov	d4, v7[1]
	fadd	d3, d3, d4
	add	x12, x12, #256
	add	x13, x13, #256
	subs	x14, x14, #8
	b.ne	LBB3_5
; %bb.6:
	mov.d	v1[1], v3[0]
	mov.d	v0[1], v2[0]
	cmp	x9, x10
	b.eq	LBB3_9
LBB3_7:
	lsl	x12, x11, #3
	add	x11, x0, x12
	add	x12, x1, x12
	sub	x9, x9, x10
LBB3_8:                                 ; =>This Inner Loop Header: Depth=1
	ldp	q3, q2, [x11], #32
	ldp	q5, q4, [x12], #32
	fsub.2d	v3, v3, v5
	fsub.2d	v2, v2, v4
	fmla.2d	v1, v2, v2
	fmla.2d	v0, v3, v3
	subs	x9, x9, #1
	b.ne	LBB3_8
LBB3_9:
	faddp.2d	d0, v0
	faddp.2d	d1, v1
	fadd	d0, d1, d0
	subs	x10, x2, x8
	b.ls	LBB3_17
LBB3_10:
	cmp	x10, #8
	b.hs	LBB3_12
; %bb.11:
	mov	x9, x8
	b	LBB3_15
LBB3_12:
	and	x11, x10, #0xfffffffffffffff8
	add	x9, x8, x11
	lsl	x8, x8, #3
	add	x12, x8, #32
	add	x8, x1, x12
	add	x12, x0, x12
	mov	x13, x11
LBB3_13:                                ; =>This Inner Loop Header: Depth=1
	ldp	q1, q2, [x12, #-32]
	ldp	q3, q4, [x12], #64
	ldp	q5, q6, [x8, #-32]
	ldp	q7, q16, [x8], #64
	fsub.2d	v1, v1, v5
	fsub.2d	v2, v2, v6
	fsub.2d	v3, v3, v7
	fsub.2d	v4, v4, v16
	fmul.2d	v1, v1, v1
	mov	d5, v1[1]
	fmul.2d	v2, v2, v2
	mov	d6, v2[1]
	fmul.2d	v3, v3, v3
	mov	d7, v3[1]
	fmul.2d	v4, v4, v4
	mov	d16, v4[1]
	fadd	d0, d0, d1
	fadd	d0, d0, d5
	fadd	d0, d0, d2
	fadd	d0, d0, d6
	fadd	d0, d0, d3
	fadd	d0, d0, d7
	fadd	d0, d0, d4
	fadd	d0, d0, d16
	subs	x13, x13, #8
	b.ne	LBB3_13
; %bb.14:
	cmp	x10, x11
	b.eq	LBB3_17
LBB3_15:
	sub	x8, x2, x9
	lsl	x10, x9, #3
	add	x9, x1, x10
	add	x10, x0, x10
LBB3_16:                                ; =>This Inner Loop Header: Depth=1
	ldr	d1, [x10], #8
	ldr	d2, [x9], #8
	fsub	d1, d1, d2
	fmadd	d0, d1, d1, d0
	subs	x8, x8, #1
	b.ne	LBB3_16
LBB3_17:
	ret
	.cfi_endproc
                                        ; -- End function
	.p2align	2                               ; -- Begin function zu_f5_3std3mem9mem_arena5Arena3rawO3_t4_3std3mem9mem_arena5Arenab5usizeb5usize
_zu_f5_3std3mem9mem_arena5Arena3rawO3_t4_3std3mem9mem_arena5Arenab5usizeb5usize: ; @zu_f5_3std3mem9mem_arena5Arena3rawO3_t4_3std3mem9mem_arena5Arenab5usizeb5usize
	.cfi_startproc
; %bb.0:
	sub	sp, sp, #96
	stp	x20, x19, [sp, #64]             ; 16-byte Folded Spill
	stp	x29, x30, [sp, #80]             ; 16-byte Folded Spill
	add	x29, sp, #80
	.cfi_def_cfa w29, 16
	.cfi_offset w30, -8
	.cfi_offset w29, -16
	.cfi_offset w19, -24
	.cfi_offset w20, -32
	mov	x19, x0
	ldr	x20, [x0, #32]
	cbz	x20, LBB4_8
; %bb.1:
	ldr	x8, [x19, #40]
	adds	x8, x8, #8
	b.hs	LBB4_14
; %bb.2:
	sub	x8, x8, #1
	and	x8, x8, #0xfffffffffffffff8
	adds	x8, x8, #8
	b.hs	LBB4_15
; %bb.3:
	adds	x8, x8, #16
	b.hs	LBB4_14
; %bb.4:
	sub	x8, x8, #1
	and	x8, x8, #0xfffffffffffffff0
	mov	w9, #8208                       ; =0x2010
	adds	x9, x8, x9
	b.hs	LBB4_16
; %bb.5:
	ldr	x10, [x20, #16]
	cmp	x9, x10
	b.ls	LBB4_11
; %bb.6:
	ldp	q0, q1, [x19]
	stp	q0, q1, [sp]
	mov	w0, #24                         ; =0x18
	movk	w0, #1, lsl #16
	bl	_malloc
	cbz	x0, LBB4_12
; %bb.7:
	add	x8, x0, #24
	stp	x20, x8, [x0]
	mov	w8, #65536                      ; =0x10000
	str	x8, [x0, #16]
	ldp	q1, q0, [sp]
	b	LBB4_10
LBB4_8:
	ldp	q0, q1, [x19]
	stp	q0, q1, [sp, #32]
	mov	w0, #24                         ; =0x18
	movk	w0, #1, lsl #16
	bl	_malloc
	cbz	x0, LBB4_12
; %bb.9:
	add	x8, x0, #24
	stp	xzr, x8, [x0]
	mov	w8, #65536                      ; =0x10000
	str	x8, [x0, #16]
	ldp	q1, q0, [sp, #32]
LBB4_10:
	stp	q1, q0, [x19]
	stp	x0, xzr, [x19, #32]
	mov	x0, x19
	bl	_zu_f5_3std3mem9mem_arena5Arena3rawO3_t4_3std3mem9mem_arena5Arenab5usizeb5usize
	b	LBB4_13
LBB4_11:
	mov	x0, #0                          ; =0x0
	ldr	x10, [x20, #8]
	str	x9, [x19, #40]
	add	x1, x10, x8
	mov	w8, #8208                       ; =0x2010
	stur	x8, [x1, #-8]
	b	LBB4_13
LBB4_12:
	mov	x1, #0                          ; =0x0
	mov	w0, #1                          ; =0x1
LBB4_13:
	ldp	x29, x30, [sp, #80]             ; 16-byte Folded Reload
	ldp	x20, x19, [sp, #64]             ; 16-byte Folded Reload
	add	sp, sp, #96
	ret
LBB4_14:
Lloh21:
	adrp	x0, l_.str.4@PAGE
Lloh22:
	add	x0, x0, l_.str.4@PAGEOFF
Lloh23:
	adrp	x3, l_.str.7@PAGE
Lloh24:
	add	x3, x3, l_.str.7@PAGEOFF
	mov	w1, #19                         ; =0x13
	mov	w2, #21                         ; =0x15
	bl	_zg_trap
LBB4_15:
Lloh25:
	adrp	x0, l_.str.4@PAGE
Lloh26:
	add	x0, x0, l_.str.4@PAGEOFF
Lloh27:
	adrp	x3, l_.str.7@PAGE
Lloh28:
	add	x3, x3, l_.str.7@PAGEOFF
	mov	w1, #41                         ; =0x29
	mov	w2, #23                         ; =0x17
	bl	_zg_trap
LBB4_16:
Lloh29:
	adrp	x0, l_.str.4@PAGE
Lloh30:
	add	x0, x0, l_.str.4@PAGEOFF
Lloh31:
	adrp	x3, l_.str.7@PAGE
Lloh32:
	add	x3, x3, l_.str.7@PAGEOFF
	mov	w1, #42                         ; =0x2a
	mov	w2, #16                         ; =0x10
	bl	_zg_trap
	.loh AdrpAdd	Lloh23, Lloh24
	.loh AdrpAdd	Lloh21, Lloh22
	.loh AdrpAdd	Lloh27, Lloh28
	.loh AdrpAdd	Lloh25, Lloh26
	.loh AdrpAdd	Lloh31, Lloh32
	.loh AdrpAdd	Lloh29, Lloh30
	.cfi_endproc
                                        ; -- End function
	.section	__TEXT,__cstring,cstring_literals
l_.str:                                 ; @.str
	.asciz	"main.zen"

l_.str.1:                               ; @.str.1
	.asciz	"out of memory"

l_.str.2:                               ; @.str.2
	.asciz	"bulk math: zero, all tails, offset pointers, aliasing: "

l_.str.3:                               ; @.str.3
	.asciz	"%s:%lu:%lu: trap: %s\n"

l_.str.4:                               ; @.str.4
	.asciz	"std/mem/mem_arena.zen"

l_.str.7:                               ; @.str.7
	.asciz	"integer overflow"

l_.str.10:                              ; @.str.10
	.asciz	"true"

l_.str.11:                              ; @.str.11
	.asciz	"false"

.subsections_via_symbols
