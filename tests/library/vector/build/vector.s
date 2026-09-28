	.section	__TEXT,__text,regular,pure_instructions
	.build_version macos, 26, 0	sdk_version 26, 2
	.globl	_main                           ; -- Begin function main
	.p2align	2
_main:                                  ; @main
	.cfi_startproc
; %bb.0:
	sub	sp, sp, #432
	stp	x20, x19, [sp, #400]            ; 16-byte Folded Spill
	stp	x29, x30, [sp, #416]            ; 16-byte Folded Spill
	add	x29, sp, #416
	.cfi_def_cfa w29, 16
	.cfi_offset w30, -8
	.cfi_offset w29, -16
	.cfi_offset w19, -24
	.cfi_offset w20, -32
	sub	x8, x29, #80
	bl	_zg_argv_vec
	movi.2d	v2, #0000000000000000
	stp	q2, q2, [sp, #304]
	stp	q2, q2, [sp, #272]
	stp	q2, q2, [sp, #240]
	stp	q2, q2, [sp, #208]
	stp	q2, q2, [sp, #176]
	stp	q2, q2, [sp, #144]
	stp	q2, q2, [sp, #112]
	stp	q2, q2, [sp, #80]
	ldp	q0, q1, [x29, #-80]
	stp	q0, q1, [sp]
	ldp	q0, q1, [x29, #-48]
	str	q0, [sp, #32]
	stp	q1, q2, [sp, #48]
	mov	x0, sp
	bl	_zu_f2_4main4mainO1_t4_3std3env3env3Env
	mov	x19, x0
	ldur	x0, [x29, #-80]
	bl	_free
	lsr	x8, x19, #32
	cmp	w19, #0
	csinc	w0, w8, wzr, eq
	ldp	x29, x30, [sp, #416]            ; 16-byte Folded Reload
	ldp	x20, x19, [sp, #400]            ; 16-byte Folded Reload
	add	sp, sp, #432
	ret
	.cfi_endproc
                                        ; -- End function
	.p2align	2                               ; -- Begin function zg_argv_vec
_zg_argv_vec:                           ; @zg_argv_vec
	.cfi_startproc
; %bb.0:
	stp	x24, x23, [sp, #-64]!           ; 16-byte Folded Spill
	stp	x22, x21, [sp, #16]             ; 16-byte Folded Spill
	stp	x20, x19, [sp, #32]             ; 16-byte Folded Spill
	stp	x29, x30, [sp, #48]             ; 16-byte Folded Spill
	add	x29, sp, #48
	.cfi_def_cfa w29, 16
	.cfi_offset w30, -8
	.cfi_offset w29, -16
	.cfi_offset w19, -24
	.cfi_offset w20, -32
	.cfi_offset w21, -40
	.cfi_offset w22, -48
	.cfi_offset w23, -56
	.cfi_offset w24, -64
	mov	x19, x8
	cmp	w0, #0
	b.le	LBB1_5
; %bb.1:
	mov	x20, x1
	mov	x22, x0
	ubfiz	x0, x22, #4, #32
	bl	_malloc
	cbz	x0, LBB1_5
; %bb.2:
	mov	x21, x0
	mov	w22, w22
	add	x23, x0, #8
	mov	x24, x22
LBB1_3:                                 ; =>This Inner Loop Header: Depth=1
	ldr	x0, [x20], #8
	stur	x0, [x23, #-8]
	bl	_strlen
	str	x0, [x23], #16
	subs	x24, x24, #1
	b.ne	LBB1_3
; %bb.4:
	stp	x21, x22, [x19]
	str	x22, [x19, #16]
	movi.2d	v0, #0000000000000000
	stur	q0, [x19, #24]
	stur	q0, [x19, #40]
	str	xzr, [x19, #56]
	b	LBB1_6
LBB1_5:
	movi.2d	v0, #0000000000000000
	stp	q0, q0, [x19, #32]
	stp	q0, q0, [x19]
LBB1_6:
	ldp	x29, x30, [sp, #48]             ; 16-byte Folded Reload
	ldp	x20, x19, [sp, #32]             ; 16-byte Folded Reload
	ldp	x22, x21, [sp, #16]             ; 16-byte Folded Reload
	ldp	x24, x23, [sp], #64             ; 16-byte Folded Reload
	ret
	.cfi_endproc
                                        ; -- End function
	.section	__TEXT,__literal8,8byte_literals
	.p2align	3, 0x0                          ; -- Begin function zu_f2_4main4mainO1_t4_3std3env3env3Env
lCPI2_0:
	.long	0                               ; 0x0
	.long	1                               ; 0x1
	.section	__TEXT,__text,regular,pure_instructions
	.p2align	2
_zu_f2_4main4mainO1_t4_3std3env3env3Env: ; @zu_f2_4main4mainO1_t4_3std3env3env3Env
	.cfi_startproc
; %bb.0:
	sub	sp, sp, #112
	stp	d11, d10, [sp, #16]             ; 16-byte Folded Spill
	stp	d9, d8, [sp, #32]               ; 16-byte Folded Spill
	stp	x24, x23, [sp, #48]             ; 16-byte Folded Spill
	stp	x22, x21, [sp, #64]             ; 16-byte Folded Spill
	stp	x20, x19, [sp, #80]             ; 16-byte Folded Spill
	stp	x29, x30, [sp, #96]             ; 16-byte Folded Spill
	add	x29, sp, #96
	.cfi_def_cfa w29, 16
	.cfi_offset w30, -8
	.cfi_offset w29, -16
	.cfi_offset w19, -24
	.cfi_offset w20, -32
	.cfi_offset w21, -40
	.cfi_offset w22, -48
	.cfi_offset w23, -56
	.cfi_offset w24, -64
	.cfi_offset b8, -72
	.cfi_offset b9, -80
	.cfi_offset b10, -88
	.cfi_offset b11, -96
	mov	x19, x0
	mov	w0, #48                         ; =0x30
	bl	_malloc
	cbz	x0, LBB2_27
; %bb.1:
	mov	x20, x0
	ldur	q0, [x19, #120]
	ldur	q1, [x19, #136]
	stp	q0, q1, [x0]
	stp	xzr, xzr, [x0, #32]
	str	x0, [sp, #8]
	bl	_zu_f5_3std3mem9mem_arena5Arena7reallocO3_t4_3std3mem9mem_arena5Arenat4_3std3mem7mem_ptr3PtrI1_b3f64b5usizeI1_b3f64
	mov	x19, x1
	cbz	w0, LBB2_3
; %bb.2:
	mov	w21, #1                         ; =0x1
	b	LBB2_26
LBB2_3:
	mov	x0, x20
	bl	_zu_f5_3std3mem9mem_arena5Arena7reallocO3_t4_3std3mem9mem_arena5Arenat4_3std3mem7mem_ptr3PtrI1_b3f64b5usizeI1_b3f64
	mov	x20, x1
	cbz	w0, LBB2_5
; %bb.4:
	mov	w21, #1                         ; =0x1
	mov	x19, x20
	b	LBB2_26
LBB2_5:
	sub	x8, x20, x19
	cmp	x8, #64
	b.hs	LBB2_7
; %bb.6:
	mov	x8, #0                          ; =0x0
	b	LBB2_9
LBB2_7:
	add	x9, x20, #32
	movi.2s	v0, #2
	movi.2s	v1, #4
Lloh0:
	adrp	x8, lCPI2_0@PAGE
Lloh1:
	ldr	d2, [x8, lCPI2_0@PAGEOFF]
	add	x10, x19, #32
	mov	w8, #1024                       ; =0x400
	movi.2s	v3, #6
	fmov.2d	v4, #0.25000000
	fmov.2d	v5, #-10.00000000
	fmov.2d	v6, #0.50000000
	fmov.2d	v7, #2.00000000
	mov	w11, #1024                      ; =0x400
	movi.2s	v16, #8
LBB2_8:                                 ; =>This Inner Loop Header: Depth=1
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
	b.ne	LBB2_8
LBB2_9:
	fmov	d0, #-10.00000000
	fmov	d1, #0.25000000
	fmov	d2, #2.00000000
	fmov	d3, #0.50000000
LBB2_10:                                ; =>This Inner Loop Header: Depth=1
	ucvtf	d4, w8
	fmadd	d5, d4, d1, d0
	str	d5, [x19, x8, lsl #3]
	fmadd	d4, d4, d3, d2
	str	d4, [x20, x8, lsl #3]
	add	x8, x8, #1
	cmp	x8, #1026
	b.ne	LBB2_10
; %bb.11:
	mov	x0, #0                          ; =0x0
	mov	x1, #0                          ; =0x0
	mov	x2, #0                          ; =0x0
	bl	_zu_f4_3std4math6vector3dotO3_t4_3std3mem7mem_ptr3PtrI1_b3f64t4_3std3mem7mem_ptr3PtrI1_b3f64b5usize
	fcmp	d0, #0.0
	b.ne	LBB2_13
; %bb.12:
	mov	x0, #0                          ; =0x0
	mov	x1, #0                          ; =0x0
	mov	x2, #0                          ; =0x0
	bl	_zu_f4_3std4math6vector16squared_distanceO3_t4_3std3mem7mem_ptr3PtrI1_b3f64t4_3std3mem7mem_ptr3PtrI1_b3f64b5usize
	fcmp	d0, #0.0
	cset	w23, eq
	b	LBB2_14
LBB2_13:
	mov	w23, #0                         ; =0x0
LBB2_14:
	mov	x21, #0                         ; =0x0
Lloh2:
	adrp	x22, l_.str@PAGE
Lloh3:
	add	x22, x22, l_.str@PAGEOFF
	b	LBB2_17
LBB2_15:                                ;   in Loop: Header=BB2_17 Depth=1
	mov	w23, #0                         ; =0x0
LBB2_16:                                ;   in Loop: Header=BB2_17 Depth=1
	add	x21, x21, #1
	cmp	x21, #1025
	b.eq	LBB2_25
LBB2_17:                                ; =>This Loop Header: Depth=1
                                        ;     Child Loop BB2_19 Depth 2
	cbz	x21, LBB2_21
; %bb.18:                               ;   in Loop: Header=BB2_17 Depth=1
	mov	x24, #0                         ; =0x0
	movi	d9, #0000000000000000
	movi	d8, #0000000000000000
LBB2_19:                                ;   Parent Loop BB2_17 Depth=1
                                        ; =>  This Inner Loop Header: Depth=2
	mov	x0, x24
	mov	w1, #1                          ; =0x1
	mov	x2, x22
	mov	w3, #16                         ; =0x10
	mov	w4, #29                         ; =0x1d
	bl	_zg_add_usize
	ldr	d10, [x19, x0, lsl #3]
	mov	x0, x24
	mov	w1, #1                          ; =0x1
	mov	x2, x22
	mov	w3, #16                         ; =0x10
	mov	w4, #52                         ; =0x34
	bl	_zg_add_usize
	ldr	d0, [x20, x0, lsl #3]
	fmadd	d9, d10, d0, d9
	fsub	d0, d10, d0
	fmadd	d8, d0, d0, d8
	add	x24, x24, #1
	cmp	x21, x24
	b.ne	LBB2_19
; %bb.20:                               ;   in Loop: Header=BB2_17 Depth=1
	tbz	w23, #0, LBB2_15
	b	LBB2_22
LBB2_21:                                ;   in Loop: Header=BB2_17 Depth=1
	movi	d8, #0000000000000000
	movi	d9, #0000000000000000
	tbz	w23, #0, LBB2_15
LBB2_22:                                ;   in Loop: Header=BB2_17 Depth=1
	add	x0, x19, #8
	add	x1, x20, #8
	mov	x2, x21
	bl	_zu_f4_3std4math6vector3dotO3_t4_3std3mem7mem_ptr3PtrI1_b3f64t4_3std3mem7mem_ptr3PtrI1_b3f64b5usize
	fcmp	d0, d9
	b.ne	LBB2_15
; %bb.23:                               ;   in Loop: Header=BB2_17 Depth=1
	add	x0, x19, #8
	add	x1, x20, #8
	mov	x2, x21
	bl	_zu_f4_3std4math6vector16squared_distanceO3_t4_3std3mem7mem_ptr3PtrI1_b3f64t4_3std3mem7mem_ptr3PtrI1_b3f64b5usize
	fcmp	d0, d8
	b.ne	LBB2_15
; %bb.24:                               ;   in Loop: Header=BB2_17 Depth=1
	mov	x0, x19
	mov	x1, x19
	mov	x2, x21
	bl	_zu_f4_3std4math6vector16squared_distanceO3_t4_3std3mem7mem_ptr3PtrI1_b3f64t4_3std3mem7mem_ptr3PtrI1_b3f64b5usize
	fcmp	d0, #0.0
	cset	w23, eq
	b	LBB2_16
LBB2_25:
Lloh4:
	adrp	x0, l_.str.2@PAGE
Lloh5:
	add	x0, x0, l_.str.2@PAGEOFF
	mov	w1, #55                         ; =0x37
	bl	_zg_print_bytes
	mov	x0, x23
	bl	_zg_print_bool
	bl	_zg_print_nl
	mov	x21, #0                         ; =0x0
	eor	w19, w23, #0x1
LBB2_26:
	add	x0, sp, #8
	bl	_zu_f5_3std3mem9mem_arena5Arena4dropO1_t4_3std3mem9mem_arena5Arena
	orr	x0, x21, x19, lsl #32
	ldp	x29, x30, [sp, #96]             ; 16-byte Folded Reload
	ldp	x20, x19, [sp, #80]             ; 16-byte Folded Reload
	ldp	x22, x21, [sp, #64]             ; 16-byte Folded Reload
	ldp	x24, x23, [sp, #48]             ; 16-byte Folded Reload
	ldp	d9, d8, [sp, #32]               ; 16-byte Folded Reload
	ldp	d11, d10, [sp, #16]             ; 16-byte Folded Reload
	add	sp, sp, #112
	ret
LBB2_27:
Lloh6:
	adrp	x0, l_.str@PAGE
Lloh7:
	add	x0, x0, l_.str@PAGEOFF
Lloh8:
	adrp	x3, l_.str.1@PAGE
Lloh9:
	add	x3, x3, l_.str.1@PAGEOFF
	mov	w1, #4                          ; =0x4
	mov	w2, #17                         ; =0x11
	bl	_zg_trap
	.loh AdrpLdr	Lloh0, Lloh1
	.loh AdrpAdd	Lloh2, Lloh3
	.loh AdrpAdd	Lloh4, Lloh5
	.loh AdrpAdd	Lloh8, Lloh9
	.loh AdrpAdd	Lloh6, Lloh7
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
Lloh10:
	adrp	x8, ___stdoutp@GOTPAGE
Lloh11:
	ldr	x8, [x8, ___stdoutp@GOTPAGEOFF]
Lloh12:
	ldr	x0, [x8]
	bl	_fflush
Lloh13:
	adrp	x23, ___stderrp@GOTPAGE
Lloh14:
	ldr	x23, [x23, ___stderrp@GOTPAGEOFF]
	ldr	x0, [x23]
	stp	x20, x19, [sp, #16]
	stp	x22, x21, [sp]
Lloh15:
	adrp	x1, l_.str.3@PAGE
Lloh16:
	add	x1, x1, l_.str.3@PAGEOFF
	bl	_fprintf
	ldr	x0, [x23]
	bl	_fflush
	mov	w0, #134                        ; =0x86
	bl	_exit
	.loh AdrpAdd	Lloh15, Lloh16
	.loh AdrpLdrGot	Lloh13, Lloh14
	.loh AdrpLdrGotLdr	Lloh10, Lloh11, Lloh12
	.cfi_endproc
                                        ; -- End function
	.p2align	2                               ; -- Begin function zu_f5_3std3mem9mem_arena5Arena7reallocO3_t4_3std3mem9mem_arena5Arenat4_3std3mem7mem_ptr3PtrI1_b3f64b5usizeI1_b3f64
_zu_f5_3std3mem9mem_arena5Arena7reallocO3_t4_3std3mem9mem_arena5Arenat4_3std3mem7mem_ptr3PtrI1_b3f64b5usizeI1_b3f64: ; @zu_f5_3std3mem9mem_arena5Arena7reallocO3_t4_3std3mem9mem_arena5Arenat4_3std3mem7mem_ptr3PtrI1_b3f64b5usizeI1_b3f64
	.cfi_startproc
; %bb.0:
	stp	x29, x30, [sp, #-16]!           ; 16-byte Folded Spill
	mov	x29, sp
	.cfi_def_cfa w29, 16
	.cfi_offset w30, -8
	.cfi_offset w29, -16
	bl	_zu_f5_3std3mem9mem_arena5Arena3rawO3_t4_3std3mem9mem_arena5Arenab5usizeb5usize
	tst	x0, #0xffffffff
	cset	w0, ne
	mov	w8, w1
	csel	x1, x8, x1, ne
	ldp	x29, x30, [sp], #16             ; 16-byte Folded Reload
	ret
	.cfi_endproc
                                        ; -- End function
	.p2align	2                               ; -- Begin function zu_f5_3std3mem9mem_arena5Arena4dropO1_t4_3std3mem9mem_arena5Arena
_zu_f5_3std3mem9mem_arena5Arena4dropO1_t4_3std3mem9mem_arena5Arena: ; @zu_f5_3std3mem9mem_arena5Arena4dropO1_t4_3std3mem9mem_arena5Arena
	.cfi_startproc
; %bb.0:
	stp	x20, x19, [sp, #-32]!           ; 16-byte Folded Spill
	stp	x29, x30, [sp, #16]             ; 16-byte Folded Spill
	add	x29, sp, #16
	.cfi_def_cfa w29, 16
	.cfi_offset w30, -8
	.cfi_offset w29, -16
	.cfi_offset w19, -24
	.cfi_offset w20, -32
	mov	x19, x0
	ldr	x8, [x0]
	ldr	x0, [x8, #32]
	cbz	x0, LBB5_3
LBB5_1:                                 ; =>This Inner Loop Header: Depth=1
	ldr	x20, [x0]
	bl	_free
	mov	x0, x20
	cbnz	x20, LBB5_1
; %bb.2:
	ldr	x8, [x19]
LBB5_3:
	mov	x0, x8
	ldp	x29, x30, [sp, #16]             ; 16-byte Folded Reload
	ldp	x20, x19, [sp], #32             ; 16-byte Folded Reload
	b	_free
	.cfi_endproc
                                        ; -- End function
	.p2align	2                               ; -- Begin function zu_f4_3std4math6vector3dotO3_t4_3std3mem7mem_ptr3PtrI1_b3f64t4_3std3mem7mem_ptr3PtrI1_b3f64b5usize
_zu_f4_3std4math6vector3dotO3_t4_3std3mem7mem_ptr3PtrI1_b3f64t4_3std3mem7mem_ptr3PtrI1_b3f64b5usize: ; @zu_f4_3std4math6vector3dotO3_t4_3std3mem7mem_ptr3PtrI1_b3f64t4_3std3mem7mem_ptr3PtrI1_b3f64b5usize
	.cfi_startproc
; %bb.0:
	stp	d13, d12, [sp, #-112]!          ; 16-byte Folded Spill
	stp	d11, d10, [sp, #16]             ; 16-byte Folded Spill
	stp	d9, d8, [sp, #32]               ; 16-byte Folded Spill
	stp	x24, x23, [sp, #48]             ; 16-byte Folded Spill
	stp	x22, x21, [sp, #64]             ; 16-byte Folded Spill
	stp	x20, x19, [sp, #80]             ; 16-byte Folded Spill
	stp	x29, x30, [sp, #96]             ; 16-byte Folded Spill
	add	x29, sp, #96
	.cfi_def_cfa w29, 16
	.cfi_offset w30, -8
	.cfi_offset w29, -16
	.cfi_offset w19, -24
	.cfi_offset w20, -32
	.cfi_offset w21, -40
	.cfi_offset w22, -48
	.cfi_offset w23, -56
	.cfi_offset w24, -64
	.cfi_offset b8, -72
	.cfi_offset b9, -80
	.cfi_offset b10, -88
	.cfi_offset b11, -96
	.cfi_offset b12, -104
	.cfi_offset b13, -112
	mov	x21, x2
	mov	x20, x1
	mov	x19, x0
	mov	x0, x2
	mov	w1, #4                          ; =0x4
	bl	_zg_div_usize
	cbz	x0, LBB6_4
; %bb.1:
	mov	x22, x0
	mov	x24, #0                         ; =0x0
	movi	d8, #0000000000000000
Lloh17:
	adrp	x23, l_.str.9@PAGE
Lloh18:
	add	x23, x23, l_.str.9@PAGEOFF
	movi	d9, #0000000000000000
	movi	d10, #0000000000000000
	movi	d11, #0000000000000000
LBB6_2:                                 ; =>This Inner Loop Header: Depth=1
	ldr	d0, [x19, x24, lsl #3]
	ldr	d1, [x20, x24, lsl #3]
	fmadd	d8, d0, d1, d8
	mov	x0, x24
	mov	w1, #1                          ; =0x1
	mov	x2, x23
	mov	w3, #14                         ; =0xe
	mov	w4, #28                         ; =0x1c
	bl	_zg_add_usize
	ldr	d12, [x19, x0, lsl #3]
	mov	x0, x24
	mov	w1, #1                          ; =0x1
	mov	x2, x23
	mov	w3, #14                         ; =0xe
	mov	w4, #44                         ; =0x2c
	bl	_zg_add_usize
	ldr	d0, [x20, x0, lsl #3]
	fmadd	d9, d12, d0, d9
	mov	x0, x24
	mov	w1, #2                          ; =0x2
	mov	x2, x23
	mov	w3, #15                         ; =0xf
	mov	w4, #28                         ; =0x1c
	bl	_zg_add_usize
	ldr	d12, [x19, x0, lsl #3]
	mov	x0, x24
	mov	w1, #2                          ; =0x2
	mov	x2, x23
	mov	w3, #15                         ; =0xf
	mov	w4, #44                         ; =0x2c
	bl	_zg_add_usize
	ldr	d0, [x20, x0, lsl #3]
	fmadd	d10, d12, d0, d10
	mov	x0, x24
	mov	w1, #3                          ; =0x3
	mov	x2, x23
	mov	w3, #16                         ; =0x10
	mov	w4, #28                         ; =0x1c
	bl	_zg_add_usize
	ldr	d12, [x19, x0, lsl #3]
	mov	x0, x24
	mov	w1, #3                          ; =0x3
	mov	x2, x23
	mov	w3, #16                         ; =0x10
	mov	w4, #44                         ; =0x2c
	bl	_zg_add_usize
	ldr	d0, [x20, x0, lsl #3]
	fmadd	d11, d12, d0, d11
	mov	x0, x24
	mov	w1, #17                         ; =0x11
	mov	w2, #16                         ; =0x10
	bl	_zg_add_int
	mov	x24, x0
	subs	x22, x22, #1
	b.ne	LBB6_2
; %bb.3:
	fadd	d0, d9, d8
	fadd	d1, d11, d10
	fadd	d0, d1, d0
	subs	x9, x21, x24
	b.hi	LBB6_5
	b	LBB6_12
LBB6_4:
	mov	x24, #0                         ; =0x0
	movi	d0, #0000000000000000
	subs	x9, x21, x24
	b.ls	LBB6_12
LBB6_5:
	cmp	x9, #8
	b.hs	LBB6_7
; %bb.6:
	mov	x8, x24
	b	LBB6_10
LBB6_7:
	and	x10, x9, #0xfffffffffffffff8
	add	x8, x24, x10
	lsl	x11, x24, #3
	add	x12, x11, #32
	add	x11, x20, x12
	add	x12, x19, x12
	mov	x13, x10
LBB6_8:                                 ; =>This Inner Loop Header: Depth=1
	ldp	q1, q2, [x12, #-32]
	ldp	q3, q4, [x12], #64
	ldp	q5, q6, [x11, #-32]
	ldp	q7, q16, [x11], #64
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
	b.ne	LBB6_8
; %bb.9:
	cmp	x9, x10
	b.eq	LBB6_12
LBB6_10:
	sub	x9, x21, x8
	lsl	x10, x8, #3
	add	x8, x20, x10
	add	x10, x19, x10
LBB6_11:                                ; =>This Inner Loop Header: Depth=1
	ldr	d1, [x10], #8
	ldr	d2, [x8], #8
	fmadd	d0, d1, d2, d0
	subs	x9, x9, #1
	b.ne	LBB6_11
LBB6_12:
	ldp	x29, x30, [sp, #96]             ; 16-byte Folded Reload
	ldp	x20, x19, [sp, #80]             ; 16-byte Folded Reload
	ldp	x22, x21, [sp, #64]             ; 16-byte Folded Reload
	ldp	x24, x23, [sp, #48]             ; 16-byte Folded Reload
	ldp	d9, d8, [sp, #32]               ; 16-byte Folded Reload
	ldp	d11, d10, [sp, #16]             ; 16-byte Folded Reload
	ldp	d13, d12, [sp], #112            ; 16-byte Folded Reload
	ret
	.loh AdrpAdd	Lloh17, Lloh18
	.cfi_endproc
                                        ; -- End function
	.p2align	2                               ; -- Begin function zu_f4_3std4math6vector16squared_distanceO3_t4_3std3mem7mem_ptr3PtrI1_b3f64t4_3std3mem7mem_ptr3PtrI1_b3f64b5usize
_zu_f4_3std4math6vector16squared_distanceO3_t4_3std3mem7mem_ptr3PtrI1_b3f64t4_3std3mem7mem_ptr3PtrI1_b3f64b5usize: ; @zu_f4_3std4math6vector16squared_distanceO3_t4_3std3mem7mem_ptr3PtrI1_b3f64t4_3std3mem7mem_ptr3PtrI1_b3f64b5usize
	.cfi_startproc
; %bb.0:
	stp	d15, d14, [sp, #-128]!          ; 16-byte Folded Spill
	stp	d13, d12, [sp, #16]             ; 16-byte Folded Spill
	stp	d11, d10, [sp, #32]             ; 16-byte Folded Spill
	stp	d9, d8, [sp, #48]               ; 16-byte Folded Spill
	stp	x24, x23, [sp, #64]             ; 16-byte Folded Spill
	stp	x22, x21, [sp, #80]             ; 16-byte Folded Spill
	stp	x20, x19, [sp, #96]             ; 16-byte Folded Spill
	stp	x29, x30, [sp, #112]            ; 16-byte Folded Spill
	add	x29, sp, #112
	.cfi_def_cfa w29, 16
	.cfi_offset w30, -8
	.cfi_offset w29, -16
	.cfi_offset w19, -24
	.cfi_offset w20, -32
	.cfi_offset w21, -40
	.cfi_offset w22, -48
	.cfi_offset w23, -56
	.cfi_offset w24, -64
	.cfi_offset b8, -72
	.cfi_offset b9, -80
	.cfi_offset b10, -88
	.cfi_offset b11, -96
	.cfi_offset b12, -104
	.cfi_offset b13, -112
	.cfi_offset b14, -120
	.cfi_offset b15, -128
	mov	x21, x2
	mov	x20, x1
	mov	x19, x0
	mov	x0, x2
	mov	w1, #4                          ; =0x4
	bl	_zg_div_usize
	cbz	x0, LBB7_4
; %bb.1:
	mov	x22, x0
	mov	x24, #0                         ; =0x0
	movi	d8, #0000000000000000
Lloh19:
	adrp	x23, l_.str.9@PAGE
Lloh20:
	add	x23, x23, l_.str.9@PAGEOFF
	movi	d9, #0000000000000000
	movi	d10, #0000000000000000
	movi	d11, #0000000000000000
LBB7_2:                                 ; =>This Inner Loop Header: Depth=1
	ldr	d0, [x19, x24, lsl #3]
	ldr	d1, [x20, x24, lsl #3]
	fsub	d12, d0, d1
	mov	x0, x24
	mov	w1, #1                          ; =0x1
	mov	x2, x23
	mov	w3, #30                         ; =0x1e
	mov	w4, #23                         ; =0x17
	bl	_zg_add_usize
	ldr	d13, [x19, x0, lsl #3]
	mov	x0, x24
	mov	w1, #1                          ; =0x1
	mov	x2, x23
	mov	w3, #30                         ; =0x1e
	mov	w4, #39                         ; =0x27
	bl	_zg_add_usize
	ldr	d0, [x20, x0, lsl #3]
	fsub	d13, d13, d0
	mov	x0, x24
	mov	w1, #2                          ; =0x2
	mov	x2, x23
	mov	w3, #31                         ; =0x1f
	mov	w4, #23                         ; =0x17
	bl	_zg_add_usize
	ldr	d14, [x19, x0, lsl #3]
	mov	x0, x24
	mov	w1, #2                          ; =0x2
	mov	x2, x23
	mov	w3, #31                         ; =0x1f
	mov	w4, #39                         ; =0x27
	bl	_zg_add_usize
	ldr	d0, [x20, x0, lsl #3]
	fsub	d14, d14, d0
	mov	x0, x24
	mov	w1, #3                          ; =0x3
	mov	x2, x23
	mov	w3, #32                         ; =0x20
	mov	w4, #23                         ; =0x17
	bl	_zg_add_usize
	ldr	d15, [x19, x0, lsl #3]
	mov	x0, x24
	mov	w1, #3                          ; =0x3
	mov	x2, x23
	mov	w3, #32                         ; =0x20
	mov	w4, #39                         ; =0x27
	bl	_zg_add_usize
	ldr	d0, [x20, x0, lsl #3]
	fsub	d0, d15, d0
	fmadd	d8, d12, d12, d8
	fmadd	d9, d13, d13, d9
	fmadd	d10, d14, d14, d10
	fmadd	d11, d0, d0, d11
	mov	x0, x24
	mov	w1, #35                         ; =0x23
	mov	w2, #15                         ; =0xf
	bl	_zg_add_int
	mov	x24, x0
	subs	x22, x22, #1
	b.ne	LBB7_2
; %bb.3:
	fadd	d0, d9, d8
	fadd	d1, d11, d10
	fadd	d0, d1, d0
	subs	x9, x21, x24
	b.hi	LBB7_5
	b	LBB7_12
LBB7_4:
	mov	x24, #0                         ; =0x0
	movi	d0, #0000000000000000
	subs	x9, x21, x24
	b.ls	LBB7_12
LBB7_5:
	cmp	x9, #8
	b.hs	LBB7_7
; %bb.6:
	mov	x8, x24
	b	LBB7_10
LBB7_7:
	and	x10, x9, #0xfffffffffffffff8
	add	x8, x24, x10
	lsl	x11, x24, #3
	add	x12, x11, #32
	add	x11, x20, x12
	add	x12, x19, x12
	mov	x13, x10
LBB7_8:                                 ; =>This Inner Loop Header: Depth=1
	ldp	q1, q2, [x12, #-32]
	ldp	q3, q4, [x12], #64
	ldp	q5, q6, [x11, #-32]
	ldp	q7, q16, [x11], #64
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
	b.ne	LBB7_8
; %bb.9:
	cmp	x9, x10
	b.eq	LBB7_12
LBB7_10:
	sub	x9, x21, x8
	lsl	x10, x8, #3
	add	x8, x20, x10
	add	x10, x19, x10
LBB7_11:                                ; =>This Inner Loop Header: Depth=1
	ldr	d1, [x10], #8
	ldr	d2, [x8], #8
	fsub	d1, d1, d2
	fmadd	d0, d1, d1, d0
	subs	x9, x9, #1
	b.ne	LBB7_11
LBB7_12:
	ldp	x29, x30, [sp, #112]            ; 16-byte Folded Reload
	ldp	x20, x19, [sp, #96]             ; 16-byte Folded Reload
	ldp	x22, x21, [sp, #80]             ; 16-byte Folded Reload
	ldp	x24, x23, [sp, #64]             ; 16-byte Folded Reload
	ldp	d9, d8, [sp, #48]               ; 16-byte Folded Reload
	ldp	d11, d10, [sp, #32]             ; 16-byte Folded Reload
	ldp	d13, d12, [sp, #16]             ; 16-byte Folded Reload
	ldp	d15, d14, [sp], #128            ; 16-byte Folded Reload
	ret
	.loh AdrpAdd	Lloh19, Lloh20
	.cfi_endproc
                                        ; -- End function
	.p2align	2                               ; -- Begin function zg_add_usize
_zg_add_usize:                          ; @zg_add_usize
	.cfi_startproc
; %bb.0:
	adds	x0, x0, x1
	b.hs	LBB8_2
; %bb.1:
	ret
LBB8_2:
	stp	x29, x30, [sp, #-16]!           ; 16-byte Folded Spill
	mov	x29, sp
	.cfi_def_cfa w29, 16
	.cfi_offset w30, -8
	.cfi_offset w29, -16
Lloh21:
	adrp	x8, l_.str.7@PAGE
Lloh22:
	add	x8, x8, l_.str.7@PAGEOFF
	mov	x0, x2
	mov	x1, x3
	mov	x2, x4
	mov	x3, x8
	bl	_zg_trap
	.loh AdrpAdd	Lloh21, Lloh22
	.cfi_endproc
                                        ; -- End function
	.p2align	2                               ; -- Begin function zg_print_bytes
_zg_print_bytes:                        ; @zg_print_bytes
	.cfi_startproc
; %bb.0:
	mov	x2, x1
Lloh23:
	adrp	x8, ___stdoutp@GOTPAGE
Lloh24:
	ldr	x8, [x8, ___stdoutp@GOTPAGEOFF]
Lloh25:
	ldr	x3, [x8]
	mov	w1, #1                          ; =0x1
	b	_fwrite
	.loh AdrpLdrGotLdr	Lloh23, Lloh24, Lloh25
	.cfi_endproc
                                        ; -- End function
	.p2align	2                               ; -- Begin function zg_print_bool
_zg_print_bool:                         ; @zg_print_bool
	.cfi_startproc
; %bb.0:
Lloh26:
	adrp	x8, l_.str.11@PAGE
Lloh27:
	add	x8, x8, l_.str.11@PAGEOFF
Lloh28:
	adrp	x9, l_.str.10@PAGE
Lloh29:
	add	x9, x9, l_.str.10@PAGEOFF
	cmp	w0, #0
	csel	x0, x9, x8, ne
	mov	w8, #4                          ; =0x4
	cinc	x1, x8, eq
	b	_zg_print_bytes
	.loh AdrpAdd	Lloh28, Lloh29
	.loh AdrpAdd	Lloh26, Lloh27
	.cfi_endproc
                                        ; -- End function
	.p2align	2                               ; -- Begin function zg_print_nl
_zg_print_nl:                           ; @zg_print_nl
	.cfi_startproc
; %bb.0:
Lloh30:
	adrp	x8, ___stdoutp@GOTPAGE
Lloh31:
	ldr	x8, [x8, ___stdoutp@GOTPAGEOFF]
Lloh32:
	ldr	x1, [x8]
	mov	w0, #10                         ; =0xa
	b	_fputc
	.loh AdrpLdrGotLdr	Lloh30, Lloh31, Lloh32
	.cfi_endproc
                                        ; -- End function
	.p2align	2                               ; -- Begin function zg_div_usize
_zg_div_usize:                          ; @zg_div_usize
	.cfi_startproc
; %bb.0:
	udiv	x0, x0, x1
	ret
	.cfi_endproc
                                        ; -- End function
	.p2align	2                               ; -- Begin function zu_f5_3std3mem9mem_arena5Arena3rawO3_t4_3std3mem9mem_arena5Arenab5usizeb5usize
_zu_f5_3std3mem9mem_arena5Arena3rawO3_t4_3std3mem9mem_arena5Arenab5usizeb5usize: ; @zu_f5_3std3mem9mem_arena5Arena3rawO3_t4_3std3mem9mem_arena5Arenab5usizeb5usize
	.cfi_startproc
; %bb.0:
	ldr	x8, [x0, #32]
	cbz	x8, LBB13_2
; %bb.1:
	sub	sp, sp, #64
	stp	x29, x30, [sp, #48]             ; 16-byte Folded Spill
	add	x29, sp, #48
	.cfi_def_cfa w29, 16
	.cfi_offset w30, -8
	.cfi_offset w29, -16
	ldr	x9, [x0, #40]
	ldp	q0, q1, [x0]
	stp	q0, q1, [sp]
	stp	x8, x9, [sp, #32]
	mov	x1, sp
	bl	_zu_f5_3std3mem9mem_arena5Arena4bumpO4_t4_3std3mem9mem_arena5Arenat4_3std3mem9mem_arena10ArenaStateb5usizeb5usize
	ldp	x29, x30, [sp, #48]             ; 16-byte Folded Reload
	add	sp, sp, #64
	ret
LBB13_2:
	b	_zu_f5_3std3mem9mem_arena5Arena5chainO3_t4_3std3mem9mem_arena5Arenab5usizeb5usize
	.cfi_endproc
                                        ; -- End function
	.p2align	2                               ; -- Begin function zg_sub_usize
_zg_sub_usize:                          ; @zg_sub_usize
	.cfi_startproc
; %bb.0:
	subs	x0, x0, x1
	b.lo	LBB14_2
; %bb.1:
	ret
LBB14_2:
	stp	x29, x30, [sp, #-16]!           ; 16-byte Folded Spill
	mov	x29, sp
	.cfi_def_cfa w29, 16
	.cfi_offset w30, -8
	.cfi_offset w29, -16
Lloh33:
	adrp	x0, l_.str.4@PAGE
Lloh34:
	add	x0, x0, l_.str.4@PAGEOFF
Lloh35:
	adrp	x8, l_.str.7@PAGE
Lloh36:
	add	x8, x8, l_.str.7@PAGEOFF
	mov	x1, x2
	mov	x2, x3
	mov	x3, x8
	bl	_zg_trap
	.loh AdrpAdd	Lloh35, Lloh36
	.loh AdrpAdd	Lloh33, Lloh34
	.cfi_endproc
                                        ; -- End function
	.p2align	2                               ; -- Begin function zu_f5_3std3mem9mem_arena5Arena5chainO3_t4_3std3mem9mem_arena5Arenab5usizeb5usize
_zu_f5_3std3mem9mem_arena5Arena5chainO3_t4_3std3mem9mem_arena5Arenab5usizeb5usize: ; @zu_f5_3std3mem9mem_arena5Arena5chainO3_t4_3std3mem9mem_arena5Arenab5usizeb5usize
	.cfi_startproc
; %bb.0:
	sub	sp, sp, #80
	stp	x22, x21, [sp, #32]             ; 16-byte Folded Spill
	stp	x20, x19, [sp, #48]             ; 16-byte Folded Spill
	stp	x29, x30, [sp, #64]             ; 16-byte Folded Spill
	add	x29, sp, #64
	.cfi_def_cfa w29, 16
	.cfi_offset w30, -8
	.cfi_offset w29, -16
	.cfi_offset w19, -24
	.cfi_offset w20, -32
	.cfi_offset w21, -40
	.cfi_offset w22, -48
	mov	x19, x0
	ldp	q0, q1, [x0]
	stp	q0, q1, [sp]
	ldr	x21, [x0, #32]
	mov	w0, #64                         ; =0x40
	mov	w1, #8                          ; =0x8
	bl	_zg_div_usize
Lloh37:
	adrp	x20, l_.str.4@PAGE
Lloh38:
	add	x20, x20, l_.str.4@PAGEOFF
	mov	w1, #16                         ; =0x10
	mov	x2, x20
	mov	w3, #58                         ; =0x3a
	mov	w4, #30                         ; =0x1e
	bl	_zg_add_usize
	mov	w1, #8208                       ; =0x2010
	mov	x2, x20
	mov	w3, #58                         ; =0x3a
	mov	w4, #38                         ; =0x26
	bl	_zg_add_usize
	mov	w8, #65536                      ; =0x10000
	cmp	x0, #16, lsl #12                ; =65536
	csel	x20, x0, x8, hi
	add	x0, x20, #24
	bl	_malloc
	cbz	x0, LBB15_2
; %bb.1:
	add	x8, x0, #24
	stp	x21, x8, [x0]
	str	x20, [x0, #16]
	ldp	q1, q0, [sp]
	stp	q1, q0, [x19]
	stp	x0, xzr, [x19, #32]
	mov	x0, x19
	bl	_zu_f5_3std3mem9mem_arena5Arena3rawO3_t4_3std3mem9mem_arena5Arenab5usizeb5usize
	b	LBB15_3
LBB15_2:
	mov	x1, #0                          ; =0x0
	mov	w0, #1                          ; =0x1
LBB15_3:
	ldp	x29, x30, [sp, #64]             ; 16-byte Folded Reload
	ldp	x20, x19, [sp, #48]             ; 16-byte Folded Reload
	ldp	x22, x21, [sp, #32]             ; 16-byte Folded Reload
	add	sp, sp, #80
	ret
	.loh AdrpAdd	Lloh37, Lloh38
	.cfi_endproc
                                        ; -- End function
	.p2align	2                               ; -- Begin function zu_f5_3std3mem9mem_arena5Arena4bumpO4_t4_3std3mem9mem_arena5Arenat4_3std3mem9mem_arena10ArenaStateb5usizeb5usize
_zu_f5_3std3mem9mem_arena5Arena4bumpO4_t4_3std3mem9mem_arena5Arenat4_3std3mem9mem_arena10ArenaStateb5usizeb5usize: ; @zu_f5_3std3mem9mem_arena5Arena4bumpO4_t4_3std3mem9mem_arena5Arenat4_3std3mem9mem_arena10ArenaStateb5usizeb5usize
	.cfi_startproc
; %bb.0:
	sub	sp, sp, #112
	stp	x26, x25, [sp, #32]             ; 16-byte Folded Spill
	stp	x24, x23, [sp, #48]             ; 16-byte Folded Spill
	stp	x22, x21, [sp, #64]             ; 16-byte Folded Spill
	stp	x20, x19, [sp, #80]             ; 16-byte Folded Spill
	stp	x29, x30, [sp, #96]             ; 16-byte Folded Spill
	add	x29, sp, #96
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
	mov	x21, x1
	mov	x19, x0
	ldp	x8, x22, [x1, #32]
	ldp	x24, x25, [x8, #8]
	mov	w0, #64                         ; =0x40
	mov	w1, #8                          ; =0x8
	bl	_zg_div_usize
	mov	x20, x0
	mov	x0, x22
	mov	x1, x20
	bl	_zu_f4_3std3mem9mem_arena8align_upO2_b5usizeb5usize
Lloh39:
	adrp	x23, l_.str.4@PAGE
Lloh40:
	add	x23, x23, l_.str.4@PAGEOFF
	mov	x1, x20
	mov	x2, x23
	mov	w3, #41                         ; =0x29
	mov	w4, #23                         ; =0x17
	bl	_zg_add_usize
	mov	w1, #16                         ; =0x10
	bl	_zu_f4_3std3mem9mem_arena8align_upO2_b5usizeb5usize
	mov	x22, x0
	mov	w1, #8208                       ; =0x2010
	mov	x2, x23
	mov	w3, #42                         ; =0x2a
	mov	w4, #16                         ; =0x10
	bl	_zg_add_usize
	cmp	x0, x25
	b.ls	LBB16_2
; %bb.1:
	mov	x0, x19
	bl	_zu_f5_3std3mem9mem_arena5Arena5chainO3_t4_3std3mem9mem_arena5Arenab5usizeb5usize
	b	LBB16_3
LBB16_2:
	ldp	q0, q1, [x21]
	stp	q0, q1, [sp]
	ldr	x21, [x21, #32]
Lloh41:
	adrp	x2, l_.str.4@PAGE
Lloh42:
	add	x2, x2, l_.str.4@PAGEOFF
	mov	w23, #8208                      ; =0x2010
	mov	x0, x22
	mov	w1, #8208                       ; =0x2010
	mov	w3, #46                         ; =0x2e
	mov	w4, #70                         ; =0x46
	bl	_zg_add_usize
	mov	x8, x0
	mov	x0, #0                          ; =0x0
	ldp	q0, q1, [sp]
	stp	q0, q1, [x19]
	stp	x21, x8, [x19, #32]
	add	x1, x24, x22
	sub	x8, x1, x20
	str	x23, [x8]
LBB16_3:
	ldp	x29, x30, [sp, #96]             ; 16-byte Folded Reload
	ldp	x20, x19, [sp, #80]             ; 16-byte Folded Reload
	ldp	x22, x21, [sp, #64]             ; 16-byte Folded Reload
	ldp	x24, x23, [sp, #48]             ; 16-byte Folded Reload
	ldp	x26, x25, [sp, #32]             ; 16-byte Folded Reload
	add	sp, sp, #112
	ret
	.loh AdrpAdd	Lloh39, Lloh40
	.loh AdrpAdd	Lloh41, Lloh42
	.cfi_endproc
                                        ; -- End function
	.p2align	2                               ; -- Begin function zu_f4_3std3mem9mem_arena8align_upO2_b5usizeb5usize
_zu_f4_3std3mem9mem_arena8align_upO2_b5usizeb5usize: ; @zu_f4_3std3mem9mem_arena8align_upO2_b5usizeb5usize
	.cfi_startproc
; %bb.0:
	stp	x20, x19, [sp, #-32]!           ; 16-byte Folded Spill
	stp	x29, x30, [sp, #16]             ; 16-byte Folded Spill
	add	x29, sp, #16
	.cfi_def_cfa w29, 16
	.cfi_offset w30, -8
	.cfi_offset w29, -16
	.cfi_offset w19, -24
	.cfi_offset w20, -32
	mov	x19, x1
Lloh43:
	adrp	x2, l_.str.4@PAGE
Lloh44:
	add	x2, x2, l_.str.4@PAGEOFF
	mov	w3, #19                         ; =0x13
	mov	w4, #21                         ; =0x15
	bl	_zg_add_usize
	mov	w1, #1                          ; =0x1
	mov	w2, #19                         ; =0x13
	mov	w3, #29                         ; =0x1d
	bl	_zg_sub_usize
	mov	x20, x0
	mov	x1, x19
	bl	_zg_mod_usize
	mov	x1, x0
	mov	x0, x20
	mov	w2, #20                         ; =0x14
	mov	w3, #12                         ; =0xc
	ldp	x29, x30, [sp, #16]             ; 16-byte Folded Reload
	ldp	x20, x19, [sp], #32             ; 16-byte Folded Reload
	b	_zg_sub_usize
	.loh AdrpAdd	Lloh43, Lloh44
	.cfi_endproc
                                        ; -- End function
	.p2align	2                               ; -- Begin function zg_mod_usize
_zg_mod_usize:                          ; @zg_mod_usize
	.cfi_startproc
; %bb.0:
	cbz	x1, LBB18_2
; %bb.1:
	udiv	x8, x0, x1
	msub	x0, x8, x1, x0
	ret
LBB18_2:
	stp	x29, x30, [sp, #-16]!           ; 16-byte Folded Spill
	mov	x29, sp
	.cfi_def_cfa w29, 16
	.cfi_offset w30, -8
	.cfi_offset w29, -16
Lloh45:
	adrp	x0, l_.str.4@PAGE
Lloh46:
	add	x0, x0, l_.str.4@PAGEOFF
Lloh47:
	adrp	x3, l_.str.5@PAGE
Lloh48:
	add	x3, x3, l_.str.5@PAGEOFF
	mov	w1, #20                         ; =0x14
	mov	w2, #22                         ; =0x16
	bl	_zg_trap
	.loh AdrpAdd	Lloh47, Lloh48
	.loh AdrpAdd	Lloh45, Lloh46
	.cfi_endproc
                                        ; -- End function
	.p2align	2                               ; -- Begin function zg_add_int
_zg_add_int:                            ; @zg_add_int
	.cfi_startproc
; %bb.0:
	adds	x0, x0, #4
	b.vs	LBB19_2
; %bb.1:
	ret
LBB19_2:
	stp	x29, x30, [sp, #-16]!           ; 16-byte Folded Spill
	mov	x29, sp
	.cfi_def_cfa w29, 16
	.cfi_offset w30, -8
	.cfi_offset w29, -16
Lloh49:
	adrp	x0, l_.str.9@PAGE
Lloh50:
	add	x0, x0, l_.str.9@PAGEOFF
Lloh51:
	adrp	x3, l_.str.7@PAGE
Lloh52:
	add	x3, x3, l_.str.7@PAGEOFF
	bl	_zg_trap
	.loh AdrpAdd	Lloh51, Lloh52
	.loh AdrpAdd	Lloh49, Lloh50
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

l_.str.5:                               ; @.str.5
	.asciz	"divide by zero"

l_.str.7:                               ; @.str.7
	.asciz	"integer overflow"

l_.str.9:                               ; @.str.9
	.asciz	"std/math/vector.zen"

l_.str.10:                              ; @.str.10
	.asciz	"true"

l_.str.11:                              ; @.str.11
	.asciz	"false"

.subsections_via_symbols
