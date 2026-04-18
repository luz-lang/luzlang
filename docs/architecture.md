# Architecture

The interpreter is a classic three-stage pipeline: **Lexer → Parser → Interpreter**.

The entry point for all execution is `run(text, interpreter)` in `main.py`, which chains these three stages. The `Interpreter` object is stateful and persists the global environment across calls (used by the REPL).

## Lexer (`luz/lexer.py`)

Converts source text to a flat `list[Token]`. The `get_tokens()` method is the single entry point. If `luz/c_lexer/luz_lexer.dll` (Windows) or `.so` (Linux/Mac) is present, it transparently delegates to the C implementation via `luz/c_lexer/bridge.py`. Otherwise it falls back to pure Python. The `_USE_C_LEXER` module-level flag controls this.

## Parser (`luz/parser.py`)

Recursive-descent parser that converts `list[Token]` to a list of AST nodes. Each grammar rule is a method; operator precedence is encoded as a call chain (`logical_or → logical_and → comparison → addition → multiplication → unary → atom`). AST node classes are plain data containers — all logic lives in the interpreter.

## Interpreter (`luz/interpreter.py`)

Tree-walking evaluator using the visitor pattern: `visit(node)` dispatches to `visit_<ClassName>(node)`. The key runtime objects are:

- **`Environment`** — lexical scope chain with `define/lookup/assign`. `is_function_scope=True` prevents assignment from leaking through closures.
- **`LuzFunction`** — wraps a `FuncDefNode` + closure `Environment`. Supports default params, variadic (`...args`), and named kwargs.
- **`LuzLambda`** — anonymous functions (`fn(x) => expr` or `fn(x) { body }`).
- **`LuzClass` / `LuzInstance` / `BoundMethod`** — class system. Methods in Luz take `self` as an **explicit** first parameter — it is never implicit.
- **`LuzModule`** — wraps a module's exported namespace for `import "x" as alias`.

Control flow (`return`, `break`, `continue`) is implemented via Python exceptions (`ReturnException`, `BreakException`, `ContinueException`). These are caught at the appropriate scope, not by user-level `attempt/rescue`.

## Errors (`luz/exceptions.py`)

All errors are subclasses of `LuzError` which carries `.line`, `.col`, and `.message`. The hierarchy splits into `SyntaxFault` (parse-time), `SemanticFault` (runtime logic), `RuntimeFault` (execution), and `UserFault` (raised by `alert`). Control flow exceptions (`ReturnException` etc.) also extend `LuzError` but are not real errors.
