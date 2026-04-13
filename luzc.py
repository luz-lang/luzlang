"""
luzc — Luz Compiler
Usage:
    luzc <file.luz> [-o output] [-O0|O1|O2|O3] [--emit-ir] [--emit-hir] [--emit-ast]
    luzc <file.luz> --run
    luzc --version
    luzc --help
"""

import sys
import os
import argparse
import subprocess

# ── Version ───────────────────────────────────────────────────────────────────

VERSION = "1.0.0"

# ── Error formatting (GCC-style: file:line:col: error: message) ───────────────

def _fmt_error(filename, exc, label="error"):
    line = getattr(exc, "line", None)
    col  = getattr(exc, "col",  None)
    msg  = getattr(exc, "message", str(exc))

    loc = filename
    if line is not None:
        loc += f":{line}"
        if col is not None:
            loc += f":{col}"

    kind = type(exc).__name__.replace("Fault", "").replace("Exception", "")
    return f"{loc}: {label}: [{kind}] {msg}"


def _die(filename, exc, label="error"):
    print(_fmt_error(filename, exc, label), file=sys.stderr)
    sys.exit(1)

# ── Pipeline helpers ──────────────────────────────────────────────────────────

def _load(filename):
    try:
        with open(filename, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        print(f"luzc: error: no such file: '{filename}'", file=sys.stderr)
        sys.exit(1)
    except OSError as e:
        print(f"luzc: error: cannot read '{filename}': {e}", file=sys.stderr)
        sys.exit(1)


def _lex_parse(source, filename):
    from luz.lexer  import Lexer
    from luz.parser import Parser

    try:
        tokens = Lexer(source).get_tokens()
    except Exception as e:
        _die(filename, e)

    try:
        return Parser(tokens).parse()
    except Exception as e:
        _die(filename, e)


def _typecheck(ast, filename):
    from luz.typechecker import TypeChecker
    errors = TypeChecker().check(ast)
    if errors:
        for e in errors:
            # TypeChecker returns formatted strings already
            print(f"{filename}: error: {e}", file=sys.stderr)
        sys.exit(1)


def _lower(ast, filename):
    from luz.hir import Lowering
    try:
        return Lowering().lower_program(ast)
    except Exception as e:
        _die(filename, e)


def _codegen(hir, filename):
    try:
        from luz.codegen import LLVMCodeGen
    except ImportError:
        print("luzc: error: llvmlite is not installed.\n"
              "       Run: pip install llvmlite", file=sys.stderr)
        sys.exit(1)

    try:
        gen = LLVMCodeGen()
        gen.gen_program(hir)
        return gen
    except Exception as e:
        _die(filename, e)


def _build_pipeline(filename):
    """Run the full pipeline up to codegen. Returns (ast, hir, gen)."""
    source = _load(filename)
    ast    = _lex_parse(source, filename)
    _typecheck(ast, filename)
    hir    = _lower(ast, filename)
    gen    = _codegen(hir, filename)
    return ast, hir, gen

# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_check(filename):
    """Syntax + type check only (no codegen). Used by the VS Code extension."""
    import json
    source = _load(filename)
    try:
        from luz.lexer  import Lexer
        from luz.parser import Parser
        tokens = Lexer(source).get_tokens()
        ast    = Parser(tokens).parse()
        from luz.typechecker import TypeChecker
        errors = TypeChecker().check(ast)
        if errors:
            print(json.dumps([{"line": None, "message": str(e)} for e in errors]))
        else:
            print(json.dumps([]))
    except Exception as e:
        line = getattr(e, "line", None)
        msg  = getattr(e, "message", str(e))
        print(json.dumps([{"line": line, "message": msg}]))


def cmd_emit_ast(filename):
    source = _load(filename)
    ast    = _lex_parse(source, filename)
    _dump(ast)


def cmd_emit_hir(filename):
    import pprint
    source = _load(filename)
    ast    = _lex_parse(source, filename)
    _typecheck(ast, filename)
    hir    = _lower(ast, filename)
    pprint.pprint(hir, width=120)


def cmd_emit_ir(filename):
    _, _, gen = _build_pipeline(filename)
    print(str(gen.module))


def cmd_compile(filename, output, opt_level, verbose):
    """Compile to a native executable."""
    if verbose:
        print(f"luzc: compiling '{filename}'...")

    _, _, gen = _build_pipeline(filename)

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
    except subprocess.CalledProcessError as e:
        print(f"luzc: error: linking failed.\n"
              f"       Make sure the runtime is compiled:\n"
              f"         cd luz/runtime && make", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"luzc: error: {e}", file=sys.stderr)
        sys.exit(1)

    if verbose:
        size = os.path.getsize(output)
        print(f"luzc: done ({size:,} bytes)")
    else:
        print(f"Compiled: {output}")


def cmd_run(filename):
    """Compile + execute immediately, then delete the binary."""
    import tempfile
    _, _, gen = _build_pipeline(filename)

    suffix = ".exe" if sys.platform == "win32" else ""
    fd, tmp = tempfile.mkstemp(suffix=suffix)
    os.close(fd)

    try:
        gen.compile_to_exe(tmp)
        result = subprocess.run([tmp], check=False)
        sys.exit(result.returncode)
    except subprocess.CalledProcessError:
        print(f"luzc: error: linking failed.\n"
              f"       Make sure the runtime is compiled:\n"
              f"         cd luz/runtime && make", file=sys.stderr)
        sys.exit(1)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)

# ── AST pretty-printer ────────────────────────────────────────────────────────

def _dump(node, indent=0):
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
            _dump(item, indent + 1)
        print(f"{pad}]"); return
    cls  = type(node).__name__
    data = vars(node) if hasattr(node, "__dict__") else {}
    if not data:
        print(f"{pad}{cls}()"); return
    print(f"{pad}{cls}(")
    for k, v in data.items():
        print(f"{pad}  {k} =")
        _dump(v, indent + 2)
    print(f"{pad})")

# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        prog="luzc",
        description="Luz compiler - compiles .luz source files to native executables.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  luzc hello.luz                  Compile to hello.exe (Windows) or hello (Linux/Mac)
  luzc hello.luz -o greet         Compile to greet.exe / greet
  luzc hello.luz --run            Compile and run immediately
  luzc hello.luz --emit-ir        Print LLVM IR to stdout
  luzc hello.luz --emit-hir       Print HIR to stdout
  luzc hello.luz --emit-ast       Print AST to stdout
""",
    )

    parser.add_argument("file",
        nargs="?",
        metavar="file.luz",
        help="Luz source file to compile")

    parser.add_argument("-o",
        metavar="output",
        dest="output",
        help="Output binary name (default: same as source, no extension)")

    parser.add_argument("-O", "-O0", "-O1", "-O2", "-O3",
        dest="opt",
        metavar="level",
        default="2",
        help="Optimization level (0-3, default 2)")

    parser.add_argument("--run",
        action="store_true",
        help="Compile and execute immediately, then delete the binary")

    parser.add_argument("--emit-ir",
        action="store_true",
        help="Print LLVM IR instead of producing a binary")

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
        help="Print compilation steps")

    parser.add_argument("--version",
        action="version",
        version=f"luzc {VERSION}")

    args = parser.parse_args()

    if args.file is None:
        parser.print_help()
        sys.exit(0)

    filename = args.file

    # Dispatch to the right command
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
        cmd_compile(filename, args.output, args.opt, args.verbose)


if __name__ == "__main__":
    main()
