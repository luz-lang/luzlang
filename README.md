<p align="center">
  <img src="img/icon.png" alt="Luz logo" width="676" height="369">
</p>

# Luz Programming Language

**Luz** is an open-source, interpreted programming language written in Python. It features clean syntax, object-oriented programming, closures, pattern matching, error handling, and a built-in package manager — all in a single file you can run with `python main.py`.

```
name = listen("What is your name? ")
write($"Hello {name}!")

for i = 1 to 5 {
    write("even" if even(i) else "odd")
}
```

## Features

- **Dynamic typing** — integers, floats, strings, booleans, lists, dictionaries, `null`
- **Format strings** — `$"Hello {name}, you are {age} years old!"`
- **Control flow** — `if / elif / else`, `while`, `for` (range and for-each), `switch`, `match`
- **Ternary operator** — `value if condition else other`
- **Functions** — default parameters, variadic (`...args`), multiple return values, closures
- **Lambdas** — `fn(x) => x * 2` and `fn(x) { body }` as first-class values
- **Compound assignment** — `+=`, `-=`, `*=`, `/=`
- **Destructuring assignment** — `x, y = func()`
- **Negative indexing** — `list[-1]`, `str[-2]`
- **Object-oriented programming** — classes, inheritance (`extends`), method overriding, `super`
- **Error handling** — `attempt / rescue` blocks and `alert`
- **Modules** — `import` other `.luz` files
- **Package manager** — [Ray](#package-manager-ray), installs packages from GitHub
- **Standard library** — `luz-math` and `luz-random` included out of the box
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
# Default parameters and variadic functions
function greet(name, greeting = "Hello") {
    write($"{greeting}, {name}!")
}

function sum(...nums) {
    total = 0
    for n in nums { total += n }
    return total
}

greet("Alice")          # Hello, Alice!
greet("Bob", "Hi")      # Hi, Bob!
write(sum(1, 2, 3, 4))  # 10

# Multiple return values + destructuring
function min_max(a, b) {
    if a < b { return a, b }
    else      { return b, a }
}

lo, hi = min_max(8, 3)

# Ternary operator
label = "even" if even(lo) else "odd"

# Switch statement
switch lo {
    case 0 { write("zero") }
    case 1, 2, 3 { write("small") }
    else { write("other") }
}

# Match expression
result = match hi {
    8 => "eight"
    _ => "something else"
}
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

`luz-math` and `luz-random` are bundled with the installer:

```
import "math"
import "random"

write(PI)                     # 3.14159265358979
write(factorial(10))          # 3628800
write(rand_int(1, 100))       # random integer
write(choice(["a","b","c"]))  # random element
```

## VS Code extension

Install from the `vscode-luz/` folder for full language support:

- Syntax highlighting
- Autocompletion — keywords, built-ins, user-defined symbols
- Error detection — syntax errors underlined on save
- Hover documentation
- Snippets

## Documentation

Full language reference, built-in functions, and architecture guide:
**[elabsurdo984.github.io/luz-lang](https://elabsurdo984.github.io/luz-lang/)**

## License

MIT — see [LICENSE](LICENSE) for details.
