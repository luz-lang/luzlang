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

def main():
    interpreter = Interpreter()

    if len(sys.argv) > 2 and sys.argv[1] == '--check':
        check(sys.argv[2])
        return

    if len(sys.argv) > 1:
        filename = sys.argv[1]
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                code = f.read()
                run(code, interpreter)
        except FileNotFoundError:
            print(f"Error: File '{filename}' not found.")
        except Exception as e:
            print(f"Error reading file: {e}")
    
    else:
        print(f"Luz Interpreter v1.18.0 - Type 'exit' to terminate")
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
