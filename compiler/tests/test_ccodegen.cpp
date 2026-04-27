// test_ccodegen.cpp — C source emitter coverage for the inferred return-type
// path (issue #99 and similar). The LLVM IR pipeline already has its own
// e2e coverage; this file exercises ccodegen specifically.

#include "test_runner.hpp"

#include "luz/ccodegen.hpp"
#include "luz/hir.hpp"
#include "luz/lexer.hpp"
#include "luz/parser.hpp"

#include <sstream>
#include <string>

namespace {

std::string emit_c_source(const std::string& source) {
    auto tokens  = luz::lex(source);
    auto program = luz::parse(tokens);
    auto hir     = luz::lower_to_hir(program);
    std::ostringstream out;
    luz::emit_c(out, hir, "test.luz");
    return out.str();
}

bool contains(const std::string& haystack, const std::string& needle) {
    return haystack.find(needle) != std::string::npos;
}

}  // namespace

// Regression test for #99 — `scan_return_type` used to hardcode the
// forward-declared return type for any function whose body returned a
// `BinOp` to `long long`, regardless of the actual operand types. A
// function returning `(a + b) / 2.0` therefore got declared as
// `long long average(double, double)` and silently truncated the
// result to an int. The fix delegates to `infer_type` so the HIR's
// type tag drives the declaration.
TEST_CASE("ccodegen: float-returning function with no explicit return type emits double") {
    const auto c_src = emit_c_source(
        "function average(a: float, b: float) {\n"
        "    return (a + b) / 2.0\n"
        "}\n"
        "write(average(1.0, 2.0))\n");

    // Must NOT advertise a long long return — that's the #99 truncation.
    CHECK(!contains(c_src, "long long average"));
    // Must declare and define the function as returning double.
    CHECK(contains(c_src, "double average("));
}

// Sanity: the bug was return-type specific. Int-returning binop
// functions must still come out as `long long`.
TEST_CASE("ccodegen: int-returning function with no explicit return type still emits long long") {
    const auto c_src = emit_c_source(
        "function add(a: int, b: int) {\n"
        "    return a + b\n"
        "}\n"
        "write(add(1, 2))\n");

    CHECK(contains(c_src, "long long add("));
    CHECK(!contains(c_src, "double add("));
}

// String concatenation also returns char* via the BinOp path. The
// pre-fix code would have mis-typed this as `long long` too.
TEST_CASE("ccodegen: string-concat function with no explicit return type emits char*") {
    const auto c_src = emit_c_source(
        "function greet(who: string) {\n"
        "    return \"hello, \" + who\n"
        "}\n"
        "write(greet(\"world\"))\n");

    CHECK(contains(c_src, "char* greet("));
    CHECK(!contains(c_src, "long long greet"));
}
