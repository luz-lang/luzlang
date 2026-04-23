#pragma once

// hir.hpp — High-level Intermediate Representation for the Luz compiler.
//
// HIR sits between the AST (parser output) and LLVM IR.
// Two responsibilities:
//   1. Make every type explicit — every value-bearing node carries a type string.
//   2. Desugar complex constructs into a minimal flat set of primitives:
//        for i = s to e step k  →  while loop with explicit counter
//        for x in list          →  index-based while loop
//        switch/case            →  nested HirIf chain
//        match expr {}          →  chain of equality checks
//        f"hello {x}"           →  string concatenations via to_str()
//        method calls           →  HirCall(builtin, [obj, args])
//                                  or HirObjectCall(obj, method, args)

#include <cstdint>
#include <iosfwd>
#include <memory>
#include <string>
#include <utility>
#include <vector>

#include "luz/ast.hpp"

namespace luz {

// Forward declare
struct HirNode;
using HirNodePtr = std::unique_ptr<HirNode>;
using HirBlock   = std::vector<HirNodePtr>;

// ─── HIR type string constants ────────────────────────────────────────────────
namespace HT {
constexpr const char* UNKNOWN  = "unknown";
constexpr const char* NULL_T   = "null";
constexpr const char* BOOL     = "bool";
constexpr const char* INT      = "int";
constexpr const char* FLOAT    = "float";
constexpr const char* STRING   = "string";
constexpr const char* LIST     = "list";
constexpr const char* DICT     = "dict";
constexpr const char* FUNCTION = "function";
}

// ─── Node kind tag ────────────────────────────────────────────────────────────
enum class HirKind {
    Literal,
    Load, Let, Assign,
    BinOp, UnaryOp,
    Call, ExprCall, ObjectCall, IsInstance,
    If, While,
    Return, Break, Continue, Pass,
    FieldLoad, FieldStore,
    Index, IndexStore,
    List, Dict,
    FuncDef, ClassDef, StructDef,
    Import, AttemptRescue, Alert,
};

// ─── Base node ────────────────────────────────────────────────────────────────
struct HirNode {
    explicit HirNode(HirKind k) : kind(k) {}
    virtual ~HirNode() = default;
    HirKind kind;
};

// ─── HirLiteral ───────────────────────────────────────────────────────────────
struct HirLiteral : HirNode {
    enum class ValKind { Int, Float, String, Bool, Null };

    ValKind      vk = ValKind::Null;
    std::int64_t i  = 0;
    double       f  = 0.0;
    std::string  s;
    bool         b  = false;

    HirLiteral() : HirNode(HirKind::Literal) {}

    static HirNodePtr make_int   (std::int64_t v);
    static HirNodePtr make_float (double v);
    static HirNodePtr make_string(std::string v);
    static HirNodePtr make_bool  (bool v);
    static HirNodePtr make_null  ();

    std::string type_str() const;
};

// ─── Variable nodes ───────────────────────────────────────────────────────────
struct HirLoad : HirNode {
    std::string name;
    std::string type;
    explicit HirLoad(std::string n, std::string t = HT::UNKNOWN)
        : HirNode(HirKind::Load), name(std::move(n)), type(std::move(t)) {}
};

struct HirLet : HirNode {
    std::string name;
    std::string type;
    HirNodePtr  value;
    HirLet(std::string n, std::string t, HirNodePtr v)
        : HirNode(HirKind::Let), name(std::move(n)), type(std::move(t)), value(std::move(v)) {}
};

struct HirAssign : HirNode {
    std::string name;
    HirNodePtr  value;
    HirAssign(std::string n, HirNodePtr v)
        : HirNode(HirKind::Assign), name(std::move(n)), value(std::move(v)) {}
};

// ─── Operators ────────────────────────────────────────────────────────────────
struct HirBinOp : HirNode {
    std::string op;   // "+", "-", "*", "/", "//", "%", "**",
                      // "==", "!=", "<", "<=", ">", ">=", "and", "or"
    HirNodePtr  left;
    HirNodePtr  right;
    std::string type;
    HirBinOp(std::string o, HirNodePtr l, HirNodePtr r, std::string t = HT::UNKNOWN)
        : HirNode(HirKind::BinOp),
          op(std::move(o)), left(std::move(l)), right(std::move(r)), type(std::move(t)) {}
};

struct HirUnaryOp : HirNode {
    std::string op;   // "-" or "not"
    HirNodePtr  operand;
    std::string type;
    HirUnaryOp(std::string o, HirNodePtr x, std::string t = HT::UNKNOWN)
        : HirNode(HirKind::UnaryOp), op(std::move(o)), operand(std::move(x)), type(std::move(t)) {}
};

// ─── Calls ────────────────────────────────────────────────────────────────────
struct HirCall : HirNode {
    std::string             func;
    std::vector<HirNodePtr> args;
    std::string             return_type;
    HirCall(std::string f, std::vector<HirNodePtr> a, std::string rt = HT::UNKNOWN)
        : HirNode(HirKind::Call),
          func(std::move(f)), args(std::move(a)), return_type(std::move(rt)) {}
};

struct HirExprCall : HirNode {
    HirNodePtr              callee;
    std::vector<HirNodePtr> args;
    std::string             return_type;
    HirExprCall(HirNodePtr c, std::vector<HirNodePtr> a, std::string rt = HT::UNKNOWN)
        : HirNode(HirKind::ExprCall),
          callee(std::move(c)), args(std::move(a)), return_type(std::move(rt)) {}
};

// Dispatch to user-defined class method at runtime.
struct HirObjectCall : HirNode {
    HirNodePtr              obj;
    std::string             method;
    std::vector<HirNodePtr> args;
    std::string             return_type;
    HirObjectCall(HirNodePtr o, std::string m, std::vector<HirNodePtr> a,
                  std::string rt = HT::UNKNOWN)
        : HirNode(HirKind::ObjectCall),
          obj(std::move(o)), method(std::move(m)), args(std::move(a)), return_type(std::move(rt)) {}
};

// instanceof(obj, ClassName) check.
struct HirIsInstance : HirNode {
    HirNodePtr  obj;
    std::string class_name;
    HirIsInstance(HirNodePtr o, std::string cn)
        : HirNode(HirKind::IsInstance), obj(std::move(o)), class_name(std::move(cn)) {}
};

// ─── Control flow ─────────────────────────────────────────────────────────────
struct HirIf : HirNode {
    HirNodePtr cond;
    HirBlock   then_block;
    HirBlock   else_block;  // empty = no else
    HirIf(HirNodePtr c, HirBlock th, HirBlock el = {})
        : HirNode(HirKind::If),
          cond(std::move(c)), then_block(std::move(th)), else_block(std::move(el)) {}
};

struct HirWhile : HirNode {
    HirNodePtr cond;
    HirBlock   body;
    HirWhile(HirNodePtr c, HirBlock b)
        : HirNode(HirKind::While), cond(std::move(c)), body(std::move(b)) {}
};

struct HirReturn : HirNode {
    HirNodePtr value;  // nullptr = bare return
    explicit HirReturn(HirNodePtr v = {})
        : HirNode(HirKind::Return), value(std::move(v)) {}
};

struct HirBreak    : HirNode { HirBreak()    : HirNode(HirKind::Break)    {} };
struct HirContinue : HirNode { HirContinue() : HirNode(HirKind::Continue) {} };
struct HirPass     : HirNode { HirPass()     : HirNode(HirKind::Pass)     {} };

// ─── Field / index access ─────────────────────────────────────────────────────
struct HirFieldLoad : HirNode {
    HirNodePtr  obj;
    std::string field;
    std::string type;
    HirFieldLoad(HirNodePtr o, std::string f, std::string t = HT::UNKNOWN)
        : HirNode(HirKind::FieldLoad), obj(std::move(o)), field(std::move(f)), type(std::move(t)) {}
};

struct HirFieldStore : HirNode {
    HirNodePtr  obj;
    std::string field;
    HirNodePtr  value;
    HirFieldStore(HirNodePtr o, std::string f, HirNodePtr v)
        : HirNode(HirKind::FieldStore),
          obj(std::move(o)), field(std::move(f)), value(std::move(v)) {}
};

struct HirIndex : HirNode {
    HirNodePtr  collection;
    HirNodePtr  index;
    std::string type;
    HirIndex(HirNodePtr c, HirNodePtr i, std::string t = HT::UNKNOWN)
        : HirNode(HirKind::Index),
          collection(std::move(c)), index(std::move(i)), type(std::move(t)) {}
};

struct HirIndexStore : HirNode {
    HirNodePtr collection;
    HirNodePtr index;
    HirNodePtr value;
    HirIndexStore(HirNodePtr c, HirNodePtr i, HirNodePtr v)
        : HirNode(HirKind::IndexStore),
          collection(std::move(c)), index(std::move(i)), value(std::move(v)) {}
};

// ─── Collections ──────────────────────────────────────────────────────────────
struct HirList : HirNode {
    std::vector<HirNodePtr> elements;
    explicit HirList(std::vector<HirNodePtr> e)
        : HirNode(HirKind::List), elements(std::move(e)) {}
};

struct HirDictPair { HirNodePtr key; HirNodePtr value; };

struct HirDict : HirNode {
    std::vector<HirDictPair> pairs;
    explicit HirDict(std::vector<HirDictPair> ps)
        : HirNode(HirKind::Dict), pairs(std::move(ps)) {}
};

// ─── Definitions ──────────────────────────────────────────────────────────────
struct HirParam { std::string name; std::string type; };

struct HirFuncDef : HirNode {
    std::string           name;
    std::vector<HirParam> params;
    std::string           return_type;
    HirBlock              body;
    bool                  is_variadic = false;
    HirFuncDef(std::string n, std::vector<HirParam> ps,
               std::string rt, HirBlock b, bool v = false)
        : HirNode(HirKind::FuncDef),
          name(std::move(n)), params(std::move(ps)), return_type(std::move(rt)),
          body(std::move(b)), is_variadic(v) {}
};

struct HirClassDef : HirNode {
    std::string name;
    std::string parent;
    HirBlock    methods;  // HirFuncDef* nodes
    HirClassDef(std::string n, std::string p, HirBlock ms)
        : HirNode(HirKind::ClassDef),
          name(std::move(n)), parent(std::move(p)), methods(std::move(ms)) {}
};

struct HirStructField { std::string name; std::string type; HirNodePtr default_val; };

struct HirStructDef : HirNode {
    std::string                 name;
    std::vector<HirStructField> fields;
    HirStructDef(std::string n, std::vector<HirStructField> f)
        : HirNode(HirKind::StructDef), name(std::move(n)), fields(std::move(f)) {}
};

// ─── Other ────────────────────────────────────────────────────────────────────
struct HirImport : HirNode {
    std::string              path;
    std::string              alias;
    std::vector<std::string> names;
    HirImport(std::string p, std::string a, std::vector<std::string> ns)
        : HirNode(HirKind::Import),
          path(std::move(p)), alias(std::move(a)), names(std::move(ns)) {}
};

struct HirAttemptRescue : HirNode {
    HirBlock    try_block;
    std::string error_var;
    HirBlock    rescue_block;
    HirBlock    finally_block;
    HirAttemptRescue(HirBlock tr, std::string ev, HirBlock rb, HirBlock fb)
        : HirNode(HirKind::AttemptRescue),
          try_block(std::move(tr)), error_var(std::move(ev)),
          rescue_block(std::move(rb)), finally_block(std::move(fb)) {}
};

struct HirAlert : HirNode {
    HirNodePtr value;
    explicit HirAlert(HirNodePtr v)
        : HirNode(HirKind::Alert), value(std::move(v)) {}
};

// ─── Public API ───────────────────────────────────────────────────────────────

// Lower an entire program AST to a flat HIR block.
HirBlock lower_to_hir(const Program& program);

// Pretty-print HIR for debugging (luzc --hir).
void print_hir(std::ostream& out, const HirBlock& block, int indent = 0);

}  // namespace luz
