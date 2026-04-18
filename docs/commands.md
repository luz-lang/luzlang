# Commands

```bash
# Run all tests
python -m pytest tests/test_suite.py -v

# Run a specific test class or test
python -m pytest tests/test_suite.py::TestArithmetic -v
python -m pytest tests/test_suite.py::TestArithmetic::test_int_addition -v

# Run Fuzzer
python tests/fuzzer.py              # 500 iterations, prints crashes
python tests/fuzzer.py 2000         # custom iteration count
python tests/fuzzer.py 500 --seed 42  # reproducible run

# Run the interpreter (REPL)
python main.py

# Run a .luz file
python main.py file.luz

# Parse-only check (used by VS Code extension)
python main.py --check file.luz

# Lint
pylint luz/

# Build the C lexer (Windows — requires MSYS2)
cd luz/c_lexer && make
```
