# Language Features

**Typed variable declarations:** Variables can declare a type annotation on assignment. The interpreter enforces it at runtime via `_check_type()`.

```luz
x: int = 5
name: string = "Alice"
```

Raises `TypeViolationFault` if the value doesn't match the declared type. Implemented in `visit_TypedVarAssignNode`.

**Slice syntax:** Lists and strings support slice expressions with optional step.

```luz
list[start:end]        # end-exclusive
list[start:end:step]   # with step
list[:end]             # from beginning
list[start:]           # to end
"hello"[1:3]           # "el"
```

Implemented in `visit_SliceNode`. Raises `ZeroDivisionFault` if step is 0.

**Dict dot methods:** Dicts support dot method syntax in addition to global builtins.

```luz
d.keys()         # same as keys(d)
d.values()       # same as values(d)
d.len()          # same as len(d)
d.contains(key)  # same as key in d
d.remove(key)    # same as remove(d, key)
```

**`insert(list, index, value)` builtin:** Inserts a value at a position in a list (in-place, like `append`).

```luz
nums = [1, 2, 4]
insert(nums, 2, 3)  # [1, 2, 3, 4]
```

**Type checking respects inheritance:** `_check_type()` walks the class hierarchy via `.parent`, so a subclass instance satisfies a parent type annotation.

```luz
class Animal {}
class Dog extends Animal {}
function greet(a: Animal) { write("hello") }
greet(Dog())  # works
```
