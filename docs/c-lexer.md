# C Lexer (`luz/c_lexer/`)

- `luz_lexer.c` — C implementation of the full lexer
- `bridge.py` — ctypes bridge; `_C_TO_PYTHON` list maps C enum indices to Python `TokenType`
- `Makefile` — uses MSYS2's `bash` + `gcc` on Windows (requires MSYS2 at `C:/msys64`)
- The `.dll`/`.so` is gitignored; run `make` to build it locally
- `INT` and `FLOAT` token values must be converted from string to `int`/`float` in the bridge
