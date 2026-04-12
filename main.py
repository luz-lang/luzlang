import sys
from luz.lexer import Lexer
from luz.parser import Parser
from luz.interpreter import Interpreter
from luz.typechecker import TypeChecker
from luz.exceptions import BreakException, ContinueException, ReturnException, SemanticFault

def run(text, interpreter):
    try:
        lexer = Lexer(text)
        tokens = lexer.get_tokens()

        parser = Parser(tokens)
        ast = parser.parse()

        errors = TypeChecker().check(ast)
        if errors:
            for e in errors:
                print(e)
            return None

        result = interpreter.visit(ast)
        return result
    except BreakException as e:
        err = SemanticFault("'break' used outside of a loop")
        err.line = e.line
        raise err
    except ContinueException as e:
        err = SemanticFault("'continue' used outside of a loop")
        err.line = e.line
        raise err
    except ReturnException as e:
        err = SemanticFault("'return' used outside of a function")
        err.line = e.line
        raise err
    except Exception as e:
        error_name = type(e).__name__
        line = getattr(e, 'line', None)
        col  = getattr(e, 'col', None)
        if line is not None and col is not None:
            prefix = f"[Line {line}, Col {col}] "
        elif line is not None:
            prefix = f"[Line {line}] "
        else:
            prefix = ""
        msg = getattr(e, 'message', str(e))
        print(f"{prefix}{error_name}: {msg}")
        return None

def check(filename):
    """Parse-only mode for the VS Code extension. Outputs errors as JSON."""
    import json
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            code = f.read()
        lexer = Lexer(code)
        tokens = lexer.get_tokens()
        parser = Parser(tokens)
        parser.parse()
        print(json.dumps([]))
    except Exception as e:
        line = getattr(e, 'line', None)
        msg = getattr(e, 'message', str(e))
        print(json.dumps([{"line": line, "message": msg}]))


def _load_source(filename):
    """Read a .luz file and return its source text."""
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        print(f"Error: File '{filename}' not found.")
        sys.exit(1)


def _build_hir(code, filename):
    """Lex, parse, and lower to HIR. Exits on syntax/type errors."""
    lexer  = Lexer(code)
    tokens = lexer.get_tokens()
    parser = Parser(tokens)
    ast    = parser.parse()

    errors = TypeChecker().check(ast)
    if errors:
        for e in errors:
            print(e)
        sys.exit(1)

    from luz.hir import Lowering
    return Lowering().lower_program(ast)


def _dump_node(node, indent=0):
    """Recursively pretty-print an AST or HIR node."""
    from luz.tokens import Token
    pad = "  " * indent
    if node is None:
        return f"{pad}null"
    if isinstance(node, bool):
        return f"{pad}{node!r}"
    if isinstance(node, (int, float, str)):
        return f"{pad}{node!r}"
    if isinstance(node, Token):
        return f"{pad}Token({node.type.name}, {node.value!r})"
    if isinstance(node, list):
        if not node:
            return f"{pad}[]"
        lines = [f"{pad}["]
        for item in node:
            lines.append(_dump_node(item, indent + 1))
        lines.append(f"{pad}]")
        return "\n".join(lines)
    if isinstance(node, dict):
        if not node:
            return f"{pad}{{}}"
        lines = [f"{pad}{{"]
        for k, v in node.items():
            lines.append(f"{pad}  {k!r}:")
            lines.append(_dump_node(v, indent + 2))
        lines.append(f"{pad}}}")
        return "\n".join(lines)
    # AST / HIR object: show class name + attributes
    cls  = type(node).__name__
    data = vars(node) if hasattr(node, "__dict__") else {}
    if not data:
        return f"{pad}{cls}()"
    lines = [f"{pad}{cls}("]
    for k, v in data.items():
        child = _dump_node(v, indent + 1)
        if "\n" not in child:
            lines.append(f"{pad}  {k} = {child.strip()}")
        else:
            lines.append(f"{pad}  {k} =")
            lines.append(child)
    lines.append(f"{pad})")
    return "\n".join(lines)


def emit_ast(filename):
    """Print the AST produced by the parser for a .luz file."""
    code   = _load_source(filename)
    lexer  = Lexer(code)
    tokens = lexer.get_tokens()
    parser = Parser(tokens)
    ast    = parser.parse()
    print(_dump_node(ast))


def emit_hir(filename):
    """Print the HIR (after lowering) for a .luz file."""
    import pprint
    code = _load_source(filename)
    hir  = _build_hir(code, filename)
    pprint.pprint(hir, width=120)


def emit_ir(filename):
    """Print the LLVM IR generated from a .luz file."""
    try:
        from luz.codegen import LLVMCodeGen
    except ImportError:
        print("Error: llvmlite is not installed. Run: pip install llvmlite")
        sys.exit(1)

    code = _load_source(filename)
    hir  = _build_hir(code, filename)
    gen  = LLVMCodeGen()
    gen.gen_program(hir)
    print(str(gen.module))


def compile_file(filename, output=None):
    """Compile a .luz file to a native executable."""
    try:
        from luz.codegen import LLVMCodeGen
    except ImportError:
        print("Error: llvmlite is not installed. Run: pip install llvmlite")
        sys.exit(1)

    import os, subprocess
    output = output or os.path.splitext(filename)[0]
    code   = _load_source(filename)
    hir    = _build_hir(code, filename)
    gen    = LLVMCodeGen()
    gen.gen_program(hir)
    try:
        gen.compile_to_exe(output)
        print(f"Compiled: {output}")
    except subprocess.CalledProcessError:
        print("Error: linking failed. Make sure the C runtime is compiled (cd luz/runtime && make).")
        sys.exit(1)


def compile_and_run(filename):
    """Compile a .luz file and run it immediately, then delete the binary."""
    try:
        from luz.codegen import LLVMCodeGen
    except ImportError:
        print("Error: llvmlite is not installed. Run: pip install llvmlite")
        sys.exit(1)

    import os, subprocess, tempfile
    code = _load_source(filename)
    hir  = _build_hir(code, filename)
    gen  = LLVMCodeGen()
    gen.gen_program(hir)

    fd, tmp = tempfile.mkstemp(suffix=(".exe" if sys.platform == "win32" else ""))
    os.close(fd)
    try:
        gen.compile_to_exe(tmp)
        subprocess.run([tmp], check=False)
    except subprocess.CalledProcessError:
        print("Error: linking failed. Make sure the C runtime is compiled (cd luz/runtime && make).")
        sys.exit(1)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def main():
    interpreter = Interpreter()
    args = sys.argv[1:]

    # --check <file>  (VS Code extension)
    if args and args[0] == '--check' and len(args) >= 2:
        check(args[1])
        return

    # --emit-ast <file>
    if args and args[0] == '--emit-ast' and len(args) >= 2:
        emit_ast(args[1])
        return

    # --emit-hir <file>
    if args and args[0] == '--emit-hir' and len(args) >= 2:
        emit_hir(args[1])
        return

    # --emit-ir <file>
    if args and args[0] == '--emit-ir' and len(args) >= 2:
        emit_ir(args[1])
        return

    # --compile <file> [-o output]
    if args and args[0] == '--compile' and len(args) >= 2:
        output = None
        if '-o' in args:
            idx = args.index('-o')
            if idx + 1 < len(args):
                output = args[idx + 1]
        compile_file(args[1], output)
        return

    # --run <file>
    if args and args[0] == '--run' and len(args) >= 2:
        compile_and_run(args[1])
        return

    if args:
        filename = args[0]
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                code = f.read()
                run(code, interpreter)
        except FileNotFoundError:
            print(f"Error: File '{filename}' not found.")
        except Exception as e:
            print(f"Error reading file: {e}")

    else:
        print(f"Luz Interpreter v1.19.0 - Type 'exit' to terminate")
        while True:
            try:
                text = input("Luz > ")
                if text.strip().lower() == "exit":
                    break
                if not text.strip():
                    continue
                    
                result = run(text, interpreter)
                if result is not None:
                    print(result)
                    
            except KeyboardInterrupt:
                print("\nExiting...")
                break
            except Exception as e:
                error_name = type(e).__name__
                line = getattr(e, 'line', None)
                col = getattr(e, 'col', None)
                if line is not None and col is not None:
                    prefix = f"[Line {line}, Col {col}] "
                elif line is not None:
                    prefix = f"[Line {line}]"
                else:
                    prefix = ""
                msg = getattr(e, 'message', str(e))
                print(f"{prefix}{error_name}: {msg}")

if __name__ == "__main__":
    main()
