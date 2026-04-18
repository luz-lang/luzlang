# Standard Library (`libs/`)

Each library lives in `libs/luz-<name>/` with an entry-point `<name>.luz` that imports submodules. Users write `import "math"` which resolves to `libs/luz-math/math.luz`.

Trig and log functions (`sin`, `cos`, `exp`, `ln`, etc.) are implemented as **native Python builtins** in `interpreter.py`, not as Luz code. The `libs/luz-math/trigonometry.luz` and `logarithms.luz` files are thin wrappers that only add utility functions on top.

A Luz library absolutely needs to have a `luz.json` file, which includes library metadata: its name, version, and description.
