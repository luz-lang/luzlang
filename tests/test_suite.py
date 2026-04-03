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
    InheritanceFault, TypeClashFault, ArgumentFault, OverflowFault
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

    def test_list_append_missing_arg_raises(self):
        with pytest.raises(ArityFault):
            val('[1, 2].append()')

    def test_list_contains_missing_arg_raises(self):
        with pytest.raises(ArityFault):
            val('[1, 2].contains()')

    def test_list_join_missing_arg_raises(self):
        with pytest.raises(ArityFault):
            val('[1, 2].join()')

    def test_string_swap_missing_arg_raises(self):
        with pytest.raises(ArityFault):
            val('"hello".swap("l")')

    def test_string_swap_no_args_raises(self):
        with pytest.raises(ArityFault):
            val('"hello".swap()')


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

    def test_finally_rescue_error_preserved(self):
        # Error from rescue must survive even if finally also raises
        with pytest.raises(UserFault):
            run("""
attempt {
    alert "original"
} rescue (e) {
    alert "from rescue"
} finally {
    alert "from finally"
}
""")

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

    def test_from_import_missing_name_leaves_nothing(self):
        # If one name doesn't exist, nothing should be defined
        from luz.exceptions import ImportFault
        interp = Interpreter()
        with pytest.raises(ImportFault):
            interp.visit(Parser(Lexer(
                'from "libs/luz-math/constants.luz" import PI, DOES_NOT_EXIST'
            ).get_tokens()).parse())
        with pytest.raises(UndefinedSymbolFault):
            interp.global_env.lookup("PI")


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

    def test_insert_out_of_bounds_raises(self):
        """Verify that positive out-of-range indices raise IndexFault."""
        with pytest.raises(IndexFault):
            val('xs = [1, 2]\ninsert(xs, 99, 9)')

    def test_insert_negative_out_of_bounds_raises(self):
        """Verify that negative out-of-range indices raise IndexFault."""
        with pytest.raises(IndexFault):
            val('xs = [1, 2]\ninsert(xs, -5, 9)')

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

    def test_subclass_satisfies_parent_type(self):
        code = """
class Animal {}
class Dog extends Animal {}
function greet(a: Animal) { return "hello" }
greet(Dog())
"""
        assert val(code) == "hello"

    def test_deep_inheritance_satisfies_ancestor_type(self):
        code = """
class A {}
class B extends A {}
class C extends B {}
function f(x: A) { return "ok" }
f(C())
"""
        assert val(code) == "ok"

    def test_unrelated_class_still_raises(self):
        code = """
class Animal {}
class Rock {}
function greet(a: Animal) { return "hello" }
greet(Rock())
"""
        with pytest.raises(TypeViolationFault):
            val(code)


# ── Typed variable declarations ──────────────────────────────────────────────

class TestTypedVariables:
    def test_basic_declaration(self):
        assert env("x: int = 5", "x") == 5

    def test_correct_reassignment(self):
        assert env("x: int = 5\nx = 10", "x") == 10

    def test_wrong_initial_value_raises(self):
        with pytest.raises(TypeViolationFault):
            val('x: int = "hola"')

    def test_wrong_reassignment_raises(self):
        with pytest.raises(TypeViolationFault):
            val('x: int = 5\nx = "hola"')

    def test_string_type(self):
        assert env('s: string = "hola"', "s") == "hola"

    def test_bool_type(self):
        assert env("b: bool = true", "b") is True

    def test_float_type(self):
        assert env("f: float = 3.14", "f") == 3.14

    def test_list_type(self):
        assert env("l: list = [1, 2, 3]", "l") == [1, 2, 3]

    def test_dict_type(self):
        assert env('d: dict = {"a": 1}', "d") == {"a": 1}

    def test_null_type(self):
        assert env("x: null = null", "x") is None

    def test_bool_not_accepted_as_int(self):
        with pytest.raises(TypeViolationFault):
            val("x: int = true")

    def test_untyped_var_unchanged(self):
        assert env('x = 5\nx = "hola"', "x") == "hola"

    def test_typed_var_in_function(self):
        assert val("function f() { x: int = 10\nx = 20\nreturn x }\nf()") == 20


# ── Fixed-size integer and float types ───────────────────────────────────────

class TestFixedSizeTypes:
    # ── int8 ──
    def test_int8_valid(self):
        assert env("x: int8 = 127", "x") == 127

    def test_int8_negative(self):
        assert env("x: int8 = -128", "x") == -128

    def test_int8_overflow_raises(self):
        with pytest.raises(OverflowFault):
            val("x: int8 = 128")

    def test_int8_underflow_raises(self):
        with pytest.raises(OverflowFault):
            val("x: int8 = -129")

    # ── uint8 ──
    def test_uint8_valid(self):
        assert env("x: uint8 = 255", "x") == 255

    def test_uint8_zero(self):
        assert env("x: uint8 = 0", "x") == 0

    def test_uint8_overflow_raises(self):
        with pytest.raises(OverflowFault):
            val("x: uint8 = 256")

    def test_uint8_negative_raises(self):
        with pytest.raises(OverflowFault):
            val("x: uint8 = -1")

    # ── int16 / int32 / int64 ──
    def test_int16_bounds(self):
        assert env("x: int16 = 32767", "x") == 32767
        assert env("x: int16 = -32768", "x") == -32768

    def test_int32_bounds(self):
        assert env("x: int32 = 2147483647", "x") == 2147483647

    def test_int64_large(self):
        assert env("x: int64 = 9223372036854775807", "x") == 9223372036854775807

    # ── uint16 / uint32 / uint64 ──
    def test_uint16_max(self):
        assert env("x: uint16 = 65535", "x") == 65535

    def test_uint32_max(self):
        assert env("x: uint32 = 4294967295", "x") == 4294967295

    # ── wrong base type ──
    def test_int32_rejects_float(self):
        with pytest.raises(TypeViolationFault):
            val("x: int32 = 3.14")

    def test_int32_rejects_bool(self):
        with pytest.raises(TypeViolationFault):
            val("x: int32 = true")

    def test_int32_rejects_string(self):
        with pytest.raises(TypeViolationFault):
            val('x: int32 = "hello"')

    # ── float32 ──
    def test_float32_valid(self):
        import struct
        expected = struct.unpack('f', struct.pack('f', 3.14))[0]
        assert env("x: float32 = 3.14", "x") == expected

    def test_float32_rejects_int(self):
        with pytest.raises(TypeViolationFault):
            val("x: float32 = 5")

    # ── float64 ──
    def test_float64_valid(self):
        assert env("x: float64 = 3.14", "x") == 3.14

    def test_float64_rejects_int(self):
        with pytest.raises(TypeViolationFault):
            val("x: float64 = 5")

    # ── reassignment overflow ──
    def test_int8_reassign_overflow_raises(self):
        with pytest.raises(OverflowFault):
            val("x: int8 = 10\nx = 200")

    # ── fixed-size type as function parameter ──
    def test_int32_param(self):
        code = "function f(n: int32) { return n }\nf(42)"
        assert val(code) == 42

    def test_int32_param_overflow_raises(self):
        code = "function f(n: int32) { return n }\nf(3000000000)"
        with pytest.raises(OverflowFault):
            val(code)

    # ── fixed-size type as return type ──
    def test_int16_return(self):
        code = "function f() -> int16 { return 1000 }\nf()"
        assert val(code) == 1000

    def test_int16_return_overflow_raises(self):
        code = "function f() -> int16 { return 40000 }\nf()"
        with pytest.raises(OverflowFault):
            val(code)


# ── Generic collection types ──────────────────────────────────────────────────

class TestGenericTypes:
    # ── list[T] variable declarations ──
    def test_list_int_valid(self):
        assert env("nums: list[int] = [1, 2, 3]", "nums") == [1, 2, 3]

    def test_list_string_valid(self):
        assert env('words: list[string] = ["a", "b"]', "words") == ["a", "b"]

    def test_list_int_wrong_element_raises(self):
        with pytest.raises(TypeViolationFault):
            val('nums: list[int] = [1, "dos", 3]')

    def test_list_int_empty_valid(self):
        assert env("nums: list[int] = []", "nums") == []

    def test_list_float_valid(self):
        assert env("xs: list[float] = [1.0, 2.5]", "xs") == [1.0, 2.5]

    # ── dict[K, V] ──
    def test_dict_string_int_valid(self):
        assert env('scores: dict[string, int] = {"a": 1}', "scores") == {"a": 1}

    def test_dict_wrong_value_raises(self):
        with pytest.raises(TypeViolationFault):
            val('scores: dict[string, int] = {"a": "oops"}')

    def test_dict_wrong_key_raises(self):
        with pytest.raises(TypeViolationFault):
            val('scores: dict[string, int] = {1: 2}')

    def test_dict_empty_valid(self):
        assert env("d: dict[string, float] = {}", "d") == {}

    # ── function parameter ──
    def test_list_param(self):
        code = "function f(xs: list[int]) { return xs }\nf([1, 2, 3])"
        assert val(code) == [1, 2, 3]

    def test_list_param_wrong_element_raises(self):
        code = 'function f(xs: list[int]) { return xs }\nf([1, "bad"])'
        with pytest.raises(TypeViolationFault):
            val(code)

    # ── return type ──
    def test_list_return_type(self):
        code = "function f() -> list[int] { return [1, 2] }\nf()"
        assert val(code) == [1, 2]

    def test_list_return_type_wrong_raises(self):
        code = 'function f() -> list[int] { return [1, "x"] }\nf()'
        with pytest.raises(TypeViolationFault):
            val(code)

    # ── nested generics ──
    def test_list_of_lists(self):
        assert env("m: list[list] = [[1], [2]]", "m") == [[1], [2]]

    # ── const ──
    def test_const_list_int(self):
        assert env("const ITEMS: list[int] = [10, 20]", "ITEMS") == [10, 20]

    # ── reassignment ──
    def test_reassign_valid(self):
        assert env("xs: list[int] = [1]\nxs = [2, 3]", "xs") == [2, 3]

    def test_reassign_wrong_raises(self):
        with pytest.raises(TypeViolationFault):
            val('xs: list[int] = [1]\nxs = ["bad"]')


class TestNullableTypes:
    # ── basic nullable declarations ──
    def test_nullable_string_with_null(self):
        assert env('name: string? = null', 'name') is None

    def test_nullable_int_with_null(self):
        assert env('x: int? = null', 'x') is None

    def test_nullable_int_with_value(self):
        assert env('x: int? = 42', 'x') == 42

    def test_nullable_string_with_value(self):
        assert env('name: string? = "Alice"', 'name') == "Alice"

    # ── non-nullable rejects null ──
    def test_non_nullable_int_rejects_null(self):
        with pytest.raises(TypeViolationFault):
            val('x: int = null')

    def test_non_nullable_string_rejects_null(self):
        with pytest.raises(TypeViolationFault):
            val('x: string = null')

    # ── reassignment ──
    def test_nullable_reassign_to_null(self):
        assert env('x: int? = 5\nx = null', 'x') is None

    def test_nullable_reassign_to_value(self):
        assert env('x: int? = null\nx = 7', 'x') == 7

    # ── generic nullable ──
    def test_nullable_list_with_null(self):
        assert env('items: list? = null', 'items') is None

    def test_nullable_generic_list_with_null(self):
        assert env('items: list[int]? = null', 'items') is None

    def test_nullable_generic_list_with_value(self):
        assert env('items: list[int]? = [1, 2]', 'items') == [1, 2]


class TestTypeInference:
    """Type checker propagates inferred types through calls and arithmetic."""

    @staticmethod
    def tc(code):
        from luz.typechecker import TypeChecker
        tokens = Lexer(code).get_tokens()
        ast = Parser(tokens).parse()
        return TypeChecker().check(ast)

    # ── function call return type propagates ──
    def test_call_result_used_in_bad_binop_caught(self):
        code = 'function f(x: int) -> int { return x }\nresult = f(5)\nwrite(result + "x")'
        assert self.tc(code)  # should have at least one error

    def test_call_result_used_in_good_binop_clean(self):
        code = 'function f(x: int) -> int { return x }\nresult = f(5)\nwrite(result + 1)'
        assert not self.tc(code)

    # ── assignment propagates inferred type ──
    def test_assign_int_literal_propagates(self):
        code = 'x = 5\nwrite(x + "bad")'
        assert self.tc(code)

    def test_assign_binop_propagates(self):
        code = 'x: int = 5\ny = x * 3\nwrite(y + "bad")'
        assert self.tc(code)

    # ── arithmetic type rules ──
    def test_int_plus_float_gives_float(self):
        code = 'x: int = 5\ny = x + 3.0\nwrite(y + "bad")'
        assert self.tc(code)  # y should be float, float+"bad" is error

    def test_int_plus_int_gives_int(self):
        code = 'x: int = 5\ny = x + 3\nwrite(y + "bad")'
        assert self.tc(code)  # y should be int, int+"bad" is error

    def test_int_div_int_gives_float(self):
        code = 'x: int = 10\ny = x / 2\nwrite(y + "bad")'
        assert self.tc(code)

    def test_int_minus_float_gives_float(self):
        code = 'x: float = 5.0\ny = x - 1\nwrite(y + "bad")'
        assert self.tc(code)

    def test_clean_arithmetic_no_errors(self):
        code = 'x: int = 5\ny = x + 3\nz = y * 2'
        assert not self.tc(code)


class TestClassAttrTypeTracking:
    """Type checker infers class attribute types from init and propagates through attr access."""

    @staticmethod
    def tc(code):
        from luz.typechecker import TypeChecker
        tokens = Lexer(code).get_tokens()
        ast = Parser(tokens).parse()
        return TypeChecker().check(ast)

    _POINT = '''
class Point {
    function init(self, x: int, y: int) {
        self.x = x
        self.y = y
    }
}
'''

    def test_attr_bad_binop_caught(self):
        code = self._POINT + 'p = Point(1, 2)\nwrite(p.x + "hello")'
        assert self.tc(code)

    def test_attr_good_binop_clean(self):
        code = self._POINT + 'p = Point(1, 2)\nresult = p.x + p.y'
        assert not self.tc(code)

    def test_attr_from_literal_string(self):
        code = '''
class Config {
    function init(self) {
        self.name = "default"
        self.count = 0
    }
}
c = Config()
write(c.name + 1)
'''
        assert self.tc(code)

    def test_attr_from_literal_int_clean(self):
        code = '''
class Counter {
    function init(self) {
        self.n = 0
    }
}
c = Counter()
result = c.n + 1
'''
        assert not self.tc(code)

    def test_constructor_result_type_propagates_through_alias(self):
        # q = p also carries the 'Point' type, so q.x + "bad" is caught too
        code = self._POINT + 'p = Point(1, 2)\nq = p\nwrite(q.x + "bad")'
        assert self.tc(code)


class TestDictDotMethods:
    def test_keys(self):
        assert val('keys({"a": 1, "b": 2})') == val('{"a": 1, "b": 2}.keys()')

    def test_values(self):
        assert val('values({"a": 1, "b": 2})') == val('{"a": 1, "b": 2}.values()')

    def test_len(self):
        assert val('{"a": 1, "b": 2}.len()') == 2

    def test_len_empty(self):
        assert val('{}.len()') == 0

    def test_contains_true(self):
        assert val('{"a": 1}.contains("a")') == True

    def test_contains_false(self):
        assert val('{"a": 1}.contains("z")') == False

    def test_remove(self):
        assert val('d = {"a": 1, "b": 2}\nd.remove("a")\nd.len()') == 1

    def test_remove_key_gone(self):
        assert val('d = {"a": 1, "b": 2}\nd.remove("b")\nd.keys()') == ["a"]

    def test_invalid_method(self):
        with pytest.raises(InvalidUsageFault):
            val('{"a": 1}.nope()')

    def test_chained_keys_len(self):
        assert val('{"x": 1, "y": 2, "z": 3}.keys().len()') == 3

    def test_contains_missing_arg_raises(self):
        with pytest.raises(ArityFault):
            val('{"a": 1}.contains()')

    def test_remove_missing_arg_raises(self):
        with pytest.raises(ArityFault):
            val('{"a": 1}.remove()')


class TestSlices:
    def test_list_basic(self):
        assert val('[1, 2, 3, 4, 5][1:3]') == [2, 3]

    def test_list_from_start(self):
        assert val('[1, 2, 3, 4, 5][:3]') == [1, 2, 3]

    def test_list_to_end(self):
        assert val('[1, 2, 3, 4, 5][2:]') == [3, 4, 5]

    def test_list_step(self):
        assert val('[1, 2, 3, 4, 5][::2]') == [1, 3, 5]

    def test_list_step_with_range(self):
        assert val('[1, 2, 3, 4, 5][1:4:2]') == [2, 4]

    def test_list_negative_start(self):
        assert val('[1, 2, 3, 4, 5][-2:]') == [4, 5]

    def test_string_basic(self):
        assert val('"hello"[1:4]') == 'ell'

    def test_string_from_start(self):
        assert val('"hello"[:3]') == 'hel'

    def test_string_step(self):
        assert val('"hello"[::2]') == 'hlo'

    def test_full_copy(self):
        assert val('[1, 2, 3][:]') == [1, 2, 3]

    def test_step_zero_raises(self):
        with pytest.raises(ZeroDivisionFault):
            val('[1, 2, 3][::0]')

    def test_invalid_type_raises(self):
        with pytest.raises(InvalidUsageFault):
            val('{"a": 1}[1:2]')

    def test_non_int_index_raises(self):
        with pytest.raises(TypeViolationFault):
            val('[1, 2, 3]["a":2]')


# ── clamp() low > high guard ──────────────────────────────────────────────────

class TestClampValidation:
    def test_clamp_normal(self):
        assert val("clamp(5, 1, 10)") == 5

    def test_clamp_below(self):
        assert val("clamp(-3, 0, 10)") == 0

    def test_clamp_above(self):
        assert val("clamp(15, 0, 10)") == 10

    def test_clamp_low_gt_high_raises(self):
        with pytest.raises(ArgumentFault):
            val("clamp(5, 10, 1)")

    def test_clamp_low_gt_high_negative(self):
        with pytest.raises(ArgumentFault):
            val("clamp(0, 3, -1)")


# ── list.sort() and list.reverse() dot methods ───────────────────────────────

class TestListDotSortReverse:
    def test_sort_basic(self):
        assert val('[3, 1, 2].sort()') is None

    def test_sort_mutates(self):
        interp = run('xs = [3, 1, 2]\nxs.sort()')
        assert interp.global_env.lookup("xs") == [1, 2, 3]

    def test_sort_strings(self):
        interp = run('xs = ["banana", "apple", "cherry"]\nxs.sort()')
        assert interp.global_env.lookup("xs") == ["apple", "banana", "cherry"]

    def test_sort_empty(self):
        interp = run('xs = []\nxs.sort()')
        assert interp.global_env.lookup("xs") == []

    def test_reverse_dot_method(self):
        assert val('[1, 2, 3].reverse()') is None

    def test_reverse_mutates(self):
        interp = run('xs = [1, 2, 3]\nxs.reverse()')
        assert interp.global_env.lookup("xs") == [3, 2, 1]

    def test_reverse_empty(self):
        interp = run('xs = []\nxs.reverse()')
        assert interp.global_env.lookup("xs") == []


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import subprocess
    result = subprocess.run(
        [sys.executable, "-m", "pytest", __file__, "-v"],
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    sys.exit(result.returncode)
