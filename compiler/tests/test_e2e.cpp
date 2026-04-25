// test_e2e.cpp — End-to-end compiler pipeline tests.
//
// Each test runs a complete .luz program through the full pipeline:
//   lex → parse → typecheck → HIR lower → LLVM IR emission
//
// IR correctness is verified via substring checks on the emitted text.
// Execution tests (compile + run) are conditionally run when clang is available.

#include "test_runner.hpp"

#include "luz/codegen.hpp"
#include "luz/diagnostics.hpp"
#include "luz/hir.hpp"
#include "luz/lexer.hpp"
#include "luz/parser.hpp"
#include "luz/typechecker.hpp"

#include <sstream>
#include <string>
#include <vector>

// ── Helpers ───────────────────────────────────────────────────────────────────

static std::string emit_ir(const std::string& source) {
    auto tokens  = luz::lex(source);
    auto program = luz::parse(tokens);
    auto hir     = luz::lower_to_hir(program);
    std::ostringstream out;
    luz::emit_llvm_ir(out, hir, "test.luz");
    return out.str();
}

static bool has(const std::string& ir, const std::string& needle) {
    return ir.find(needle) != std::string::npos;
}

static std::vector<luz::TypeCheckError> check_errors(const std::string& source) {
    auto tokens  = luz::lex(source);
    auto program = luz::parse(tokens);
    return luz::type_check(program);
}

static bool parse_ok(const std::string& source) {
    try { luz::parse(luz::lex(source)); return true; }
    catch (...) { return false; }
}

// ── Parse errors ─────────────────────────────────────────────────────────────

TEST_CASE("e2e: parse error on invalid syntax") {
    CHECK_FALSE(parse_ok("function foo( {"));
    CHECK_FALSE(parse_ok("if x == {"));
    CHECK_FALSE(parse_ok("write("));
}

TEST_CASE("e2e: parse succeeds on valid programs") {
    CHECK(parse_ok("write(42)"));
    CHECK(parse_ok("x: int = 1\nwrite(x)"));
    CHECK(parse_ok("function f() -> int { return 1 }"));
}

// ── Type errors ───────────────────────────────────────────────────────────────

TEST_CASE("e2e: type error int assigned string") {
    auto errs = check_errors("x: int = \"hello\"");
    REQUIRE_FALSE(errs.empty());
    CHECK(errs[0].message.find("int") != std::string::npos);
}

TEST_CASE("e2e: type error float assigned bool") {
    auto errs = check_errors("x: float = true");
    REQUIRE_FALSE(errs.empty());
}

TEST_CASE("e2e: type error const reassignment") {
    auto errs = check_errors("const X: int = 1\nX = 2");
    REQUIRE_FALSE(errs.empty());
}

TEST_CASE("e2e: type error wrong arity") {
    auto errs = check_errors(
        "function f(a: int, b: int) -> int { return a + b }\nf(1)");
    REQUIRE_FALSE(errs.empty());
}

TEST_CASE("e2e: no type errors on clean program") {
    auto errs = check_errors(
        "function add(a: int, b: int) -> int { return a + b }\nwrite(add(1, 2))");
    CHECK(errs.empty());
}

// ── IR: scalars and basic expressions ─────────────────────────────────────────

TEST_CASE("e2e: int literal emits i64") {
    auto ir = emit_ir("write(42)");
    CHECK(has(ir, "i64 42"));
}

TEST_CASE("e2e: float literal emits double") {
    auto ir = emit_ir("write(3.14)");
    CHECK(has(ir, "double 3.14"));
}

TEST_CASE("e2e: bool true emits i1 1") {
    auto ir = emit_ir("write(true)");
    CHECK(has(ir, "i1 1"));
}

TEST_CASE("e2e: bool false emits i1 0") {
    auto ir = emit_ir("write(false)");
    CHECK(has(ir, "i1 0"));
}

TEST_CASE("e2e: string literal creates global constant") {
    auto ir = emit_ir("write(\"hello\")");
    CHECK(has(ir, "c\"hello\\00\""));
    CHECK(has(ir, "@printf"));
}

TEST_CASE("e2e: arithmetic int add") {
    auto ir = emit_ir("x: int = 1\ny: int = 2\nwrite(x + y)");
    CHECK(has(ir, "add i64"));
}

TEST_CASE("e2e: arithmetic int mul") {
    auto ir = emit_ir("x: int = 3\ny: int = 4\nwrite(x * y)");
    CHECK(has(ir, "mul i64"));
}

TEST_CASE("e2e: constant folding int") {
    auto ir = emit_ir("write(2 + 3)");
    // HIR constant-folds 2+3 → 5, so the IR should have literal 5
    CHECK(has(ir, "i64 5"));
}

TEST_CASE("e2e: comparison emits icmp") {
    auto ir = emit_ir("x: int = 5\nwrite(x > 3)");
    CHECK(has(ir, "icmp sgt i64"));
}

TEST_CASE("e2e: float comparison emits fcmp") {
    auto ir = emit_ir("x: float = 1.5\nwrite(x < 2.0)");
    CHECK(has(ir, "fcmp olt double"));
}

// ── IR: variables ─────────────────────────────────────────────────────────────

TEST_CASE("e2e: typed int variable uses alloca/store/load") {
    auto ir = emit_ir("x: int = 10\nwrite(x)");
    CHECK(has(ir, "alloca i64"));
    CHECK(has(ir, "store i64 10"));
    CHECK(has(ir, "load i64"));
}

TEST_CASE("e2e: typed float variable") {
    auto ir = emit_ir("f: float = 2.5\nwrite(f)");
    CHECK(has(ir, "alloca double"));
    CHECK(has(ir, "store double 2.5"));
}

TEST_CASE("e2e: typed string variable") {
    auto ir = emit_ir("s: string = \"world\"\nwrite(s)");
    CHECK(has(ir, "alloca i8*"));
    CHECK(has(ir, "c\"world\\00\""));
}

TEST_CASE("e2e: typed bool variable") {
    auto ir = emit_ir("b: bool = true\nwrite(b)");
    CHECK(has(ir, "alloca i1"));
}

// ── IR: control flow ──────────────────────────────────────────────────────────

TEST_CASE("e2e: if emits conditional branch") {
    auto ir = emit_ir("x: int = 5\nif x > 3 { write(1) }");
    CHECK(has(ir, "br i1"));
    CHECK(has(ir, "if_then"));
    CHECK(has(ir, "if_after"));
}

TEST_CASE("e2e: if/else emits both branches") {
    auto ir = emit_ir("x: int = 5\nif x > 3 { write(1) } else { write(0) }");
    CHECK(has(ir, "if_then"));
    CHECK(has(ir, "if_else"));
    CHECK(has(ir, "if_after"));
}

TEST_CASE("e2e: while loop emits loop labels") {
    auto ir = emit_ir("i: int = 0\nwhile i < 10 { i = i + 1 }");
    CHECK(has(ir, "lp_cond"));
    CHECK(has(ir, "lp_body"));
    CHECK(has(ir, "lp_exit"));
}

TEST_CASE("e2e: for loop desugars to while") {
    auto ir = emit_ir("for i = 0 to 5 { write(i) }");
    CHECK(has(ir, "lp_cond"));
    CHECK(has(ir, "lp_body"));
}

TEST_CASE("e2e: break emits unconditional branch") {
    auto ir = emit_ir("while true { break }");
    CHECK(has(ir, "lp_exit"));
}

TEST_CASE("e2e: return emits ret") {
    auto ir = emit_ir("function f() -> int { return 42 }");
    CHECK(has(ir, "ret i64 42"));
}

// ── IR: functions ─────────────────────────────────────────────────────────────

TEST_CASE("e2e: function def emits define") {
    auto ir = emit_ir("function add(a: int, b: int) -> int { return a + b }");
    CHECK(has(ir, "define i64 @add(i64 %a.in, i64 %b.in)"));
}

TEST_CASE("e2e: function call emits call instruction") {
    auto ir = emit_ir(
        "function double(x: int) -> int { return x * 2 }\n"
        "write(double(5))");
    CHECK(has(ir, "call i64 @double"));
    CHECK(has(ir, "i64 5"));
}

TEST_CASE("e2e: recursive function") {
    auto ir = emit_ir(
        "function fib(n: int) -> int {\n"
        "    if n <= 1 { return n }\n"
        "    return fib(n - 1) + fib(n - 2)\n"
        "}");
    CHECK(has(ir, "define i64 @fib"));
    CHECK(has(ir, "call i64 @fib"));
    CHECK(has(ir, "icmp sle i64"));
}

TEST_CASE("e2e: function params spilled to alloca") {
    auto ir = emit_ir("function f(x: int) -> int { return x }");
    CHECK(has(ir, "%x.addr = alloca i64"));
    CHECK(has(ir, "store i64 %x.in, i64* %x.addr"));
}

// ── IR: strings ───────────────────────────────────────────────────────────────

TEST_CASE("e2e: string concatenation uses luz_str_concat") {
    auto ir = emit_ir("a: string = \"hi\"\nb: string = \" there\"\nwrite(a + b)");
    CHECK(has(ir, "luz_str_concat"));
}

TEST_CASE("e2e: f-string uses to_str and concat") {
    auto ir = emit_ir("x: int = 7\nwrite($\"value is {x}\")");
    CHECK(has(ir, "luz_to_str_int"));
    CHECK(has(ir, "luz_str_concat"));
}

TEST_CASE("e2e: f-string with float") {
    auto ir = emit_ir("f: float = 1.5\nwrite($\"f={f}\")");
    CHECK(has(ir, "luz_to_str_float"));
}

TEST_CASE("e2e: f-string with bool") {
    auto ir = emit_ir("b: bool = true\nwrite($\"b={b}\")");
    CHECK(has(ir, "luz_to_str_bool"));
}

TEST_CASE("e2e: string equality uses luz_str_eq") {
    auto ir = emit_ir("a: string = \"x\"\nwrite(a == \"x\")");
    CHECK(has(ir, "luz_str_eq"));
}

TEST_CASE("e2e: string len uses luz_str_len") {
    auto ir = emit_ir("s: string = \"hello\"\nwrite(s.len())");
    CHECK(has(ir, "luz_str_len"));
}

TEST_CASE("e2e: string contains uses luz_str_contains") {
    auto ir = emit_ir("s: string = \"hello world\"\nwrite(s.contains(\"world\"))");
    CHECK(has(ir, "luz_str_contains"));
}

// ── IR: dicts ─────────────────────────────────────────────────────────────────

TEST_CASE("e2e: dict literal creates new dict and sets entries") {
    auto ir = emit_ir("d: dict = {\"a\": 1, \"b\": 2}");
    CHECK(has(ir, "luz_dict_new"));
    CHECK(has(ir, "luz_dict_set_int"));
}

TEST_CASE("e2e: dict index read uses luz_dict_get") {
    auto ir = emit_ir("d: dict = {\"x\": 42}\nwrite(d[\"x\"])");
    CHECK(has(ir, "luz_dict_get_int"));
}

TEST_CASE("e2e: dict index store uses luz_dict_set") {
    auto ir = emit_ir("d: dict = {}\nd[\"k\"] = 99");
    CHECK(has(ir, "luz_dict_set_int"));
}

TEST_CASE("e2e: dict len uses luz_dict_len") {
    auto ir = emit_ir("d: dict = {\"a\": 1}\nwrite(d.len())");
    CHECK(has(ir, "luz_dict_len"));
}

TEST_CASE("e2e: dict contains uses luz_dict_contains") {
    auto ir = emit_ir("d: dict = {\"a\": 1}\nwrite(d.contains(\"a\"))");
    CHECK(has(ir, "luz_dict_contains"));
}

TEST_CASE("e2e: dict remove uses luz_dict_remove") {
    auto ir = emit_ir("d: dict = {\"a\": 1}\nd.remove(\"a\")");
    CHECK(has(ir, "luz_dict_remove"));
}

// ── IR: classes ───────────────────────────────────────────────────────────────

TEST_CASE("e2e: class method emits LLVM function") {
    auto ir = emit_ir(
        "class Counter {\n"
        "    function init(n: int) { self.n = n }\n"
        "    function get() -> int { return self.n }\n"
        "}");
    CHECK(has(ir, "define void @Counter__init"));
    CHECK(has(ir, "define i64 @Counter__get"));
}

TEST_CASE("e2e: class constructor creates dict and calls init") {
    auto ir = emit_ir(
        "class Point {\n"
        "    function init(x: int, y: int) { self.x = x\nself.y = y }\n"
        "}\n"
        "p: Point = Point(1, 2)");
    CHECK(has(ir, "luz_dict_new"));
    CHECK(has(ir, "call void @Point__init"));
    CHECK(has(ir, "%p.addr = alloca i8*"));
}

TEST_CASE("e2e: class field store uses dict_set") {
    auto ir = emit_ir(
        "class Box {\n"
        "    function init(v: int) { self.v = v }\n"
        "}");
    CHECK(has(ir, "luz_dict_set_int"));
}

TEST_CASE("e2e: class field load uses dict_get") {
    auto ir = emit_ir(
        "class Box {\n"
        "    function init(v: int) { self.v = v }\n"
        "    function get() -> int { return self.v }\n"
        "}");
    CHECK(has(ir, "luz_dict_get_int"));
}

TEST_CASE("e2e: method call dispatches to correct function") {
    auto ir = emit_ir(
        "class Dog {\n"
        "    function init(name: string) { self.name = name }\n"
        "    function speak() { write(self.name) }\n"
        "}\n"
        "d: Dog = Dog(\"Rex\")\n"
        "d.speak()");
    CHECK(has(ir, "call void @Dog__speak"));
}

TEST_CASE("e2e: inheritance dispatches overridden method to child class") {
    auto ir = emit_ir(
        "class Animal {\n"
        "    function init(name: string) { self.name = name }\n"
        "    function speak() { write(self.name) }\n"
        "}\n"
        "class Dog extends Animal {\n"
        "    function speak() { write(\"Woof\") }\n"
        "}\n"
        "d: Dog = Dog(\"Rex\")\n"
        "d.speak()");
    CHECK(has(ir, "call void @Dog__speak"));
    CHECK_FALSE(has(ir, "call void @Animal__speak(i8* %"));
}

TEST_CASE("e2e: inheritance uses parent method when not overridden") {
    auto ir = emit_ir(
        "class Animal {\n"
        "    function init(name: string) { self.name = name }\n"
        "    function get_name() -> string { return self.name }\n"
        "}\n"
        "class Dog extends Animal {}\n"
        "d: Dog = Dog(\"Rex\")\n"
        "write(d.get_name())");
    CHECK(has(ir, "call i8* @Animal__get_name"));
}

// ── IR: structs ───────────────────────────────────────────────────────────────

TEST_CASE("e2e: struct definition registers field types") {
    // Struct with int and float fields — codegen must use correct typed getters
    auto ir = emit_ir(
        "struct Vec2 { x: float\ny: float }\n"
        "v: Vec2 = Vec2{x: 1.0, y: 2.0}\n"
        "write(v.x)");
    CHECK(has(ir, "luz_dict_set_float"));
    CHECK(has(ir, "luz_dict_get_float"));
    CHECK(has(ir, "%v.addr = alloca i8*"));
}

TEST_CASE("e2e: struct field update uses dict_set") {
    auto ir = emit_ir(
        "struct Point { x: float\ny: float }\n"
        "p: Point = Point{x: 0.0, y: 0.0}\n"
        "p.x = 5.0");
    CHECK(has(ir, "luz_dict_set_float"));
}

TEST_CASE("e2e: struct with mixed field types") {
    auto ir = emit_ir(
        "struct Person { name: string\nage: int\nactive: bool }\n"
        "p: Person = Person{name: \"Ana\", age: 25, active: true}\n"
        "write(p.name)\nwrite(p.age)\nwrite(p.active)");
    CHECK(has(ir, "luz_dict_set_str"));
    CHECK(has(ir, "luz_dict_set_int"));
    CHECK(has(ir, "luz_dict_set_bool"));
    CHECK(has(ir, "luz_dict_get_str"));
    CHECK(has(ir, "luz_dict_get_int"));
    CHECK(has(ir, "luz_dict_get_bool"));
}

// ── IR: lambdas ───────────────────────────────────────────────────────────────

TEST_CASE("e2e: lambda assign emits named function") {
    auto ir = emit_ir("add = fn(a: int, b: int) => a + b");
    CHECK(has(ir, "define i64 @add"));
    CHECK(has(ir, "add i64"));
}

TEST_CASE("e2e: lambda call dispatches by variable name") {
    auto ir = emit_ir(
        "double = fn(x: int) => x * 2\n"
        "write(double(5))");
    CHECK(has(ir, "define i64 @double"));
    CHECK(has(ir, "call i64 @double"));
}

TEST_CASE("e2e: multiple lambdas emit separate functions") {
    auto ir = emit_ir(
        "square = fn(x: int) => x * x\n"
        "cube   = fn(x: int) => x * x * x\n"
        "write(square(3))\nwrite(cube(2))");
    CHECK(has(ir, "define i64 @square"));
    CHECK(has(ir, "define i64 @cube"));
}

// ── IR: attempt / rescue ──────────────────────────────────────────────────────

TEST_CASE("e2e: attempt emits setjmp pattern") {
    auto ir = emit_ir(
        "attempt {\n"
        "    write(1)\n"
        "} rescue {\n"
        "    write(0)\n"
        "} finally {\n"
        "    write(2)\n"
        "}");
    CHECK(has(ir, "alloca [512 x i8]"));
    CHECK(has(ir, "call void @luz_push_rescue_ptr"));
    CHECK(has(ir, "call i32 @setjmp"));
    CHECK(has(ir, "try_body"));
    CHECK(has(ir, "rescue_block"));
    CHECK(has(ir, "try_finally"));
}

TEST_CASE("e2e: alert calls luz_alert_throw") {
    auto ir = emit_ir("alert(\"oops\")");
    CHECK(has(ir, "call void @luz_alert_throw"));
    CHECK(has(ir, "unreachable"));
}

TEST_CASE("e2e: attempt with alert — try block has throw, rescue has handler") {
    auto ir = emit_ir(
        "attempt {\n"
        "    alert(\"boom\")\n"
        "} rescue {\n"
        "    write(\"caught\")\n"
        "}");
    CHECK(has(ir, "luz_alert_throw"));
    CHECK(has(ir, "try_body"));
    CHECK(has(ir, "rescue_block"));
}

// ── IR: switch / match (desugared by HIR) ────────────────────────────────────

TEST_CASE("e2e: switch desugars to if chain") {
    auto ir = emit_ir(
        "x: int = 2\n"
        "switch x {\n"
        "    case 1 { write(1) }\n"
        "    case 2 { write(2) }\n"
        "}");
    CHECK(has(ir, "icmp eq i64"));
    CHECK(has(ir, "if_then"));
}

TEST_CASE("e2e: match desugars to if chain") {
    auto ir = emit_ir(
        "x: int = 3\n"
        "y = match x {\n"
        "    1 => 10\n"
        "    3 => 30\n"
        "    _ => 0\n"
        "}");
    CHECK(has(ir, "icmp eq i64"));
}

// ── IR: write() builtin ───────────────────────────────────────────────────────

TEST_CASE("e2e: write int calls printf with int format") {
    auto ir = emit_ir("write(42)");
    CHECK(has(ir, "@.fmt.int"));
    CHECK(has(ir, "@printf"));
}

TEST_CASE("e2e: write float calls printf with float format") {
    auto ir = emit_ir("write(3.14)");
    CHECK(has(ir, "@.fmt.float"));
}

TEST_CASE("e2e: write string calls printf with string format") {
    auto ir = emit_ir("write(\"hello\")");
    CHECK(has(ir, "@.fmt.str"));
}

TEST_CASE("e2e: write bool branches on true/false format strings") {
    auto ir = emit_ir("write(true)");
    CHECK(has(ir, "@.fmt.true"));
    CHECK(has(ir, "@.fmt.false"));
    CHECK(has(ir, "br i1"));
}

// ── IR: real example programs ─────────────────────────────────────────────────

TEST_CASE("e2e: fizzbuzz compiles to IR") {
    const std::string fizzbuzz =
        "for i = 1 to 20 {\n"
        "    if i % 15 == 0 { write(\"FizzBuzz\") }\n"
        "    elif i % 3 == 0 { write(\"Fizz\") }\n"
        "    elif i % 5 == 0 { write(\"Buzz\") }\n"
        "    else { write(i) }\n"
        "}";
    auto ir = emit_ir(fizzbuzz);
    CHECK(has(ir, "srem i64"));    // i % 15
    CHECK(has(ir, "lp_cond"));     // loop
    CHECK(has(ir, "if_then"));     // if branch
    CHECK(has(ir, "c\"FizzBuzz\\00\""));
}

TEST_CASE("e2e: fibonacci compiles to IR with recursion") {
    const std::string fib =
        "function fib(n: int) -> int {\n"
        "    if n <= 1 { return n }\n"
        "    return fib(n - 1) + fib(n - 2)\n"
        "}\n"
        "write(fib(10))";
    auto ir = emit_ir(fib);
    CHECK(has(ir, "define i64 @fib"));
    CHECK(has(ir, "call i64 @fib"));   // recursive call
    CHECK(has(ir, "icmp sle i64"));
    CHECK(has(ir, "i64 10"));          // fib(10) argument
}

TEST_CASE("e2e: class with inheritance compiles to IR") {
    const std::string prog =
        "class Animal {\n"
        "    function init(name: string) { self.name = name }\n"
        "    function speak() { write(self.name) }\n"
        "}\n"
        "class Dog extends Animal {\n"
        "    function speak() { write(\"Woof\") }\n"
        "}\n"
        "a: Animal = Animal(\"Cat\")\n"
        "a.speak()\n"
        "d: Dog = Dog(\"Rex\")\n"
        "d.speak()";
    auto ir = emit_ir(prog);
    CHECK(has(ir, "define void @Animal__init"));
    CHECK(has(ir, "define void @Animal__speak"));
    CHECK(has(ir, "define void @Dog__speak"));
    CHECK(has(ir, "call void @Animal__speak"));
    CHECK(has(ir, "call void @Dog__speak"));
}

TEST_CASE("e2e: struct with field access compiles to IR") {
    const std::string prog =
        "struct Point { x: float\ny: float }\n"
        "p: Point = Point{x: 3.0, y: 4.0}\n"
        "write(p.x)\n"
        "write(p.y)\n"
        "p.x = 0.0";
    auto ir = emit_ir(prog);
    CHECK(has(ir, "luz_dict_new"));
    CHECK(has(ir, "luz_dict_set_float"));
    CHECK(has(ir, "luz_dict_get_float"));
}

TEST_CASE("e2e: format strings with multiple types") {
    const std::string prog =
        "name: string = \"Luz\"\n"
        "version: int = 2\n"
        "stable: bool = false\n"
        "write($\"{name} v{version} stable={stable}\")";
    auto ir = emit_ir(prog);
    CHECK(has(ir, "luz_to_str_int"));
    CHECK(has(ir, "luz_to_str_bool"));
    CHECK(has(ir, "luz_str_concat"));
}

TEST_CASE("e2e: attempt rescue finally all present in IR") {
    const std::string prog =
        "function risky(x: int) -> int {\n"
        "    if x < 0 { alert(\"negative\") }\n"
        "    return x * 2\n"
        "}\n"
        "attempt {\n"
        "    write(risky(5))\n"
        "    write(risky(-1))\n"
        "} rescue {\n"
        "    write(\"error\")\n"
        "} finally {\n"
        "    write(\"done\")\n"
        "}";
    auto ir = emit_ir(prog);
    CHECK(has(ir, "define i64 @risky"));
    CHECK(has(ir, "luz_alert_throw"));
    CHECK(has(ir, "setjmp"));
    CHECK(has(ir, "try_body"));
    CHECK(has(ir, "rescue_block"));
    CHECK(has(ir, "try_finally"));
}
