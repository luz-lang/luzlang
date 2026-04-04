# Usage

## Interactive REPL

Run `main.py` with no arguments to open the interactive shell:

```bash
python main.py
```

```
Luz Interpreter v1.18.0 - Type 'exit' to terminate
Luz > x = 10
Luz > write(x * 2)
20
Luz > name: string = "world"
Luz > write($"Hello {name}!")
Hello world!
Luz > exit
```

The REPL evaluates one statement at a time. Multi-line constructs (functions, classes, loops) are not supported in the REPL — use a file for those.

## Run a file

```bash
python main.py program.luz
```

Any `.luz` file can be executed this way. The interpreter runs the file from top to bottom and exits when it reaches the end.

## Parse-only check

The `--check` flag runs the lexer and parser only, returning any syntax errors as JSON. This is used by the VS Code extension:

```bash
python main.py --check program.luz
```

Output: `[]` on success, or `[{"line": N, "message": "..."}]` on error.

## Run the test suite

```bash
python -m pytest tests/test_suite.py -v
```

Run a specific test class or case:

```bash
python -m pytest tests/test_suite.py::TestArithmetic -v
python -m pytest tests/test_suite.py::TestArithmetic::test_int_addition -v
```

## Run all examples

```bash
python run_examples.py
```

Runs every `.luz` file in `examples/`, prints a pass/fail/interactive status for each, and exits with code 1 if any failures are found.

## Using the standalone installer (Windows)

Download and run the installer from the [download page](https://elabsurdo984.github.io/luz-lang/download/). After installation `luz` is available from any terminal:

```bash
luz program.luz    # run a file
luz                # open the REPL
ray install user/repo   # install a package
```
