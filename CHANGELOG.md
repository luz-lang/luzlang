# Changelog

All notable changes to Luz are documented here.
Format: `## [version] - YYYY-MM-DD` followed by categorized entries.

---

## [1.19.0] - 2026-04-12

### Added

**Compiler pipeline (interpreter → native executable)**
- `--compile <file> [-o output]` CLI flag: compiles a `.luz` file to a native executable via LLVM IR → object file → linker
- `--emit-ir <file>` CLI flag: prints the generated LLVM IR to stdout
- `--run <file>` CLI flag: compiles to a temporary executable, runs it, then deletes the binary
- `--emit-ast <file>` CLI flag: prints the full AST (class names + fields) produced by the parser for debugging
- `--emit-hir <file>` CLI flag: prints the lowered HIR using dataclass reprs for debugging
- HIR (High-level Intermediate Representation) lowering pass in `luz/hir.py` — 27 node types that desugar the AST into a flat, compiler-friendly representation before code generation; desugaring includes: `for` → while loop, `for x in list` → index-based while, `switch/case` → if/elif/else, `match` → equality chain, `x ?? y` → null check, `a if cond else b` → ternary if, f-strings → string concatenations
- LLVM IR code generator in `luz/codegen.py` — lowers HIR to LLVM IR via llvmlite; all values are represented uniformly as `luz_value_t {i32 tag, i32 pad, i64 data}` matching the C runtime ABI
- Native C runtime library in `luz/runtime/` — implements the full Luz type system and 40+ builtin functions as C functions: `luz_runtime.h` (tagged union, SSO strings, dynamic arrays, open-addressing hash table, vtable objects, setjmp/longjmp exceptions), `luz_runtime.c` (ARC retain/release, all data structure operations, builtins), dynamic dispatch helpers in `luz_rt_ops.c`
- Tail call optimization (TCO) in the compiler: tail-position calls to user functions are marked `musttail` (self-recursive) or `tail` (cross-function); the LLVM TCO pass then eliminates the call frame, enabling stack-safe deep recursion in compiled mode
- Indirect calls and function-pointer support in compiled mode: `_gen_HirExprCall` now stores function pointers in `luz_value_t{TAG_FUNCTION}` and performs real indirect calls via `inttoptr`; functions stored in variables, passed as arguments, or returned from other functions work correctly under `--compile`

**Type checker**
- Generic collection types `list[T]` and `dict[K, V]` are now enforced by the type checker — element types are validated on assignment and on function call arguments/return values
- Definite assignment analysis: raises `UninitializedFault` for variables that may be read before being written on all control flow paths; `if` without `else` does not guarantee assignment, `if/else` propagates guaranteed names to the parent scope, `while`/`for` loop bodies are not guaranteed

**HIR optimizer**
- Constant folding in the HIR lowering pass: literal binary expressions (`3 + 4`, `"hello" + " world"`, `not false`) and unary expressions (`-5`) are evaluated at compile time in `lower_BinOpNode` / `lower_UnaryOpNode` and replaced with a single `HirLiteral`, eliminating the runtime call entirely

**Standard library**
- `luz-func` — functional programming utilities (`import "func"`):
  - `higher.luz`: `map`, `filter`, `reduce`, `each`, `flat_map`, `zip_with`, `take_while`, `drop_while`, `count_if`, `find_first`, `group_by`
  - `compose.luz`: `identity`, `constant`, `compose`, `compose3`, `pipe`, `flip`, `negate`, `all_of`, `any_of`
  - `partial.luz`: `partial`, `partial2`, `once`, `memoize`

### Fixed

- `in` and `not in` operators on dicts now work correctly — previously only lists and strings were supported
- Unary `+` operator is now accepted (it is a no-op, like in most languages)
- `instanceof()` now works correctly with struct instances
- `break`, `continue`, and `return` used outside their valid scope now raise the proper Luz error instead of leaking a Python exception
- `sort()` on a mixed-type list (e.g. `[3, "a", 1]`) now raises `TypeViolationFault` instead of leaking an internal Python `TypeError`
- Type checker: `string * int` and `int * string` are now accepted as valid string repetition — previously the type checker rejected them even though the interpreter handled them correctly
- `pop()` error message is now more descriptive when called on an empty list
- `path_ext()` in `luz-system` now returns only the file extension instead of the full basename
- Windows x64 ABI mismatch in `--compile`: added pointer-wrapped `_pw` shims for all runtime functions that pass or return `luz_value_t` by value, so LLVM-generated code and MinGW-compiled C agree on the struct calling convention; `lower_BinOpNode` in `hir.py` was also fixed where a missing `op` field caused compiled arithmetic to always output null
- C runtime: replaced GCC-specific `__attribute__((noreturn))` with a portable `LUZ_NORETURN` macro that falls back gracefully on MSVC and other compilers

### Performance

- Lexer: identifier and keyword matching now uses `frozenset` for O(1) lookups; string token accumulation uses list+join instead of repeated string concatenation — measurably faster on large source files
- Compiler: LLVM middle-end optimization pipeline now runs before native object emission — applies SROA/mem2reg (promotes alloca/store/load triples to SSA registers), instruction combining, CFG simplification, dead store elimination, aggressive DCE, constant merging, and global optimization; at `-O2` also applies tail call elimination, jump threading, and memcpy optimization

---

## [1.18.0] - 2026-04-03

### Added
- Nullable types: `T?` syntax — a variable declared as `int?` accepts both `int` values and `null`; a plain `int` rejects `null` at runtime and at the type-checker level
- Generic collection types: `list[T]` and `dict[K, V]` — type parameters are enforced on assignment and on function call arguments/return values
- Fixed-size numeric types: `int8`, `int16`, `int32`, `int64`, `uint8`, `uint16`, `uint32`, `uint64`, `float32`, `float64` — backed by Python `int`/`float` at runtime with range/overflow checks
- `struct` keyword for typed, value-type data containers with optional default field values
- `const` keyword for immutable bindings — reassignment raises `InvalidUsageFault`
- Compile-time type checker pass — runs after parsing and before execution; collects all type errors rather than stopping at the first one
- Unused variable, import, and parameter detector (Go-style) — names prefixed with `_` are exempt
- `string.len()` dot method, consistent with `list.len()` and `dict.len()`
- `list.sort()` and `list.reverse()` dot methods
- Type checker now infers return types through function calls and propagates them through arithmetic (`int + float → float`, `int / int → float`, etc.)
- Type checker now tracks class attribute types inferred from `init` body and returns the correct type for `instance.attr` access

### Fixed
- `clamp()` now raises `ArgumentFault` when `low > high` instead of silently returning a wrong value
- `insert()` now raises `IndexFault` for out-of-bounds indices
- C lexer bridge: `self` tokens were emitted without a value (`None`); now correctly carry `'self'` to match the Python lexer

### Performance
- Scope chain: `assign()` previously walked the scope chain twice (once to check existence via `lookup()`, once to update); replaced with a single `_find_scope()` traversal (~31% faster on variable-heavy programs)
- Type checking: parsed generic type strings (`list[int]`, `dict[string, int]`, …) are now cached in `Interpreter._TYPE_PARSE_CACHE` so the character-by-character bracket parse runs only once per unique type string (~1.5x faster on the type-check hot path)

---

## [1.17.0] - 2026-03-29

### Added
- Slice syntax for lists and strings: `list[start:end]`, `list[start:end:step]`, `string[start:end]`
- Typed variable declarations: `x: int = 5` — type is enforced at assignment
- Type annotations on function parameters and return values now respect class inheritance — a subclass instance satisfies a parent type annotation
- `insert(list, index, value)` builtin — inserts an element at a position, shifting elements right
- Dict dot method syntax: `dict.keys()`, `dict.values()`, `dict.len()`, `dict.contains(key)`, `dict.remove(key)`
- `luz-types` standard library — type predicates (`is_int`, `is_float`, `is_number`, etc.), safe casting (`safe_int`, `safe_float`, `safe_str`, `safe_bool`), and schema validation (`validate`)

### Fixed
- `exp(x)` was calling `math.log(x)` internally — now correctly calls `math.exp(x)`
- `swap()`, `append()`, `contains()`, `join()`, `remove()` and `insert()` dot methods now raise `ArityFault` on missing arguments instead of crashing with a Python `IndexError`
- `0 ** negative` now raises `ZeroDivisionFault` instead of leaking a raw Python `ZeroDivisionError`
- `string // int` and `round(x, non-int)` now raise proper Luz faults instead of leaking a raw Python `ValueError`
- `int in string` now raises `TypeClashFault` instead of leaking a raw Python `TypeError`
- `split(s, "")` now raises `ArgumentFault` instead of leaking a raw Python `ValueError`
- `finally` block no longer silently discards an exception that was already pending from the `rescue` block — the original error is preserved
- `from "x" import a, b` is now atomic — if any name doesn't exist, nothing is imported into scope

---

## [1.16.0] - 2026-03-24

### Added
- Bound methods: retrieving a method from an instance (`m = obj.method`) now returns a bound method that carries `self` automatically — calling `m()` no longer requires passing the instance manually
- String dot method syntax: `str.uppercase()`, `str.lowercase()`, `str.trim()`, `str.swap(old, new)`, `str.split(sep)`
- List dot method syntax: `list.append(x)`, `list.pop()`, `list.len()`, `list.contains(x)`, `list.join(sep)`
- Versioning policy documentation (`docs/versioning.md`)
- Automated release notes: tagging `vX.Y.Z` now extracts the matching changelog entry and sets it as the GitHub release body

### Fixed
- `self.attr[i]` now correctly indexes into instance attributes — previously the index was silently ignored and the full attribute was returned
- Lists, dicts, booleans, and `null` now print in Luz syntax (`"hello"`, `true`, `null`) instead of Python syntax (`'hello'`, `True`, `None`)

---

## [1.15.0] - 2026-03-22

### Added
- Pylint to CI pipeline with a minimum score of 9.0/10
- `.pylintrc` configuration silencing false positives from intentional design decisions
- Lint instructions to `CONTRIBUTING.md`

---

## [1.14.0] - 2026-03-15

### Added
- `from "module" import name` syntax for selective imports
- `import "module" as alias` syntax for aliased imports
- `finally` block in `attempt / rescue`
- `rescue` now accepts an optional error variable (can be omitted)
- Unicode escape sequences (`\uXXXX`, `\UXXXXXXXX`) in string literals
- Scientific notation support for numeric literals (`1.5e10`, `3e-4`)

### Fixed
- `for` loop now validates step direction (errors if step sign contradicts range direction)
- Recursion error messages now report the function name

---

## [1.13.0] - 2026-03-01

### Added
- Block scope for `if` and `while` — variables declared inside do not leak out
- Default function arguments now evaluate in caller scope, not closure scope
- CI test matrix across Python 3.10, 3.11, and 3.12
- 72-test pytest suite organized in 9 classes

### Fixed
- `typeof` module resolution no longer errors on built-in type names
- Scope leak: assigning to a variable no longer creates it in the wrong scope
- Circular inheritance no longer causes infinite recursion (raises `InheritanceFault`)
- Failed imports are properly deregistered so re-importing works correctly
- `len()` no longer uses a bare `except` clause

---

## [1.12.0] - 2026-02-15

### Added
- `switch / case` statement
- `match` expression with multiple value patterns per case
- Compound assignment operators: `+=`, `-=`, `*=`, `/=`
- Negative indexing for lists and strings (`list[-1]`)
- Destructuring assignment: `x, y = func()`

---

## [1.11.0] - 2026-02-01

### Added
- Multiple return values from functions
- Variadic arguments (`...args`)
- Named arguments at call sites
- Lambda expressions: `fn(x) => x * 2` and `fn(x) { body }`

---

## [1.10.0] - 2026-01-15

### Added
- Object-oriented programming: `class`, `extends`, method overriding, `super`
- `attempt / rescue` error handling and `alert` to raise errors
- Module system: `import "path"`
- Ray package manager

---
