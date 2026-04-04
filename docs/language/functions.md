# Functions

## Defining a function

```
function greet(name) {
    return "Hello, " + name + "!"
}

write(greet("world"))   # Hello, world!
```

- `return` exits the function with a value.
- A function that reaches the end without a `return` returns `null`.

## Default parameters

Parameters can have a default value. All required parameters must come before defaults.

```
function greet(name, greeting = "Hello") {
    write($"{greeting}, {name}!")
}

greet("Alice")             # Hello, Alice!
greet("Bob", "Hi")         # Hi, Bob!
```

```
function connect(host, port = 8080, secure = false) {
    write($"{host}:{port} secure={secure}")
}

connect("localhost")                # localhost:8080 secure=false
connect("example.com", 443, true)   # example.com:443 secure=true
```

## Named (keyword) arguments

Any argument can be passed by name, regardless of its position. Positional arguments must come before named ones.

```
function create_user(name, age, role = "user") {
    write($"{name} (age {age}, role: {role})")
}

create_user("Alice", 30)                     # Alice (age 30, role: user)
create_user("Bob", age: 25, role: "admin")   # Bob (age 25, role: admin)
create_user(name: "Carol", age: 28)          # Carol (age 28, role: user)
```

## Variadic functions

A `...name` parameter collects all extra arguments into a list. It must be the last parameter.

```
function sum(...nums) {
    total = 0
    for n in nums { total += n }
    return total
}

write(sum(1, 2, 3))         # 6
write(sum(10, 20, 30, 40))  # 100
write(sum())                # 0
```

Variadic can be combined with regular parameters:

```
function log(level, ...messages) {
    for msg in messages {
        write($"[{level}] {msg}")
    }
}

log("INFO", "Server started", "Ready")
```

## Multiple return values

A function can return multiple values. Use destructuring assignment to unpack them.

```
function min_max(a, b) {
    if a < b { return a, b }
    else      { return b, a }
}

lo, hi = min_max(8, 3)
write(lo)   # 3
write(hi)   # 8
```

```
function coords() {
    return 4, 7, 9
}

x, y, z = coords()
```

## Functions as values

Functions are first-class values — they can be stored and passed as arguments:

```
function double(x) {
    return x * 2
}

f = double
write(f(5))   # 10
```

## Closures

Inner functions capture variables from the enclosing scope:

```
function make_counter() {
    count = 0
    function increment() {
        count = count + 1
        return count
    }
    return increment
}

counter = make_counter()
write(counter())   # 1
write(counter())   # 2
write(counter())   # 3
```

## Recursion

```
function factorial(n) {
    if n <= 1 { return 1 }
    return n * factorial(n - 1)
}

write(factorial(6))   # 720
```

## Type annotations

Parameters and return values can be annotated with a type. The type is checked at call time — a mismatch raises a `TypeViolationFault`. The static type checker also reports violations before execution.

```
function add(a: int, b: int) -> int {
    return a + b
}

write(add(2, 3))   # 5
```

Return type annotations are also enforced:

```
function positive(x: float) -> bool {
    return x > 0
}
```

Nullable return types use `?`:

```
function find_index(lst: list, val: int) -> int? {
    for i = 0 to lst.len() - 1 {
        if lst[i] == val { return i }
    }
    return null
}
```

For class types, a subclass satisfies a parent type annotation:

```
class Animal {}
class Dog extends Animal {}

function greet(a: Animal) { write("hello") }

greet(Dog())   # works — Dog extends Animal
```

Valid type names: `int`, `float`, `number`, `string`, `bool`, `list`, `dict`, `null`, `any`, nullable `T?`, generic `list[T]` / `dict[K,V]`, fixed-size integers (`int8`…`int64`, `uint8`…`uint64`), fixed-size floats (`float32`, `float64`), or any class/struct name. Unannotated parameters accept any type.

## Higher-order functions

```
function apply_twice(f, x) {
    return f(f(x))
}

write(apply_twice(fn(x) => x * 2, 3))   # 12
```
