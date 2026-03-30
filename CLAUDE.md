# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run all tests
python -m pytest tests/test_suite.py -v

# Run a specific test class or test
python -m pytest tests/test_suite.py::TestArithmetic -v
python -m pytest tests/test_suite.py::TestArithmetic::test_int_addition -v

# Run Fuzzer
python tests/fuzzer.py              # 500 iterations, prints crashes
python tests/fuzzer.py 2000         # custom iteration count
python tests/fuzzer.py 500 --seed 42  # reproducible run

# Run the interpreter (REPL)
python main.py

# Run a .luz file
python main.py file.luz

# Parse-only check (used by VS Code extension)
python main.py --check file.luz

# Lint
pylint luz/

# Build the C lexer (Windows — requires MSYS2)
cd luz/c_lexer && make
```

## Architecture

The interpreter is a classic three-stage pipeline: **Lexer → Parser → Interpreter**.

The entry point for all execution is `run(text, interpreter)` in `main.py`, which chains these three stages. The `Interpreter` object is stateful and persists the global environment across calls (used by the REPL).

### Lexer (`luz/lexer.py`)

Converts source text to a flat `list[Token]`. The `get_tokens()` method is the single entry point. If `luz/c_lexer/luz_lexer.dll` (Windows) or `.so` (Linux/Mac) is present, it transparently delegates to the C implementation via `luz/c_lexer/bridge.py`. Otherwise it falls back to pure Python. The `_USE_C_LEXER` module-level flag controls this.

### Parser (`luz/parser.py`)

Recursive-descent parser that converts `list[Token]` to a list of AST nodes. Each grammar rule is a method; operator precedence is encoded as a call chain (`logical_or → logical_and → comparison → addition → multiplication → unary → atom`). AST node classes are plain data containers — all logic lives in the interpreter.

### Interpreter (`luz/interpreter.py`)

Tree-walking evaluator using the visitor pattern: `visit(node)` dispatches to `visit_<ClassName>(node)`. The key runtime objects are:

- **`Environment`** — lexical scope chain with `define/lookup/assign`. `is_function_scope=True` prevents assignment from leaking through closures.
- **`LuzFunction`** — wraps a `FuncDefNode` + closure `Environment`. Supports default params, variadic (`...args`), and named kwargs.
- **`LuzLambda`** — anonymous functions (`fn(x) => expr` or `fn(x) { body }`).
- **`LuzClass` / `LuzInstance` / `BoundMethod`** — class system. Methods in Luz take `self` as an **explicit** first parameter — it is never implicit.
- **`LuzModule`** — wraps a module's exported namespace for `import "x" as alias`.

Control flow (`return`, `break`, `continue`) is implemented via Python exceptions (`ReturnException`, `BreakException`, `ContinueException`). These are caught at the appropriate scope, not by user-level `attempt/rescue`.

### Errors (`luz/exceptions.py`)

All errors are subclasses of `LuzError` which carries `.line`, `.col`, and `.message`. The hierarchy splits into `SyntaxFault` (parse-time), `SemanticFault` (runtime logic), `RuntimeFault` (execution), and `UserFault` (raised by `alert`). Control flow exceptions (`ReturnException` etc.) also extend `LuzError` but are not real errors.

## Important Patterns

**Class methods require explicit `self`:** Unlike Python, Luz class methods must declare `self` as the first parameter. The interpreter prepends the instance to the argument list when calling methods.

```luz
class Foo {
    function init(self, x) { self.x = x }
    function get(self) { return self.x }
}
```

**Method names must not shadow builtins:** If a class method is named `len`, `min`, `max`, or `sum`, it will shadow the builtin inside the class body, causing `ArityFault` when the interpreter tries to call the builtin with the wrong number of args. Use alternative names (`size`, `minimum`, `maximum`, `total`).

**Import resolution order:** `import "math"` resolves by trying in order: literal path → `luz_modules/math/` → file-relative path → `$LUZ_HOME/lib/` → `libs/luz-math/math.luz` (dev fallback). Circular imports are silently skipped via `self.imported_files` (set of absolute paths).

**`from "x" import ...` and `import "x" as ...`** execute the module in an isolated `Environment`. Plain `import "x"` executes in the current scope.

## Language Features

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

## Standard Library (`libs/`)

Each library lives in `libs/luz-<name>/` with an entry-point `<name>.luz` that imports submodules. Users write `import "math"` which resolves to `libs/luz-math/math.luz`.

Trig and log functions (`sin`, `cos`, `exp`, `ln`, etc.) are implemented as **native Python builtins** in `interpreter.py`, not as Luz code. The `libs/luz-math/trigonometry.luz` and `logarithms.luz` files are thin wrappers that only add utility functions on top.

A Luz library absolutely needs to have a luz.json file, which includes library metadata: its name, version, and description.

## C Lexer (`luz/c_lexer/`)

- `luz_lexer.c` — C implementation of the full lexer
- `bridge.py` — ctypes bridge; `_C_TO_PYTHON` list maps C enum indices to Python `TokenType`
- `Makefile` — uses MSYS2's `bash` + `gcc` on Windows (requires MSYS2 at `C:/msys64`)
- The `.dll`/`.so` is gitignored; run `make` to build it locally
- `INT` and `FLOAT` token values must be converted from string to `int`/`float` in the bridge

## IMPORTANT:
- Any bugs encountered, whether in the code or the language, while adding something else, should be created as an issue using the GitHub CLI so they can be resolved later.