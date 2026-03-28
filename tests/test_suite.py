"""
Luz Language Test Suite
Runs with: pytest tests/test_suite.py  or  python tests/test_suite.py
"""
import sys
import os
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from luz.lexer import Lexer
from luz.parser import Parser
from luz.interpreter import Interpreter
from luz.exceptions import (
    ArityFault, TypeViolationFault, ZeroDivisionFault, IndexFault,
    UndefinedSymbolFault, InvalidUsageFault, ImportFault, UserFault,
    InheritanceFault, TypeClashFault
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def run(code):
    """Execute Luz code and return the interpreter (for env inspection)."""
    interp = Interpreter()
    ast = Parser(Lexer(code).get_tokens()).parse()
    interp.visit(ast)
    return interp

def val(code):
    """Execute a single expression and return its value."""
    interp = Interpreter()
    return interp.visit(Parser(Lexer(code).get_tokens()).parse())

def env(code, name):
    """Execute code and return the value of a variable."""
    return run(code).global_env.lookup(name)


# ── Arithmetic ────────────────────────────────────────────────────────────────

class TestArithmetic:
    def test_int_addition(self):
        assert val("5 + 5") == 10
        assert isinstance(val("5 + 5"), int)

    def test_float_addition(self):
        assert val("5 + 5.0") == 10.0
        assert isinstance(val("5 + 5.0"), float)

    def test_division_always_float(self):
        assert val("10 / 2") == 5.0
        assert isinstance(val("10 / 2"), float)

    def test_integer_division(self):
        assert val("7 // 2") == 3

    def test_modulo(self):
        assert val("10 % 3") == 1

    def test_power(self):
        assert val("2 ** 10") == 1024

    def test_zero_division(self):
        with pytest.raises(ZeroDivisionFault):
            val("1 / 0")

    def test_zero_integer_division(self):
        with pytest.raises(ZeroDivisionFault):
            val("1 // 0")

    def test_negative_numbers(self):
        assert val("-5 + 3") == -2

    def test_operator_precedence(self):
        assert val("2 + 3 * 4") == 14
        assert val("(2 + 3) * 4") == 20


# ── Strings ───────────────────────────────────────────────────────────────────

class TestStrings:
    def test_concatenation(self):
        assert val('"hello" + " world"') == "hello world"

    def test_repetition(self):
        assert val('"ab" * 3') == "ababab"
        assert val('3 * "ab"') == "ababab"

    def test_fstring(self):
        assert env('x = 42\ns = $"value is {x}"', 's') == "value is 42"

    def test_escape_sequences(self):
        assert val('"a\\nb"') == "a\nb"
        assert val('"a\\tb"') == "a\tb"

    def test_uppercase(self):
        assert val('"hello".uppercase()') == "HELLO"

    def test_lowercase(self):
        assert val('"HELLO".lowercase()') == "hello"

    def test_trim(self):
        assert val('"  hello  ".trim()') == "hello"

    def test_swap(self):
        assert val('"hello".swap("l", "r")') == "herro"

    def test_split(self):
        assert val('"a,b,c".split(",")') == ["a", "b", "c"]
# ── Variables and scope ───────────────────────────────────────────────────────

class TestScope:
    def test_basic_assignment(self):
        assert env("x = 42", "x") == 42

    def test_if_block_scope(self):
        i = run("x = 1\nif true { y = 99 }")
        assert i.global_env.lookup("x") == 1
        with pytest.raises(UndefinedSymbolFault):
            i.global_env.lookup("y")

    def test_if_modifies_outer(self):
        assert env("x = 1\nif true { x = 42 }", "x") == 42

    def test_while_block_scope(self):
        i = run("n = 0\nwhile n < 1 { inner = 5\nn = 1 }")
        with pytest.raises(UndefinedSymbolFault):
            i.global_env.lookup("inner")

    def test_while_modifies_outer(self):
        assert env("n = 3\nwhile n > 0 { n = n - 1 }", "n") == 0

    def test_for_block_scope(self):
        i = run("for k = 1 to 2 { inner = 99 }")
        with pytest.raises(UndefinedSymbolFault):
            i.global_env.lookup("inner")

    def test_for_modifies_outer(self):
        assert env("total = 0\nfor i = 1 to 4 { total = total + i }", "total") == 10

    def test_compound_assign(self):
        assert env("x = 10\nx += 5", "x") == 15
        assert env("x = 10\nx -= 3", "x") == 7
        assert env("x = 4\nx *= 3", "x") == 12
        assert env("x = 10\nx /= 4", "x") == 2.5
        assert env("x = 10\nx %= 3", "x") == 1
        assert env("x = 2\nx **= 8", "x") == 256


# ── Control flow ──────────────────────────────────────────────────────────────

class TestControlFlow:
    def test_while(self):
        assert env("i = 0\nwhile i < 5 { i = i + 1 }", "i") == 5

    def test_for_inclusive(self):
        assert env("s = 0\nfor i = 1 to 5 { s = s + i }", "s") == 15

    def test_for_step(self):
        assert env("s = 0\nfor i = 10 to 1 step -1 { s = s + i }", "s") == 55

    def test_for_invalid_direction(self):
        with pytest.raises(InvalidUsageFault):
            run("for i = 10 to 1 { }")

    def test_for_invalid_negative_step(self):
        with pytest.raises(InvalidUsageFault):
            run("for i = 1 to 10 step -1 { }")

    def test_for_equal_bounds(self):
        assert env("s = 0\nfor i = 5 to 5 { s = i }", "s") == 5

    def test_break(self):
        assert env("i = 0\nwhile true { i = i + 1\nif i == 3 { break } }", "i") == 3

    def test_continue(self):
        assert env("s = 0\nfor i = 1 to 5 { if i == 3 { continue }\ns = s + i }", "s") == 12

    def test_ternary(self):
        assert val("5 if true else 10") == 5
        assert val("5 if false else 10") == 10


# ── Functions ─────────────────────────────────────────────────────────────────

class TestFunctions:
    def test_basic(self):
        assert env("function add(a, b) { return a + b }\nres = add(10, 20)", "res") == 30

    def test_arity_error(self):
        with pytest.raises(ArityFault):
            run("function f(a, b) { return a + b }\nf(1)")

    def test_default_args(self):
        assert env('function greet(name = "World") { return name }\nres = greet()', "res") == "World"

    def test_default_args_caller_scope(self):
        assert env('suffix = "!"\nfunction f(x = suffix) { return x }\nres = f()', "res") == "!"

    def test_named_args(self):
        assert env("function f(a, b) { return a - b }\nres = f(b: 3, a: 10)", "res") == 7

    def test_variadic(self):
        assert env("function sum(...nums) { s = 0\nfor n in nums { s = s + n }\nreturn s }\nres = sum(1, 2, 3, 4)", "res") == 10

    def test_closures(self):
        # Closures capture variables by reference — reads work across function boundary
        code = """
multiplier = 3
function make_multiplier() {
    function apply(x) { return x * multiplier }
    return apply
}
triple = make_multiplier()
res = triple(7)
"""
        assert env(code, "res") == 21

    def test_lambda_short(self):
        assert env("double = fn(x) => x * 2\nres = double(5)", "res") == 10

    def test_recursion(self):
        assert env("function fib(n) { if n <= 1 { return n }\nreturn fib(n-1) + fib(n-2) }\nres = fib(10)", "res") == 55


# ── Collections ───────────────────────────────────────────────────────────────

class TestCollections:
    def test_list_index(self):
        assert env("l = [10, 20, 30]\nv = l[1]", "v") == 20

    def test_list_negative_index(self):
        assert env("l = [10, 20, 30]\nv = l[-1]", "v") == 30

    def test_list_float_index_error(self):
        with pytest.raises(TypeViolationFault):
            run("l = [1, 2]\nv = l[1.5]")

    def test_list_out_of_range(self):
        with pytest.raises(IndexFault):
            run("l = [1, 2]\nv = l[5]")

    def test_list_comprehension(self):
        assert env("squares = [x * x for x in [1, 2, 3, 4]]", "squares") == [1, 4, 9, 16]

    def test_list_comprehension_filter(self):
        assert env("evens = [x for x in [1, 2, 3, 4, 5, 6] if x % 2 == 0]", "evens") == [2, 4, 6]

    def test_dict_access(self):
        assert env('d = {"a": 1, "b": 2}\nv = d["a"]', "v") == 1

    def test_dict_destructure(self):
        i = run('person = {"name": "Alice", "age": 30}\n{name, age} = person')
        assert i.global_env.lookup("name") == "Alice"
        assert i.global_env.lookup("age") == 30

    def test_in_operator_list(self):
        assert val("2 in [1, 2, 3]") == True
        assert val("5 in [1, 2, 3]") == False

    def test_not_in_operator(self):
        assert val("5 not in [1, 2, 3]") == True

    def test_in_operator_string(self):
        assert val('"ell" in "hello"') == True

    def test_null_coalesce(self):
        assert val("null ?? 42") == 42
        assert val("10 ?? 42") == 10

    def test_list_dot_append(self):
        assert env("l = [1, 2]\nl.append(3)", "l") == [1, 2, 3]

    def test_list_dot_pop(self):
        assert env("l = [1, 2, 3]\nv = l.pop()", "v") == 3

    def test_list_dot_len(self):
        assert env("l = [1, 2, 3]\nv = l.len()", "v") == 3

    def test_list_dot_contains(self):
        assert env("l = [1, 2, 3]\nv = l.contains(2)", "v") == True
        assert env("l = [1, 2, 3]\nv = l.contains(99)", "v") == False

    def test_list_dot_join(self):
        assert env('l = ["a", "b", "c"]\nv = l.join(", ")', "v") == "a, b, c"


# ── OOP ───────────────────────────────────────────────────────────────────────

class TestOOP:
    def test_basic_class(self):
        code = """
class Dog {
    function init(self, name) { self.name = name }
    function bark(self) { return self.name + " barks" }
}
d = Dog("Rex")
res = d.bark()
"""
        assert env(code, "res") == "Rex barks"

    def test_inheritance(self):
        code = """
class Animal {
    function speak(self) { return "sound" }
}
class Dog extends Animal {
    function speak(self) { return "woof" }
}
d = Dog()
res = d.speak()
"""
        assert env(code, "res") == "woof"

    def test_super(self):
        code = """
class Animal {
    function speak(self) { return "sound" }
}
class Dog extends Animal {
    function speak(self) {
        base = super.speak()
        return base + "+woof"
    }
}
d = Dog()
res = d.speak()
"""
        assert env(code, "res") == "sound+woof"

    def test_circular_inheritance(self):
        with pytest.raises(Exception):
            code = """
class A extends B { }
class B extends A { }
a = A()
a.x()
"""
            run(code)

    def test_bound_method(self):
        code = """
class Counter {
    function init(self) { self.n = 0 }
    function inc(self) { self.n = self.n + 1\nreturn self.n }
}
c = Counter()
inc = c.inc
a = inc()
b = inc()
"""
        assert env(code, "a") == 1
        assert env(code, "b") == 2

    def test_bound_method_carries_instance(self):
        code = """
class Dog {
    function init(self, name) { self.name = name }
    function speak(self) { return self.name }
}
d = Dog("Rex")
speak = d.speak
res = speak()
"""
        assert env(code, "res") == "Rex"

    def test_self_attr_index(self):
        code = """
class T {
    function init(self) { self.data = [10, 20, 30] }
    function get(self, i) { return self.data[i] }
}
t = T()
a = t.get(0)
b = t.get(2)
"""
        assert env(code, "a") == 10
        assert env(code, "b") == 30

    def test_self_attr_index_expression(self):
        code = """
class T {
    function init(self) { self.data = [10, 20, 30] }
    function last(self) { return self.data[self.data.len() - 1] }
}
res = T().last()
"""
        assert env(code, "res") == 30

    def test_chained_index_and_dot(self):
        assert env("l = [[1, 2], [3, 4]]\nv = l[1][0]", "v") == 3


# ── Error handling ────────────────────────────────────────────────────────────

class TestErrorHandling:
    def test_attempt_rescue(self):
        assert env("""
x = 0
attempt { alert("oops") } rescue (e) { x = 1 }
""", "x") == 1

    def test_rescue_without_variable(self):
        assert env("""
x = 0
attempt { alert("oops") } rescue { x = 1 }
""", "x") == 1

    def test_finally_runs_on_success(self):
        assert env("""
log = ""
attempt { log = log + "try " } rescue { log = log + "rescue " } finally { log = log + "finally" }
""", "log") == "try finally"

    def test_finally_runs_on_error(self):
        assert env("""
log = ""
attempt { alert("fail")\nlog = "unreachable" } rescue { log = "rescued " } finally { log = log + "finally" }
""", "log") == "rescued finally"

    def test_alert_raises(self):
        with pytest.raises(UserFault):
            run('alert("intentional")')


# ── Operators ─────────────────────────────────────────────────────────────────

class TestOperators:
    def test_logical_and(self):
        assert val("true and false") == False
        assert val("true and true") == True

    def test_logical_or(self):
        assert val("false or true") == True

    def test_logical_not(self):
        assert val("not true") == False

    def test_comparisons(self):
        assert val("1 < 2") == True
        assert val("2 > 1") == True
        assert val("1 <= 1") == True
        assert val("2 >= 2") == True
        assert val("1 == 1") == True
        assert val("1 != 2") == True


# ── Casting ───────────────────────────────────────────────────────────────────

class TestCasting:
    def test_to_int(self):
        assert val('to_int("10")') == 10

    def test_to_float(self):
        assert val('to_float("10")') == 10.0

    def test_to_str_bool(self):
        assert val('to_str(true)') == "true"

    def test_to_str_null(self):
        assert val('to_str(null)') == "null"


# ── Imports ───────────────────────────────────────────────────────────────────

class TestImports:
    def test_from_import(self):
        i = run('from "libs/luz-math/constants.luz" import PI')
        assert abs(i.global_env.lookup("PI") - 3.14159265358979) < 1e-6

    def test_import_as(self):
        i = run('import "libs/luz-math/constants.luz" as consts')
        from luz.interpreter import LuzModule
        mod = i.global_env.lookup("consts")
        assert isinstance(mod, LuzModule)
        assert abs(mod.get("PI") - 3.14159265358979) < 1e-6

    def test_failed_import_retryable(self):
        interp = Interpreter()
        with pytest.raises(Exception):
            interp.visit(Parser(Lexer('import "nonexistent.luz"').get_tokens()).parse())
        # Should not be stuck in imported_files
        assert not any("nonexistent" in p for p in interp.imported_files)


class TestBuiltinIndexInsert:
    def test_index_found(self):
        assert val('index([10, 20, 30], 20)') == 1

    def test_index_not_found(self):
        assert val('index([10, 20, 30], 99)') == -1

    def test_index_first_element(self):
        assert val('index(["a", "b", "c"], "a")') == 0

    def test_index_empty_list(self):
        assert val('index([], 1)') == -1

    def test_index_non_list_raises(self):
        with pytest.raises(Exception):
            val('index("hello", "e")')

    def test_insert_basic(self):
        assert env('xs = [1, 2, 3]\ninsert(xs, 1, 99)\nxs', 'xs') == [1, 99, 2, 3]

    def test_insert_at_end(self):
        assert env('xs = [1, 2]\ninsert(xs, 2, 99)\nxs', 'xs') == [1, 2, 99]

    def test_insert_at_start(self):
        assert env('xs = [1, 2]\ninsert(xs, 0, 99)\nxs', 'xs') == [99, 1, 2]

    def test_insert_returns_null(self):
        assert val('xs = [1]\ninsert(xs, 0, 99)') is None

    def test_insert_non_list_raises(self):
        with pytest.raises(Exception):
            val('insert("hello", 0, "x")')

    def test_insert_non_int_index_raises(self):
        with pytest.raises(Exception):
            val('xs = [1]\ninsert(xs, "a", 99)')


# ── reverse, any, all builtins ────────────────────────────────────────────────

class TestBuiltinsReverseAnyAll:
    def test_reverse_list(self):
        assert val("reverse([1, 2, 3])") == [3, 2, 1]

    def test_reverse_string(self):
        assert val('reverse("hello")') == "olleh"

    def test_reverse_empty_list(self):
        assert val("reverse([])") == []

    def test_reverse_empty_string(self):
        assert val('reverse("")') == ""

    def test_reverse_original_unchanged(self):
        interp = run('nums = [1, 2, 3]\nrev = reverse(nums)')
        assert interp.global_env.lookup("nums") == [1, 2, 3]
        assert interp.global_env.lookup("rev") == [3, 2, 1]

    def test_reverse_invalid_type(self):
        with pytest.raises(TypeClashFault):
            val("reverse(42)")

    def test_any_true(self):
        assert val("any([false, false, true])") is True

    def test_any_false(self):
        assert val("any([false, false, false])") is False

    def test_any_empty(self):
        assert val("any([])") is False

    def test_any_invalid_type(self):
        with pytest.raises(TypeClashFault):
            val('any("hello")')

    def test_all_true(self):
        assert val("all([true, true, true])") is True

    def test_all_false(self):
        assert val("all([true, false, true])") is False

    def test_all_empty(self):
        assert val("all([])") is True

    def test_all_invalid_type(self):
        with pytest.raises(TypeClashFault):
            val('all("hello")')


# ── Optional type annotations ────────────────────────────────────────────────

class TestTypeAnnotations:
    def test_no_types_still_works(self):
        assert val("function f(x) { return x * 2 }\nf(5)") == 10

    def test_correct_arg_type_passes(self):
        assert val("function f(x: int) { return x + 1 }\nf(5)") == 6

    def test_wrong_arg_type_raises(self):
        with pytest.raises(TypeViolationFault):
            val('function f(x: int) { return x }\nf("hola")')

    def test_correct_return_type_passes(self):
        assert val("function f() -> int { return 42 }  f()") == 42

    def test_wrong_return_type_raises(self):
        with pytest.raises(TypeViolationFault):
            val('function f() -> int { return "hola" }  f()')

    def test_missing_return_raises(self):
        with pytest.raises(TypeViolationFault):
            val("function f() -> int { }  f()")

    def test_return_null_type_no_return(self):
        assert val("function f() -> null { }  f()") is None

    def test_multiple_typed_params(self):
        assert val('function f(a: int, b: string) { return b }\nf(1, "ok")') == "ok"

    def test_mixed_typed_and_untyped_params(self):
        assert val("function f(a: int, b) { return a + b }\nf(3, 7)") == 10

    def test_bool_type(self):
        assert val("function f(x: bool) { return x }\nf(true)") is True

    def test_bool_not_accepted_as_int(self):
        with pytest.raises(TypeViolationFault):
            val("function f(x: int) { return x }\nf(true)")

    def test_float_type(self):
        assert val("function f(x: float) { return x }\nf(3.14)") == 3.14

    def test_list_type(self):
        assert val("function f(x: list) { return x }\nf([1, 2, 3])") == [1, 2, 3]

    def test_dict_type(self):
        assert val('function f(x: dict) { return x }\nf({"a": 1})') == {"a": 1}

    def test_null_type(self):
        assert val("function f(x: null) { return x }\nf(null)") is None

    def test_class_instance_type(self):
        code = """
class Dog { function init(self, name) { self.name = name } }
function greet(d: Dog) { return d.name }
greet(Dog("Rex"))
"""
        assert val(code) == "Rex"

    def test_class_instance_wrong_type_raises(self):
        code = """
class Dog { function init(self, name) { self.name = name } }
class Cat { function init(self, name) { self.name = name } }
function greet(d: Dog) { return d.name }
greet(Cat("Kitty"))
"""
        with pytest.raises(TypeViolationFault):
            val(code)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import subprocess
    result = subprocess.run(
        [sys.executable, "-m", "pytest", __file__, "-v"],
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    sys.exit(result.returncode)
