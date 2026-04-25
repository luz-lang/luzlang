# Contributing to Luz

Thank you for your interest in contributing to Luz! This document explains how to get started.

## Getting started

1. Fork the repository
2. Clone your fork:
   ```bash
   git clone https://github.com/YOUR_USERNAME/luz-lang.git
   cd luz-lang
   ```
3. Create a branch for your change:
   ```bash
   git checkout -b feature/my-feature
   ```

## Project structure

```
luz-lang/
├── compiler/             # Native C++ compiler (luzc)
│   ├── src/              # Lexer, parser, typechecker, HIR, codegen
│   ├── include/luz/      # Public headers
│   ├── c_lexer/          # C lexer shared with the compiler
│   ├── runtime/          # luz_rt.c — C runtime linked by clang
│   └── tests/            # C++ unit + E2E test suite
├── luzc.py               # Thin Python wrapper that delegates to luzc binary
├── main.py               # Legacy entry point (delegates to luzc.py)
├── ray.py                # Ray package manager
├── libs/                 # Standard library (bundled with installer)
│   └── luz-math/         # Math library
├── tests/
│   └── test_suite.py     # Python test suite (calls luzc binary)
├── installer/
│   └── luz_installer.iss # Inno Setup installer script
├── vscode-luz/           # VS Code extension
└── docs/                 # MkDocs documentation
```

## Building the compiler

```bash
cd compiler
cmake -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build
```

The binary is at `compiler/build/luzc` (Linux/macOS) or `compiler/build/luzc.exe` (Windows).

## Running the tests

```bash
# C++ tests (unit + end-to-end)
ctest --test-dir compiler/build --output-on-failure

# Python test suite (calls the C++ binary)
pip install pytest
pytest tests/test_suite.py -v
```

All tests must pass before opening a pull request.

## Making changes to the language

The compiler pipeline has these stages:

| Stage | Files |
|---|---|
| Lexer | `compiler/src/lexer.cpp` |
| Parser + AST | `compiler/src/parser.cpp`, `compiler/include/luz/ast.hpp` |
| Type checker | `compiler/src/typechecker.cpp` |
| HIR lowering | `compiler/src/hir.cpp`, `compiler/include/luz/hir.hpp` |
| LLVM IR codegen | `compiler/src/codegen.cpp` |
| Runtime | `compiler/runtime/luz_rt.c` |

When adding a new language feature, update all stages and add tests in `compiler/tests/`.

## Code style

- Follow the existing style in each file
- Add comments for non-obvious logic
- Keep functions focused and small

## Opening a pull request

1. Make sure all C++ tests pass: `ctest --test-dir compiler/build --output-on-failure`
2. Make sure Python tests pass: `pytest tests/test_suite.py -v`
3. Open a PR against `master`
