"""Legacy entry point for Luz.

Delegates all commands to luzc.py, which in turn calls the native C++ binary.
Kept for backwards compatibility with the VS Code extension and existing scripts.
"""
import os
import subprocess
import sys


_LEGACY_FILE_FIRST_FLAGS = {'--emit-ast', '--emit-hir', '--emit-ir', '--run'}


def _translate_legacy_args(args):
    """Translate old `--flag <file>` form into luzc's `<file> --flag` form."""
    if not args:
        return args
    if args[0] == '--compile' and len(args) >= 2:
        return [args[1], *args[2:]]
    if args[0] in _LEGACY_FILE_FIRST_FLAGS and len(args) >= 2:
        return [args[1], args[0], *args[2:]]
    if not args[0].startswith('-') and len(args) == 1:
        return [args[0], '--run']
    return args


def _delegate_to_luzc(args):
    luzc = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'luzc.py')
    result = subprocess.run([sys.executable, luzc, *_translate_legacy_args(args)])
    sys.exit(result.returncode)


def main():
    args = sys.argv[1:]

    if not args:
        print(
            "Luz compiler. Usage:\n"
            "  python luzc.py file.luz          compile to binary\n"
            "  python luzc.py file.luz --run    compile and run\n"
            "  python luzc.py file.luz --emit-llvm  emit LLVM IR"
        )
        sys.exit(1)

    _delegate_to_luzc(args)


if __name__ == "__main__":
    main()
