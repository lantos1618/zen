tests/corpus/closures-capture/a_mutation_before_defer_is_invisible -- fill_record copies at registration, not block exit; reading the frame slot at thunk time instead prints 99
tests/corpus/closures-capture/b_two_writers_one_snapshot_each -- one shared record cell for two defers (or a single fill-at-exit) makes both prints agree; per-registration fields give 6 then 50
tests/corpus/closures-capture/c_byref_param_capture_aliases_the_caller -- ref_field emits `T *` for a captured `::` param; flipping it to by-value (declarator) prints 5 instead of 2505
tests/corpus/closures-capture/d_capture_walk_descends_nested_bodies -- captures() stops recursing into nested blocks / lambdas / match arms and the record loses `n`; four reads in four shapes all go wrong
tests/corpus/closures-capture/e_shadowing_bind_is_not_a_capture -- write_unpack reuses the record slot for the body's own `v ::= 999` bind instead of fresh storage: shadow prints 22-side values or main's v moves
tests/corpus/closures-capture/f_loop_body_accumulates_through_a_captured_local -- loop-body store into an outer binding lowered as declare-fresh-per-pass: sum prints 16 (last term) not 30
tests/corpus/closures-capture/g_inner_block_snapshot_outer_frame -- inner block registers on the OUTER record or shares its cell: inner/outer prints collapse to one value; live-frame read makes both say 7
tests/corpus/closures-capture/h_lambda_argument_reads_the_live_binding -- run_lambda skips enter_frame(cl.floor) so the inlined lambda reads a stale copy: second call prints 45 again, deferred/live lines converge
tests/corpus/closures-capture/i_local_function_reads_the_live_frame -- declare_local_function taking its home after binding its own name, or copying captures at the declaration, prints live 1 / stored 7
tests/corpus/closures-capture/j_local_function_try_returns_from_its_writer -- lowering a local function with its own return target makes `.try()` return from pick: picked line prints and 3 comes back instead of -1

NOTES ON WHAT THE PROBING FOUND

1. A function declared in a body (`bump = (by: i64) { n = n + by; }`, no
   `;`) is a local closure called by name: see i_ and j_ and DESIGN.md
   "A function declared in a body is a local closure".

2. `str + str` is rejected by cc, not by zen: `tag = tag + "b";` emits C
   with binary `+` on two zg_str structs ("invalid operands"). Zen has no
   string concatenation method visible in std/text, so this may just be
   unsupported source, but the failure lands in the C compiler rather
   than as a Zen diagnostic -- worth a look.

3. An untyped integer literal binds i64, so `big ::= 18446744073709551615`
   silently becomes -1 inside a deferred print while `body` prints it via
   a u64-typed slot correctly... actually: `big ::= <u64 max>` prints -1
   in BOTH places; only `big: u64 ::= ...` is correct. Untyped literal
   defaults to signed i64 and wraps. Plausible-by-design (literals settle
   i64), recording it here because a capture test tripped over it first.

TESTS: 10
