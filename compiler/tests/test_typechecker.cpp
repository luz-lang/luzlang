#include "test_runner.hpp"

#include "luz/lexer.hpp"
#include "luz/parser.hpp"
#include "luz/typechecker.hpp"

using namespace luz;

// ── helpers ──────────────────────────────────────────────────────────────────

static std::vector<TypeCheckError> check(const std::string& src) {
    return type_check(parse(lex(src)));
}

static bool has_error(const std::vector<TypeCheckError>& errors,
                      const std::string& substring) {
    for (const auto& e : errors) {
        if (e.message.find(substring) != std::string::npos)
            return true;
    }
    return false;
}

// ── clean programs ────────────────────────────────────────────────────────────

TEST_CASE("TypeChecker: empty program") {
    CHECK(check("").empty());
}

TEST_CASE("TypeChecker: int assignment") {
    CHECK(check("x: int = 5").empty());
}

TEST_CASE("TypeChecker: float assignment") {
    CHECK(check("x: float = 3.14").empty());
}

TEST_CASE("TypeChecker: string assignment") {
    CHECK(check("x: string = \"hello\"").empty());
}

TEST_CASE("TypeChecker: bool assignment") {
    CHECK(check("x: bool = true").empty());
}

TEST_CASE("TypeChecker: const declaration") {
    CHECK(check("const PI: float = 3.14").empty());
}

TEST_CASE("TypeChecker: function definition") {
    CHECK(check("function add(a: int, b: int) -> int { return a + b }").empty());
}

TEST_CASE("TypeChecker: used variable") {
    CHECK(check("x = 5\nwrite(x)").empty());
}

// ── type mismatch ─────────────────────────────────────────────────────────────

TEST_CASE("TypeChecker: int annotated with string value is an error") {
    auto errors = check("x: int = \"hello\"");
    CHECK_FALSE(errors.empty());
    CHECK(has_error(errors, "int"));
}

TEST_CASE("TypeChecker: float annotated with bool is an error") {
    auto errors = check("x: float = true");
    CHECK_FALSE(errors.empty());
}

TEST_CASE("TypeChecker: string annotated with bool is an error") {
    auto errors = check("x: string = false");
    CHECK_FALSE(errors.empty());
}

// ── const reassignment ────────────────────────────────────────────────────────

TEST_CASE("TypeChecker: const reassignment is an error") {
    auto errors = check("const X = 1\nX = 2");
    CHECK_FALSE(errors.empty());
    CHECK((has_error(errors, "X") || has_error(errors, "const")));
}

// ── undefined variable ────────────────────────────────────────────────────────

TEST_CASE("TypeChecker: undefined variable inside function is an error") {
    // Undefined variable checks only trigger at fn_depth > 0.
    auto errors = check("function f() { write(undeclared) }");
    CHECK_FALSE(errors.empty());
    CHECK((has_error(errors, "undeclared") || has_error(errors, "undefined")));
}

// ── wrong arity ───────────────────────────────────────────────────────────────

TEST_CASE("TypeChecker: too few arguments is an error") {
    auto errors = check("function f(a: int, b: int) { pass }\nf(1)");
    CHECK_FALSE(errors.empty());
    CHECK((has_error(errors, "argument") || has_error(errors, "arity") || has_error(errors, "f")));
}

TEST_CASE("TypeChecker: too many arguments is an error") {
    auto errors = check("function f(a: int) { pass }\nf(1, 2, 3)");
    CHECK_FALSE(errors.empty());
}

TEST_CASE("TypeChecker: correct arity is clean") {
    // Use params in the body to avoid unused-param warnings.
    CHECK(check("function f(a: int, b: int) -> int { return a + b }\nf(1, 2)").empty());
}

// ── unused variables ─────────────────────────────────────────────────────────

TEST_CASE("TypeChecker: unused local variable inside function is an error") {
    // Global untyped assigns are not tracked; locals inside functions are.
    auto errors = check("function f() { x = 42 }");
    CHECK_FALSE(errors.empty());
    CHECK((has_error(errors, "x") || has_error(errors, "unused")));
}

TEST_CASE("TypeChecker: unused import alias is an error") {
    // 'import "math"' with no alias creates no binding.
    // 'import "math" as m' creates alias 'm' which is tracked.
    auto errors = check("import \"math\" as m");
    CHECK_FALSE(errors.empty());
    CHECK((has_error(errors, "m") || has_error(errors, "unused")));
}

// ── nullable types ────────────────────────────────────────────────────────────

TEST_CASE("TypeChecker: nullable type assigned null is clean") {
    CHECK(check("x: int? = null").empty());
}

TEST_CASE("TypeChecker: nullable type assigned value is clean") {
    CHECK(check("x: int? = 5").empty());
}

// ── return type checking ──────────────────────────────────────────────────────

TEST_CASE("TypeChecker: return type mismatch is an error") {
    auto errors = check("function f() -> int { return \"oops\" }");
    CHECK_FALSE(errors.empty());
}

TEST_CASE("TypeChecker: matching return type is clean") {
    CHECK(check("function f() -> int { return 42 }").empty());
}

// ── builtin calls ─────────────────────────────────────────────────────────────

TEST_CASE("TypeChecker: write builtin accepts any value") {
    CHECK(check("write(\"hello\")").empty());
    CHECK(check("write(42)").empty());
}

TEST_CASE("TypeChecker: len builtin on list") {
    CHECK(check("x = [1, 2, 3]\nlen(x)").empty());
}

// ── multiple errors ───────────────────────────────────────────────────────────

TEST_CASE("TypeChecker: collects multiple errors") {
    auto errors = check("a: int = \"bad\"\nb: float = true");
    CHECK(errors.size() >= 2);
}
