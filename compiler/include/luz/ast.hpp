#pragma once

#include <cstdint>
#include <memory>
#include <string>
#include <utility>
#include <vector>

namespace luz {

struct SourcePos {
    int line = 0;
    int col  = 0;
};

enum class NodeKind {
    IntLit, FloatLit, StringLit, BoolLit, NullLit,
    Identifier,
    UnaryOp, BinaryOp,
    Call
};

enum class UnOp { Neg, Not };

enum class BinOp {
    Add, Sub, Mul, Div, FloorDiv, Mod, Pow,
    Eq, Ne, Lt, Gt, Le, Ge,
    And, Or
};

// Abstract base for every expression. Owning the children through unique_ptr
// keeps the tree acyclic and destruction deterministic. Prefer downcast via
// the explicit `kind` tag over RTTI.
struct Expr {
    explicit Expr(NodeKind k, SourcePos p) : kind(k), pos(p) {}
    virtual ~Expr() = default;

    NodeKind  kind;
    SourcePos pos;
};

using ExprPtr = std::unique_ptr<Expr>;

struct IntLit : Expr {
    IntLit(std::int64_t v, SourcePos p) : Expr(NodeKind::IntLit, p), value(v) {}
    std::int64_t value;
};

struct FloatLit : Expr {
    FloatLit(double v, SourcePos p) : Expr(NodeKind::FloatLit, p), value(v) {}
    double value;
};

struct StringLit : Expr {
    StringLit(std::string v, SourcePos p)
        : Expr(NodeKind::StringLit, p), value(std::move(v)) {}
    std::string value;
};

struct BoolLit : Expr {
    BoolLit(bool v, SourcePos p) : Expr(NodeKind::BoolLit, p), value(v) {}
    bool value;
};

struct NullLit : Expr {
    explicit NullLit(SourcePos p) : Expr(NodeKind::NullLit, p) {}
};

struct Identifier : Expr {
    Identifier(std::string n, SourcePos p)
        : Expr(NodeKind::Identifier, p), name(std::move(n)) {}
    std::string name;
};

struct UnaryOp : Expr {
    UnaryOp(UnOp o, ExprPtr x, SourcePos p)
        : Expr(NodeKind::UnaryOp, p), op(o), operand(std::move(x)) {}
    UnOp    op;
    ExprPtr operand;
};

struct BinaryOp : Expr {
    BinaryOp(BinOp o, ExprPtr l, ExprPtr r, SourcePos p)
        : Expr(NodeKind::BinaryOp, p), op(o), lhs(std::move(l)), rhs(std::move(r)) {}
    BinOp   op;
    ExprPtr lhs;
    ExprPtr rhs;
};

struct Call : Expr {
    Call(ExprPtr c, std::vector<ExprPtr> a, SourcePos p)
        : Expr(NodeKind::Call, p), callee(std::move(c)), args(std::move(a)) {}
    ExprPtr              callee;
    std::vector<ExprPtr> args;
};

// Top-level program: a flat list of expression statements for now.
// Statements (let, if, while, function, class) will be added as the parser
// grows beyond expressions.
struct Program {
    std::vector<ExprPtr> statements;
};

}  // namespace luz
