<p align="center">
  <img src="img/icon.png" alt="Luz logo" width="676" height="369">
</p>

# Luz Programming Language

**Luz** is an open-source, interpreted programming language written in Python. It features clean syntax, optional static typing, object-oriented programming, closures, pattern matching, error handling, and a built-in package manager — all in a single file you can run with `python main.py`.

```
name = listen("What is your name? ")
write($"Hello {name}!")

for i = 1 to 5 {
    write("even" if even(i) else "odd")
}
```

## Features

- **Optional static typing** — annotate variables, parameters, and return types; the type checker validates them before execution
- **Nullable types** — `T?` allows `null` alongside any type; `??` provides a null-safe fallback
- **Generic collections** — `list[int]`, `dict[string, float]`, enforced at assignment time
- **Fixed-size numeric types** — `int8`…`int64`, `uint8`…`uint64`, `float32`, `float64`
- **Constants** — `const NAME: type = value`, checked at compile time
- **Structs** — `struct` defines typed, lightweight value records with optional defaults
- **Format strings** — `$"Hello {name}, you are {age} years old!"`
- **Control flow** — `if / elif / else`, `while`, `for` (range and for-each), `switch`, `match`
- **Ternary operator** — `value if condition else other`
- **Membership** — `x in list`, `key in dict`, `sub in string`
- **Functions** — default parameters, variadic (`...args`), named kwargs, multiple return values, closures
- **Lambdas** — `fn(x) => x * 2` and `fn(x) { body }` as first-class values
- **List comprehensions** — `[x * 2 for x in nums if even(x)]`
- **Dot method syntax** — `"hello".uppercase()`, `list.sort()`, `dict.contains(key)`
- **Bound methods** — `m = obj.method` stores the method with `self` already bound
- **Compound assignment** — `+=`, `-=`, `*=`, `/=`
- **Destructuring assignment** — `x, y = func()`
- **Negative indexing** — `list[-1]`, `str[-2]`
- **Slice syntax** — `list[1:4]`, `list[::2]`, `str[0:5]`
- **Object-oriented programming** — classes, inheritance (`extends`), method overriding, `super`
- **Error handling** — `attempt / rescue / finally` blocks and `alert`
- **Modules** — `import`, `from "x" import name`, `import "x" as alias`
- **Static type checker** — reports type errors, unused variables, and arity mismatches before execution
- **Package manager** — [Ray](#package-manager-ray), installs packages from GitHub
- **Standard library** — `luz-math`, `luz-random`, `luz-io`, `luz-system`, `luz-clock`, `luz-types`
- **Helpful errors** — every error includes the line number
- **REPL** — interactive shell for quick experimentation
- **VS Code extension** — syntax highlighting, autocompletion, error detection, hover docs, snippets
- **Standalone installer** — no Python required

## Quick start

Requires **Python 3.8+**, no external dependencies.

```bash
git clone https://github.com/Elabsurdo984/luz-lang.git
cd luz-lang
python main.py          # open the REPL
python main.py file.luz # run a file
```

Or download the **[Windows installer](https://elabsurdo984.github.io/luz-lang/download/)** and run `luz` from anywhere.

## Language at a glance

```
# Optional static typing
name: string  = "Alice"
age: int      = 30
score: float? = null      # nullable — can be float or null

const MAX: int = 100

# Struct — typed value record
struct Point { x: float, y: float }
p = Point(3.0, 4.0)
write($"({p.x}, {p.y})")

# Default parameters, named args, and variadic functions
function greet(name: string, greeting: string = "Hello") -> string {
    return $"{greeting}, {name}!"
}

function total(...nums) -> float {
    acc: float = 0.0
    for n in nums { acc += n }
    return acc
}

write(greet("Alice"))
write(greet("Bob", greeting: "Hi"))
write(total(1, 2, 3, 4))   # 10.0

# List comprehension, slices, and in operator
nums: list[int] = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
evens = [x for x in nums if even(x)]   # [2, 4, 6, 8, 10]
write(evens[1:4])                       # [4, 6, 8]
write(3 in nums)                        # true

# Multiple return values + destructuring
function min_max(a, b) {
    if a < b { return a, b }
    else      { return b, a }
}
lo, hi = min_max(8, 3)

# switch statement
switch lo {
    case 0 { write("zero") }
    case 1, 2, 3 { write("small") }
    else { write("other") }
}

# match expression
label: string = match hi {
    8 => "eight"
    _ => "something else"
}

# Dot method syntax — strings and lists
words: list[string] = "hello world".split(" ")
words.sort()
write(words.join(", "))
write(words.contains("hello"))   # true

# Object-oriented programming + bound methods
class Counter {
    function init(self) { self.n = 0 }
    function inc(self)  { self.n += 1 }
    function get(self) -> int { return self.n }
}

c: Counter = Counter()
step = c.inc          # bound method — self already attached
step()
step()
write(c.get())        # 2

# Error handling
attempt {
    result = 10 / 0
} rescue (e) {
    write($"Caught: {e}")
} finally {
    write("done")
}

# Null-coalescing
display: string = score ?? "N/A"
```

## Package manager — Ray

Ray installs Luz packages from GitHub into `luz_modules/`:

```bash
ray init                   # create luz.json
ray install user/repo      # install a package
ray list                   # list installed packages
ray remove package-name    # remove a package
```

## Standard library

All standard libraries are bundled with the installer:

```
import "math"
import "random"

write(PI)                       # 3.14159265358979
write(factorial(10))            # 3628800
write(random_int(1, 100))       # random integer
write(pick(["a", "b", "c"]))    # random element
```

Available modules: `math`, `random`, `io`, `system`, `clock`, `types`.

## VS Code extension

Install from the `vscode-luz/` folder for full language support:

- Syntax highlighting
- Autocompletion — keywords, built-ins, user-defined symbols
- Error detection — syntax errors underlined on save
- Hover documentation
- Snippets

## Documentation

Full language reference, built-in functions, and architecture guide:
**[elabsurdo984.github.io/luzlang](https://elabsurdo984.github.io/luzlang/)**

## License

MIT — see [LICENSE](LICENSE) for details.
