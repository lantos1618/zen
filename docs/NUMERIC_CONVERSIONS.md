# Numeric conversions

Primitive conversions belong to `std.core.num`. A dot call uses the exported
operation associated with its receiver type; a bare call imports it explicitly.
Both spellings evaluate the operand once.

Lossless widening returns the destination value directly. Checked conversion
returns `Res<T>`: a fitting value becomes `Ok(value)`, and a value outside the
destination range becomes `None`. No `to_` conversion allocates, truncates,
wraps, saturates, rounds, or silently changes an error into absence; the only
rounding conversions are the explicit `narrow_` family below.

```zen
to_i32 = std.core.num

parse_count = (text: str) Res<i32> {
    text.parse_i64().try().to_i32()
}
```

The source type selects the overload; the expected return type does not.
An `i16` receiver's `to_i32()` is lossless and returns `i32`. An `i64` receiver's
`to_i32()` is checked and returns `Res<i32>`. A caller can propagate `None` with
`.try()` or translate it explicitly with `.ok_or(error)`.

## Supported checked conversions

| Source | Destination |
| --- | --- |
| `usize`, `u32` | `u8` |
| `u64` | `u16`, `usize`, `i32` |
| `u128` | `u64` |
| `i64` | `i32` |
| `i32` | `c_int` |
| `c_int` | `i32` |

## Floating-point conversions

Every `to_f64` / `to_f32` whose source values all fit exactly is lossless and
returns the float directly: `i8`, `i16`, `i32`, `u8`, `u16`, `u32` and `f32`
to `f64`; `i8`, `i16`, `u8`, `u16` to `f32`.

Conversions between an integer and `f64` that some values cannot survive are
checked like integer narrowing and return `Res<T>`:

| Source | Destination | `None` when |
| --- | --- | --- |
| `f64` | `i32`, `i64` | the value is fractional, NaN, infinite, or outside the range |
| `i64`, `u64` | `f64` | the integer lies between two doubles (possible only beyond 2^53) |

A caller that wants rounding says so: `std.math.round(x).to_i64()`.

Rounding is a separate, explicit family spelled `narrow_`, so that a `to_`
call always means "every value, or `None`":

| Operation | Result |
| --- | --- |
| `f64.narrow_f32()` | `f32` |
| `i64.narrow_f64()`, `u64.narrow_f64()` | `f64` |

A narrowing always produces a value: the nearest representable one under
IEEE 754 round-to-nearest, ties to even (Zen never changes the floating-point
environment). An `f64` at or beyond `f32.MAX` plus half a unit in the last
place becomes positive or negative infinity; one between `f32.MAX` and that
bound becomes `f32.MAX`. NaN stays NaN and infinities stay infinite. The C
backend tests the range before casting, so no input reaches C's undefined
out-of-range float conversion. Composing `i64.narrow_f64().narrow_f32()`
rounds twice and can differ from a single rounding by one ulp.

There is no `to_f32` on `f64`, no conversion from `f32` straight to an
integer (widen with `to_f64` first; that is exact), and no truncating
float-to-integer operation.

`usize` follows the target pointer width; current targets are 64-bit. The
`u64` conversion keeps an optional result even on a 64-bit target. C integer
bridges use the destination's limits from the selected native ABI.

The existing `ToI64`, `ToU64`, and other widening bounds remain useful for
functions accepting several losslessly convertible source types. Their
`widen_*` members are implemented by the same standard conversion declarations.
They do not promise checked narrowing or authorize new compiler operations.

Explicit truncation (`truncate_u32` and friends) and `mul_wide` are separate
machine primitives, not conversions; see DESIGN.md "Wide integers and
truncation". They keep the conversion rule that nothing narrows implicitly.

## Compiler boundary

The bodyless declarations in [std.core.num](../src/std/core/num.zen) are
compiler-provided. [Semantic validation](../src/sema/sema_numeric.zen) checks
their defining module, visibility, arity,
mutability, generic parameters, source type, and result type against the finite
supported contract. It records validated operations by declaration identity
before checking function bodies. Re-exports and local import aliases retain
that identity.

[C numeric generation](../src/gen/gen_c/gen_c_num.zen) renders these recorded
operations. C call lowering
never interprets a `to_` prefix as permission to cast. Checked target ranges
form an enum, so adding a range requires handling it in the renderer.

A source module cannot introduce a bodyless primitive conversion of its own,
even if nobody calls it. Write a function body or import the standard operation.
A user function with a body remains an ordinary function, including one named
`to_i32`. A translated C declaration keeps its explicit foreign binding and is
not interpreted as a conversion.

This contract uses the existing standard-library declaration mechanism; there
is no new intrinsic annotation or syntax. Other compiler-provided operations
still need their own explicit contracts. Scalar JS/assembly currently refuse
numeric types and conversion calls outside their documented support; this
change does not extend their supported surface.

## Evidence

The conversion corpus checks signed and unsigned boundaries, evaluation once,
free and dot calls, parsing, and native C integer bridges. Semantic fixtures
reject local conversion declarations and malformed standard signatures, while
existing tests exercise ordinary same-named functions and generic widening
bounds. `make verify` remains the aggregate gate.
