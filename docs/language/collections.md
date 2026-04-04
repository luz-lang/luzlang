# Collections

## Lists

A list is an ordered, mutable sequence of values.

```
fruits = ["apple", "banana", "cherry"]
mixed  = [1, "two", 3.0, true, null]
empty  = []
```

### Generic type annotations

Annotate the element type for static checking:

```
scores: list[int]    = [88, 72, 95]
names:  list[string] = ["Alice", "Bob"]
```

### Indexing

Zero-based. Negative indices count from the end:

```
write(fruits[0])    # apple
write(fruits[-1])   # cherry  (last element)
write(fruits[-2])   # banana
```

### Assignment by index

```
fruits[1] = "mango"
```

### Iteration

```
for fruit in fruits {
    write(fruit)
}
```

### Membership test

```
write("apple" in fruits)      # true
write("grape" not in fruits)  # true
```

### Slicing

Extract a sub-list using `[start:end]` or `[start:end:step]`. Indices are end-exclusive. Negative indices count from the end.

```
nums = [10, 20, 30, 40, 50]

write(nums[1:3])     # [20, 30]
write(nums[:3])      # [10, 20, 30]
write(nums[2:])      # [30, 40, 50]
write(nums[::2])     # [10, 30, 50]   (every other element)
write(nums[::-1])    # [50, 40, 30, 20, 10]  (reversed)
```

Slice indices must be integers. A step of `0` raises a `ZeroDivisionFault`.

### List comprehensions

Build a new list from an expression and an optional filter:

```
squares = [x * x for x in [1, 2, 3, 4, 5]]          # [1, 4, 9, 16, 25]
evens   = [x for x in range(1, 10) if even(x)]       # [2, 4, 6, 8]
upper   = [s.uppercase() for s in ["a", "b", "c"]]   # ["A", "B", "C"]
```

### List built-ins

| Function | Description |
|---|---|
| `len(list)` | Number of elements |
| `append(list, value)` | Add element to the end |
| `pop(list)` | Remove and return the last element |
| `pop(list, index)` | Remove and return element at index |
| `insert(list, index, value)` | Insert value at index, shifting elements right |
| `sum(list)` | Sum all numeric elements |

```
nums = [1, 2, 4, 5]
insert(nums, 2, 3)
write(nums)       # [1, 2, 3, 4, 5]
write(sum(nums))  # 15
```

### List dot methods

| Method | Description |
|---|---|
| `list.append(value)` | Add element to the end |
| `list.pop()` | Remove and return the last element |
| `list.pop(index)` | Remove and return element at index |
| `list.len()` | Number of elements |
| `list.contains(value)` | True if value is in the list |
| `list.join(sep)` | Join elements into a string |
| `list.sort()` | Sort in place (ascending) |
| `list.reverse()` | Reverse in place |

```
nums = [3, 1, 4, 1, 5, 9]
nums.sort()
write(nums)              # [1, 1, 3, 4, 5, 9]
nums.reverse()
write(nums)              # [9, 5, 4, 3, 1, 1]
write(nums.contains(4))  # true
write(nums.len())        # 6
```

---

## Strings

Strings support indexing and negative indices:

```
s = "hello"
write(s[0])    # h
write(s[-1])   # o
```

Strings also support slicing:

```
write(s[1:3])   # el
write(s[:3])    # hel
write(s[1:])    # ello
```

Membership test:

```
write("ell" in "hello")   # true
```

### String dot methods

| Method | Description |
|---|---|
| `s.len()` | String length |
| `s.trim()` | Remove surrounding whitespace |
| `s.uppercase()` | Convert to uppercase |
| `s.lowercase()` | Convert to lowercase |
| `s.swap(old, new)` | Replace all occurrences of `old` with `new` |
| `s.split(sep?)` | Split into a list (default sep: whitespace) |

```
title = "  Hello, World!  "
write(title.trim())                   # Hello, World!
write(title.trim().lowercase())       # hello, world!
write("a,b,c".split(","))            # ["a", "b", "c"]
write(title.trim().len())            # 13
```

Methods can be chained:

```
slug = "  My Title  ".trim().lowercase().swap(" ", "-")
write(slug)   # my-title
```

---

## Dictionaries

A dictionary maps keys to values. Keys must be strings or numbers.

```
person = {"name": "Alice", "age": 30}
```

### Generic type annotations

```
prices: dict[string, float] = {"apple": 1.5, "banana": 0.8}
counts: dict[string, int]   = {"a": 1, "b": 2}
```

### Access and assignment

```
write(person["name"])   # Alice
person["age"] = 31
person["city"] = "Madrid"
```

### Membership test

```
write("name" in person)      # true
write("email" not in person) # true
```

### Iteration

Iterating over a dictionary yields its keys:

```
for key in person {
    write($"{key}: {person[key]}")
}
```

### Dictionary built-ins

| Function | Description |
|---|---|
| `len(dict)` | Number of key-value pairs |
| `keys(dict)` | Returns a list of all keys |
| `values(dict)` | Returns a list of all values |
| `remove(dict, key)` | Remove key and return its value |

### Dictionary dot methods

| Method | Equivalent built-in |
|---|---|
| `dict.keys()` | `keys(dict)` |
| `dict.values()` | `values(dict)` |
| `dict.len()` | `len(dict)` |
| `dict.contains(key)` | `key in dict` |
| `dict.remove(key)` | `remove(dict, key)` |

```
person = {"name": "Alice", "age": 30}

write(person.keys())           # ["name", "age"]
write(person.values())         # ["Alice", 30]
write(person.len())            # 2
write(person.contains("age"))  # true
person.remove("age")
```
