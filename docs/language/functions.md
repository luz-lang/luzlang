# Functions

## Defining functions

```luz
function greet(name) {
    write($"Hello, {name}!")
}
greet("World")  # Hello, World!
```

## Return values

```luz
function add(a, b) {
    return a + b
}
result = add(3, 4)  # 7
```

## Default parameters

```luz
function greet(name, greeting = "Hello") {
    write($"greeting}, {name}!")
}
greet("Alice")            # Hello, Alice!
greet("Bob", "Hey")       # Hey, Bob!
```

## Variadic parameters

```luz
function sum(...numbers) {
    total = 0
    for n in numbers {
        total += n
    }
    return total
}
sum(1, 2, 3)  # 6
```

## Multiple return values

```luz
function divide(a, b) {
    return a / b, a % b
}
quotient, remainder = divide(17, 5)
write(quotient)   # 3
write(remainder)  # 2
```

## Closures

Functions can reference variables from their surrounding scope. These are called **closures**.

### Closure-by-reference

Closures in Luz capture variables **by reference** (like Python and JavaScript). This means a closure doesn't store the value of a variable at the time it's created — it holds a reference to the variable itself, which may change later.

#### The gotcha

```luz
functions = []
for i = 1 to 3 {
    fn f() => i
    append(functions, f)
}
write(functions[0]())  # 4 (unexpected — i is 4 after the loop ends)
write(functions[1]())  # 4
write(functions[2]())  # 4
```

After the loop, `i` equals `4` (the value that caused the loop to stop). Since all three closures reference the *same* `i`, they all return `4`.

#### The workaround

Use an intermediate function to capture the current value of the loop variable:

```luz
functions = []
for i = 1 to 3 {
    function capture(val) {
        fn f() => val
        return f
    }
    append(functions, capture(i))
}
write(functions[0]())  # 1
write(functions[1]())  # 2
write(functions[2]())  # 3
```

Each call to `capture(i)` creates a new scope with a local `val` parameter. The closure inside now references `val`, which is unique per iteration and won't change after the loop moves on.

#### Default parameters also work

```luz
functions = []
for i = 1 to 3 {
    fn f(x = i) => x
    append(functions, f)
}
write(functions[0]())  # 1
write(functions[1]())  # 2
write(functions[2]())  # 3
```

This works because default parameter values are evaluated at function definition time, effectively snapshotting the current value of `i`.
