# luz-types

Type predicates, safe casting, and schema validation.

```
from "types" import types
```

---

## Type predicates

Check the runtime type of any value without writing `typeof(x) == "..."` everywhere.

| Method | Returns `true` when |
|---|---|
| `types.is_int(x)` | `x` is an integer |
| `types.is_float(x)` | `x` is a float |
| `types.is_number(x)` | `x` is an int or float |
| `types.is_string(x)` | `x` is a string |
| `types.is_bool(x)` | `x` is a boolean |
| `types.is_null(x)` | `x` is `null` |
| `types.is_list(x)` | `x` is a list |
| `types.is_dict(x)` | `x` is a dict |
| `types.is_callable(x)` | `x` is a function or lambda |

```
write(types.is_int(42))         # true
write(types.is_float(3.14))     # true
write(types.is_number(42))      # true
write(types.is_string("hi"))    # true
write(types.is_bool(true))      # true
write(types.is_null(null))      # true
write(types.is_list([1, 2]))    # true
write(types.is_dict({"a": 1}))  # true
write(types.is_callable(fn(x) => x))  # true
```

---

## Safe casting

Convert values to another type with a descriptive error on failure instead of a raw `CastFault`.

| Method | Description |
|---|---|
| `types.safe_int(x)` | Convert to int — raises if not possible |
| `types.safe_float(x)` | Convert to float — raises if not possible |
| `types.safe_str(x)` | Convert to string — always succeeds |
| `types.safe_bool(x)` | Convert to boolean — always succeeds |

```
write(types.safe_int("42"))     # 42
write(types.safe_float("3.14")) # 3.14
write(types.safe_str(99))       # 99
write(types.safe_bool(0))       # false

attempt {
    types.safe_int("abc")
} rescue (e) {
    write(e)   # cannot cast abc to int
}
```

---

## Schema validation

`types.validate(data, schema, required)` checks that a dict matches an expected shape.

- `data` — the dict to validate
- `schema` — a dict mapping field names to expected type strings
- `required` — a list of required field names, or `null` to require all fields in the schema

Raises a `UserFault` on the first violation found.

```
schema = {
    "name": "string",
    "age":  "int",
    "active": "bool"
}

data = {"name": "Alice", "age": 30, "active": true}
types.validate(data, schema, null)   # passes

# Missing required field
attempt {
    types.validate({"name": "Alice"}, schema, null)
} rescue (e) {
    write(e)   # missing required field 'age'
}

# Wrong type
attempt {
    types.validate({"name": "Alice", "age": "30", "active": true}, schema, null)
} rescue (e) {
    write(e)   # field 'age' expected int, got string
}

# Only 'name' is required — other fields are optional
types.validate({"name": "Alice"}, schema, ["name"])   # passes
```
