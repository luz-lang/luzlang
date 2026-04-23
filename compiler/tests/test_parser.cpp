#include "test_runner.hpp"

#include "luz/ast.hpp"
#include "luz/lexer.hpp"
#include "luz/parser.hpp"

using namespace luz;

// ── helpers ──────────────────────────────────────────────────────────────────

static Program parse_src(const std::string& src) {
    return parse(lex(src));
}

template<class T>
static const T* as(const Stmt* s) {
    return dynamic_cast<const T*>(s);
}

template<class T>
static const T* as_expr(const Expr* e) {
    return dynamic_cast<const T*>(e);
}

// ── literal expressions ───────────────────────────────────────────────────────

TEST_CASE("Parser: integer literal") {
    auto prog = parse_src("42");
    REQUIRE(prog.statements.size() == 1);
    auto* es = as<ExprStmt>(prog.statements[0].get());
    REQUIRE(es != nullptr);
    auto* lit = as_expr<IntLit>(es->expr.get());
    REQUIRE(lit != nullptr);
    CHECK(lit->value == 42);
}

TEST_CASE("Parser: float literal") {
    auto prog = parse_src("3.14");
    auto* es  = as<ExprStmt>(prog.statements[0].get());
    REQUIRE(es != nullptr);
    auto* lit = as_expr<FloatLit>(es->expr.get());
    REQUIRE(lit != nullptr);
    CHECK(lit->value == doctest::Approx(3.14));
}

TEST_CASE("Parser: string literal") {
    auto prog = parse_src("\"hello\"");
    auto* es  = as<ExprStmt>(prog.statements[0].get());
    REQUIRE(es != nullptr);
    auto* lit = as_expr<StringLit>(es->expr.get());
    REQUIRE(lit != nullptr);
    CHECK(lit->value == "hello");
}

TEST_CASE("Parser: bool literals") {
    {
        auto prog = parse_src("true");
        auto* es  = as<ExprStmt>(prog.statements[0].get());
        REQUIRE(es != nullptr);
        auto* lit = as_expr<BoolLit>(es->expr.get());
        REQUIRE(lit != nullptr);
        CHECK(lit->value == true);
    }
    {
        auto prog = parse_src("false");
        auto* es  = as<ExprStmt>(prog.statements[0].get());
        REQUIRE(es != nullptr);
        auto* lit = as_expr<BoolLit>(es->expr.get());
        REQUIRE(lit != nullptr);
        CHECK(lit->value == false);
    }
}

TEST_CASE("Parser: null literal") {
    auto prog = parse_src("null");
    auto* es  = as<ExprStmt>(prog.statements[0].get());
    REQUIRE(es != nullptr);
    CHECK(es->expr->kind == NodeKind::NullLit);
}

// ── binary operations ─────────────────────────────────────────────────────────

TEST_CASE("Parser: simple addition") {
    auto prog = parse_src("1 + 2");
    auto* es  = as<ExprStmt>(prog.statements[0].get());
    REQUIRE(es != nullptr);
    auto* bin = as_expr<BinaryOp>(es->expr.get());
    REQUIRE(bin != nullptr);
    CHECK(bin->op == BinOp::Add);
    CHECK(dynamic_cast<IntLit*>(bin->lhs.get())->value == 1);
    CHECK(dynamic_cast<IntLit*>(bin->rhs.get())->value == 2);
}

TEST_CASE("Parser: arithmetic precedence (mul before add)") {
    auto prog = parse_src("1 + 2 * 3");
    auto* es  = as<ExprStmt>(prog.statements[0].get());
    REQUIRE(es != nullptr);
    auto* outer = as_expr<BinaryOp>(es->expr.get());
    REQUIRE(outer != nullptr);
    CHECK(outer->op == BinOp::Add);
    auto* inner = dynamic_cast<BinaryOp*>(outer->rhs.get());
    REQUIRE(inner != nullptr);
    CHECK(inner->op == BinOp::Mul);
}

TEST_CASE("Parser: parentheses override precedence") {
    auto prog = parse_src("(1 + 2) * 3");
    auto* es  = as<ExprStmt>(prog.statements[0].get());
    REQUIRE(es != nullptr);
    auto* outer = as_expr<BinaryOp>(es->expr.get());
    REQUIRE(outer != nullptr);
    CHECK(outer->op == BinOp::Mul);
    auto* inner = dynamic_cast<BinaryOp*>(outer->lhs.get());
    REQUIRE(inner != nullptr);
    CHECK(inner->op == BinOp::Add);
}

TEST_CASE("Parser: unary negation") {
    auto prog = parse_src("-5");
    auto* es  = as<ExprStmt>(prog.statements[0].get());
    REQUIRE(es != nullptr);
    auto* u = as_expr<UnaryOp>(es->expr.get());
    REQUIRE(u != nullptr);
    CHECK(u->op == UnOp::Neg);
}

TEST_CASE("Parser: logical not") {
    auto prog = parse_src("not true");
    auto* es  = as<ExprStmt>(prog.statements[0].get());
    REQUIRE(es != nullptr);
    auto* u = as_expr<UnaryOp>(es->expr.get());
    REQUIRE(u != nullptr);
    CHECK(u->op == UnOp::Not);
}

// ── assignment ────────────────────────────────────────────────────────────────

TEST_CASE("Parser: simple assignment") {
    auto prog = parse_src("x = 5");
    REQUIRE(prog.statements.size() == 1);
    auto* a = as<Assign>(prog.statements[0].get());
    REQUIRE(a != nullptr);
    CHECK(a->name == "x");
    CHECK(dynamic_cast<IntLit*>(a->value.get())->value == 5);
}

TEST_CASE("Parser: typed assignment") {
    auto prog = parse_src("x: int = 10");
    REQUIRE(prog.statements.size() == 1);
    auto* ta = as<TypedAssign>(prog.statements[0].get());
    REQUIRE(ta != nullptr);
    CHECK(ta->name      == "x");
    CHECK(ta->type_name == "int");
    CHECK(dynamic_cast<IntLit*>(ta->value.get())->value == 10);
}

TEST_CASE("Parser: const declaration") {
    auto prog = parse_src("const PI = 3");
    REQUIRE(prog.statements.size() == 1);
    auto* cd = as<ConstDecl>(prog.statements[0].get());
    REQUIRE(cd != nullptr);
    CHECK(cd->name == "PI");
}

// ── function call ─────────────────────────────────────────────────────────────

TEST_CASE("Parser: function call no args") {
    auto prog = parse_src("foo()");
    auto* es  = as<ExprStmt>(prog.statements[0].get());
    REQUIRE(es != nullptr);
    auto* call = as_expr<Call>(es->expr.get());
    REQUIRE(call != nullptr);
    CHECK(call->args.size() == 0);
}

TEST_CASE("Parser: function call multi args") {
    auto prog = parse_src("add(1, 2, 3)");
    auto* es  = as<ExprStmt>(prog.statements[0].get());
    REQUIRE(es != nullptr);
    auto* call = as_expr<Call>(es->expr.get());
    REQUIRE(call != nullptr);
    CHECK(call->args.size() == 3);
}

// ── if / while ────────────────────────────────────────────────────────────────

TEST_CASE("Parser: if statement") {
    auto prog = parse_src("if x == 1 { y = 2 }");
    REQUIRE(prog.statements.size() == 1);
    auto* s = as<If>(prog.statements[0].get());
    REQUIRE(s != nullptr);
    CHECK(s->branches.size()  == 1);
    CHECK(s->else_body.size() == 0);
}

TEST_CASE("Parser: if-else statement") {
    auto prog = parse_src("if x { a = 1 } else { b = 2 }");
    REQUIRE(prog.statements.size() == 1);
    auto* s = as<If>(prog.statements[0].get());
    REQUIRE(s != nullptr);
    CHECK(s->branches.size()  == 1);
    CHECK(s->else_body.size() >  0);
}

TEST_CASE("Parser: while statement") {
    auto prog = parse_src("while x > 0 { x = x - 1 }");
    REQUIRE(prog.statements.size() == 1);
    auto* w = as<While>(prog.statements[0].get());
    REQUIRE(w != nullptr);
    CHECK(w->body.size() == 1);
}

// ── for loops ─────────────────────────────────────────────────────────────────

TEST_CASE("Parser: for loop") {
    auto prog = parse_src("for i = 0 to 10 { pass }");
    REQUIRE(prog.statements.size() == 1);
    auto* f = as<For>(prog.statements[0].get());
    REQUIRE(f != nullptr);
    CHECK(f->var == "i");
}

TEST_CASE("Parser: foreach loop") {
    auto prog = parse_src("for x in items { pass }");
    REQUIRE(prog.statements.size() == 1);
    auto* fe = as<ForEach>(prog.statements[0].get());
    REQUIRE(fe != nullptr);
    CHECK(fe->var == "x");
}

// ── function definition ───────────────────────────────────────────────────────

TEST_CASE("Parser: function definition") {
    auto prog = parse_src("function add(a, b) { return a + b }");
    REQUIRE(prog.statements.size() == 1);
    auto* fd = as<FuncDef>(prog.statements[0].get());
    REQUIRE(fd != nullptr);
    CHECK(fd->name           == "add");
    CHECK(fd->params.size()  == 2);
}

TEST_CASE("Parser: function with return type annotation") {
    auto prog = parse_src("function square(n: int) -> int { return n * n }");
    REQUIRE(prog.statements.size() == 1);
    auto* fd = as<FuncDef>(prog.statements[0].get());
    REQUIRE(fd != nullptr);
    CHECK(fd->return_type         == "int");
    CHECK(fd->params[0].type_name == "int");
}

// ── collections ───────────────────────────────────────────────────────────────

TEST_CASE("Parser: list literal") {
    auto prog = parse_src("[1, 2, 3]");
    auto* es  = as<ExprStmt>(prog.statements[0].get());
    REQUIRE(es != nullptr);
    auto* lst = as_expr<ListLit>(es->expr.get());
    REQUIRE(lst != nullptr);
    CHECK(lst->elements.size() == 3);
}

TEST_CASE("Parser: dict literal") {
    auto prog = parse_src("{\"a\": 1, \"b\": 2}");
    auto* es  = as<ExprStmt>(prog.statements[0].get());
    REQUIRE(es != nullptr);
    auto* d = as_expr<DictLit>(es->expr.get());
    REQUIRE(d != nullptr);
    CHECK(d->pairs.size() == 2);
}

TEST_CASE("Parser: index access") {
    auto prog = parse_src("arr[0]");
    auto* es  = as<ExprStmt>(prog.statements[0].get());
    REQUIRE(es != nullptr);
    CHECK(es->expr->kind == NodeKind::IndexAccess);
}

// ── class definition ──────────────────────────────────────────────────────────

TEST_CASE("Parser: class definition") {
    auto prog = parse_src("class Animal { function speak(self) { pass } }");
    REQUIRE(prog.statements.size() == 1);
    auto* cd = as<ClassDef>(prog.statements[0].get());
    REQUIRE(cd != nullptr);
    CHECK(cd->name           == "Animal");
    CHECK(cd->parent         == "");
    CHECK(cd->methods.size() == 1);
}

TEST_CASE("Parser: class with inheritance") {
    auto prog = parse_src("class Dog extends Animal { }");
    auto* cd  = as<ClassDef>(prog.statements[0].get());
    REQUIRE(cd != nullptr);
    CHECK(cd->parent == "Animal");
}

// ── import ────────────────────────────────────────────────────────────────────

TEST_CASE("Parser: import statement") {
    auto prog = parse_src("import \"math\"");
    REQUIRE(prog.statements.size() == 1);
    auto* imp = as<Import>(prog.statements[0].get());
    REQUIRE(imp != nullptr);
    CHECK(imp->path  == "math");
    CHECK(imp->alias == "");
}

TEST_CASE("Parser: import as") {
    auto prog = parse_src("import \"math\" as m");
    auto* imp = as<Import>(prog.statements[0].get());
    REQUIRE(imp != nullptr);
    CHECK(imp->alias == "m");
}

// ── attempt/rescue ────────────────────────────────────────────────────────────

TEST_CASE("Parser: attempt/rescue") {
    auto prog = parse_src("attempt { x = 1 } rescue(e) { pass }");
    REQUIRE(prog.statements.size() == 1);
    auto* at = as<Attempt>(prog.statements[0].get());
    REQUIRE(at != nullptr);
    CHECK(at->error_var == "e");
}

// ── lambda ────────────────────────────────────────────────────────────────────

TEST_CASE("Parser: lambda short form") {
    auto prog = parse_src("fn(x) => x * 2");
    auto* es  = as<ExprStmt>(prog.statements[0].get());
    REQUIRE(es != nullptr);
    auto* lam = as_expr<Lambda>(es->expr.get());
    REQUIRE(lam != nullptr);
    CHECK(lam->params.size()  == 1);
    CHECK(lam->expr_body.get() != nullptr);
}

// ── parse error ───────────────────────────────────────────────────────────────

TEST_CASE("Parser: unmatched paren throws") {
    CHECK_THROWS(parse_src("(1 + 2"));
}
