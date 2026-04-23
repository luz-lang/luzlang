#include "test_runner.hpp"
#include <sstream>

#include "luz/hir.hpp"
#include "luz/lexer.hpp"
#include "luz/parser.hpp"

using namespace luz;

// ── helpers ──────────────────────────────────────────────────────────────────

static HirBlock lower(const std::string& src) {
    return lower_to_hir(parse(lex(src)));
}

static std::string hir_text(const std::string& src) {
    std::ostringstream ss;
    print_hir(ss, lower(src));
    return ss.str();
}

template<class T>
static const T* hir_as(const HirNode* n) {
    return dynamic_cast<const T*>(n);
}

// ── basic lowering ────────────────────────────────────────────────────────────

TEST_CASE("HIR: empty program produces empty block") {
    CHECK(lower("").empty());
}

TEST_CASE("HIR: int literal lowers to HirLiteral") {
    auto blk = lower("42");
    REQUIRE(blk.size() == 1);
    CHECK(blk[0]->kind == HirKind::Literal);
    auto* lit = hir_as<HirLiteral>(blk[0].get());
    REQUIRE(lit != nullptr);
    CHECK(lit->vk == HirLiteral::ValKind::Int);
    CHECK(lit->i  == 42);
}

TEST_CASE("HIR: string literal lowers correctly") {
    auto blk = lower("\"hello\"");
    REQUIRE(blk.size() == 1);
    auto* lit = hir_as<HirLiteral>(blk[0].get());
    REQUIRE(lit != nullptr);
    CHECK(lit->vk == HirLiteral::ValKind::String);
    CHECK(lit->s  == "hello");
}

TEST_CASE("HIR: untyped assignment lowers to HirAssign") {
    auto blk = lower("x = 5");
    REQUIRE(blk.size() == 1);
    CHECK(blk[0]->kind == HirKind::Assign);
    auto* a = hir_as<HirAssign>(blk[0].get());
    REQUIRE(a != nullptr);
    CHECK(a->name == "x");
}

TEST_CASE("HIR: typed assignment lowers to HirLet") {
    auto blk = lower("x: int = 10");
    REQUIRE(blk.size() == 1);
    CHECK(blk[0]->kind == HirKind::Let);
    auto* let = hir_as<HirLet>(blk[0].get());
    REQUIRE(let != nullptr);
    CHECK(let->name == "x");
    CHECK(let->type == "int");
}

TEST_CASE("HIR: function def lowers to HirFuncDef") {
    auto blk = lower("function add(a, b) { return a + b }");
    REQUIRE(blk.size() == 1);
    CHECK(blk[0]->kind == HirKind::FuncDef);
    auto* fd = hir_as<HirFuncDef>(blk[0].get());
    REQUIRE(fd != nullptr);
    CHECK(fd->name          == "add");
    CHECK(fd->params.size() == 2);
}

TEST_CASE("HIR: class def lowers to HirClassDef") {
    auto blk = lower("class Dog { }");
    REQUIRE(blk.size() == 1);
    CHECK(blk[0]->kind == HirKind::ClassDef);
}

// ── constant folding ──────────────────────────────────────────────────────────

TEST_CASE("HIR: folds int addition") {
    auto blk = lower("3 + 4");
    REQUIRE(blk.size() == 1);
    auto* lit = hir_as<HirLiteral>(blk[0].get());
    REQUIRE(lit != nullptr);
    CHECK(lit->vk == HirLiteral::ValKind::Int);
    CHECK(lit->i  == 7);
}

TEST_CASE("HIR: folds int subtraction") {
    auto blk = lower("10 - 3");
    auto* lit = hir_as<HirLiteral>(blk[0].get());
    REQUIRE(lit != nullptr);
    CHECK(lit->i == 7);
}

TEST_CASE("HIR: folds int multiplication") {
    auto blk = lower("6 * 7");
    auto* lit = hir_as<HirLiteral>(blk[0].get());
    REQUIRE(lit != nullptr);
    CHECK(lit->i == 42);
}

TEST_CASE("HIR: folds int floor division") {
    auto blk = lower("10 // 3");
    auto* lit = hir_as<HirLiteral>(blk[0].get());
    REQUIRE(lit != nullptr);
    CHECK(lit->i == 3);
}

TEST_CASE("HIR: folds int comparison to bool") {
    auto blk = lower("5 > 3");
    auto* lit = hir_as<HirLiteral>(blk[0].get());
    REQUIRE(lit != nullptr);
    CHECK(lit->vk == HirLiteral::ValKind::Bool);
    CHECK(lit->b  == true);
}

TEST_CASE("HIR: folds string concatenation") {
    auto blk = lower("\"foo\" + \"bar\"");
    auto* lit = hir_as<HirLiteral>(blk[0].get());
    REQUIRE(lit != nullptr);
    CHECK(lit->vk == HirLiteral::ValKind::String);
    CHECK(lit->s  == "foobar");
}

TEST_CASE("HIR: folds float addition") {
    auto blk = lower("1.5 + 2.5");
    auto* lit = hir_as<HirLiteral>(blk[0].get());
    REQUIRE(lit != nullptr);
    CHECK(lit->vk == HirLiteral::ValKind::Float);
    CHECK(lit->f  == doctest::Approx(4.0));
}

TEST_CASE("HIR: non-literal binop is not folded") {
    auto blk = lower("x = 1\nx + 1");
    REQUIRE(blk.size() >= 2);
    CHECK(blk.back()->kind == HirKind::BinOp);
}

// ── for loop desugaring ───────────────────────────────────────────────────────

TEST_CASE("HIR: for loop desugars to while") {
    auto blk = lower("for i = 0 to 5 { pass }");
    REQUIRE_FALSE(blk.empty());
    bool found_while = false;
    for (const auto& node : blk) {
        if (node->kind == HirKind::While) { found_while = true; break; }
    }
    CHECK(found_while);
}

TEST_CASE("HIR: for loop counter initialized as let") {
    // lower_for emits: let __end, let __step, let i, while(...)
    auto blk = lower("for i = 0 to 10 { pass }");
    REQUIRE(blk.size() >= 3);
    // Find the let node whose name is "i"
    bool found = false;
    for (const auto& node : blk) {
        auto* let = hir_as<HirLet>(node.get());
        if (let && let->name == "i") { found = true; break; }
    }
    CHECK(found);
}

// ── foreach desugaring ────────────────────────────────────────────────────────

TEST_CASE("HIR: foreach desugars to while") {
    auto blk = lower("items = [1, 2, 3]\nfor x in items { pass }");
    bool found_while = false;
    for (const auto& node : blk) {
        if (node->kind == HirKind::While) { found_while = true; break; }
    }
    CHECK(found_while);
}

// ── switch desugaring ─────────────────────────────────────────────────────────

TEST_CASE("HIR: switch desugars to if chain") {
    auto blk = lower("x = 1\nswitch x {\n  case 1 { pass }\n  case 2 { pass }\n}");
    bool found_if = false;
    for (const auto& node : blk) {
        if (node->kind == HirKind::If) { found_if = true; break; }
    }
    CHECK(found_if);
}

// ── f-string desugaring ───────────────────────────────────────────────────────

TEST_CASE("HIR: f-string with interpolation lowers to concat or call") {
    auto blk = lower("name = \"world\"\n$\"hello {name}\"");
    REQUIRE_FALSE(blk.empty());
    auto& last = blk.back();
    bool ok = (last->kind == HirKind::BinOp  ||
               last->kind == HirKind::Call   ||
               last->kind == HirKind::Literal);
    CHECK(ok);
}

TEST_CASE("HIR: f-string pure text folds to string literal") {
    auto blk = lower("$\"no interpolation\"");
    REQUIRE(blk.size() == 1);
    auto* lit = hir_as<HirLiteral>(blk[0].get());
    REQUIRE(lit != nullptr);
    CHECK(lit->vk == HirLiteral::ValKind::String);
}

// ── match desugaring ──────────────────────────────────────────────────────────

TEST_CASE("HIR: match expression desugars to if chain in assign value") {
    // Untyped assign → HirAssign; the value is the HirIf chain.
    auto blk = lower("x = 1\ny = match x { 1 => \"one\"  _ => \"other\" }");
    REQUIRE(blk.size() >= 2);
    auto* a = hir_as<HirAssign>(blk.back().get());
    REQUIRE(a != nullptr);
    CHECK(a->value->kind == HirKind::If);
}

// ── lambda lowering ───────────────────────────────────────────────────────────

TEST_CASE("HIR: lambda short form lowers to FuncDef") {
    auto blk = lower("fn(x) => x * 2");
    REQUIRE(blk.size() == 1);
    CHECK(blk[0]->kind == HirKind::FuncDef);
}

// ── HIR printer (smoke) ───────────────────────────────────────────────────────

TEST_CASE("HIR: printer produces non-empty output") {
    CHECK_FALSE(hir_text("x = 42").empty());
}

TEST_CASE("HIR: printer output contains 'let' for typed assign") {
    // Typed assign lowers to HirLet, printed as "(let ...)"
    CHECK(hir_text("x: int = 5").find("let") != std::string::npos);
}

TEST_CASE("HIR: printer output contains 'assign' for untyped assign") {
    CHECK(hir_text("x = 5").find("assign") != std::string::npos);
}

TEST_CASE("HIR: printer output contains 'while' for for-loop") {
    CHECK(hir_text("for i = 0 to 3 { pass }").find("while") != std::string::npos);
}
