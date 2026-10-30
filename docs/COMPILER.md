# Zen compiler reference (v0.8 core profile)

Language-neutral pseudocode for the compiler's contract. Follow one native path: validated IR → selected templates → physical assembly → text. MacArm64 is the primary target; Linux differences are in Appendix A. The language it compiles is [ZEN_LANGUAGE.md](ZEN_LANGUAGE.md); building, packages and FFI are [BUILD_AND_PACKAGES.md](BUILD_AND_PACKAGES.md).

This is the v0.7 reference (in git history, commit 4955d5932) trimmed to a core profile for a small, elegant compiler with a low attack surface:

- **Removed from the core:** atomics (`AtomicLoad/Store/Rmw`, `CompareExchange`, `Fence`, `MemoryOrder`), `NativeAddress` and `IntegerToPointer`, the browser/Wasm route, and the coverage registry. Each can return later as a separate, gated feature.
- **Routes:** the C route and MacArm64 / LinuxArm64. LinuxX64 (Appendix A.2) is the optional second ISA.
- **Added:** C.1–C.4 lowering for `.match`, closures and non-local exit, trait values, cleanups (replacing C-style if/while); H. backend organisation (templates as data, one descriptor table); I. frontend stages, generics, flow, comptime, diagnostics; J. security and limits; K. bootstrap from the old compiler; L. runtime and T0 std.

Everything kept is word for word v0.7 unless noted.

## Contents

0. The pipeline
1. `Ir`: what the backend receives
2. Target facts: MacArm64
3. `.lower(target)`: one template per instruction
4. `.alloc()`: homes, frame, code
5. `.write(sink)`: text and toolchain
6. Worked examples
- A. Other targets: LinuxArm64, LinuxX64
- B. Exact semantics and interpreter
- C. Source modules, storage, and SEMA
- D. C route
- E. Coverage, tests, and evidence
- F. Build order and decisions
- G. Physical instruction inventory
- H. Backend organisation: templates as data
- I. Frontend: passes and budgets
- J. Security
- K. Bootstrap
- L. Runtime and the T0 standard library

## 0. The pipeline

~~~text
source.lex()            -> Tokens       frontend
      .parse()          -> Ast          frontend
      .sema()           -> Ir           checked and frozen; stages in Appendix I.1

Ir.lower(target)        -> Mir          selection and template verification
Mir.alloc()             -> Asm          homes, frames, physical verification
Asm.write(sink)         -> Result<Unit, WriteError>

driver.assemble(file)   -> Object       external tool
driver.link(objects)    -> Artifact     external tool
~~~

Rules of the chain:

- lower and alloc return new stage types; only their checked constructors can create them. write writes to a sink and returns success or an output error. No stage mutates its predecessor.
- Transformations return output or diagnostics. The writer returns output errors. No operation silently repairs its input.
- `IrBuilder.finish()` is the other way to get an `Ir`. It runs the same validation as the frontend's `.lower()`.
- Other routes leave from Ir: run (reference interpreter), write_c (C), and dump. Their direction is preserved in the appendices.

The whole design is four rules:

1. IR registers are mutable variables, not SSA. A register can be assigned on many paths.
2. Every register gets one home for the whole function: a register or a typed spill slot. The home pools and ABI decide which registers need call saves.
3. A template reads its inputs into fixed scratch registers, computes, then writes its outputs to their homes. Scratch never survives a template.
4. Every specified program trap branches to a terminal stub. Invalid low-level memory is not promised a native trap.

What follows from them:

- Mutable registers need no phi elimination. The C route maps registers to locals one to one.
- Spilling uses the template’s reserved work registers: a read loads from the slot, a write stores to it. Allocation runs once. There is no spill loop.
- Home pools exclude the ABI argument registers, so they never overlap. Argument moves are a plain sequence, never a parallel move, and calls preserve live homes that the target ABI may clobber, notably x86-64 floats.
- Homes never move, so there are no copies on CFG edges and no critical-edge splitting.
- The cost is conservative code with extra moves; section 6.1 makes that overhead visible. That is accepted. There is no optimizer here.

Notation: enums are closed, structs have named fields, IDs are distinct integer types. `List`, `Map`, `Set`, `Option` and exact integers are ordinary primitives. Arithmetic is mathematical unless it names a machine width. A **diagnostic** stops compilation, a **trap** is a program result, and they never mix. Interpreter faults are a third, separate outcome.

## 1. `Ir`: what the backend receives

`.sema()` (or `IrBuilder.finish()`) hands over an `Ir`: a frozen `Module` that passed every check in 1.2. The backend relies on validation and does not re-check types.

### 1.1 Records

~~~text
distinct FunctionId, SignatureId, RegisterId, BlockId, InstructionId,
         SymbolId, StackObjectId, GlobalId: U32

enum ScalarType     { Bool, I8, U8, I16, U16, I32, U32, I64, U64, F32, F64,
                      Pointer, FunctionPointer(SignatureId) }
enum Constant       { Bool(Boolean), Integer { type: ScalarType, bits: U64 },
                      F32Bits(U32), F64Bits(U64), NullPointer, NullFunctionPointer(SignatureId) }
enum Value          { Register(RegisterId), Constant(Constant) }

enum Overflow       { Checked, Wrapping }
enum IntOp          { Add(Overflow), Subtract(Overflow), Multiply(Overflow), Divide, Remainder,
                      And, Or, Xor, ShiftLeft, ShiftRightLogical, ShiftRightArithmetic }
enum FloatOp        { Add, Subtract, Multiply, Divide }
enum IntPredicate   { Equal, NotEqual, Less, LessEqual, Greater, GreaterEqual }
enum FloatPredicate { Equal, NotEqual, Less, LessEqual, Greater, GreaterEqual, Unordered }
enum ConvertOp      { IntegerChecked, IntegerWrapping, IntegerToFloat, FloatToIntegerChecked,
                      FloatWidth, BoolToInteger, PointerToInteger, Bitcast }
enum AddressBase    { Register(RegisterId), StackObject(StackObjectId), Symbol(SymbolId) }
enum Callee         { Function(FunctionId), Register(RegisterId) }
enum Access         { Ordinary, Volatile }
struct MemoryAccess { alignment: U32, access: Access }
enum TrapCode       { IntegerOverflow, DivisionByZero, InvalidShift, InvalidConversion,
                      InvalidValue, StackOverflow, Explicit(U32) }

enum Instruction {
    Set { dst: RegisterId, value: Value },
    Select { dst: RegisterId, condition: Value, yes: Value, no: Value },
    IntBinary { dst: RegisterId, op: IntOp, lhs: Value, rhs: Value },
    FloatBinary { dst: RegisterId, op: FloatOp, lhs: Value, rhs: Value },
    FloatNegate { dst: RegisterId, value: Value },
    IntCompare { dst: RegisterId, op: IntPredicate, lhs: Value, rhs: Value },
    PointerCompare { dst: RegisterId, op: IntPredicate, lhs: Value, rhs: Value },
    FloatCompare { dst: RegisterId, op: FloatPredicate, lhs: Value, rhs: Value },
    Convert { dst: RegisterId, op: ConvertOp, value: Value },
    Address { dst: RegisterId, base: AddressBase, byte_offset: Value },
    Load { dst: RegisterId, address: Value, memory: MemoryAccess },
    Store { address: Value, value: Value, memory: MemoryAccess },
    Call { dst: Option<RegisterId>, callee: Callee, args: List<Value> },
}
struct SwitchCase { value: Constant, target: BlockId }
enum Exit {
    Jump { target: BlockId },        Branch { condition, yes: BlockId, no: BlockId },
    Switch { value, cases: List<SwitchCase>, default: BlockId },
    Return { value: Option<Value> }, CallNever { callee: Callee, args: List<Value> },
    Trap { code: TrapCode }
}

enum ReturnContract    { Returns(Option<ScalarType>), Never }
enum Abi               { AppleArm64, Aapcs64Linux, SysVAMD64 }
enum Backend { NativeAssembly, C }
enum CallingConvention { PlatformDefault, Exact(Abi) }
struct Signature  { parameters: List<ScalarType>, result: ReturnContract,
                    calling_convention: CallingConvention }
enum SymbolKind   { Function, Data }
enum Linkage      { Internal, ExternalDefinition, ExternalImport }
struct Symbol     { id: SymbolId, kind: SymbolKind, linkage: Linkage,
                    external_name: Option<String> }
enum InitializerPart { Bytes(List<U8>), ZeroBytes(U64),
                       Address { symbol: SymbolId, addend: I64, type: ScalarType } }
struct Export     { symbol: SymbolId, definition: FunctionId | GlobalId }
struct Global     { symbol: SymbolId, size: U64, alignment: U32, mutable: Boolean,
                    initializer: List<InitializerPart> }
struct StackObject { id: StackObjectId, size: U64, alignment: U32 }
struct InstructionRecord { id: InstructionId, instruction: Instruction }
struct Block      { id: BlockId, instructions: List<InstructionRecord>, exit: Exit }
struct Function   { id: FunctionId, symbol: SymbolId, signature: SignatureId,
                    parameters: List<RegisterId>,
                    register_types: Table<RegisterId, ScalarType>,
                    objects: Table<StackObjectId, StackObject>,
                    entry: BlockId, blocks: Table<BlockId, Block> }
struct Import     { function: FunctionId, symbol: SymbolId, signature: SignatureId }
struct Module     { signatures: Table<SignatureId, Signature>,
                    symbols: Table<SymbolId, Symbol>,
                    globals: Table<GlobalId, Global>,
                    imports: Table<FunctionId, Import>,
                    functions: Table<FunctionId, Function>,
                    exports: List<Export>,
                    trap_handler: Option<FunctionId> }   // an Import of type (U32) -> Never
~~~

Ir is a private wrapper around a validated, frozen Module; IrBuilder.finish performs validation before constructing it.

An export binds a defined function/global to an ExternalDefinition symbol; private definitions use generated internal symbols.

### 1.2 What validation guarantees

| Item | Guarantee |
| --- | --- |
| IDs and references | Unique, bounded, every reference resolves; every block has exactly one exit; successors exist |
| `Set`, `Select` | Source and destination types are equal; the condition is `Bool` |
| `IntBinary` | `lhs`, `rhs` and `dst` share one integer type; a shift count may be any integer type |
| `IntCompare` | Equal integer types; `Bool` and `FunctionPointer` allow only `Equal`/`NotEqual`; `dst` is `Bool` |
| `PointerCompare` | Data pointers; `dst` is `Bool` |
| Float operations | Equal float types; compare `dst` is `Bool` |
| `Convert` | Legal pairs only. `IntegerWrapping`, `IntegerChecked`: integer to integer. `IntegerToFloat`: integer to float. `FloatToIntegerChecked`: float to integer. `FloatWidth`: F32 to F64 or back. `BoolToInteger`: Bool to integer. `PointerToInteger`: Pointer to U64. `Bitcast`: equal widths, between integer and float only |
| `Address` | Data base gives `Pointer`; a function symbol gives its `FunctionPointer`, offset statically 0; the offset is an integer |
| `Load`, `Store` | Address is `Pointer`; value is a scalar; alignment is a power of two |
| `Call`, `CallNever` | Signature and arity match; `Never` callees appear only in `CallNever` |
| `Switch` | Integer selector; cases unique and of the selector's type |
| `Return` | Matches the signature; absent from `Never` functions |
| Constants | `Integer` bits fit the type's width |
| Symbols | `ExternalDefinition` and `ExternalImport` symbols have an external name; external names are unique and match `[A-Za-z_][A-Za-z0-9_]*` |
| `trap_handler` | If present, an `Import` of type `(U32) -> Never` |
| Globals | Symbol kind `Data`, defined here; alignment a power of two; parts add up to exactly `size`; `Address` parts are `Pointer` or `FunctionPointer` (8 bytes) |
| Stack objects | Size above 0; alignment a power of two |
| Registers | Definitely initialized before every use (1.4) |

Trap codes, as program results: `IntegerOverflow` 1, `DivisionByZero` 2, `InvalidShift` 3, `InvalidConversion` 4 (also failed checked integer casts), `InvalidValue` 5, `StackOverflow` 6 (stack-checked profile only, §4.4), `Explicit(n)` is `n`, and validation requires `n >= 65536`.

### 1.3 Uses and definitions

One exhaustive visitor is shared by initialization and liveness. Reads retain order and multiplicity; dataflow turns them into sets. Constants, symbols, and block IDs are not register reads.

~~~text
regs(Register(r)) = [r]
regs(Constant(_)) = []
callee_regs(Function(_)) = []
callee_regs(Register(r)) = [r]
base_regs(AddressBase.Register(r)) = [r]
base_regs(StackObject(_) | Symbol(_)) = []

uses(item):
    match item:
        Template(t): return [r for Read(Register(r), _) in t.steps]
        Set(_, value) | FloatNegate(_, value) | Convert(_, _, value):
            return regs(value)
        IntBinary(_, _, a, b) | FloatBinary(_, _, a, b) |
        IntCompare(_, _, a, b) | FloatCompare(_, _, a, b) |
        PointerCompare(_, _, a, b):
            return regs(a) + regs(b)
        Select(_, c, yes, no): return regs(c) + regs(yes) + regs(no)
        Address(_, base, offset): return base_regs(base) + regs(offset)
        Load(_, address, _): return regs(address)
        Store(address, value, _):
            return regs(address) + regs(value)
        Call(_, callee, arguments) | CallNever(callee, arguments):
            return callee_regs(callee) + concatenate(regs(v) for v in arguments)
        Branch(condition, _, _): return regs(condition)
        Switch(value, _, _): return regs(value)
        Return(Some(value)): return regs(value)
        Return(None) | Jump(_) | Trap(_): return []

defs(item):
    match item:
        Template(t): return [r for Commit(r, _) in t.steps]
        Set(dst, _) | Select(dst, _, _, _) |
        IntBinary(dst, _, _, _) | FloatBinary(dst, _, _, _) |
        FloatNegate(dst, _) | IntCompare(dst, _, _, _) |
        PointerCompare(dst, _, _, _) | FloatCompare(dst, _, _, _) |
        Convert(dst, _, _) | Address(dst, _, _) |
        Load(dst, _, _):
            return [dst]
        Call(Some(dst), _, _): return [dst]
        Store(_, _, _) |
        Call(None, _, _) | Jump(_) | Branch(_, _, _) |
        Switch(_, _, _) | Return(_) | CallNever(_, _) | Trap(_):
            return []
~~~

InstructionRecord is unwrapped before visiting.

### 1.4 Definite initialization

~~~text
check_definite_initialization(function):
    blocks = reachable_blocks(function)
    for b in blocks: IN[b] = OUT[b] = all_registers(function)
    repeat until nothing changes:
        for b in blocks:
            incoming = [OUT[p] for p in reachable_predecessors(b)]
            if b == function.entry: incoming.push(set(function.parameters))
            IN[b]  = intersection(incoming)
            OUT[b] = IN[b] | all_defs(b)
    for b in blocks:
        initialized = IN[b]
        for item in instructions_then_exit(b):
            require set(uses(item)) <= initialized else fail UninitializedRegister
            initialized |= set(defs(item))
~~~

The entry block keeps its synthetic predecessor even when a back edge reaches it. A trapping instruction defines its outputs only on the normal path.

Why not SSA: text backends want variables, the native backend needs liveness rather than SSA, and mutable registers need no phi elimination. The cost is this one forward analysis and the frontend's duty to snapshot operands it could later overwrite.

## 2. Target facts: MacArm64

### 2.1 Targets

| Target | Here | Object format | Notes |
| --- | --- | --- | --- |
| MacArm64 | Core, this section | Mach-O | The Apple arm64 ABI |
| LinuxArm64 | Delta, Appendix A.1 | ELF | Same registers and templates |
| LinuxX64 | Delta, Appendix A.2 | ELF | Different ISA, same design |

~~~text
enum Target { MacArm64, LinuxArm64, LinuxX64 }
~~~

Baselines: ARMv8.0-A with no extensions (no LSE); x86-64 with SSE2 and CMOV. A request for anything else is `UnsupportedTarget`.

### 2.2 Registers

| Role | Integer | Float |
| --- | --- | --- |
| Homes (callee-saved) | x19-x28 | d8-d15 |
| Template scratch | x9-x12 | d16, d17 |
| Expansion temporary (float constants) | x16 | |
| Arguments and results | x0-x7, result x0 | d0-d7, result d0 |
| Reserved | sp, x29 (frame record), x30 (link), x18 (platform), xzr | |
| Unused | x8, x13-x15, x17 | d18-d31 |

Integer registers are written as `w` for types of 32 bits or fewer and `x` for 64-bit types. Float registers are written as `s` for F32 and `d` for F64.

### 2.3 Canonical form

Every value in a home is canonical, and so is every argument and result this backend passes:

- `Bool`: 0 or 1.
- `I8`, `I16`, `I32`: sign-extended to 32 bits. `U8`, `U16`, `U32`: zero-extended to 32 bits. For all six, bits 63:32 are zero.
- `I64`, `U64`, `Pointer`, `FunctionPointer`: all 64 bits. `F32`, `F64`: IEEE bits.

Writes establish it and reads assume it. `I8(-1)` is `0x00000000_FFFFFFFF`.

Why: every write to a `w` register clears bits 63:32, and 32-bit compare, divide and convert are exact on canonical narrow values. What it costs, each handled by one rule:

- A narrow result can leave canonical form, so every Commit of `Bool`, 8-bit or 16-bit type re-extends first (4.5).
- Right shifts of narrow values re-extend by the shift's kind, not the type's. `I8(-1)` shifted right logically by 1 is 127, but `lsr` on `0xFFFFFFFF` followed by re-extension gives -1.
- Widening a signed value of 32 bits or fewer to 64 bits needs `sxtw`.

### 2.4 Calling convention

| | MacArm64 | LinuxArm64 |
| --- | --- | --- |
| Integer arguments | x0-x7 | x0-x7 |
| Float arguments | d0-d7, counted separately from integers | Same |
| Results | x0 or d0 | Same |
| Narrow arguments | Caller extends to 32 bits | Bits above the type are unspecified |
| Stack arguments | Natural size and alignment, packed | One 8-byte slot each |
| Preserved by the callee | x19-x28, x29, sp, low 64 bits of v8-v15 | Same |
| Stack pointer | 16-byte aligned at all times | Same |
| x29 | Must always address a valid frame record | Always set here anyway |
| Variadic calls | All variadic arguments on the stack | Different rules: not supported here |

~~~text
enum ArgLocation { Reg(PhysReg), Stack { offset: U32, size: U32 } }
struct CallPlan  { params: List<ArgLocation>, result: Option<PhysReg>, stack_bytes: U32 }

int_args(MacArm64 | LinuxArm64)   = [x0..x7]     int_args(LinuxX64)   = [rdi, rsi, rdx, rcx, r8, r9]
float_args(MacArm64 | LinuxArm64) = [d0..d7]     float_args(LinuxX64) = [xmm0..xmm7]
slot(MacArm64, type) = size_of(type)             slot(LinuxArm64 | LinuxX64, type) = 8

classify(signature, target) -> CallPlan:
    require signature.calling_convention is PlatformDefault or Exact(abi of target)
        else fail UnsupportedFeature
    ints = int_args(target); floats = float_args(target)
    next_int = 0; next_float = 0; stack = 0; params = []
    for type in signature.parameters:
        if is_float(type) and next_float < length(floats):
            params.push(Reg(floats[next_float])); next_float += 1
        else if not is_float(type) and next_int < length(ints):
            params.push(Reg(ints[next_int])); next_int += 1
        else:
            size = slot(target, type)
            stack = checked_align_up(stack, size)
            params.push(Stack { offset: stack, size: size })
            stack = checked_add(stack, size)
    require stack <= 4064 else fail ResourceLimit     // keeps [x29, #16 + offset] encodable
    result = none, or the first integer or float argument register, by signature.result
    return CallPlan { params, result, stack_bytes: checked_align_up(stack, 16) }
~~~

pointer_bytes = 8 on every target. Use this constant for layout and pointer conversions.

The abi of a target is `AppleArm64`, `Aapcs64Linux` or `SysVAMD64`.

One behaviour satisfies both ABIs: pass canonical values (that is Apple's caller-extension rule), and re-normalize every incoming parameter and every call result; validate the low byte of Bool as 0 or 1 (Linux promises nothing above the type's width). Commit does the second (4.5).

## 3. `.lower(target)`: one template per instruction

### 3.1 Records

~~~text
enum PhysReg {
    X(0..30), D(0..31), Sp, Zero,
    RAX, RCX, RDX, RBX, RSP, RBP, RSI, RDI, R8, R9, R10, R11, R12, R13, R14, R15,
    XMM(0..15)
}    // bounded ranges abbreviate closed enums
enum View      { B8, B16, W, X, S, D }                // 32-bit, 64-bit integer; F32, F64
enum Condition { Eq, Ne, Cs, Cc, Mi, Pl, Vs, Vc, Hi, Ls, Ge, Lt, Gt, Le }   // Hs = Cs, Lo = Cc
enum LabelId   { Block(BlockId), Trap(TrapCode), Local(U32) }   // Local: numbered per function
enum Operand {
    Reg(PhysReg, View), Imm(I64), ShiftedImm { value: U16, shift: U8 },
    Mem { base: PhysReg, offset: I64 }, MemPre { base: PhysReg, offset: I64 },
    MemPost { base: PhysReg, offset: I64 }, Cond(Condition), Label(LabelId),
    FrameObject(StackObjectId), TrapStub(TrapCode),             // resolved by .alloc()
    Page(SymbolId), PageOffset(SymbolId), GotPage(SymbolId),
    GotMem { base: PhysReg, symbol: SymbolId },                 // [base, GOT page offset of s]
    CallTarget(FunctionId)
}
enum Opcode { A64(A64Opcode), X64(X64Opcode) }
struct MachineInstruction {
    opcode: Opcode, operands: List<Operand>,
    width: Option<Width>, condition: Option<X64Condition>
}
enum Step {
    Read   { value: Value, into: PhysReg },      // view taken from the value's type
    Emit   (MachineInstruction),                 // every operand carries its own view
    Label  (LabelId),
    Commit  { dst: RegisterId, from: PhysReg },   // view taken from dst's type
    Return                                       // expands to the epilogue and ret
}
struct Template {
    steps: List<Step>, scratch: Set<PhysReg>,
    clobbers: RegisterUnitSet, private_slots: List<StackSlot>
}     // every Read comes before every Commit
struct MirBlock    { id: BlockId, templates: List<Template>, successors: List<BlockId> }
struct MirFunction { ir: Function, param_locations: List<ArgLocation>, blocks: List<MirBlock>,
                     outgoing_bytes: U32, traps: Set<TrapCode> }
struct Mir         { target: Target, module: Ir, functions: List<MirFunction> }
~~~

The complete closed opcode enums are in Appendix G. Width and condition fields are explicit; descriptors reject missing or inapplicable fields.
- Operands follow each ISA writer’s declared order: ARM native order and x86 AT&T order. Each opcode descriptor owns mixed-width, fixed-operand, and unary forms; there is no global reversal.
- Explicit views represent mixed forms such as sxtw x9, w9 and fcvtzs w9, d16.

### 3.2 The selector

~~~text
lower(ir, target) -> Mir:
    require target in {MacArm64, LinuxArm64, LinuxX64} else fail UnsupportedTarget
    check_names(ir, target)                                  // A.1: register-like names
    functions = []
    for f in ir.functions:
        m = MirFunction {
            ir:f, param_locations:classify(signature(f), target).params,
            blocks:[], outgoing_bytes:0, traps:{}
        }
        for b in f.blocks, entry first, then by ascending id:
            templates = [select(i, f, m) for i in b.instructions] + [select_exit(b.exit, f, m)]
            m.blocks.push(MirBlock(b.id, templates, successors(b.exit)))
        derive_expansion_requirements(m)  // includes Bool guards and float-constant scratch
        verify_template_plans(m, target)
        functions.push(m)
    if any(m.traps is not empty for m in functions) and ir.trap_handler is none:
        fail UnsupportedFeature("module can trap but declares no trap handler")
    return Mir(target, ir, functions)

select(instruction, f, m) -> Template:
    match instruction:                       // exhaustive, no default arm
        each variant: select its exact type/mode row in 3.3
~~~

Template rules:

- Every IR input goes through a Read, constants included. Templates never turn an IR value into an immediate.
- Templates touch only declared scratch, SP, and their own ABI argument/result registers. Constant expansion additionally declares x16. Derive these clobbers before liveness; no new helper call or scratch use may appear later.
- `trap(c)` in a template is the operand `TrapStub(c)`, and it adds `c` to `m.traps`.
- `L(ok)` is a fresh `Local` label; `.lower` numbers them per function, so they are unique.
- Shorthand: `R9` is `w9` for types of 32 bits or fewer and `x9` for 64-bit types (same for `R10`, `R11`). `F16` is `s16` for F32 and `d16` for F64 (same for `F17`).

### 3.3 Templates

Unless a row says otherwise: integer inputs are read `lhs -> x9`, `rhs -> x10`; float inputs `lhs -> d16`, `rhs -> d17`; the result is written from x9 or d16. The type in a row is the operation's type.

**Copy**

| IR | ARM64 |
| --- | --- |
| `Set d, v` | Read `v -> x9` (floats: `d16`); write. No instruction in between |

**Integer arithmetic**

| IR | ARM64 |
| --- | --- |
| `Add`, `Subtract`, `Multiply` Wrapping; `And`, `Or`, `Xor` | `add`, `sub`, `mul`, `and`, `orr` or `eor` `R9, R9, R10` |
| `Add`/`Subtract` Checked, I32/I64 | `adds`/`subs R9, R9, R10`; `b.vs trap(1)` |
| `Add` Checked, U32/U64 | `adds R9, R9, R10`; `b.cs trap(1)` |
| `Subtract` Checked, U32/U64 | `subs R9, R9, R10`; `b.cc trap(1)`. On ARM64, carry clear means borrow |
| `Add`/`Subtract`/`Multiply` Checked, 8/16-bit | `add`/`sub`/`mul w9, w9, w10` (exact in 32 bits); `ext w11, w9`; `cmp w11, w9`; `b.ne trap(1)`. `ext` is `sxtb`, `sxth`, `uxtb` or `uxth` by type |
| `Multiply` Checked, I64 | `mul x11, x9, x10`; `smulh x12, x9, x10`; `asr x9, x11, #63`; `cmp x12, x9`; `b.ne trap(1)`; write from x11 |
| `Multiply` Checked, U64 | `mul x11, x9, x10`; `umulh x12, x9, x10`; `cbnz x12, trap(1)`; write from x11 |
| `Multiply` Checked, I32 | `sxtw x9, w9`; `sxtw x10, w10`; `mul x9, x9, x10`; `sxtw x10, w9`; `cmp x10, x9`; `b.ne trap(1)` |
| `Multiply` Checked, U32 | `mul x9, x9, x10`; `lsr x10, x9, #32`; `cbnz x10, trap(1)` |
| `Divide`, unsigned | `cbz R10, trap(2)`; `udiv R9, R9, R10` |
| `Divide`, signed | `cbz R10, trap(2)`; read MIN(type) -> x11; read -1 -> R12; `cmp R10, R12`; `b.ne L(ok)`; `cmp R9, R11`; `b.eq trap(1)`; `L(ok):` `sdiv R9, R9, R10` |
| `Remainder` | `cbz R10, trap(2)`; `sdiv` or `udiv R11, R9, R10`; `msub R9, R11, R10, R9`. No MIN/-1 case: SDIV returns MIN there and `msub` then gives the required 0 |
| Shifts | `cmp x10, #width`; `b.hs trap(3)`. Then `ShiftRightLogical` on I8/I16: `uxtb`/`uxth w9, w9`; `ShiftRightArithmetic` on U8/U16: `sxtb`/`sxth w9, w9`. Then `lsl`, `lsr` or `asr R9, R9, R10` |

The shift check reads the count's `x` view. A canonical negative count of any type is at least 2^31 there, so one unsigned compare rejects negative and oversized counts alike.

**Compare and select**

| IR | ARM64 |
| --- | --- |
| `IntCompare` | `cmp R9, R10`; `cset w9, c`. Signed: `eq ne lt le gt ge`. Unsigned, `Bool`, `FunctionPointer`: `eq ne lo ls hi hs` |
| `PointerCompare` | As unsigned `IntCompare` on x registers |
| `Select` | Read `condition -> x9`, `yes -> x10`, `no -> x11`; `cmp w9, #0`; `b.ne L(chosen)`; `mov R10, R11`; `L(chosen):`; write from x10. Floats: `yes -> d16`, `no -> d17`; `b.ne L(chosen)`; `fmov F16, F17`; `L(chosen):` |

**Floats**

| IR | ARM64 |
| --- | --- |
| `FloatBinary` | `fadd`, `fsub`, `fmul` or `fdiv F16, F16, F17` |
| `FloatNegate` | `fneg F16, F16` |
| `FloatCompare` | `fcmp F16, F17`; `cset w9, c` with Equal `eq`, NotEqual `ne`, Less `mi`, LessEqual `ls`, Greater `gt`, GreaterEqual `ge`, Unordered `vs`. Using `lt` or `le` would be true for NaN |

**Conversions** (`S` source type, `T` destination type)

| IR | ARM64 |
| --- | --- |
| `IntegerWrapping` | Read `-> x9`; `sxtw x9, w9` if S is signed and 32 bits or fewer; write (Commit truncates and normalizes) |
| `IntegerChecked` | As wrapping, plus the range check below before the write |
| `BoolToInteger`, `PointerToInteger` | Copy |
| `IntegerToFloat` | `scvtf` (signed S) or `ucvtf F16, R9` |
| `FloatToIntegerChecked` | The bounds check below, then `fcvtzs` (signed T) or `fcvtzu R9, F16` |
| `FloatWidth` | `fcvt d16, s16` or `fcvt s16, d16` |
| `Bitcast` | Integer to float `fmov F16, R9`; float to integer `fmov R9, F16`; integer-to-integer uses IntegerWrapping, not Bitcast |

- Integer range check. Let `v` be the source widened to 64 bits, `lo = max(min S, min T)` and `hi = min(max S, max T)`. Bounds are read into x10 as 64-bit constants, then `cmp x9, x10`. Signed S: if `lo > min S`, `b.lt trap(4)`; if `hi < max S`, `b.gt trap(4)`. Unsigned S: if `hi < max S`, `b.hi trap(4)`. A check that cannot fail is omitted.
- Float bounds check. The conversion is valid exactly when `lo < x < hi`, with `lo = min T - 1` and `hi = max T + 1`. `hi` is a power of two, so it is exact in F32 and F64. If `lo` is not exactly representable in S, test `min T <= x` instead: no value of S lies between. Each test reads the bound into d17, does `fcmp F16, F17`, and traps with code 4 on `b.le` (strict `lo`), `b.lt` (`min T`) or `b.pl` (`hi`). All three branches are taken for NaN. After them, `fcvtzs`/`fcvtzu` cannot overflow.

**Memory and addresses**

| IR | ARM64 |
| --- | --- |
| `Load` | Read `address -> x9`; load into `R10`/`F16` from `[x9]` with `ldrsb` (I8), `ldrb` (U8, Bool), `ldrsh` (I16), `ldrh` (U16), `ldr w` (32-bit), `ldr x` (64-bit, pointers), `ldr s`/`d` (floats). Bool: `cmp w10, #1`; `b.hi trap(5)`. Commit from x10 or d16 |
| `Store` | Read `address -> x9`, `value -> x10` or `d16`; `strb`, `strh`, `str w`, `str x`, `str s` or `str d` to `[x9]` |
| `Address`, `StackObject(o)` | Read offset `-> x10`, widened; `add x9, sp, #frame(o)`; `add x9, x9, x10` |
| `Address`, `Register(p)` | Read `p -> x9`, offset `-> x10`, widened; `add x9, x9, x10` |
| `Address`, `Symbol(s)` | Defined: `adrp x9, Page(s)`; `add x9, x9, PageOffset(s)`. Imported: `adrp x9, GotPage(s)`; `ldr x9, GotMem(x9, s)`. Data symbols then add the offset as above; function symbols have offset 0 |

**Offset check:** U64 offsets above INT64_MAX branch to trap(4) before addition. Then "widened" means `sxtw x10, w10` when the offset type is signed and 32 bits or fewer, and nothing otherwise. `Volatile` uses the same single load or store; nothing here merges or removes accesses. Ordinary alignment-1 accesses are supported. Volatile is restricted to naturally aligned supported integer/pointer types. A violated declared alignment is invalid execution, not a promised program trap.

**Calls**

~~~text
call template (Call or CallNever):
    plan = classify(signature(callee), target)
    m.outgoing_bytes = max(m.outgoing_bytes, plan.stack_bytes)
    for each (arg, Stack { offset, size }):  integer: read arg -> x9; strb/strh/str w9/str x9 by size
                                             float:   read arg -> d16; str s16 or str d16
                                             both to [sp, #offset]
    for each (arg, Reg(r)):                  read arg -> r
    callee Function(f): bl CallTarget(f)
    callee Register(p): read p -> x9; blr x9
    Call with dst:  write dst from x0 or d0          // Commit normalizes the result
    CallNever:      brk #0
~~~

Order matters: stack arguments first (they use x9 and d16), then register arguments, then an indirect callee into x9, which is not an argument register. Every source is a home or a constant, never an argument register, so plain sequential moves are correct.

**Exits**

| Exit | ARM64 |
| --- | --- |
| `Jump b` | `b L(b)` |
| `Branch c, yes, no` | Read `c -> x9`; `cbnz w9, L(yes)`; `b L(no)` |
| `Switch v, cases, default` | Read `v -> x9`; per case: read `k -> x10`, `cmp R9, R10`, `b.eq L(target)`; then `b L(default)` |
| `Return v` | Read `v -> x0` or `d0`; Return step |
| `CallNever` | The call template |
| `Trap c` | `b trap(c)` |

### 3.4 Template verification

Each fixed PhysReg in a Step specializes a WorkValue constraint from the contract. Descriptors supply its register-unit aliases, fixed/tied operands, read/write timing, flags, and legal views.

~~~text
verify_template_plans(function, target):
    for template in function.templates:
        require all scratch and call clobbers are declared
        require every input is captured before any destination commit
        walk every local path:
            require instruction forms match target descriptors
            require overlapping live work values never share register units
            require flags reach consumers without an intervening clobber
            require no work/flags survive a template boundary
            require normal paths commit declared outputs
            require trap paths commit no output
~~~

A commit may trap during Bool boundary validation; declare that dependency during selection. Call arguments, indirect targets, Select inputs, and all CAS inputs must be captured before any aliased destination is committed. Never borrow a home as scratch.

## 4. `.alloc()`: homes, frame, code

~~~text
Mir.alloc():
    items = []; plans = []
    for m in self.functions:
        live = solve_liveness(m)
        graph = build_graph(m, live)
        homes = color_each_class(graph, target_home_pools(self.target))
        frame = plan_frame(m, homes, live)
        physical = expand(m, homes, frame)
        verify_frame_calls_and_physical_forms(physical, frame)
        items.extend(physical)
        plans.push(frame.proof_record)
    items.extend(emit_globals(self.module))
    items.push(ModuleEnd)
    return Asm(self.target, self.module, items, plans)  // private constructor

~~~

### 4.1 Liveness

Over templates, using the template's own uses and definitions:

~~~text
uses(t) = [r for each Read(Register(r), _) in t.steps]
defs(t) = [d for each Commit(d, _) in t.steps]

solve_liveness(m):
    for b in m.blocks:
        use[b] = {}; def[b] = {}
        for t in b.templates:
            use[b] |= set(uses(t)) - def[b]
            def[b] |= set(defs(t))
        live_in[b] = live_out[b] = {}
    repeat until nothing changes:
        for b in reverse(m.blocks):
            live_out[b] = union(live_in[s] for s in b.successors)
            live_in[b]  = use[b] | (live_out[b] - def[b])
    for b in m.blocks:
        live = live_out[b]
        for t in reverse(b.templates):
            after[t]  = live
            live      = set(uses(t)) | (live - set(defs(t)))
            before[t] = live
~~~

Every Read comes before every Commit, so `before = uses + (after - defs)` holds for a whole template.

### 4.2 Interference and homes

~~~text
build_graph(m, live):
    nodes = every register in a Read or a Commit, plus every parameter
    for t in all templates:
        clique(live.before[t]); clique(live.after[t]); clique(defs(t))
        for d in defs(t): for v in live.after[t]: if d != v: edge(d, v)
    clique(m.ir.parameters)                   // all written at entry
    // edges only join registers of the same class: integer or float

color(graph, pool):                           // once per class, deterministic
    remaining = copy(graph); stack = []
    while remaining is not empty:
        small = vertices of remaining with degree < size(pool)
        if small: v = min(small, by (degree, id))
        else:     v = min(remaining, by (cost(v) / (degree(v) + 1), id))   // exact fractions
        stack.push(v); remaining.remove(v)
    while stack is not empty:
        v = stack.pop()
        free = registers of pool not used by an already colored neighbor
        home[v] = Register(free[0]) if free else Spill(v)
~~~

- Pools: x19-x28 and d8-d15, in that order. `cost(v)` is the number of Reads and Commits of v, plus 1 for a parameter.
- A dead definition still interferes with everything live after it, so writing it cannot clobber a live value.
- A dying input may share a home with the output: every Read happens before every Commit.
- A spilled register gets a slot and nothing is retried. Reads and Commits reach the slot through scratch, so spilling never needs another allocated home.
- No live-range splitting, no coalescing, no edge copies. Changing that needs new algorithms and tests, not a tweak here.

### 4.3 Frame

~~~text
plan_frame(m, homes, live):
    cursor = m.outgoing_bytes                       // [sp, sp + outgoing): stack arguments
    for o in m.ir.objects by id:
        require o.alignment <= 16 else fail UnsupportedFeature
        cursor = checked_align_up(cursor, o.alignment)
        offset[o] = cursor; cursor = checked_add(cursor, o.size)
    for each spilled v by id:
        cursor = checked_align_up(cursor, alignment_of(type(v)))
        offset[v] = cursor; cursor = checked_add(cursor, size_of(type(v)))
    for each template-private slot by stable ID:
        reserve using checked alignment/addition
    for each register home live across a call that the target may clobber:
        reserve a typed CallSave slot using checked alignment/addition
    for each used callee-preserved home in target register order:
        cursor = checked_align_up(cursor, 8); save[h] = cursor; cursor = checked_add(cursor, 8)
    size = checked_align_up(cursor, 16)
    require size <= 4080 else fail ResourceLimit
    return frame containing size, offsets, saves, call saves and proof record
~~~

~~~text
x29 + 16 ...   incoming stack arguments
x29 + 8        saved x30
x29            saved x29: the frame record, x29 always points here
sp + size - 1  .. down to sp + outgoing: saved homes, spill slots, stack objects
sp             outgoing stack arguments
~~~

Why 4080 bytes: `sub sp, sp, #size` takes a 12-bit immediate, sp stays 16-aligned, and every slot offset then fits the scaled 12-bit offset of `ldr`/`str`. Larger frames need a separately specified expansion and stack-probing policy. That is a later step, not a silent truncation.

### 4.4 Prologue, entry, epilogue

~~~text
prologue:                                  epilogue (expands each Return step):
    stp x29, x30, [sp, #-16]!                  ldr h, [sp, #save[h]]   for each saved home
    mov x29, sp                                mov sp, x29
    sub sp, sp, #size       if size > 0        ldp x29, x30, [sp], #16
    str h, [sp, #save[h]]   for each           ret
~~~

**Stack-checked profile.** A program that spawns actors runs functions on fixed-size turn stacks without guard pages (MEMORY_AND_ACTORS.md §4), so every function checks its frame against the current stack's limit before touching it. The driver picks the profile once per program, after cull. Programs without actors are compiled exactly as above, and §6 is unchanged.

~~~text
MacArm64 / LinuxArm64 (x16, x17: intra-call scratch, free at entry)
    mrs  x16, tpidr_el0
    ldr  x16, [x16, #stack_limit]          // runtime keeps the running stack's limit in a TLS slot
    sub  x17, sp, #(16 + size)             // the lowest address this frame will touch
    cmp  x17, x16
    b.lo trap(StackOverflow)               // the function's trap stub, as for every trap code
    ...normal prologue...

LinuxX64 (r10, r11: free at entry in SysV)
    mov  r11, fs:[stack_limit]
    lea  r10, [rsp - (16 + size)]
    cmp  r10, r11
    jb   trap(StackOverflow)
~~~

The runtime updates `stack_limit` at every stack switch, and sets it for `main` from the thread's stack size. Frames above the probing threshold (Appendix F) check the whole frame here, so probing is not needed in this profile. The C route emits the same comparison against a runtime global through `__builtin_frame_address`.

- Entry: after the prologue, each parameter moves into its home. A register location is a Commit from that register. A stack location loads from `[x29, #16 + offset]` with the type's extending load into x9 or d16, then Commits.
- Return reads its value into x0 or d0 before the epilogue restores the homes. The order matters: the value may live in a home that is about to be restored.

### 4.5 Expansion

~~~text
expand(m, homes, frame) -> List<AsmItem>:
    items = [Section(Text), Align(4), Begin(symbol(m))] + prologue(frame) + entry moves
    for b in m.blocks:
        items += Label(block_label(m, b))
        for t in b.templates, for step in t.steps:
            Read(v, r)   -> read(v, r)
            Emit(i)      -> i, with FrameObject(o) -> Imm(offset[o]) and TrapStub(c) -> trap_label(m, c)
            Label(l)     -> Label(l)
            Commit(d, r)  -> commit_home(d, r)
            Return       -> epilogue(frame)
    for c in sorted(m.traps):
        items += Label(trap_label(m, c)) + materialize(code(c), w0)
        items += [bl CallTarget(trap_handler), brk #1]
    items += End(symbol(m))

read(value, r):
    Constant c        -> materialize(canonical bits of c, r)
    home Register(h)  -> mov r, h         (fmov for floats; view by type)
    home Spill(v)     -> typed_load r, [sp, #offset[v]]; normalize by type(v)

commit_home(dst, r):
    Bool: uxtb; cmp with 1; b.hi trap(InvalidValue)
    U8: uxtb; I8: sxtb; U16: uxth; I16: sxth      (in place, on r's w view)
    home Register(h)  -> mov h, r         (fmov for floats)
    home Spill(v)     -> typed_store r, [sp, #offset[v]] at logical width

materialize(bits, r):
    integer: movz r, #bits[15:0], then movk r, #chunk, lsl #16k for each other nonzero chunk
             (two chunks in the w view, four in the x view)
    float:   materialize the bits into x16 (w16 for F32), then fmov r, x16
~~~

typed_load selects LDRB/LDRH/LDR W/LDR X or scalar float LDR; signed byte/halfword reloads use LDRSB/LDRSH to W. typed_store selects STRB/STRH/STR W/STR X or scalar float STR. On x86 the equivalent MOVSX/MOVZX and width-specific MOVs apply.

- Spill slots use the logical value size and natural alignment. Store only those bytes; reload with the proper sign/zero extension to reconstruct the canonical container. A spill never becomes an addressable user object.
- The trap stub runs inside the function's frame, so sp is aligned and x29 is valid when it calls the handler. The `brk` is defensive: the handler never returns.

### 4.6 Check

Before an `Asm` exists, every instruction is checked against its encoding: register classes and views, immediates (`add`/`sub` 0-4095, `movz`/`movk` 16 bits, shifts below the width, `brk` 16 bits), scaled load and store offsets, `stp`/`ldp` offsets in -512..504, and labels defined exactly once and only referenced if defined. An invalid selected physical form is InvalidInstructionForm; a configured size/feature limit is an explicit resource or unsupported-feature diagnostic.

Two limits are resource limits, not bugs, and fail with `ResourceLimit` before anything is written:

- A function's code is at most 1 MiB. `b.cond`, `cbz` and `cbnz` reach only +/-1 MiB, and trap stubs sit after the last block. Count emitted instruction bytes, then check each actual branch displacement, including its exact endpoint.
- Stack arguments are at most 4064 bytes (`classify`), so every `[x29, #16 + offset]` and `[sp, #offset]` is encodable.

Retain each frame's slot ranges, preserved-register saves, call alignment/argument layout, and prologue/return item ranges. Verify actual instructions against these obligations. The platform assembler is an additional check, not a substitute for frame/template verification.

## 5. `.write(sink)`: text and toolchain

### 5.1 Items

~~~text
enum AsmSection { Text, ReadOnlyData, Data }
enum AsmItem {
    Section(AsmSection), Align { bytes: U32 }, Begin(SymbolId), End(SymbolId), Label(LabelId),
    Instruction(MachineInstruction), Bytes(List<U8>), Zero(U64),
    Address64 { symbol: SymbolId, addend: I64 },
    Comment(String),                  // annotation mode only
    ModuleEnd                         // appended once, after the last global
}
enum SlotPurpose { UserObject, Spill, CallSave, TemplateTemporary, SavedRegister }
struct StackSlot {
    id: StackSlotId, size: U64, alignment: U32, offset: I64,
    type: Option<ScalarType>, purpose: SlotPurpose
}
distinct StackSlotId, RecipeId, TestId: U32
struct ItemRange { begin: U32, end_exclusive: U32 }
struct CallSitePlan {
    item: U32, signature: SignatureId, locations: CallPlan,
    live_saved_homes: List<StackSlotId>
}
struct FramePlan {
    function: FunctionId, frame_bytes: U64, slots: List<StackSlot>,
    calls: List<CallSitePlan>, prologue: ItemRange, returns: List<ItemRange>
}
struct Asm {
    target: Target, module: Ir, items: List<AsmItem>, plans: List<FramePlan>
}   // built only by .alloc()
~~~

`.alloc()` emits every function (4.5), then every global, then one `ModuleEnd`. In annotation mode a `Comment` with the template's IR precedes each template. Each global becomes `Section`, `Align(its alignment in bytes)`, `Begin`, its parts in order (`Bytes`, `Zero`, `Address64`), `End`. An immutable global with no `Address` part goes to `ReadOnlyData`; everything else goes to `Data`, because a pointer in read-only data needs a relocation the loader would have to write.

### 5.2 The sink operation

~~~text
enum WriteError { IoFailure, CapacityExceeded }
interface TextSink {
    write_text(text: String) -> Result<Unit, WriteError>
}

Asm.write(sink):
    for item in self.items:
        match item:
            Section(kind): write_section(kind, self.target, sink)?
            Align(bytes): write_alignment(log2(bytes), sink)?
            Begin(symbol): write_symbol_begin(symbol, self.target, sink)?
            End(symbol): write_symbol_end(symbol, self.target, sink)?
            Label(label): write_label(label, self.target, sink)?
            Instruction(instruction):
                descriptor_for(self.target, instruction).write(instruction, sink)?
            Bytes(bytes): write_bytes(bytes, sink)?
            Zero(size): write_zero_bytes(size, sink)?
            Address64(symbol, addend): write_address(symbol, addend, sink)?
            Comment(text): write_escaped_single_line_comment(text, sink)?
            ModuleEnd: write_module_footer(self.target, sink)?
    return Ok(Unit)

buffer = StringSink()
asm.write(buffer)?
assembly_text = buffer.contents()

file = FileSink("module.s")
asm.write(file)?
file.close()?  // the caller owns and closes the sink
driver.assemble("module.s", tools)
~~~

write supports a string buffer, file, or bounded sink. Errors propagate immediately. It neither closes nor flushes caller-owned sinks; finalization errors belong to the caller. Partial output is possible on failure. For replacement-safe files, write a temporary file and rename only after successful close.

Only verified physical records reach this method. It performs no selection, register allocation, spill insertion, or instruction repair. Each descriptor formats its own operands; x86 records already use AT&T order.

### 5.3 Text per format


| Item | Mach-O (MacArm64) | ELF (LinuxArm64) |
| --- | --- | --- |
| `Section(Text)` | `.section __TEXT,__text,regular,pure_instructions` | `.text` |
| `Section(ReadOnlyData)` | `.section __TEXT,__const` | `.section .rodata` |
| `Section(Data)` | `.section __DATA,__data` | `.data` |
| `Align(n)` | `.p2align log2(n)` | `.p2align log2(n)` |
| `Begin(s)` | `.globl _name` if exported, then `_name:` | `.globl name` if exported, `.type name, %function` (or `%object`), `name:` |
| `End(s)` | Nothing | `.size name, .-name` |
| `Label(l)` | `Lname:` | `.Lname:` |
| `Bytes`, `Zero`, `Address64` | `.byte 1, 2`, `.space n`, `.quad _sym+8` | `.byte 1, 2`, `.space n`, `.quad sym+8` |
| `Page(s)`, `PageOffset(s)` | `_s@PAGE`, `_s@PAGEOFF` | `s`, `:lo12:s` |
| `GotPage(s)`, `GotMem(x9, s)` | `_s@GOTPAGE`, `[x9, _s@GOTPAGEOFF]` | `:got:s`, `[x9, :got_lo12:s]` |
| `ShiftedImm`, `MemPre`, `MemPost` | `#v, lsl #s`, `[sp, #-16]!`, `[sp], #16` | Same |
| `Comment(t)` | `// t` | `// t` |
| `ModuleEnd` | `.subsections_via_symbols` | `.section .note.GNU-stack,"",@progbits` |

Names:

- External names print as given. Mach-O adds one leading underscore, exactly once.
- Internal functions print as `fn.<function id>` and internal data as `sym.<symbol id>`. A dot cannot appear in a validated external name, so they never collide. They are real local symbols, which keeps `.subsections_via_symbols` safe.
- Labels: blocks `f<function>.b<block>`, trap stubs `f<function>.trap<code>`, template-local labels `f<function>.l<n>`, each behind the private prefix (`L` or `.L`).
- AArch64 instructions use native operand order. Comments are `//` on both formats.

### 5.4 Assemble and link

The driver runs tools with argument arrays, never a shell string built from names, and declares every input file.

- MacArm64: `clang -c -arch arm64 module.s -o module.o`; link with `clang` and the macOS SDK.
- LinuxArm64: `clang --target=aarch64-linux-gnu -c module.s -o module.o` (or the target's `as`); link with the target's `gcc` or `clang` and its sysroot.
- The trap handler and any helper are ordinary imports. The link must be given the object or library that defines them.
- A nonzero exit is `ExternalToolFailure`, carrying the tool's output.
- v1 builds executables. Defined symbols are addressed directly (`adrp`/`add`); a shared library would need GOT access for definitions that can be preempted.

## 6. Worked examples

Both examples use construction shorthand, not a second dump grammar. Canonical dumps keep the contract’s S-expression spelling, ordered IDs, and fixed-width bit patterns. Both examples start at Ir; frontend storage and SEMA are in Appendix C. The following listings trace one concrete lowering and allocation. The `//` comments come from the writer's annotation mode: one line per template, showing its IR.

### 6.1 `answer()`: a stack object through every step

Source intent: `x = 40; p = &x; *p = *p + 2 (wrapping); return x`.

**`Ir`.** The frontend chose a stack object for `x` because its address is taken.

~~~text
function f0 "answer" () -> I64, exported
object o0 { size: 8, alignment: 8 }
registers r0: Pointer, r1: I64, r2: I64, r3: I64
b0:
    r0 = Address(StackObject(o0), I64 0)
    Store([r0], I64 40)
    r1 = Load(I64, [r0])
    r2 = IntBinary(Add(Wrapping), r1, I64 2)
    Store([r0], r2)
    r3 = Load(I64, [r0])
    Return(r3)
~~~

**`.lower(MacArm64)`.** One template per instruction:

~~~text
t0  read 0 -> x10; add x9, sp, #frame(o0); add x9, x9, x10; write r0 <- x9
t1  read r0 -> x9; read 40 -> x10; str x10, [x9]
t2  read r0 -> x9; ldr x10, [x9]; write r1 <- x10
t3  read r1 -> x9; read 2 -> x10; add x9, x9, x10; write r2 <- x9
t4  read r0 -> x9; read r2 -> x10; str x10, [x9]
t5  read r0 -> x9; ldr x10, [x9]; write r3 <- x10
t6  read r3 -> x0; return
~~~

**`.alloc()`.**

| Template | Live before | Live after |
| --- | --- | --- |
| t0 | | r0 |
| t1 | r0 | r0 |
| t2 | r0 | r0, r1 |
| t3 | r0, r1 | r0, r2 |
| t4 | r0, r2 | r0 |
| t5 | r0 | r3 |
| t6 | r3 | |

- Edges: r0-r1 (t2) and r0-r2 (t3). r3 does not interfere with r0: r0 is read by t5 before r3 is written.
- Simplify order by (degree, id): r3, r1, r0, r2. Select pops r2 -> x19, r0 -> x20, r1 -> x19, r3 -> x19.
- Frame: o0 at sp+0, x19 saved at sp+8, x20 saved at sp+16, size 32. The object is not a spill slot.

**`.write(sink)`**, Mach-O. 31 instructions.

~~~asm
.section __TEXT,__text,regular,pure_instructions
.p2align 2
.globl _answer
_answer:
    stp x29, x30, [sp, #-16]!
    mov x29, sp
    sub sp, sp, #32
    str x19, [sp, #8]
    str x20, [sp, #16]
Lf0.b0:
    // r0 = address o0 + 0
    movz x10, #0
    add x9, sp, #0
    add x9, x9, x10
    mov x20, x9
    // store [r0], 40
    mov x9, x20
    movz x10, #40
    str x10, [x9]
    // r1 = load [r0]
    mov x9, x20
    ldr x10, [x9]
    mov x19, x10
    // r2 = add.wrap r1, 2
    mov x9, x19
    movz x10, #2
    add x9, x9, x10
    mov x19, x9
    // store [r0], r2
    mov x9, x20
    mov x10, x19
    str x10, [x9]
    // r3 = load [r0]
    mov x9, x20
    ldr x10, [x9]
    mov x19, x10
    // return r3
    mov x0, x19
    ldr x19, [sp, #8]
    ldr x20, [sp, #16]
    mov sp, x29
    ldp x29, x30, [sp], #16
    ret
.subsections_via_symbols
~~~

For LinuxArm64 only the directives and names change: `.text`, `.globl answer`, `.type answer, %function`, `answer:`, `.Lf0.b0:`, `.size answer, .-answer`, and the `.note.GNU-stack` footer.

### 6.2 `sum_to(n)`: a loop, checked arithmetic and a trap stub

Source intent: `s = 0; i = 0; while i < n { i = i + 1; s = s + i }; return s`, with checked adds.

~~~text
import f100 "eir_trap" (U32) -> Never;  module.trap_handler = f100
function f1 "sum_to" (r0: I32) -> I32, exported
registers r1: I32, r2: I32, r3: Bool
b0: r1 = Set(I32 0);  r2 = Set(I32 0);  Jump(b1)
b1: r3 = IntCompare(Less, r2, r0);  Branch(r3, b2, b3)
b2: r2 = IntBinary(Add(Checked), r2, I32 1)
    r1 = IntBinary(Add(Checked), r1, r2);  Jump(b1)
b3: Return(r1)
~~~

- r1 and r2 are assigned in b0 and again in b2. They are mutable registers with one home each, so the back edge needs no copies.
- All four registers are live together at the compare, so they get four homes: r0 -> x22, r1 -> x21, r2 -> x20, r3 -> x19.
- Both checked adds branch to the code-1 stub; the uniform Bool commit declares the code-5 stub.

~~~asm
.section __TEXT,__text,regular,pure_instructions
.p2align 2
.globl _sum_to
_sum_to:
    stp x29, x30, [sp, #-16]!
    mov x29, sp
    sub sp, sp, #32
    str x19, [sp]
    str x20, [sp, #8]
    str x21, [sp, #16]
    str x22, [sp, #24]
    // parameter r0
    mov w22, w0
Lf1.b0:
    // r1 = 0
    movz w9, #0
    mov w21, w9
    // r2 = 0
    movz w9, #0
    mov w20, w9
    // jump b1
    b Lf1.b1
Lf1.b1:
    // r3 = icmp.lt r2, r0
    mov w9, w20
    mov w10, w22
    cmp w9, w10
    cset w9, lt
    uxtb w9, w9
    cmp w9, #1
    b.hi Lf1.trap5
    mov w19, w9
    // branch r3, b2, b3
    mov w9, w19
    cbnz w9, Lf1.b2
    b Lf1.b3
Lf1.b2:
    // r2 = add.checked r2, 1
    mov w9, w20
    movz w10, #1
    adds w9, w9, w10
    b.vs Lf1.trap1
    mov w20, w9
    // r1 = add.checked r1, r2
    mov w9, w21
    mov w10, w20
    adds w9, w9, w10
    b.vs Lf1.trap1
    mov w21, w9
    // jump b1
    b Lf1.b1
Lf1.b3:
    // return r1
    mov w0, w21
    ldr x19, [sp]
    ldr x20, [sp, #8]
    ldr x21, [sp, #16]
    ldr x22, [sp, #24]
    mov sp, x29
    ldp x29, x30, [sp], #16
    ret
Lf1.trap1:
    movz w0, #1
    bl _eir_trap
    brk #1
Lf1.trap5:
    movz w0, #5
    bl _eir_trap
    brk #1
.subsections_via_symbols
~~~

The extension and validation after CSET use the uniform Bool commit rule. They are redundant for CSET but keep the initial implementation uniform.

These ARM listings are illustrative. Run them through the platform assembler and on the target before advertising support. Verified project evidence is listed in Appendix E.

## Appendix A. Other targets

### A.1 LinuxArm64

Same registers, canonical form, templates, allocator and frame as MacArm64. Only these change:

- Writing: the ELF column of 5.3.
- `classify`: every stack argument takes one 8-byte slot.
- Callers do not extend narrow arguments. The entry Commit already normalizes them.
- x18 is an ordinary temporary on Linux. It stays unused, so both targets share one register table.
- Names print without a prefix, so `check_names` rejects external names that clang's assembler reads as registers: `x`, `w`, `v`, `b`, `h`, `s`, `d` or `q` followed by digits, and `sp`, `wsp`, `xzr`, `wzr`, `lr`, `fp`, `nzcv`. That is `InvalidSymbol`. GNU `as` accepts them; clang does not. Mach-O's underscore avoids the problem, so `check_names` passes everything on MacArm64.
- Link with the target sysroot (5.4).

### A.2 LinuxX64

System V AMD64, AT&T syntax, same IR, same four rules, same allocator. The canonical form is identical: every 32-bit write on x86-64 also clears bits 63:32.

| Topic | LinuxX64 |
| --- | --- |
| Registers | `PhysReg` adds rax-r15 and xmm0-xmm15; integer views are 8, 16, 32 and 64 bits (`%al`, `%ax`, `%eax`, `%rax`) |
| Homes | rbx, r12-r15 (integer); xmm8-xmm13 (float). System V has no callee-saved XMM register, so float homes are caller-saved |
| Scratch | rax, rcx, rdx (integer); xmm14, xmm15 (float); r10 holds an indirect callee; r11 is the expansion temporary for float constants |
| Arguments | rdi, rsi, rdx, rcx, r8, r9; xmm0-xmm7; then one 8-byte stack slot each. Results in rax or xmm0 |
| Frame | `pushq %rbp; movq %rsp, %rbp; subq $size, %rsp`. Same layout as 4.3 (outgoing, objects, spills, call-save slots, saved integer homes), addressed from rsp. Incoming stack arguments at `16(%rbp)`. Epilogue: restore, `leave`, `ret` |
| Float homes and calls | Each float IR register that is live across some call and has a register home gets one 8-byte call-save slot, placed after the spill slots. Before each call, every such register live after it (other than the call's result) is stored to its slot; after the call it is reloaded |
| Reads and writes | Constants: `movl $imm` (32-bit view) or `movabsq` (64-bit); floats through r11 then `movd`/`movq`. Commit normalizes with `movzbl`, `movsbl`, `movzwl`, `movswl` |
| Checked add, subtract | 32/64-bit: `jo` for signed, `jc` for unsigned, after both `add` and `sub` (x86 CF is the borrow, no inversion). 8/16-bit: the ARM64 rule (32-bit op, re-extend, compare), because flags from a 32-bit op miss 8- and 16-bit overflow |
| Checked multiply | I64, I32: two-operand `imul`, then `jo`. U64, U32: one-operand `mul` (rdx:rax = rax x rcx), then `jc`. 8/16-bit: the ARM64 rule (32-bit op, re-extend, compare) |
| Divide, remainder | Dividend rax, divisor rcx; zero test, then `cqto`/`cltd` and `idiv`, or `xorl %edx, %edx` and `div`. Quotient in rax, remainder in rdx. Signed MIN/-1 is guarded for both, because `idiv` faults there: divide traps with code 1, remainder returns 0 |
| Shifts | Count in rcx: `cmpq $width, %rcx; jae trap(3)`; the same pre-extension rule; `shl`, `shr` or `sar` by `%cl` |
| Compare | `cmp`, `setcc %al`, `movzbl %al, %eax`. Signed `l le g ge`, unsigned `b be a ae` |
| Select | `testl` and conditional branches around width-matched MOV. Floats branch around `movss`/`movsd` |
| Float compare | `ucomiss`/`ucomisd`. Equal: `sete` and `setnp`. NotEqual: `setne` or `setp`. Greater `seta`, GreaterEqual `setae`. Less and LessEqual swap the operands, then `seta`/`setae`. Unordered `setp` |
| FloatNegate | `xorps`/`xorpd` with the sign bit, read as a constant into xmm15 |
| IntegerToFloat | Signed: `cvtsi2ss`/`cvtsi2sd` from the 32- or 64-bit view. U8-U32: from the zero-extended 64-bit view. U64 with the top bit set: halve keeping the low bit (`shrq $1`, `andl $1`, `orq`), convert, then add the result to itself |
| FloatToIntegerChecked | The ARM64 bounds with `ucomis*`: `jbe` (strict lower bound), `jb` (`min T`), and `jbe` with swapped operands (upper bound) all trap on NaN. Then `cvttss2si`/`cvttsd2si`. U8-U32 use the 64-bit conversion. U64 at or above 2^63: subtract 2^63, convert, flip bit 63 |
| FloatWidth, Bitcast | `cvtss2sd`/`cvtsd2ss`; `movd`/`movq` |
| Addresses | `leaq off(%rsp)` for objects; `leaq sym(%rip)` for definitions; `movq sym@GOTPCREL(%rip)` for imports |
| Calls | `call sym`, or `call sym@PLT` for imports; indirect `call *%r10`; `ud2` after a `CallNever` |
| Trap stub | `movl $code, %edi; call handler@PLT; ud2` |
| Printing | Records use AT&T operand order; descriptors add register/immediate syntax and width suffixes without globally reversing operands. `.p2align 4` for functions, `.type name, @function`, `#` comments, `.zero` for `Zero` |


## Appendix B. Exact semantics and interpreter

### B.1 Values and arithmetic

~~~text
mask(type) = 2^width(type) - 1

mathematical(type, bits):
    n = bits & mask(type)
    if signed(type) and n >= 2^(width(type)-1): n -= 2^width(type)
    return n

encode(type, value) = value modulo 2^width(type)

finish(type, value, mode):
    if mode == Checked and value not_in range(type): trap IntegerOverflow
    return encode(type, value)

signed_divide_or_remainder(type, a, b, operation):
    if b == 0: trap DivisionByZero
    if a == MIN(type) and b == -1:
        if operation == Remainder: return 0
        trap IntegerOverflow
    quotient = floor(abs(a) / abs(b))
    if (a < 0) != (b < 0): quotient = -quotient
    return encode(type, quotient if operation == Divide else a - quotient*b)

checked_float_to_integer(type, value):
    if is_nan(value) or is_infinite(value): trap InvalidConversion
    n = truncate_toward_zero_exactly(value)
    if n not_in range(type): trap InvalidConversion
    return encode(type, n)
~~~

Checked add/subtract/multiply compute mathematically, then use finish. Wrapping operations reduce modulo the logical width. Shift counts retain their own integer type and must lie in [0, width). Left shift drops high bits; logical right shift fills zero; arithmetic right shift fills the logical sign bit, including for unsigned types.

IntegerChecked interprets the source mathematically and checks the destination range; failure is InvalidConversion. IntegerWrapping reduces the source mathematical value modulo destination width. BoolToInteger produces exactly 0 or 1. Bitcast only preserves equal-width integer↔float bits.

Floating arithmetic rounds at each declared width using nearest-even, gradual underflow, and masked exceptions. Entry adapters establish nearest-even rounding, gradual underflow, and masked floating exceptions; foreign callers establish the same environment and imports preserve it. A host unable to comply cannot advertise float support. No implicit contraction or reassociation. NaN makes ordered comparisons false and NotEqual/Unordered true. Negation flips only the sign bit. Arithmetic NaN payloads are unspecified; non-arithmetic copies preserve bits.

The float conversion rule admits -0.5 as unsigned zero, rejects -1.0 for unsigned, and rejects 2^63 for I64. Do not compare with a rounded floating MAX_I64.

### B.2 Pointers and memory

~~~text
distinct AllocationId: U64
struct PointerValue { bits: U64, allocation: Option<AllocationId> }
struct Allocation {
    id: AllocationId, base: U64, size: U64, alignment: U32,
    bytes: ByteArray, initialized: BitSet, permissions: Set<Permission>, live: Boolean
}
enum Permission { Read, Write }
enum InterpreterFault {
    DeadAllocation, OutOfBounds, Misaligned, PermissionDenied,
    UninitializedMemory, InvalidPointer, ImportContractViolation
}
enum RuntimeValue {
    Integer { type: ScalarType, bits: U64 }, Bool(Boolean),
    F32Bits(U32), F64Bits(U64), Pointer(PointerValue),
    FunctionPointer { signature: SignatureId, callable: FunctionId | HostCallbackId | Null }
}
distinct HostCallbackId: U32
enum Outcome {
    Returned(Option<RuntimeValue>), Trapped(TrapCode),
    Fault(InterpreterFault), ResourceLimit
}
~~~

ObjectMemory pointers retain allocation identity. Address stays within a live object, including its non-dereferenceable one-past position. Access checks lifetime, range, permission, declared alignment, and initialized bytes for loads. Stack objects get fresh identities per activation and die on all exits.

PointerToInteger returns the unsigned U64 address representation. Equality compares address bits; portable ordering requires the same live allocation. Numeric addresses, pointer bytes, and cross-object boundary equality are not ordinary cross-backend equality fixtures.


~~~text
store_pointer(address, pointer_value):
    range = checked_access(address, pointer_bytes, Write)
    invalidate_pointer_shadow_overlapping(range)
    write_bytes_and_mark_initialized(range, pointer_value.bits)
    install_pointer_shadow(range, pointer_value)

execute(instruction):
    inputs = snapshot_all_inputs(instruction)
    result = evaluate(instruction, inputs)
    commit_named_destinations(result)  // only after successful evaluation
~~~

Typed pointer loads restore matching shadow metadata. Zero-filled pointer storage can represent null. Other overlapping writes invalidate metadata; arbitrary byte reconstruction is outside ObjectMemory. Function pointers retain callable identity and exact signature; they are not data addresses.

Select reads condition and both values. Calls capture arguments before execution and commit only on normal return. Returning from a Never import is ImportContractViolation. Release activation storage on return, trap, fault, and resource exhaustion.

## Appendix C. Source modules, storage, and SEMA

Source modules are namespaces; IR modules are compilation containers. The source layer is frontend-owned.

~~~text
distinct ModuleId, DefId, LocalId, NameId, TypeId, ScopeId: U32
enum Visibility { Private, Public }
enum Binding { Local(LocalId), Definition(DefId) }
struct Scope { parent: Option<ScopeId>, bindings: Map<NameId, Binding> }
struct Definition {
    id: DefId, module: ModuleId, name: NameId,
    visibility: Visibility, kind: Function | Global | Type | Extern,
    payload: FrontendDeclaration
}
enum LocalStorage {
    Virtual(RegisterId),
    Addressed { object: StackObjectId, type: ScalarType }
}
struct LocalBinding { type: TypeId, mutable: Boolean, storage: LocalStorage }

sema(project):
    collect_declarations_and_assign_definition_ids(project)
    resolve_named_imports_and_lexical_names()
    resolve_types_and_signatures()
    for function:
        body = check_source_types_calls_and_returns(function)   // init, moves, must-use: flow (I.3)
        decide_address_taken_storage(body)
        lower_to_scalar_ir(body)
    return IrBuilder.finish()  // independently validates all emitted IR
~~~

Collect declarations before bodies to permit mutual recursion. Reject duplicate same-scope names, private/missing imports, invalid recursive value types, and incompatible calls. Nested scopes may shadow. Globals have constant initializers; modules do not execute hidden constructors.

Determine address-taken locals before lowering. Ordinary scalars get virtual registers; addressed locals own objects. Aggregate source values use object layouts and field/element operations.

~~~text
read_local(binding):
    match binding.storage:
        Virtual(r): return Register(r)
        Addressed(object, type):
            pointer = emit Address(object, zero_offset)
            return emit Load(type, pointer)

assign_local(binding, value):
    require binding.mutable and source_type(value) == binding.type
    value = snapshot(value)
    match binding.storage:
        Virtual(r): emit Set(r, value)
        Addressed(object, type): emit Store(emit Address(object, zero_offset), value)

snapshot(value):
    r = fresh_register(type_of(value))
    emit Set(r, value)
    return Register(r)

lower_and_snapshot(expression):
    value = lower_expression(expression)
    if path_terminated: return Terminated
    require value != NoValue else fail TypeMismatch
    return snapshot(value)

resolve_direct_function_or_snapshot_indirect_target(expression):
    if expression names a resolved function: return Callee.Function(function_id(expression))
    value = lower_and_snapshot(expression)
    if path_terminated: return Terminated
    return Callee.Register(value.register_id)

lower_call(callee_expression, argument_expressions):
    callee = resolve_direct_function_or_snapshot_indirect_target(callee_expression)
    if path_terminated: return Terminated
    args = []
    for expression in argument_expressions:
        value = lower_and_snapshot(expression)
        if path_terminated: return Terminated
        args.push(value)
    match signature(callee).result:
        Never:
            end_block(CallNever(callee, args))
            return Terminated
        Returns(None):
            emit Call(None, callee, args)
            return NoValue
        Returns(Some(type)):
            result = fresh_register(type)
            emit Call(Some(result), callee, args)
            return Register(result)
~~~

For left-to-right source evaluation, capture a binary expression's left value before evaluating the right. Source calls must similarly retain x in f(x, expression_that_changes_x()). NoValue and Terminated are frontend outcomes, not scalar values.

An addressed local is loaded on every read; pointer writes and calls can change it. A spill is never addressable source storage. Returning a local address does not extend its lifetime. Heap allocation is an explicit runtime/import operation.

Scalar layout is little-endian: Bool 1 byte, integer width/8, F32 4, F64 8, pointers pointer_bytes(target). Natural alignment equals size. Lay out record fields in declaration order with checked align/add and tail padding; arrays use checked size multiplication. Reject zero-sized addressable objects in this baseline.

### C.1 Branching: every `.match` is a `Branch` or a `Switch`

Zen has no `if` and no `while`. The four bool forms and `.then` lower through one function; enum and integer matches lower through `Switch`.

~~~text
lower_bool_match(condition, yes_body, no_body, result_type):
    // .match({ true => a, false => c })   .match({ a }, { c })   .match({ a })   .then({ a })
    value = lower_and_snapshot(condition)
    if path_terminated: return
    result = result_type is unit ? none : new_result(result_type)    // register, or object if aggregate
    yes = new_block(); no = new_block(); join = reserve_block_id()
    end_block(Branch(value, yes, no))
    lower_arm(yes, yes_body, result, join)
    lower_arm(no,  no_body,  result, join)      // .then: no_body writes None; yes_body writes Ok(a)
    if join_has_predecessors: create_and_continue_at(join)
    else: mark_path_terminated()
    return result

lower_arm(block, body, result, join):
    continue_at(block)
    value = lower_body(body)
    if path_open:
        if result: store_result(result, value)
        run_cleanups(scopes_left_by(join))       // C.4
        end_block(Jump(join))
~~~

Enum layout is fixed at declaration: `tag: U32` at offset 0, tags numbered in declaration order from 0; the payload starts at `round_up(4, max_payload_align)`; size is rounded up to the largest alignment. An enum whose variants are all unit is just the `U32` tag and lives in a register unless its address is taken.

~~~text
lower_enum_match(scrutinee, arms, result_type):
    // exhaustiveness was checked by fit: every variant has an arm, or there is a `_`
    object = address_of(scrutinee)               // enums with payloads are objects
    tag = snapshot(Load(U32, Address(object, 0)))
    result = new_result(result_type); join = reserve_block_id()
    cases = []
    for arm in arms where arm.pattern is a variant:
        block = new_block(); cases.push(SwitchCase(Integer(U32, tag_of(arm.variant)), block))
    default = wildcard_arm ? new_block() : cases.pop().target      // exhaustive: last arm is default
    end_block(Switch(tag, cases, default))
    for arm, block:
        continue_at(block)
        bind_payload(arm.pattern, Address(object, payload_offset))   // a view into the scrutinee
        lower_arm_body(arm, result, join)
    continue_or_terminate(join)
~~~

Integer matches use the same `Switch` with the integer as the selector.

**Patterns:** literals, variants, payload bindings, `_`, and where they fit, **ranges** and **nesting**:

~~~text
n.match({ 0 => "zero", 1..10 => "small", _ => "big" })          // a range is half-open, like Range
r.match({ Ok(Circle(rad)) => rad, Ok(_) => 0.0, Err(e) => .. })  // nested: test the outer tag, then the inner
~~~

- **Lowering:** an arm with a range becomes two `IntCompare`s and a `Branch` ahead of the `Switch`'s default. A nested pattern becomes a `Switch` on the outer tag whose arm holds a `Switch` on the inner tag. This is a decision tree, built arm by arm in source order, with no pattern-matrix compiler.
- **Exhaustiveness, per level:** every variant at each level is covered, or that level has a `_`. Integer ranges are exhaustive only with `_`.
- **Unreachable arms are an error:** an arm whose pattern is already covered by an earlier arm is refused.
- *Proposed syntax:* `a..b` in a pattern means `Range(a, b)`. The exact spelling is still open.

### C.2 Closures and non-local exit

A closure literal (or a local function) passed to a function-typed parameter is never a value: the call is **inlined**. The callee is instantiated with the closure substituted for that parameter, and its body is lowered into the caller's frame. Captures are the frame's own bindings, read live. There is no closure record and no allocation.

Every inlined call has three exit targets, and the language's three exits are jumps to them:

~~~text
inline_call(callee, closure_args, other_args):
    after_call = reserve_block_id()                  // the inlined callee returns here
    push_exits(callee_return = after_call)
    lower callee body with each closure parameter p bound to its literal
        a call p(args) inside it:
            after_closure = reserve_block_id()
            push_exits(closure_return = after_closure)
            lower closure body with its parameters bound to args
            pop_exits(); continue_at(after_closure)
    pop_exits(); continue_at(after_call)

exits, each preceded by run_cleanups(scopes being left):
    tail value / h.next()   -> Jump(closure_return)              // this invocation of the closure ends
    h.break(v)              -> store v as the callee's result; Jump(callee_return)
    .try() on Err / None    -> write Err/None into the function's result; Return
    callee's own Return(v)  -> store v; Jump(callee_return)
~~~

`loop`, `find`, `map` and `filter` are ordinary std functions; nothing in the compiler knows their names. `Range` and fixed arrays are walked directly (as DESIGN.md requires) by `walk`, which the std `loop` calls:

~~~text
lower_walk(seq, body):                          // seq: Range<T> or [T, N]; body: the closure call above
    i = fresh_register(index_type); Set(i, seq.start)
    header = new_block(); end_block(Jump(header)); continue_at(header)
    c = IntCompare(Less, i, seq.end); body_block = new_block(); done = new_block()
    end_block(Branch(c, body_block, done))
    continue_at(body_block)
    v = seq is Range ? i : checked_element(seq, i)     // the bound was just checked; no second test
    call body(i, v)                               // inlined: closure_return lands on `step`
    step: Set(i, IntBinary(Add(Wrapping), i, 1)); Jump(header)   // cannot wrap: i < end
    continue_at(done)
~~~

Inlining depth is limited (Appendix J). A closure that reaches itself through inlining is a `ResourceLimit`, not an infinite expansion.

### C.3 Trait values: `.as(I)`

Bounded generics (`<T: Rect>`) are monomorphized and need nothing at runtime. A trait **value** is a fat value:

~~~text
TraitValue = { data: Pointer, table: Pointer }      // 16 bytes, alignment 8
table(Type, I) = one Global, one FunctionPointer per member of I in declaration order;
                 a computed field (Circle.impl(Rect, { width: .. })) becomes a getter function
d.m(args)      = fp = Load(Pointer, table + 8 * index_of(m)); Call(Register(fp), [data] + args)
~~~

`data` points at the concrete value's storage, so the trait value carries the SCOPED qualifier: fit refuses to return it or store it past that storage's lifetime.

### C.4 Cleanups: `Drop` and `@scope.defer`

Every lexical scope keeps one cleanup list, in the order things were registered: a `Drop` local when it is initialized, a deferred closure when `@scope.defer` runs.

~~~text
run_cleanups(scopes):                            // innermost scope first
    for scope in scopes:
        for c in reverse(scope.cleanups):
            Defer(closure): lower closure body inline (its captures are still alive)
            Drop(local):
                if moved_on_every_path(local): skip                       // known statically
                else if maybe_moved(local): Branch(drop_flag(local), drop_block, skip_block)
                else: emit Call(drop_of(type(local)), [Address(local)])
~~~

- **Cleanups run on every exit edge:** falling out of a block, `h.next`, `h.break`, `.try()` and `Return`. A trap runs none; it aborts.
- **`@scope.deadline` and `@scope.cancel_on`** register with the runtime when they run, and their cleanup (an ordinary entry in the scope's list) retires the deadline and cancels any wait still pending from that scope. A cancelled wait returns `Err(Cancelled)` or `Err(Timeout)`, which leaves through the normal `.try()` path (MEMORY_AND_ACTORS.md §4).
- **The deferred code is duplicated per exit.** That's simple and bounded by the number of exits; a shared cleanup block is an optimization this compiler doesn't do.
- **Drop flags:** a local that is moved on some paths only gets a `Bool` drop flag. It's set when the local is initialized and cleared at `.consume()`. Flow (I.3) knows which locals need one.

## Appendix D. C route

The C backend leaves from Ir and bypasses native selection/allocation.

~~~text
Ir.write_c(sink, target):
    emit exact-width declarations, prototypes, and required semantic helpers
    for function:
        declare one local per IR register and storage per object
        emit goto entry_label
        for block:
            emit block_label
            for instruction:
                snapshot inputs into typed temporaries
                emit defined_C_operation(instruction)
                assign destinations after successful checks
            emit explicit branch/goto/switch/return/terminal call
~~~

| IR behavior | Required C lowering |
| --- | --- |
| Wrapping arithmetic | Unsigned operations, explicit width normalization |
| Checked arithmetic | Verified overflow builtins or exact helpers |
| Narrow unsigned multiply | Widen before C integer promotions can overflow |
| Divide/remainder | Guard zero and signed MIN/-1 before C division |
| Shift/conversion | Exact defined helpers; validate counts and ranges |
| Unaligned/aliasing memory | Exact-width byte-copy helpers |
| Volatile | Matching-width supported volatile access; no memcpy substitute |
| Float negate/bitcast | Exact bit operations/copy, no arithmetic conversion |
| Calls | Prototypes and captured arguments; no reliance on C evaluation order |
| Trap/Never | Nonreturning adapter and no continuation |

Run both unoptimized and optimized C tests. Record compiler versions and required builtins. Reject unsupported pointer/call forms for this route with a diagnostic.

Two practical rules learned from v07: emit one C unit per source module with stable, content-derived names (so objects cache across programs), and keep lowering's output small. A giant function compiled at -O0 gets one stack slot per register; the fix is fewer registers (out-of-line aggregate copies), not a different register model.

## Appendix E. Tests and evidence

### E.1 Diagnostics

~~~text
enum DiagnosticCode {
    UnknownName, DuplicateName, PrivateImport, InvalidRecursiveType,
    InvalidId, DuplicateId, TypeMismatch, ArityMismatch,
    MissingExit, InvalidSuccessor, DuplicateSwitchCase, UninitializedRegister,
    InvalidConstant, InvalidAlignment, InvalidLayout, InvalidSymbol,
    InvalidInstructionForm, InvalidReturnContract,
    UnsupportedTarget, UnsupportedFeature, MissingLowering,
    ResourceLimit, ExternalToolFailure
}
enum DiagnosticStage { Source, IR, Target, Selection, Allocation, Assembly, Toolchain }
struct Diagnostic {
    code: DiagnosticCode, stage: DiagnosticStage,
    function: Option<FunctionId>, block: Option<BlockId>,
    instruction: Option<InstructionId>, source_span: Option<SourceSpan>, message: String
}
~~~

### E.2 Acceptance

| Boundary | Required checks |
| --- | --- |
| IR | Bad IDs/types/constants/signatures/exits; uninitialized branches and first loop iteration |
| Integers | Every width, MIN/MAX, checked/wrapping overflow, signed divide/remainder, invalid shift counts |
| Containers | Poisoned high bits, narrow widening, Bool 2 rejection, spill/reload normalization |
| Templates | Every legal destination/input alias, preserved flags, two spilled inputs, spilled Store |
| Allocation/frame | Dead definitions, loops, pressure, dying-input reuse, real registers and spills |
| ABI | C callers/callees, mixed banks, stack arguments, callee-save sentinels, live values across calls |
| Float | NaN/±0/subnormals, unsigned conversions, truncation/range boundaries, 2^63 rejection |
| Memory | Exact access width, alignment 1, pointers/shadow/lifetimes, globals and relocations |
| Output | Every legal instruction form assembled; missing labels/invalid encodings rejected |
| C | Optimized and unoptimized C, values beyond 2^53 |

Compare an independent mathematical oracle, interpreter, and generated-code execution. Compare defined values/effects/traps; faults and two timeouts are not matching successes. Exclude layout-dependent address equality and unspecified arithmetic NaN payloads.

The test suite is four things, no registry:

1. **Goldens**: §6.1 and §6.2 output byte-identical to this document, comments included.
2. **Acceptance sweeps**: every row above, generated as IR and run on every route against the interpreter.
3. **Differential fuzzing**: random valid IR through the interpreter, C at -O0/-O2 and each native target; failures are shrunk and kept as regression cases.
4. **Mutation checks**: remove an overflow check, invert a condition, corrupt a frame offset, swap two arguments, widen a store — each must fail some test.

Source-level acceptance is `tests/run` (programs) and `tests/fail` (must-fail), run by `tests/run.py` against any compiler.

- **One file per test** (or one directory for a multi-module test). The expectations sit in `//!` lines at the end, so line numbers in the program never shift.
- **The first comment names the bug the test catches.** A test that catches nothing new is not added.
- **Must-fail checks the position**, not the wording: `//! error: L:C`. The expected message is kept as `//! hint:` for people.
- **The baseline** (`tests/baseline-*.txt`) lists the passing tests. A change may add passes, and may not lose one.

### E.3 Recorded evidence

The v07 implementation of this design (branch `v07` of the Zen repository) recorded, against the reference interpreter:

| Check | Result |
| --- | --- |
| §6.1 / §6.2 MacArm64 listings | byte-identical, comments included |
| E.2 sweeps | 76,156 cases per route (LinuxX64, LinuxArm64 under qemu, C at three configurations), 0 mismatches |
| Differential fuzzing | 77,760 generated functions on five routes, 0 mismatches; all five mutations caught within 10 modules |
| Language corpus | 1138 / 1141 (the 3 remaining are invalid programs refused on purpose) |
| Must-fail corpus | 616 / 617 rejected |
| Self-hosting | stage-2 C == stage-3 C |

## Appendix F. Build order and decisions

| Step | Build | Done when |
| --- | --- | --- |
| 0 | Bring `tests/corpus`, `tests/must-fail` and the scorer from the old branch; the scorer runs any compiler binary | The old compiler's score is recorded as the baseline |
| 1 | Records, builder, validation, dump, reference semantics | Invalid IR fails predictably; independent expected results pass |
| 2 | MacArm64 / LinuxArm64 integer/Bool/memory/control | Both worked examples match §6 byte for byte; LinuxArm64 runs them |
| 3 | Calls/traps/globals/imports/indirect/Never | C works in both directions; stack args and sentinels pass |
| 4 | Floats/conversions | Every supported operation/type boundary passes |
| 5 | C route | Same defined corpus passes C and native |
| 6 | Frontend (Appendix I) | Language and must-fail corpora pass |
| Optional | LinuxX64 (A.2) | Same corpus passes the second ISA |

Public names are lower, alloc, write. The native example starts with MacArm64 and treats other native targets as deltas. Keep typed spills, explicit normalization, bounded scratch, coverage, and verification.

The 4080-byte frame and 1-MiB function policies are implementation-profile limits, not universal architecture facts. Larger frames are expanded with stack probing (touch each 4 KiB page in order before use) and checked by the physical verifier; anything above the profile's encodable range is a ResourceLimit. No custom object encoder or optimizer framework is required.

Each change names a test row, supplies semantics/validation, lowers it, and passes its tests before support is advertised.

## Appendix G. Physical instruction inventory

The main MachineInstruction and Asm records remain the only machine/output schemas. Every opcode has descriptors for operand forms, implicit registers/flags, encoding limits, and writing.

~~~text
enum Width { B8, B16, B32, B64 }
enum X64Condition { O, No, B, Ae, E, Ne, Be, A, S, Ns, P, Np, L, Ge, Le, G }
enum A64Opcode {
    Mov, MovZ, MovN, MovK, FMov,
    Add, Adds, Sub, Subs, Mul, SMulH, UMulH, MSub, SDiv, UDiv,
    And, Orr, Eor, Mvn, Lsl, Lsr, Asr, Cmp, CSet,
    SxtB, SxtH, SxtW, UxtB, UxtH, Adr, Adrp,
    Ldr, LdrB, LdrH, LdrSB, LdrSH, LdrSW,
    Ldur, LdurB, LdurH, LdurSB, LdurSH, LdurSW,
    Str, StrB, StrH, Stur, SturB, SturH, Ldp, Stp,
    FAdd, FSub, FMul, FDiv, FNeg, FCmp, FCvt,
    SCvtF, UCvtF, FCvtZS, FCvtZU,
    B, BCond, Cbz, Cbnz, Bl, Blr, Ret, Br, Brk
}
enum X64Opcode {
    Mov, MovAbs, MovSignExtend, MovZeroExtend, Lea,
    Add, Sub, IMul, Mul, IDiv, Div, Cdq, Cqo,
    And, Or, Xor, Not, Shl, Shr, Sar, Cmp, Test, SetCondition,
    MovSS, MovSD, MovD, MovQ,
    AddSS, AddSD, SubSS, SubSD, MulSS, MulSD, DivSS, DivSD,
    XorPS, XorPD, UcomiSS, UcomiSD,
    CvtSS2SD, CvtSD2SS, CvtSI2SS, CvtSI2SD, CvttSS2SI, CvttSD2SI,
    Jmp, JumpCondition, Call, Ret, Push, Pop, Leave, Ud2
}
~~~

PhysReg includes the sixteen x86 GPR identities and XMM0–XMM15. Views distinguish low 8/16/32/64-bit GPRs and scalar floats; AH/BH/CH/DH are excluded. X86 RSP cannot be an index; AArch64 SP and the zero register are distinct. Register-unit tables encode aliases and 32-bit-write zeroing.

Descriptor lookup unwraps Opcode.A64 or Opcode.X64, rejects the wrong target, and checks that width/condition fields and operand views match the selected form. The writer consumes the checked form without global operand reversal.

## Appendix H. Backend organisation: templates as data

§3.3 is already a set of tables. Implement it as tables. Split the backend **by IR kind, with targets as columns**, not by target.

~~~text
backend/
  int.zen  float.zen  convert.zen  memory.zen  call.zen  control.zen   // TABLE[op][class(type)][target]
  steps.zen    one interpreter of Read / Emit / Label / Commit / Return
  alloc.zen    liveness -> colour (§4.2 order) -> frame -> expand        // target-neutral
  target.zen   per-target facts only: pools, scratch, views, prologue, classify
  ops.zen      ONE opcode descriptor table (App. G)
  write.zen    one writer, per-format spellings (§5.3) as data
~~~

~~~text
template(op, type, target) = TABLE[op][class(type)][target]      // a row of §3.3
expand(t)                  = for step in t.steps: steps.run(step, homes, frame)

descriptor(opcode) = { operand forms, views, implicit registers, flags read/written,
                       immediate ranges, spelling per format }
verify_template(t)  uses descriptor   // §3.4
check_physical(i)   uses descriptor   // §4.6
write(i)            uses descriptor   // §5
~~~

One descriptor table feeds selection checks, physical checks and writing, so an instruction form is described once. Budget: the whole native backend (both ISAs) ≤ 3,000 lines.

**Compiler source style** (every part, not only the backend):

- **Closed sets are enums:** opcodes, diagnostic codes, targets, trap codes, token kinds. A table is indexed by an enum and matched exhaustively, so adding a variant makes the compiler name every place that must change.
- **No integer constants for kinds.** A number appears only where the format needs it: an encoding, an exit code, an ABI value.
- **The pseudocode in this document is the code.** Records here are written as Zen records with the same names. If the code and this document disagree, one of them changes in the same commit.

## Appendix I. Frontend: passes and budgets

The language is [ZEN_LANGUAGE.md](ZEN_LANGUAGE.md). The frontend is six passes; each owns the rules its section of that document is tagged with.

~~~text
lex/parse   bytes -> tree (kind, field, span); faults as ERROR/MISSING; lexical rules
collect     every declaration -> its signature (shape), keyed by canonical path; imports, modules, layout
fit         each body: does this expression's shape fit the expected one?  one fits(actual, expected)
            over interned types whose key carries qualifiers MUT | SECRET | SCOPED | REGION | FRAME
resolve     pin each name/call to the one declaration that fit; generics by substitution
cull        reach from main; every owned body is CHECKED, only reached ones are LOWERED
lower       resolved tree -> Ir (Appendix C rules); aggregates as stack objects, copies out of line
flow        on the validated Ir: definite assignment, use after move, must-use; spans mapped back
~~~

Rules that took the most code in v07 and must stay simple here:

- **Literals** fit any type whose range holds them; the context settles the type.
- **Overloads**: candidates whose shape fits; zero is an error naming the nearest, two or more is ambiguous.
- **Generics**: check the body once with variables, then once per concrete instance.
- **Ownership** is a type qualifier wherever the rule is about shape; only path-dependent rules go to flow.
- **Closures** passed to function-typed parameters, and loop bodies, are inlined; `h.break`, `h.next` and `.try()` are jumps.
- **Aggregate copies** above a small size call one copy function per type (v07: inline copies were 90% of all instructions).

| Pass | Budget (lines) |
| --- | --- |
| lex + parse | 2,000 |
| collect | 1,000 |
| fit + types + resolve | 4,000 |
| lower | 5,000 |
| flow | 800 |

### I.1 Pipeline as stages

`.sema()` in §0 is these stages. Each returns a new value and never changes its input.

~~~text
source.lex().parse()     -> Ast          syntax only; limits from Appendix J
Ast.collect()            -> Decls        every signature by canonical path; imports; layouts
Decls.check()            -> Checked      resolve + fit + cull; every owned body checked
Checked.lower()          -> Ir + Origins every reached body; IrBuilder.finish() validates
Ir.flow(Origins)         -> Ir           init, moves, must-use; errors carry source spans
~~~

`Origins` is a side table `(FunctionId, InstructionId | exit of BlockId) -> SourceSpan`, kept beside the Ir and never inside it. The backend never sees it. A frontend diagnostic uses it to point at source.

### I.2 Generics: instance by key

Generic functions, generic types and type-returning comptime calls share one identity rule: **an instance is its (definition, arguments) key.**

~~~text
intern(Box<i32>)          = types[(DefId(Box), [i32])]            // a TypeId, made once
instance(f, [i32, str])   = functions[(DefId(f), [i32, str])]     // a FunctionId, lowered once

check_generic(f):         // once, with each type variable standing for its bound
    check f.body treating T as an opaque type that has exactly T's bound's members
lower_instance(f, args):  // once per key that cull reaches
    lower f.body with T := args                                   // substitution, no re-check
~~~

- **Checking once with variables** finds errors in generics no one has instantiated yet. A body error found only after substitution is a compiler bug, not a user error.
- **Inference** reads type arguments from argument types through `fits()`. Literals follow DESIGN.md: they take the context's type, else `i32` when they fit, else `i64`.
- **Polymorphic recursion** (an instance that needs a bigger instance of itself) stops at the instance-depth limit with `ResourceLimit`.

### I.3 Flow: one solver, three facts

Flow runs on the validated Ir's control-flow graph. Lowering attaches **events** to instructions, in a side table like `Origins`:

| Event | Meaning |
|---|---|
| `Def(local)` | `local` is initialized |
| `Use(local)` | `local` is read |
| `Move(local)` | `.consume()`: `local` is dead afterwards |
| `Result(local)` | `local` holds a failing `Res` that must be used |
| `Exit(scope)` | `scope` ends: every pending `Result` in it must have been used |

One forward dataflow solver (the §1.4 loop, made generic over the join) computes all three facts:

| Fact | Join at a merge | Error |
|---|---|---|
| definitely initialized | intersection | `Use` of a local that is not in the set |
| maybe moved | union | `Use` or `Move` of a local that is in the set (`use after move`) |
| pending must-use | union | `Exit(scope)` while one of its locals is still pending |

§1.4's register check stays in `Ir.validate` as the backend's safety net; I.3 is the user-facing check with spans. A failing `Res` that is never bound (an expression statement) is refused in fit already; flow handles the path-dependent cases only.

### I.4 Comptime

Comptime has three jobs, and only one needs an evaluator.

| Job | How |
|---|---|
| `@meta(n: T).fields().loop(..)`, `@meta(v).kind` typecase | **unrolled during check**: the field list and the kind are known, so the loop body is checked and lowered once per field. No evaluator. |
| Constants: globals, `Limits.WIDTH`, array counts, `build.zen` | **lower to Ir, validate, run on the Appendix B interpreter.** The result is read back as bytes by its layout: a constant, a global initializer, or the `Package`/`Graph` data. |
| Type-returning functions (`AddFoo(Circle)`) | T2. When added, they use I.2's instance key. |

The evaluator gets **no `Env`**. A comptime program that calls an import fails with `UnsupportedFeature`. It is step-limited and memory-limited (Appendix J), and the same inputs always give the same bytes. There is one interpreter: the reference oracle from Appendix B is also the comptime engine.

### I.5 Diagnostics policy

- **Within a body: stop at the first error.** Recovering inside an expression doubles a checker's size for cascades no one reads.
- **Across bodies: keep going.** Each body is checked independently, and an error in one doesn't stop the others.
- **Cap: 100 diagnostics.** Collect errors (duplicate or unknown declarations) stop before check.
- **Every diagnostic** has a code (E.1), a span and one sentence. If there's a fix, it's named (for example, the missing import).

## Appendix J. Security

The compiler's attack surface is every input it reads: source, the build manifest, dependency sources, native headers.

- **Trusted core**: lex/parse, collect/fit, and `Ir.validate`. Everything after validation consumes checked data; nothing downstream re-interprets source.
- **No foreign code in the trusted path.** The parser is written in Zen; no generated C parser, no header parsing.
- **External tools** (cc, as, ld, git) are invoked with argument arrays, never a shell string; every input and output path is declared.
- **Build files run without `Env`**: no file, network, clock or process access at build-evaluation time. Dependencies' build code never runs (BUILD_AND_PACKAGES.md §6).
- **Generated code**: checked arithmetic and bounds by default; traps abort; `Ptr<T>` and `c.bind` are the only unchecked doors, and both are visible in source.
- **JIT is out of the core profile.** Mapping executable memory is the riskiest feature; if added, W^X only, never writable and executable at once.
- **Resource limits** on every phase. Hitting one is a `ResourceLimit` diagnostic, never a crash or a hang:

| Limit | Default |
|---|---|
| Source file size | 16 MiB |
| Token or string literal length | 1 MiB |
| Parser nesting depth (an explicit counter, not the host stack) | 256 |
| Inlining depth (C.2) and generic instance depth (I.2) | 64 |
| Generic instances per program | 100,000 |
| Comptime steps / memory per evaluation | 10^8 steps / 256 MiB |
| IR function size, frame size | §F: 1 MiB, 4080 bytes before probing |
- **Fuzzing** covers every input stage: the parser (mutated sources), the checker (must-fail corpus plus mutations), and the backend (Appendix E.2 differential fuzzing).
- **Runtime C** (entry, trap handler, Env glue) stays under 200 lines.

## Appendix K. Bootstrap

The seed is part of the attack surface; keep it small and auditable.

~~~text
seed (generated C of the compiler, one file per module)
  --cc-->  stage 1 compiler
  stage 1 builds stage 2;  stage 2 builds stage 3;  require C(stage 2) == C(stage 3)
~~~

- The seed must compile with a small C compiler (TCC) as well as clang/gcc, so it can sit in an auditable bootstrap chain (stage0 → Mes → TCC).
- Reproducible: the same sources give byte-identical seed and stage outputs.
- **Diverse double-compiling**: build the compiler with two independent compilers (for example the old Zen compiler and this one); their stage-2 outputs must be identical.
- Seed size tracks compiler size; a smaller compiler is a smaller seed.

**Stage 0 is the existing compiler.** The old Zen compiler (branch `codex/jit-land-20261021`, Zen to C) builds the first one:

~~~text
old zen   builds new  -> new0      the new compiler is written in the T0 subset both accept
new0      builds new  -> new1
new1      builds new  -> new2      require C(new1) == C(new2); commit new2's C as the seed
seed --cc (clang, gcc, tcc) -> new  the old compiler is no longer needed
~~~

The rule while the old compiler is stage 0: every commit of the new compiler must still build with it, so the T0 subset is enforced by a test, not by memory.

## Appendix L. Runtime and the T0 standard library

The compiler is useless without the std it compiles itself with. T0 needs only this:

| Module | Contents |
|---|---|
| `std.core` | `Res`, `Ok`, `Err`, `None`, `Error`, `Eq`, `Drop`, `value_or`, `ok_or`, `ignore` |
| `std.mem` | `Alloc` (interface), `Arena` over `env.mem` pages, `Ptr<T>` read/write/copy |
| `std.seq` | `Seq<T>`, `Range<T>`, `loop`, `find`, `map`, `filter` (C.2) |
| `std.text` | `str`, `String`, `Sink`, formatting of integers and `str` (`{}`, `{name}`) |
| `std.collections` | `Vec<T>`, `Map<K, V>` (open addressing) |
| `std.io` | `Writer` (`write`, `print`, `println`), `Env.out`, `Env.err`, `Env.fs.read`/`write`, `Env.args` |

The runtime is C, at most 200 lines (Appendix J):

~~~text
entry(argc, argv):  build Env (pages, out, fs, args) -> call zen main -> map its result to an exit code
                    Ok(n) -> n;  Err -> print it, 1;  () main -> 0
trap(code):         print "file:line:col: trap: <what>" -> exit 134
~~~

**How a trap knows its location.** Decided for v1:

- **Checks the frontend inserts** (bounds, `.unwrap`-style, unreachable) use `Explicit(65536 + site)` trap codes. The runtime looks `site` up in a global table `(file, line, col, what)` that lowering emits, so the message is exact: `file:line:col: trap: <what>`.
- **Arithmetic traps from templates** (§3.3) keep the shared per-function stubs, so §6 stays byte-identical. Their message is `trap: integer overflow in <function>`.

Exact arithmetic locations can come later as an option (one stub per site, two instructions each) without changing the IR.

**Std rules**, so it stays small:

- **One way to do each job.** No aliases, no convenience wrappers, and no second API that differs only in naming.
- **Memory has one model.** `Alloc` is the only allocation interface and `Arena` (pages from `env.mem`) is the only T0 implementation. There is no global heap, no reference counting and no GC. Collections take an `Alloc` and free with their arena.
- **Closed sets are enums.** Error kinds, modes and flags are enum variants, never groups of integer constants (ZEN_LANGUAGE.md §4).
- **Each module is under 400 lines.** A module that grows past that splits by job, not by helper.

Budget: std for T0 ≤ 4,000 lines of Zen, runtime ≤ 200 lines of C.
