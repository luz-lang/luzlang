# Architecture

Luz follows a four-stage pipeline: source text is lexed, parsed, type-checked, and then evaluated.

```
Source code (text)
      |
   [Lexer]           luz/lexer.py
      |
 Token stream
      |
   [Parser]          luz/parser.py
      |
  AST (tree)
      |
 [TypeChecker]       luz/typechecker.py
      |
  Error list
      |
 [Interpreter]       luz/interpreter.py
      |
   Result
```

## Lexer (`luz/lexer.py`)

Converts raw source text into a flat list of `Token` objects.

- Handles integers, floats (including `.5` notation), strings, format strings, identifiers, keywords, and all operators.
- Emits a `QUESTION` token for `?` to support nullable type annotations (`T?`).
- Tracks line numbers on every token so errors can report the correct source line.
- Resolves string escape sequences (`\n`, `\t`, `\\`, `\"`) at this stage.
- Format strings store the raw template (e.g. `"Hello {name}"`) — expression parsing happens later in the parser.
- Optionally delegates to a C implementation (`luz/c_lexer/luz_lexer.dll` / `.so`) for faster tokenisation.

## Parser (`luz/parser.py`)

Consumes the token stream and builds an **Abstract Syntax Tree (AST)** using a **recursive descent parser**.

Operator precedence is enforced through a chain of parsing functions, each calling the next higher-precedence level:

```
logical_or → logical_and → logical_not → comp_expr
           → arith_expr → term → power → factor
```

Each node type (`BinOpNode`, `IfNode`, `CallNode`, `ClassDefNode`, `StructDefNode`, etc.) is a plain Python class defined at the top of the file. Nodes hold references to their child nodes, forming a tree.

Format string parsing: the lexer stores raw template text; the parser splits it on `{...}` (tracking brace depth for nesting), then sub-parses each embedded expression using a fresh `Lexer` + `Parser`.

Type expressions (used in variable annotations and function signatures) are parsed by `parse_type_expr()`, which produces strings like `"int"`, `"string?"`, `"list[int]"`, or `"dict[string, float]"`.

## Type Checker (`luz/typechecker.py`)

Walks the AST before execution and collects type errors without running any code. The main entry point is `TypeChecker().check(ast)`, which returns a list of `TypeCheckError` objects.

Key responsibilities:

- **Typed variable declarations** — checks that the assigned value matches the declared type annotation.
- **Function call arity** — checks that the number of arguments (positional + keyword) falls within the allowed range, accounting for default parameters.
- **Function return type** — checks that `return` expressions match the declared `-> type` annotation.
- **Class attribute inference** — scans the `init` body to build a map of `self.<attr>` types, enabling attribute access checks on typed instances.
- **Unused variable / import / parameter detection** — reports identifiers that are declared but never read (Go-style).
- **Type inference** — propagates types through arithmetic (`int + float → float`), function calls, and binary operations.

The `T` class defines type constants (`T.INT`, `T.STRING`, etc.) and a `T.compatible(declared, actual)` predicate that handles nullable types, generic collections, and fixed-size numeric widening.

## Interpreter (`luz/interpreter.py`)

Walks the AST using the **Visitor pattern**: `visit(node)` dispatches to `visit_IfNode`, `visit_BinOpNode`, etc. based on the node's class name.

**Scope** is managed through a chain of `Environment` objects. Each block or function call creates a new environment linked to its parent, enabling proper variable scoping and closures. A single `_find_scope()` traversal is used for assignment to avoid the previous double-walk.

**OOP** is implemented through:

| Object | Role |
|---|---|
| `LuzClass` | Stores the method dictionary and a reference to the parent class |
| `LuzInstance` | Stores the instance's attribute dictionary and a reference to its class |
| `LuzSuperProxy` | Wraps an instance + a parent class; resolves `super.method()` calls |
| `LuzFunction` | A named function with a closure |
| `LuzLambda` | An anonymous function (short `fn(x) => expr` or long `fn(x) { body }`) |
| `LuzStruct` / `LuzStructInstance` | Value-type data container with typed fields |
| `LuzModule` | Wraps a module's exported namespace for `import "x" as alias` |

Method calls automatically inject `self` and `super` into the method's local scope.

**Control flow signals** (`return`, `break`, `continue`) are implemented as Python exceptions that propagate up the call stack and are caught at the appropriate node handler.

**Type enforcement** at runtime: typed variable assignments call `_check_type()`, which handles generic collections, nullable types, fixed-size numeric bounds (`_enforce_type()`), and class hierarchy walking. A `_TYPE_PARSE_CACHE` class-level dict avoids re-parsing generic type strings on repeated assignments.

## Error system (`luz/exceptions.py`)

All errors inherit from `LuzError`:

```
LuzError
├── SyntaxFault           (lexer / parser errors)
├── SemanticFault         (type errors, undefined variables, wrong argument count…)
│   ├── TypeViolationFault
│   ├── AttributeNotFoundFault
│   └── ArityFault
├── RuntimeFault          (division by zero, index out of bounds…)
├── CastFault             (failed type conversion)
└── UserFault             (raised by the alert keyword)
```

Every error carries a `line` attribute that is attached when the error propagates through `visit()`.

## File overview

```
luz-lang/
├── main.py               # Entry point: REPL, file execution, --check mode
├── luz/
│   ├── tokens.py         # TokenType enum and Token class
│   ├── lexer.py          # Lexer: text → tokens
│   ├── parser.py         # Parser: tokens → AST + all AST node classes
│   ├── typechecker.py    # Static type checker: AST → list[TypeCheckError]
│   ├── interpreter.py    # Interpreter: executes the AST
│   ├── exceptions.py     # Full error class hierarchy
│   └── c_lexer/          # Optional C lexer (faster tokenisation on Windows/Linux)
│       ├── luz_lexer.c
│       ├── bridge.py     # ctypes bridge
│       └── Makefile
├── libs/                 # Standard library (luz-math, luz-random, luz-io, …)
├── tests/
│   ├── test_suite.py     # pytest test suite
│   └── fuzzer.py         # Random-input fuzzer
├── docs/                 # This documentation (MkDocs)
├── installer/            # Windows Inno Setup installer script
├── vscode-luz/           # VS Code language extension
└── examples/             # 28 example programs
```
