"""Legacy entry point for Luz.

The interpreter has been removed. This module now only:
  * Provides `--check` for the VS Code extension (lexer/parser only).
  * Delegates every other command (`--compile`, `--run`, `--emit-*`, `<file>`)
    to `luzc.py`, the compiler driver.
"""
import json
import os
import subprocess
import sys

from luz.lexer import Lexer
from luz.parser import Parser


def check(filename):
    """Parse-only mode for the VS Code extension. Outputs errors as JSON."""
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


_LEGACY_FILE_FIRST_FLAGS = {'--emit-ast', '--emit-hir', '--emit-ir', '--run'}


def _translate_legacy_args(args):
    """Translate old `--flag <file>` form into luzc's `<file> --flag` form.

    Old main.py accepted things like `--run file.luz` and `--compile file.luz -o out`.
    luzc.py puts the filename first. Anything else is passed through unchanged.
    """
    if not args:
        return args

    # `--compile file.luz [-o out]`  ->  `file.luz [-o out]`
    if args[0] == '--compile' and len(args) >= 2:
        return [args[1], *args[2:]]

    # `--run file.luz`, `--emit-*  file.luz`  ->  `file.luz --flag`
    if args[0] in _LEGACY_FILE_FIRST_FLAGS and len(args) >= 2:
        return [args[1], args[0], *args[2:]]

    # Bare `file.luz` used to run via the interpreter — compile+run it now.
    if not args[0].startswith('-') and len(args) == 1:
        return [args[0], '--run']

    return args


def _delegate_to_luzc(args):
    """Forward CLI arguments to luzc.py and exit with its return code."""
    luzc = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'luzc.py')
    result = subprocess.run([sys.executable, luzc, *_translate_legacy_args(args)])
    sys.exit(result.returncode)


def main():
    args = sys.argv[1:]

    if args and args[0] == '--check' and len(args) >= 2:
        check(args[1])
        return

    if not args:
        print(
            "Luz no longer ships a REPL. Use luzc.py to compile a program.\n"
            "Examples:\n"
            "  python luzc.py file.luz --run\n"
            "  python luzc.py file.luz -o out\n"
            "  python luzc.py file.luz --emit-ir"
        )
        sys.exit(1)

    _delegate_to_luzc(args)


if __name__ == "__main__":
    main()
