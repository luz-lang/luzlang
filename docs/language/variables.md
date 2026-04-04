# Variables

Variables are assigned with `=`. No declaration keyword is needed.

```
x = 10
name = "Luz"
items = [1, 2, 3]
data = {"score": 100}
empty = null
```

## Reassignment

Variables can be reassigned to any type at any time:

```
x = 10
x = "now a string"
x = true
```

## Scope

Variables live in the scope where they are assigned. Functions create their own scope. Inner scopes can read variables from outer scopes (closures), but assigning in an inner scope creates a new local variable — it does not modify the outer one.

```
x = 10

function show() {
    write(x)   # reads outer x → 10
}

function shadow() {
    x = 99     # creates a new local x, does not touch outer x
    write(x)   # 99
}

show()
shadow()
write(x)   # still 10
```

## Typed declarations

A variable can declare its expected type on assignment. The type is checked at runtime — assigning a value of the wrong type raises a `TypeViolationFault`.

```
x: int     = 5
name: string = "Alice"
active: bool = true
ratio: float = 0.5
```

The Luz static type checker also reports violations at check time, before execution.

Valid type names: `int`, `float`, `number`, `string`, `bool`, `list`, `dict`, `null`, `any`, any class or struct name, or a generic collection type (see below).

```
attempt {
    x: int = "oops"
} rescue (e) {
    write(e)   # TypeViolationFault: Variable 'x' expects type 'int', got 'string'
}
```

## Generic collection types

You can annotate the element type of a list or the key/value types of a dict:

```
ids:    list[int]            = [1, 2, 3]
names:  list[string]         = ["Alice", "Bob"]
prices: dict[string, float]  = {"apple": 1.5, "banana": 0.8}
```

A plain `list` or `dict` literal satisfies any `list[T]` / `dict[K,V]` annotation.

## Nullable types

Appending `?` to a type allows the variable to also hold `null`:

```
username: string? = null    # ok — string or null
username = "Alice"          # ok

index: int? = find_item()   # may return null
```

Use the `??` (null-coalescing) operator to supply a fallback when a value is `null`:

```
display = username ?? "Anonymous"
```

## Constants

`const` declares a compile-time constant. It cannot be reassigned after declaration.

```
const MAX_SIZE: int    = 1024
const APP_NAME: string = "MyApp"
const PI: float        = 3.14159
```

Attempting to reassign a constant raises a `SemanticFault`.

## Compound assignment

Luz supports `+=`, `-=`, `*=`, and `/=`:

```
count += 1
total *= 2
score -= 5
ratio /= 4
```
