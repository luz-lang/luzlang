# Important Patterns

**Class methods require explicit `self`:** Unlike Python, Luz class methods must declare `self` as the first parameter. The interpreter prepends the instance to the argument list when calling methods.

```luz
class Foo {
    function init(self, x) { self.x = x }
    function get(self) { return self.x }
}
```

**Method names must not shadow builtins:** If a class method is named `len`, `min`, `max`, or `sum`, it will shadow the builtin inside the class body, causing `ArityFault` when the interpreter tries to call the builtin with the wrong number of args. Use alternative names (`size`, `minimum`, `maximum`, `total`).

**Import resolution order:** `import "math"` resolves by trying in order: literal path → `luz_modules/math/` → file-relative path → `$LUZ_HOME/lib/` → `libs/luz-math/math.luz` (dev fallback). Circular imports are silently skipped via `self.imported_files` (set of absolute paths).

**`from "x" import ...` and `import "x" as ...`** execute the module in an isolated `Environment`. Plain `import "x"` executes in the current scope.
