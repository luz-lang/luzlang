# Types

Luz is dynamically typed by default, with optional static type annotations that are checked both at runtime and by the built-in static type checker.

## Primitive types

| Type | Example | Notes |
|---|---|---|
| `int` | `42`, `-7`, `0` | Whole numbers, arbitrary size |
| `float` | `3.14`, `-0.5`, `.5` | Decimal numbers (IEEE 754) |
| `string` | `"hello"` | Double-quoted, immutable |
| `bool` | `true`, `false` | Lowercase literals |
| `null` | `null` | Represents the absence of a value |

## Collection types

| Type | Example | Notes |
|---|---|---|
| `list` | `[1, "two", 3.0]` | Ordered, mixed types allowed |
| `dict` | `{"key": value}` | String or number keys |

Generic annotations narrow the element type:

```
scores: list[int]           = [90, 85, 70]
labels: list[string]        = ["a", "b"]
prices: dict[string, float] = {"item": 1.5}
```

## Fixed-size numeric types

For performance-sensitive or memory-constrained code, Luz provides fixed-width integer and float types. The interpreter enforces the valid range at assignment time.

| Type | Range |
|---|---|
| `int8` | −128 to 127 |
| `int16` | −32 768 to 32 767 |
| `int32` | −2 147 483 648 to 2 147 483 647 |
| `int64` | −9 007 199 254 740 992 to 9 007 199 254 740 992 |
| `uint8` | 0 to 255 |
| `uint16` | 0 to 65 535 |
| `uint32` | 0 to 4 294 967 295 |
| `float32` | 32-bit IEEE 754 float |
| `float64` | 64-bit IEEE 754 float |

```
byte: uint8  = 255
temp: int16  = -200
pi32: float32 = 3.14159
```

Narrower fixed-size integers satisfy wider annotations (widening is safe):

```
small: int8  = 42
wider: int32 = small   # ok — int8 widens to int32
```

Out-of-range assignments raise a `TypeViolationFault`.

## Nullable types

Appending `?` to any type allows `null` in addition to the base type:

```
name: string? = null     # ok
name = "Alice"           # ok

function find(id: int) -> string? {
    # ...
    return null
}
```

Use `??` to provide a fallback when the value is `null`:

```
display = name ?? "Anonymous"
```

## Type inspection

Use `typeof()` to get the type name as a string:

```
write(typeof(42))        # int
write(typeof(3.14))      # float
write(typeof("hello"))   # string
write(typeof(true))      # bool
write(typeof(null))      # null
write(typeof([1, 2]))    # list
write(typeof({"a": 1}))  # dict
```

For objects, `typeof()` returns the class name:

```
class Dog { }
d = Dog()
write(typeof(d))   # Dog
```

## Escape sequences in strings

| Sequence | Result |
|---|---|
| `\n` | Newline |
| `\t` | Horizontal tab |
| `\r` | Carriage return |
| `\\` | Literal backslash |
| `\"` | Literal double quote |

```
write("line one\nline two")
write("column1\tcolumn2")
write("She said \"hello\"")
```

## Type casting

Use the built-in cast functions to convert between types:

| Function | Description |
|---|---|
| `to_int(v)` | Convert to integer (truncates floats) |
| `to_float(v)` | Convert to float |
| `to_str(v)` | Convert to string |
| `to_bool(v)` | Convert to boolean |
| `to_num(v)` | Convert to int or float (auto-detects from string) |

```
write(to_int(3.9))      # 3
write(to_float("2.5"))  # 2.5
write(to_str(42))       # "42"
write(to_bool(0))       # false
write(to_num("10"))     # 10
write(to_num("3.14"))   # 3.14
```

If the conversion fails, a `CastFault` is raised:

```
attempt {
    x = to_int("abc")
} rescue (e) {
    write(e)   # CastFault: cannot convert "abc" to int
}
```
