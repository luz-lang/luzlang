# Built-in Functions

## I/O

| Function | Description |
|---|---|
| `write(...)` | Print one or more values to stdout, separated by spaces |
| `listen(prompt?)` | Print `prompt` and read a line from stdin. Automatically converts to `int` or `float` if the input is numeric; returns a `string` otherwise |

```
write("hello")              # hello
write(1, 2, 3)              # 1 2 3
name = listen("Name: ")     # returns string
age  = listen("Age: ")      # returns int if user types a number
```

---

## Type inspection

| Function | Description | Example |
|---|---|---|
| `typeof(value)` | Returns the type name as a string | `typeof(42)` → `"int"` |
| `instanceof(obj, Class)` | True if obj is an instance of Class or a subclass | `instanceof(d, Animal)` → `true` |

---

## Type casting

| Function | Description |
|---|---|
| `to_int(v)` | Convert to integer (truncates floats, parses strings) |
| `to_float(v)` | Convert to float |
| `to_str(v)` | Convert to string |
| `to_bool(v)` | Convert to boolean |
| `to_num(v)` | Convert string to int or float (auto-detects) |

Raises `CastFault` if the conversion is not possible.

```
to_int(3.9)      # 3
to_int("42")     # 42
to_float("2.5")  # 2.5
to_str(true)     # "true"
to_bool(0)       # false
to_bool("")      # false
to_num("10")     # 10
to_num("3.14")   # 3.14
```

---

## Math

| Function | Description | Example |
|---|---|---|
| `abs(x)` | Absolute value | `abs(-7)` → `7` |
| `sqrt(x)` | Square root | `sqrt(16)` → `4.0` |
| `floor(x)` | Round down to integer | `floor(3.9)` → `3` |
| `ceil(x)` | Round up to integer | `ceil(3.1)` → `4` |
| `round(x, digits?)` | Round to N decimal places (default 0) | `round(3.567, 2)` → `3.57` |
| `clamp(x, low, high)` | Force x into the range [low, high] | `clamp(15, 0, 10)` → `10` |
| `max(a, b, ...)` or `max(list)` | Maximum of values or a list | `max(3, 8, 2)` → `8` |
| `min(a, b, ...)` or `min(list)` | Minimum of values or a list | `min([5, 1, 9])` → `1` |
| `sum(list)` | Sum all numeric elements of a list | `sum([1, 2, 3])` → `6` |
| `sign(x)` | Returns -1, 0, or 1 | `sign(-5)` → `-1` |
| `odd(x)` | True if x is odd | `odd(3)` → `true` |
| `even(x)` | True if x is even | `even(4)` → `true` |

---

## Lists

| Function | Description |
|---|---|
| `len(list)` | Number of elements |
| `append(list, value)` | Add element to the end (modifies in place) |
| `pop(list)` | Remove and return the last element |
| `pop(list, index)` | Remove and return the element at index |
| `insert(list, index, value)` | Insert value at index, shifting elements right |
| `sum(list)` | Sum of all numeric elements |

```
nums = [10, 20, 30]
append(nums, 40)
write(len(nums))      # 4
write(pop(nums))      # 40
write(pop(nums, 0))   # 10
write(sum(nums))      # 50

items = [1, 2, 4]
insert(items, 2, 3)
write(items)          # [1, 2, 3, 4]
```

---

## Dictionaries

| Function | Description |
|---|---|
| `len(dict)` | Number of key-value pairs |
| `keys(dict)` | Returns a list of all keys |
| `values(dict)` | Returns a list of all values |
| `remove(dict, key)` | Remove key and return its value |

```
d = {"a": 1, "b": 2}
write(keys(d))         # ["a", "b"]
write(values(d))       # [1, 2]
write(remove(d, "a"))  # 1
```

---

## Strings

### Global functions

| Function | Description | Example |
|---|---|---|
| `len(s)` | String length | `len("hi")` → `2` |
| `trim(s)` | Remove surrounding whitespace | `trim("  hi  ")` → `"hi"` |
| `uppercase(s)` | Convert to uppercase | `uppercase("hi")` → `"HI"` |
| `lowercase(s)` | Convert to lowercase | `lowercase("HI")` → `"hi"` |
| `swap(s, old, new)` | Replace all occurrences of `old` with `new` | `swap("aXb", "X", "-")` → `"a-b"` |
| `split(s, sep?)` | Split into list (default sep: whitespace) | `split("a,b", ",")` → `["a","b"]` |
| `join(sep, list)` | Join list into a string | `join("-", ["a","b"])` → `"a-b"` |
| `contains(s, sub)` | True if `sub` is in `s` | `contains("hello", "ell")` → `true` |
| `begins(s, prefix)` | True if `s` starts with `prefix` | `begins("hello", "he")` → `true` |
| `ends(s, suffix)` | True if `s` ends with `suffix` | `ends("hello", "lo")` → `true` |
| `find(s, sub)` | Index of first occurrence, `-1` if not found | `find("hello", "ll")` → `2` |
| `count(s, sub)` | Count occurrences of `sub` in `s` | `count("banana", "a")` → `3` |

### Dot methods

All string operations are also available as dot methods and can be chained:

| Method | Equivalent global |
|---|---|
| `s.len()` | `len(s)` |
| `s.trim()` | `trim(s)` |
| `s.uppercase()` | `uppercase(s)` |
| `s.lowercase()` | `lowercase(s)` |
| `s.swap(old, new)` | `swap(s, old, new)` |
| `s.split(sep?)` | `split(s, sep?)` |

```
title = "  Hello World  "
write(title.trim().lowercase())          # hello world
slug  = title.trim().lowercase().swap(" ", "-")
write(slug)                              # hello-world
words = "a,b,c".split(",")
write(words.join(" | "))                 # a | b | c
```
