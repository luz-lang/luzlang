"""
luzc -- Luz Compiler driver (thin wrapper around the native luzc binary).

Delegates all commands to the C++ luzc binary. Kept as a Python entry point
so existing tooling (VS Code extension, scripts) can invoke `python luzc.py`
without changes during the 1.x → 2.0 transition.

Flag mapping (old Python flags → C++ flags):
  --emit-ir   → --emit-llvm
  --emit-hir  → --hir
  --emit-ast  → --ast
  --check     → --check-json   (JSON output expected by the VS Code extension)
"""

import sys
import os
import subprocess


def _find_binary() -> str | None:
    """Locate the native luzc binary relative to this file or in PATH."""
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(here, "compiler", "build", "luzc.exe"),
        os.path.join(here, "compiler", "build", "luzc"),
        os.path.join(here, "compiler", "build", "Release", "luzc.exe"),
        os.path.join(here, "compiler", "build", "Debug",   "luzc.exe"),
    ]
    for path in candidates:
        if os.path.isfile(path):
            return path
    # PATH fallback
    import shutil
    return shutil.which("luzc")


_FLAG_MAP = {
    "--emit-ir":  "--emit-llvm",
    "--emit-hir": "--hir",
    "--emit-ast": "--ast",
    # --check from the VS Code extension expects JSON output
    "--check":    "--check-json",
}


def main() -> None:
    binary = _find_binary()
    if binary is None:
        print(
            "luzc: error: native luzc binary not found.\n"
            "  Build it with:\n"
            "    cd compiler\n"
            "    cmake -B build -DCMAKE_BUILD_TYPE=Release\n"
            "    cmake --build build",
            file=sys.stderr,
        )
        sys.exit(1)

    translated = [_FLAG_MAP.get(a, a) for a in sys.argv[1:]]
    result = subprocess.run([binary] + translated)
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
