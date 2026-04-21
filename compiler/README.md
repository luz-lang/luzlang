# luzc (C++ implementation)

Native implementation of the Luz compiler. Reuses `../luz/c_lexer/` for
tokenization and ports the rest of the pipeline from the Python sources.

## Status

- [x] Lexer — C (reused from `luz/c_lexer/`)
- [x] Parser — expressions only (literals, arithmetic, calls)
- [ ] Parser — statements (let, if, while, for, function, class, struct, …)
- [ ] Typechecker
- [ ] HIR lowering
- [ ] Codegen (LLVM C API or direct asm)
- [ ] Self-hosting

## Build

```bash
cmake -S compiler -B compiler/build
cmake --build compiler/build
```

## Run

```bash
./compiler/build/luzc file.luz --tokens    # dump tokens
./compiler/build/luzc file.luz --ast       # dump AST
```

## Layout

```
compiler/
├── CMakeLists.txt
├── include/luz/     public headers (token, lexer, ast, parser, diagnostics)
├── src/             implementation
└── tests/           GoogleTest suite (TBD)
```
