#pragma once

#include <cstdint>
#include <memory>
#include <string>
#include <utility>
#include <vector>

namespace luz {

// ─── Source position ────────────────────────────────────────────────────────
struct SourcePos {
    int line = 0;
    int col  = 0;
};

// ─── Expression hierarchy ────────────────────────────────────────────────────
enum class NodeKind {
    // Expressions
    IntLit, FloatLit, StringLit, BoolLit, NullLit,
    Identifier,
    UnaryOp, BinaryOp,
    Call,
    ListLit,      // [expr, ...]
    DictLit,      // {key: value, ...}
    IndexAccess,  // expr[index]
    Attribute,    // expr.name
    // Statements
    ExprStmt,
    Assign,         // x = expr  (new binding or reassignment)
    TypedAssign,    // x: type = expr
    ConstDecl,      // const x = expr  or  const x: type = expr
    CompoundAssign, // x += expr  (desugared to Assign at printer/codegen level)
    Block,          // { stmts... }
    If,
    While,
    For,            // for i = start to end { block }
    ForEach,        // for x in iterable { block }
    Break, Continue, Pass,
    Return,
    FuncDef,
    StructDef,
    ClassDef,
    AttrAssign,   // expr.name = value
    IndexAssign,  // expr[idx]  = value
};

enum class UnOp  { Neg, Not };
enum class BinOp {
    Add, Sub, Mul, Div, FloorDiv, Mod, Pow,
    Eq, Ne, Lt, Gt, Le, Ge,
    And, Or
};

// Abstract base for expression nodes.
struct Expr {
    explicit Expr(NodeKind k, SourcePos p) : kind(k), pos(p) {}
    virtual ~Expr() = default;
    NodeKind  kind;
    SourcePos pos;
};
using ExprPtr = std::unique_ptr<Expr>;

// Abstract base for statement nodes.
struct Stmt {
    explicit Stmt(NodeKind k, SourcePos p) : kind(k), pos(p) {}
    virtual ~Stmt() = default;
    NodeKind  kind;
    SourcePos pos;
};
using StmtPtr = std::unique_ptr<Stmt>;
using Block   = std::vector<StmtPtr>;

// ─── Expression nodes ────────────────────────────────────────────────────────
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

struct ListLit : Expr {
    ListLit(std::vector<ExprPtr> e, SourcePos p)
        : Expr(NodeKind::ListLit, p), elements(std::move(e)) {}
    std::vector<ExprPtr> elements;
};

struct DictPair {
    ExprPtr key;
    ExprPtr value;
};

struct DictLit : Expr {
    DictLit(std::vector<DictPair> ps, SourcePos p)
        : Expr(NodeKind::DictLit, p), pairs(std::move(ps)) {}
    std::vector<DictPair> pairs;
};

struct IndexAccess : Expr {
    IndexAccess(ExprPtr b, ExprPtr i, SourcePos p)
        : Expr(NodeKind::IndexAccess, p), base(std::move(b)), index(std::move(i)) {}
    ExprPtr base;
    ExprPtr index;
};

struct Attribute : Expr {
    Attribute(ExprPtr o, std::string n, SourcePos p)
        : Expr(NodeKind::Attribute, p), object(std::move(o)), name(std::move(n)) {}
    ExprPtr     object;
    std::string name;
};

// ─── Statement nodes ─────────────────────────────────────────────────────────

// An expression used as a statement (most commonly a function call).
struct ExprStmt : Stmt {
    ExprStmt(ExprPtr e, SourcePos p)
        : Stmt(NodeKind::ExprStmt, p), expr(std::move(e)) {}
    ExprPtr expr;
};

// x = value  (first binding or reassignment — Luz has no explicit `let`)
struct Assign : Stmt {
    Assign(std::string n, ExprPtr v, SourcePos p)
        : Stmt(NodeKind::Assign, p), name(std::move(n)), value(std::move(v)) {}
    std::string name;
    ExprPtr     value;
};

// x: TypeName = value
struct TypedAssign : Stmt {
    TypedAssign(std::string n, std::string t, ExprPtr v, SourcePos p)
        : Stmt(NodeKind::TypedAssign, p),
          name(std::move(n)), type_name(std::move(t)), value(std::move(v)) {}
    std::string name;
    std::string type_name;
    ExprPtr     value;
};

// const x = value  or  const x: TypeName = value
struct ConstDecl : Stmt {
    ConstDecl(std::string n, std::string t, ExprPtr v, SourcePos p)
        : Stmt(NodeKind::ConstDecl, p),
          name(std::move(n)), type_name(std::move(t)), value(std::move(v)) {}
    std::string name;
    std::string type_name;  // empty if no annotation
    ExprPtr     value;
};

// if (cond) { block } elif (cond) { block }* else { block }?
struct IfBranch {
    ExprPtr condition;
    Block   body;
};

struct If : Stmt {
    explicit If(SourcePos p) : Stmt(NodeKind::If, p) {}
    std::vector<IfBranch> branches;   // if + elif branches in order
    Block                 else_body;  // empty if no else
};

// while cond { block }
struct While : Stmt {
    While(ExprPtr c, Block b, SourcePos p)
        : Stmt(NodeKind::While, p), condition(std::move(c)), body(std::move(b)) {}
    ExprPtr condition;
    Block   body;
};

// for i = start to end { block }  (step optional)
struct For : Stmt {
    For(std::string v, ExprPtr s, ExprPtr e, ExprPtr st, Block b, SourcePos p)
        : Stmt(NodeKind::For, p),
          var(std::move(v)), start(std::move(s)), end(std::move(e)),
          step(std::move(st)), body(std::move(b)) {}
    std::string var;
    ExprPtr     start;
    ExprPtr     end;
    ExprPtr     step;  // nullptr = default step 1
    Block       body;
};

// for x in iterable { block }
struct ForEach : Stmt {
    ForEach(std::string v, ExprPtr it, Block b, SourcePos p)
        : Stmt(NodeKind::ForEach, p),
          var(std::move(v)), iterable(std::move(it)), body(std::move(b)) {}
    std::string var;
    ExprPtr     iterable;
    Block       body;
};

struct Break    : Stmt { explicit Break   (SourcePos p) : Stmt(NodeKind::Break,    p) {} };
struct Continue : Stmt { explicit Continue(SourcePos p) : Stmt(NodeKind::Continue, p) {} };
struct Pass     : Stmt { explicit Pass    (SourcePos p) : Stmt(NodeKind::Pass,     p) {} };

// return expr?
struct Return : Stmt {
    Return(ExprPtr v, SourcePos p) : Stmt(NodeKind::Return, p), value(std::move(v)) {}
    ExprPtr value;  // nullptr for bare `return`
};

// Typed parameter: name + optional type annotation + optional default
struct Param {
    std::string name;
    std::string type_name;  // empty if not annotated
    ExprPtr     default_val;  // nullptr if required
    bool        variadic = false;
};

// function name(params...) -> ReturnType { block }
struct FuncDef : Stmt {
    FuncDef(std::string n, std::vector<Param> ps, std::string rt, Block b, SourcePos p)
        : Stmt(NodeKind::FuncDef, p),
          name(std::move(n)), params(std::move(ps)),
          return_type(std::move(rt)), body(std::move(b)) {}
    std::string        name;
    std::vector<Param> params;
    std::string        return_type;  // empty if not annotated
    Block              body;
};

// expr.name = value
struct AttrAssign : Stmt {
    AttrAssign(ExprPtr obj, std::string attr, ExprPtr val, SourcePos p)
        : Stmt(NodeKind::AttrAssign, p),
          object(std::move(obj)), attr(std::move(attr)), value(std::move(val)) {}
    ExprPtr     object;
    std::string attr;
    ExprPtr     value;
};

// expr[idx] = value
struct IndexAssign : Stmt {
    IndexAssign(ExprPtr base, ExprPtr idx, ExprPtr val, SourcePos p)
        : Stmt(NodeKind::IndexAssign, p),
          base(std::move(base)), index(std::move(idx)), value(std::move(val)) {}
    ExprPtr base;
    ExprPtr index;
    ExprPtr value;
};

// struct Name { field: Type [= default], ... }
struct StructField {
    std::string name;
    std::string type_name;
    ExprPtr     default_val;  // nullptr if no default
};

struct StructDef : Stmt {
    StructDef(std::string n, std::vector<StructField> fs, SourcePos p)
        : Stmt(NodeKind::StructDef, p), name(std::move(n)), fields(std::move(fs)) {}
    std::string              name;
    std::vector<StructField> fields;
};

// class Name [extends Parent] { function method(...) { ... } ... }
struct ClassDef : Stmt {
    ClassDef(std::string n, std::string parent, std::vector<StmtPtr> ms, SourcePos p)
        : Stmt(NodeKind::ClassDef, p),
          name(std::move(n)), parent(std::move(parent)), methods(std::move(ms)) {}
    std::string          name;
    std::string          parent;   // empty if no inheritance
    std::vector<StmtPtr> methods;  // FuncDef nodes only
};

// ─── Top-level program ────────────────────────────────────────────────────────
struct Program {
    Block statements;
};

}  // namespace luz
