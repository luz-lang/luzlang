"""
luzc -- Luz Compiler
Usage:
    luzc <file.luz> [-o output] [-O0|-O1|-O2|-O3] [--emit-ir] [--emit-hir] [--emit-ast]
    luzc <file.luz> --run
    luzc --version
    luzc --help
"""

import sys
import os
import re
import argparse
import subprocess

VERSION = "1.0.0"

# ── Diagnostics engine ────────────────────────────────────────────────────────
#
# Produces GCC/Clang-style messages:
#
#   hello.luz:5:8: error: undeclared variable 'x'
#       5 | write(x)
#         |       ^
#
# Severities:
#   error   -- fatal, compilation stops
#   warning -- non-fatal (unused vars, etc.), compilation continues
#   note    -- informational hint attached to a previous error

class Diagnostics:
    """Collects and formats compiler diagnostics for a single source file."""

    # LuzError subclass names -> severity override
    # Anything not listed here defaults to "error"
    _WARNINGS = {
        "UnusedVariableFault",
        "UnusedImportFault",
    }

    # Class name -> human-readable label
    # Built dynamically from CamelCase; override specific ones here
    _LABEL_OVERRIDE = {
        "ExpressionFault":      "invalid expression",
        "UnexpectedTokenFault": "unexpected token",
        "UnexpectedEOFault":    "unexpected end of file",
        "InvalidTokenFault":    "invalid token",
        "StructureFault":       "syntax error",
        "ParseFault":           "syntax error",
        "OperatorFault":        "operator error",
        "TypeClashFault":       "type mismatch",
        "TypeViolationFault":   "type error",
        "TypeCheckFault":       "type error",
        "CastFault":            "invalid cast",
        "UndefinedSymbolFault": "undeclared identifier",
        "DuplicateSymbolFault": "duplicate definition",
        "ArityFault":           "wrong number of arguments",
        "ArgumentFault":        "invalid argument",
        "IndexFault":           "index out of range",
        "ZeroDivisionFault":    "division by zero",
        "UnusedVariableFault":  "unused variable",
        "UnusedImportFault":    "unused import",
        "ModuleNotFoundFault":  "module not found",
        "ImportFault":          "import error",
        "AttributeNotFoundFault": "attribute not found",
        "InheritanceFault":     "invalid inheritance",
        "UserFault":            "alert",
    }

    def __init__(self, filename: str, source: str):
        self.filename      = filename
        self._lines        = source.splitlines()
        self.error_count   = 0
        self.warning_count = 0

    # ── Public API ─────────────────────────────────────────────────────────────

    def report(self, exc, severity: str = None):
        """Format and print a LuzError (or any exception) as a diagnostic."""
        line = getattr(exc, "line", None)
        col  = getattr(exc, "col",  None)
        msg  = getattr(exc, "message", str(exc))
        cls  = type(exc).__name__

        if severity is None:
            severity = "warning" if cls in self._WARNINGS else "error"

        label = self._label(cls)
        self._emit(line, col, severity, label, msg)

    def report_typecheck(self, tc_err):
        """Format a TypeCheckError object from luz.typechecker."""
        line     = getattr(tc_err, "line",       None)
        col      = getattr(tc_err, "col",        None)
        msg      = getattr(tc_err, "message",    str(tc_err))
        fault    = getattr(tc_err, "fault_kind", "TypeCheckFault")
        severity = "warning" if "Unused" in fault else "error"
        label    = self._label(fault)
        self._emit(line, col, severity, label, msg)

    def report_internal(self, exc):
        """Format an unexpected Python exception as an internal compiler error."""
        msg = f"internal compiler error: {type(exc).__name__}: {exc}"
        print(f"luzc: {msg}", file=sys.stderr)
        if os.environ.get("LUZC_DEBUG"):
            import traceback
            traceback.print_exc()
        self.error_count += 1

    def die(self, exc):
        """Report a fatal error and exit immediately."""
        self.report(exc)
        self._summary_and_exit()

    def die_internal(self, exc):
        """Report an internal error and exit."""
        self.report_internal(exc)
        self._summary_and_exit()

    def ok(self) -> bool:
        return self.error_count == 0

    def summary(self):
        """Print the final error/warning count line (only if there were any)."""
        parts = []
        if self.error_count:
            s = "s" if self.error_count != 1 else ""
            parts.append(f"{self.error_count} error{s}")
        if self.warning_count:
            s = "s" if self.warning_count != 1 else ""
            parts.append(f"{self.warning_count} warning{s}")
        if parts:
            print(f"luzc: {', '.join(parts)} generated.", file=sys.stderr)

    # ── Internals ──────────────────────────────────────────────────────────────

    def _emit(self, line, col, severity, label, msg):
        loc = self.filename
        if line is not None:
            loc += f":{line}"
            if col is not None:
                loc += f":{col}"

        print(f"{loc}: {severity}: {label}: {msg}", file=sys.stderr)

        # Source context: the offending line + caret
        ctx = self._context(line, col)
        if ctx:
            print(ctx, file=sys.stderr)

        if severity == "warning":
            self.warning_count += 1
        else:
            self.error_count += 1

    def _context(self, line, col) -> str:
        """Return the source line + caret indicator, or empty string."""
        if line is None or line < 1 or line > len(self._lines):
            return ""
        src = self._lines[line - 1]
        # Truncate very long lines for readability
        display = src if len(src) <= 120 else src[:117] + "..."
        num     = str(line)
        pad     = " " * len(num)
        out     = f"  {num} | {display}\n"
        out    += f"  {pad} | "
        if col is not None and 1 <= col <= len(src) + 1:
            out += " " * (col - 1) + "^"
        return out

    def _label(self, class_name: str) -> str:
        if class_name in self._LABEL_OVERRIDE:
            return self._LABEL_OVERRIDE[class_name]
        # Strip "Fault" / "Error" / "Exception" suffix, then CamelCase -> words
        name = re.sub(r"(Fault|Error|Exception)$", "", class_name)
        return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", name).lower()

    def _summary_and_exit(self):
        self.summary()
        sys.exit(1)


# ── Pipeline stages ───────────────────────────────────────────────────────────

def _load(filename: str) -> str:
    try:
        with open(filename, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        print(f"luzc: error: no such file: '{filename}'", file=sys.stderr)
        sys.exit(1)
    except OSError as e:
        print(f"luzc: error: cannot read '{filename}': {e}", file=sys.stderr)
        sys.exit(1)


def _lex_parse(source: str, diag: Diagnostics):
    from luz.lexer  import Lexer
    from luz.parser import Parser

    try:
        tokens = Lexer(source).get_tokens()
    except Exception as e:
        diag.die(e)

    try:
        return Parser(tokens).parse()
    except Exception as e:
        diag.die(e)


def _typecheck(ast, diag: Diagnostics):
    from luz.typechecker import TypeChecker

    errors = TypeChecker().check(ast)
    if not errors:
        return

    for e in errors:
        diag.report_typecheck(e)

    if not diag.ok():
        diag._summary_and_exit()


def _lower(ast, diag: Diagnostics, source_file: str = ""):
    from luz.hir import Lowering
    try:
        return Lowering(source_file=source_file).lower_program(ast)
    except Exception as e:
        diag.die(e)


def _codegen(hir, diag: Diagnostics):
    try:
        from luz.codegen import LLVMCodeGen
    except ImportError:
        print(
            "luzc: error: llvmlite is not installed.\n"
            "       Run: pip install llvmlite",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        gen = LLVMCodeGen()
        gen.gen_program(hir)
        return gen
    except Exception as e:
        # Codegen errors may be LuzErrors with location info,
        # or plain Python exceptions (internal compiler bugs).
        from luz.exceptions import LuzError
        if isinstance(e, LuzError):
            diag.die(e)
        else:
            diag.die_internal(e)


def _build_pipeline(filename: str):
    """Full Lex->Parse->Typecheck->Lower->Codegen pipeline.
    Returns (ast, hir, gen, diag)."""
    source = _load(filename)
    diag   = Diagnostics(filename, source)
    ast    = _lex_parse(source, diag)
    _typecheck(ast, diag)
    hir    = _lower(ast, diag, source_file=filename)
    gen    = _codegen(hir, diag)
    return ast, hir, gen, diag


# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_check(filename: str):
    """Syntax + type check only. Outputs JSON for editor integration."""
    import json
    source = _load(filename)
    out    = []
    try:
        from luz.lexer       import Lexer
        from luz.parser      import Parser
        from luz.typechecker import TypeChecker
        tokens = Lexer(source).get_tokens()
        ast    = Parser(tokens).parse()
        for e in TypeChecker().check(ast):
            out.append({
                "line":    getattr(e, "line",    None),
                "col":     getattr(e, "col",     None),
                "message": getattr(e, "message", str(e)),
            })
    except Exception as e:
        out.append({
            "line":    getattr(e, "line",    None),
            "col":     getattr(e, "col",     None),
            "message": getattr(e, "message", str(e)),
        })
    print(json.dumps(out))


def cmd_emit_ast(filename: str):
    source = _load(filename)
    diag   = Diagnostics(filename, source)
    ast    = _lex_parse(source, diag)
    _dump_node(ast)


def cmd_emit_hir(filename: str):
    import pprint
    _, hir, _, _ = _build_pipeline(filename)
    pprint.pprint(hir, width=120)


def cmd_emit_ir(filename: str):
    _, _, gen, _ = _build_pipeline(filename)
    print(str(gen.module))


def cmd_compile(filename: str, output, verbose: bool):
    if verbose:
        print(f"luzc: compiling '{filename}'...")

    _, _, gen, diag = _build_pipeline(filename)

    # Warnings don't stop compilation, but print the summary line
    if diag.warning_count:
        diag.summary()

    # Resolve output path
    if output is None:
        base   = os.path.splitext(filename)[0]
        output = base + (".exe" if sys.platform == "win32" else "")
    elif sys.platform == "win32" and not output.lower().endswith(".exe"):
        output = output + ".exe"

    if verbose:
        print(f"luzc: linking -> '{output}'")

    try:
        gen.compile_to_exe(output)
    except subprocess.CalledProcessError:
        print(
            "luzc: error: linking failed.\n"
            "       Make sure the runtime is compiled:\n"
            "         cd luz/runtime && make",
            file=sys.stderr,
        )
        sys.exit(1)
    except Exception as e:
        print(f"luzc: error: {e}", file=sys.stderr)
        sys.exit(1)

    if verbose:
        size = os.path.getsize(output)
        print(f"luzc: done ({size:,} bytes)")
    else:
        print(f"Compiled: {output}")


def cmd_run(filename: str):
    """Compile + execute immediately, then delete the binary."""
    import tempfile
    _, _, gen, diag = _build_pipeline(filename)

    if diag.warning_count:
        diag.summary()

    suffix = ".exe" if sys.platform == "win32" else ""
    fd, tmp = tempfile.mkstemp(suffix=suffix)
    os.close(fd)

    try:
        gen.compile_to_exe(tmp)
        result = subprocess.run([tmp], check=False)
        sys.exit(result.returncode)
    except subprocess.CalledProcessError:
        print(
            "luzc: error: linking failed.\n"
            "       Make sure the runtime is compiled:\n"
            "         cd luz/runtime && make",
            file=sys.stderr,
        )
        sys.exit(1)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


# ── AST pretty-printer ────────────────────────────────────────────────────────

def _dump_node(node, indent=0):
    from luz.tokens import Token
    pad = "  " * indent
    if node is None:
        print(f"{pad}null"); return
    if isinstance(node, bool):
        print(f"{pad}{node!r}"); return
    if isinstance(node, (int, float, str)):
        print(f"{pad}{node!r}"); return
    if isinstance(node, Token):
        print(f"{pad}Token({node.type.name}, {node.value!r})"); return
    if isinstance(node, list):
        print(f"{pad}[")
        for item in node:
            _dump_node(item, indent + 1)
        print(f"{pad}]"); return
    cls  = type(node).__name__
    data = vars(node) if hasattr(node, "__dict__") else {}
    if not data:
        print(f"{pad}{cls}()"); return
    print(f"{pad}{cls}(")
    for k, v in data.items():
        print(f"{pad}  {k} =")
        _dump_node(v, indent + 2)
    print(f"{pad})")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        prog="luzc",
        description="Luz compiler - compiles .luz source files to native executables.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  luzc hello.luz                  Compile to hello.exe (Windows) or hello (Linux/Mac)
  luzc hello.luz -o greet         Compile to greet.exe / greet
  luzc hello.luz --run            Compile and run immediately
  luzc hello.luz --emit-ir        Print LLVM IR to stdout
  luzc hello.luz --emit-hir       Print HIR to stdout
  luzc hello.luz --emit-ast       Print AST to stdout

Environment:
  LUZC_DEBUG=1                    Print full Python traceback on internal errors
""",
    )

    parser.add_argument("file",
        nargs="?",
        metavar="file.luz",
        help="Luz source file to compile")

    parser.add_argument("-o",
        metavar="output",
        dest="output",
        help="Output binary name (default: source name without extension)")

    parser.add_argument("-O", "-O0", "-O1", "-O2", "-O3",
        dest="opt",
        metavar="level",
        default="2",
        help="Optimization level 0-3 (default: 2)")

    parser.add_argument("--run",
        action="store_true",
        help="Compile and execute immediately, then delete the binary")

    parser.add_argument("--emit-ir",
        action="store_true",
        help="Print LLVM IR to stdout instead of producing a binary")

    parser.add_argument("--emit-hir",
        action="store_true",
        help="Print the High-level IR (after lowering) and exit")

    parser.add_argument("--emit-ast",
        action="store_true",
        help="Print the parsed AST and exit")

    parser.add_argument("--check",
        action="store_true",
        help="Syntax + type check only, output JSON (for editor integration)")

    parser.add_argument("-v", "--verbose",
        action="store_true",
        help="Print each compilation step")

    parser.add_argument("--version",
        action="version",
        version=f"luzc {VERSION}")

    args = parser.parse_args()

    if args.file is None:
        parser.print_help()
        sys.exit(0)

    filename = args.file

    if args.check:
        cmd_check(filename)
    elif args.emit_ast:
        cmd_emit_ast(filename)
    elif args.emit_hir:
        cmd_emit_hir(filename)
    elif args.emit_ir:
        cmd_emit_ir(filename)
    elif args.run:
        cmd_run(filename)
    else:
        cmd_compile(filename, args.output, args.verbose)


if __name__ == "__main__":
    main()
