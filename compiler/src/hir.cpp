// hir.cpp — Luz HIR lowering pass (C++ port of luz/hir.py).
//
// Transforms the parser AST into HIR by:
//   - Desugaring for/switch/match/fstring into while loops and if chains.
//   - Constant-folding binary operations on integer/float/string literals.
//   - Flattening if/elif/else into nested binary HirIf nodes.
//   - Dispatching method calls to either builtin HirCall or HirObjectCall.

#include "luz/hir.hpp"

#include <cassert>
#include <iostream>
#include <sstream>
#include <string>
#include <unordered_set>
#include <vector>

namespace luz {

// ─── HirLiteral factory methods ──────────────────────────────────────────────

HirNodePtr HirLiteral::make_int(std::int64_t v) {
    auto n = std::make_unique<HirLiteral>();
    n->vk = ValKind::Int;
    n->i  = v;
    return n;
}
HirNodePtr HirLiteral::make_float(double v) {
    auto n = std::make_unique<HirLiteral>();
    n->vk = ValKind::Float;
    n->f  = v;
    return n;
}
HirNodePtr HirLiteral::make_string(std::string v) {
    auto n = std::make_unique<HirLiteral>();
    n->vk = ValKind::String;
    n->s  = std::move(v);
    return n;
}
HirNodePtr HirLiteral::make_bool(bool v) {
    auto n = std::make_unique<HirLiteral>();
    n->vk = ValKind::Bool;
    n->b  = v;
    return n;
}
HirNodePtr HirLiteral::make_null() {
    return std::make_unique<HirLiteral>();
}
std::string HirLiteral::type_str() const {
    switch (vk) {
        case ValKind::Int:    return HT::INT;
        case ValKind::Float:  return HT::FLOAT;
        case ValKind::String: return HT::STRING;
        case ValKind::Bool:   return HT::BOOL;
        default:              return HT::NULL_T;
    }
}

// ─── Lowering pass ────────────────────────────────────────────────────────────

class Lowering {
public:
    HirBlock lower_program(const Program& prog) {
        // Pre-scan: collect struct names so instantiation can be detected
        for (auto& s : prog.statements) {
            if (s->kind == NodeKind::StructDef)
                struct_names_.insert(static_cast<const StructDef*>(s.get())->name);
        }
        return lower_block(prog.statements);
    }

private:
    int temp_counter_ = 0;
    std::unordered_set<std::string> struct_names_;

    // ── Helpers ──────────────────────────────────────────────────────────────

    std::string fresh(const char* prefix = "__t") {
        std::string name = prefix;
        name += std::to_string(temp_counter_++);
        return name;
    }

    static HirNodePtr hir_load(const std::string& name) {
        return std::make_unique<HirLoad>(name);
    }
    static HirNodePtr hir_int(std::int64_t v)  { return HirLiteral::make_int(v);   }
    static HirNodePtr hir_bool(bool v)          { return HirLiteral::make_bool(v);  }
    static HirNodePtr hir_null()                { return HirLiteral::make_null();   }

    static HirNodePtr hir_binop(std::string op, HirNodePtr l, HirNodePtr r,
                                std::string t = HT::UNKNOWN) {
        return std::make_unique<HirBinOp>(std::move(op), std::move(l), std::move(r), std::move(t));
    }

    // Build a HirBlock from a Block (vector of StmtPtr).
    // Special case: fuse struct instantiation pattern
    //   TypedAssign(name: StructType = StructName)
    //   ExprStmt(DictLit{Ident(field): val, ...})
    // into a single HirLet with a proper HirDict (string keys).
    HirBlock lower_block(const Block& stmts) {
        HirBlock out;
        for (std::size_t i = 0; i < stmts.size(); ++i) {
            auto* s = stmts[i].get();

            // Detect struct init: TypedAssign where type is a known struct
            // and value is just Ident(StructName)
            if (s->kind == NodeKind::TypedAssign) {
                auto* ta = static_cast<const TypedAssign*>(s);
                if (struct_names_.count(ta->type_name) &&
                    ta->value && ta->value->kind == NodeKind::Identifier &&
                    static_cast<const Identifier*>(ta->value.get())->name == ta->type_name &&
                    i + 1 < stmts.size()) {

                    // Peek at next stmt — must be ExprStmt(DictLit{Ident: val})
                    auto* next = stmts[i + 1].get();
                    if (next->kind == NodeKind::ExprStmt) {
                        auto* es = static_cast<const ExprStmt*>(next);
                        if (es->expr && es->expr->kind == NodeKind::DictLit) {
                            auto* dl = static_cast<const DictLit*>(es->expr.get());
                            // Confirm all keys are Ident nodes (field names)
                            bool all_ident = true;
                            for (auto& p : dl->pairs) {
                                if (!p.key || p.key->kind != NodeKind::Identifier) {
                                    all_ident = false; break;
                                }
                            }
                            if (all_ident) {
                                // Build HirDict with string literal keys
                                std::vector<HirDictPair> pairs;
                                for (auto& p : dl->pairs) {
                                    std::string fname = static_cast<const Identifier*>(
                                        p.key.get())->name;
                                    HirDictPair hp;
                                    hp.key   = HirLiteral::make_string(fname);
                                    hp.value = lower_expr(p.value.get());
                                    pairs.push_back(std::move(hp));
                                }
                                auto dict_node = std::make_unique<HirDict>(std::move(pairs));
                                out.push_back(std::make_unique<HirLet>(
                                    ta->name, ta->type_name, std::move(dict_node)));
                                ++i; // skip the dict stmt
                                continue;
                            }
                        }
                    }
                }
            }

            lower_stmt(s, out);
        }
        return out;
    }

    // ── Operator mapping ─────────────────────────────────────────────────────

    static const char* binop_str(BinOp op) {
        switch (op) {
            case BinOp::Add:      return "+";
            case BinOp::Sub:      return "-";
            case BinOp::Mul:      return "*";
            case BinOp::Div:      return "/";
            case BinOp::FloorDiv: return "//";
            case BinOp::Mod:      return "%";
            case BinOp::Pow:      return "**";
            case BinOp::Eq:       return "==";
            case BinOp::Ne:       return "!=";
            case BinOp::Lt:       return "<";
            case BinOp::Le:       return "<=";
            case BinOp::Gt:       return ">";
            case BinOp::Ge:       return ">=";
            case BinOp::And:      return "and";
            case BinOp::Or:       return "or";
            default:              return "?";
        }
    }

    // ── Constant folding ─────────────────────────────────────────────────────

    // Attempt to fold a binary op on two literal HIR nodes.
    // Returns nullptr if folding is not applicable.
    static HirNodePtr try_fold(BinOp op, const HirLiteral* l, const HirLiteral* r) {
        using VK = HirLiteral::ValKind;

        // Int × Int
        if (l->vk == VK::Int && r->vk == VK::Int) {
            switch (op) {
                case BinOp::Add:      return hir_int(l->i + r->i);
                case BinOp::Sub:      return hir_int(l->i - r->i);
                case BinOp::Mul:      return hir_int(l->i * r->i);
                case BinOp::FloorDiv: if (r->i) return hir_int(l->i / r->i); break;
                case BinOp::Mod:      if (r->i) return hir_int(l->i % r->i); break;
                case BinOp::Eq:       return hir_bool(l->i == r->i);
                case BinOp::Ne:       return hir_bool(l->i != r->i);
                case BinOp::Lt:       return hir_bool(l->i <  r->i);
                case BinOp::Le:       return hir_bool(l->i <= r->i);
                case BinOp::Gt:       return hir_bool(l->i >  r->i);
                case BinOp::Ge:       return hir_bool(l->i >= r->i);
                default: break;
            }
        }

        // Float × Float (or mixed numeric)
        bool l_num = (l->vk == VK::Int || l->vk == VK::Float);
        bool r_num = (r->vk == VK::Int || r->vk == VK::Float);
        if (l_num && r_num) {
            double lf = l->vk == VK::Float ? l->f : (double)l->i;
            double rf = r->vk == VK::Float ? r->f : (double)r->i;
            switch (op) {
                case BinOp::Add: return HirLiteral::make_float(lf + rf);
                case BinOp::Sub: return HirLiteral::make_float(lf - rf);
                case BinOp::Mul: return HirLiteral::make_float(lf * rf);
                case BinOp::Div: if (rf != 0.0) return HirLiteral::make_float(lf / rf); break;
                case BinOp::Eq:  return hir_bool(lf == rf);
                case BinOp::Ne:  return hir_bool(lf != rf);
                case BinOp::Lt:  return hir_bool(lf <  rf);
                case BinOp::Le:  return hir_bool(lf <= rf);
                case BinOp::Gt:  return hir_bool(lf >  rf);
                case BinOp::Ge:  return hir_bool(lf >= rf);
                default: break;
            }
        }

        // String + String
        if (l->vk == VK::String && r->vk == VK::String && op == BinOp::Add)
            return HirLiteral::make_string(l->s + r->s);

        // String equality
        if (l->vk == VK::String && r->vk == VK::String) {
            if (op == BinOp::Eq) return hir_bool(l->s == r->s);
            if (op == BinOp::Ne) return hir_bool(l->s != r->s);
        }

        return nullptr;
    }

    // ── Known builtin method names ────────────────────────────────────────────

    static bool is_builtin_method(const std::string& m) {
        static const std::unordered_set<std::string> kBuiltins = {
            "append","pop","insert","sort","reverse",
            "keys","values","len","contains","remove",
            "upper","lower","trim","split","find","replace",
            "starts_with","ends_with",
        };
        return kBuiltins.count(m) > 0;
    }

    // ── Expression lowering ───────────────────────────────────────────────────

    HirNodePtr lower_expr(const Expr* e) {
        if (!e) return hir_null();

        switch (e->kind) {
            case NodeKind::IntLit:
                return hir_int(static_cast<const IntLit*>(e)->value);
            case NodeKind::FloatLit:
                return HirLiteral::make_float(static_cast<const FloatLit*>(e)->value);
            case NodeKind::StringLit:
                return HirLiteral::make_string(static_cast<const StringLit*>(e)->value);
            case NodeKind::BoolLit:
                return hir_bool(static_cast<const BoolLit*>(e)->value);
            case NodeKind::NullLit:
                return hir_null();
            case NodeKind::Identifier:
                return hir_load(static_cast<const Identifier*>(e)->name);
            case NodeKind::UnaryOp:
                return lower_unary(static_cast<const UnaryOp*>(e));
            case NodeKind::BinaryOp:
                return lower_binary(static_cast<const BinaryOp*>(e));
            case NodeKind::Call:
                return lower_call(static_cast<const Call*>(e));
            case NodeKind::ListLit:
                return lower_list_lit(static_cast<const ListLit*>(e));
            case NodeKind::DictLit:
                return lower_dict_lit(static_cast<const DictLit*>(e));
            case NodeKind::IndexAccess:
                return lower_index_access(static_cast<const IndexAccess*>(e));
            case NodeKind::Attribute:
                return lower_attribute(static_cast<const Attribute*>(e));
            case NodeKind::FStringLit:
                return lower_fstring(static_cast<const FStringLit*>(e));
            case NodeKind::Match:
                return lower_match_expr(static_cast<const Match*>(e));
            case NodeKind::Lambda:
                return lower_lambda(static_cast<const Lambda*>(e));
            default:
                return hir_null();
        }
    }

    HirNodePtr lower_unary(const UnaryOp* n) {
        auto operand = lower_expr(n->operand.get());

        // Constant fold on literal
        if (operand->kind == HirKind::Literal) {
            auto* lit = static_cast<HirLiteral*>(operand.get());
            using VK = HirLiteral::ValKind;
            if (n->op == UnOp::Neg && (lit->vk == VK::Int || lit->vk == VK::Float)) {
                if (lit->vk == VK::Int)   return hir_int(-lit->i);
                return HirLiteral::make_float(-lit->f);
            }
            if (n->op == UnOp::Not)
                return hir_bool(lit->vk == VK::Null || (lit->vk == VK::Bool && !lit->b));
        }

        const char* op_str = (n->op == UnOp::Neg) ? "-" : "not";
        return std::make_unique<HirUnaryOp>(op_str, std::move(operand));
    }

    HirNodePtr lower_binary(const BinaryOp* n) {
        auto left  = lower_expr(n->lhs.get());
        auto right = lower_expr(n->rhs.get());

        // Attempt constant fold
        if (left->kind == HirKind::Literal && right->kind == HirKind::Literal) {
            auto folded = try_fold(n->op,
                static_cast<const HirLiteral*>(left.get()),
                static_cast<const HirLiteral*>(right.get()));
            if (folded) return folded;
        }

        // Determine result type for comparisons
        std::string rtype = HT::UNKNOWN;
        switch (n->op) {
            case BinOp::Eq: case BinOp::Ne:
            case BinOp::Lt: case BinOp::Le:
            case BinOp::Gt: case BinOp::Ge:
            case BinOp::And: case BinOp::Or:
                rtype = HT::BOOL;
                break;
            case BinOp::Div:      rtype = HT::FLOAT; break;
            case BinOp::FloorDiv: rtype = HT::INT;   break;
            default: break;
        }

        return hir_binop(binop_str(n->op), std::move(left), std::move(right), rtype);
    }

    HirNodePtr lower_call(const Call* n) {
        // Check if callee is a method call: obj.method(args)
        if (n->callee->kind == NodeKind::Attribute) {
            return lower_method_call(n, static_cast<const Attribute*>(n->callee.get()));
        }

        // Named function call: foo(args)
        if (n->callee->kind == NodeKind::Identifier) {
            auto& fname = static_cast<const Identifier*>(n->callee.get())->name;

            // instanceof(obj, ClassName) → HirIsInstance
            if (fname == "instanceof" && n->args.size() == 2
                    && n->args[1]->kind == NodeKind::Identifier) {
                auto obj_hir = lower_expr(n->args[0].get());
                auto& cls = static_cast<const Identifier*>(n->args[1].get())->name;
                return std::make_unique<HirIsInstance>(std::move(obj_hir), cls);
            }

            std::vector<HirNodePtr> hir_args;
            hir_args.reserve(n->args.size());
            for (auto& a : n->args) hir_args.push_back(lower_expr(a.get()));
            return std::make_unique<HirCall>(fname, std::move(hir_args));
        }

        // Expression call: (expr)(args)
        auto callee_hir = lower_expr(n->callee.get());
        std::vector<HirNodePtr> hir_args;
        hir_args.reserve(n->args.size());
        for (auto& a : n->args) hir_args.push_back(lower_expr(a.get()));
        return std::make_unique<HirExprCall>(std::move(callee_hir), std::move(hir_args));
    }

    HirNodePtr lower_method_call(const Call* call, const Attribute* attr) {
        auto obj_hir = lower_expr(attr->object.get());

        std::vector<HirNodePtr> hir_args;
        hir_args.reserve(call->args.size());
        for (auto& a : call->args) hir_args.push_back(lower_expr(a.get()));

        // Known builtin methods → HirCall(method, [obj, ...args])
        if (is_builtin_method(attr->name)) {
            std::vector<HirNodePtr> full_args;
            full_args.push_back(std::move(obj_hir));
            for (auto& a : hir_args) full_args.push_back(std::move(a));
            return std::make_unique<HirCall>(attr->name, std::move(full_args));
        }

        // User-defined method → HirObjectCall
        return std::make_unique<HirObjectCall>(
            std::move(obj_hir), attr->name, std::move(hir_args));
    }

    HirNodePtr lower_list_lit(const ListLit* n) {
        std::vector<HirNodePtr> elems;
        elems.reserve(n->elements.size());
        for (auto& e : n->elements) elems.push_back(lower_expr(e.get()));
        return std::make_unique<HirList>(std::move(elems));
    }

    HirNodePtr lower_dict_lit(const DictLit* n) {
        std::vector<HirDictPair> pairs;
        pairs.reserve(n->pairs.size());
        for (auto& p : n->pairs) {
            HirDictPair hp;
            hp.key   = lower_expr(p.key.get());
            hp.value = lower_expr(p.value.get());
            pairs.push_back(std::move(hp));
        }
        return std::make_unique<HirDict>(std::move(pairs));
    }

    HirNodePtr lower_index_access(const IndexAccess* n) {
        return std::make_unique<HirIndex>(
            lower_expr(n->base.get()), lower_expr(n->index.get()));
    }

    HirNodePtr lower_attribute(const Attribute* n) {
        return std::make_unique<HirFieldLoad>(lower_expr(n->object.get()), n->name);
    }

    // Desugar $"hello {x}" → "hello " + to_str(x)
    HirNodePtr lower_fstring(const FStringLit* n) {
        std::vector<HirNodePtr> parts;
        for (auto& part : n->parts) {
            if (part.kind == FStringPart::Kind::Text) {
                if (!part.text.empty())
                    parts.push_back(HirLiteral::make_string(part.text));
            } else {
                auto expr_hir = lower_expr(part.expr.get());
                std::vector<HirNodePtr> wrap_args;
                wrap_args.push_back(std::move(expr_hir));
                parts.push_back(std::make_unique<HirCall>(
                    "to_str", std::move(wrap_args), HT::STRING));
            }
        }

        if (parts.empty()) return HirLiteral::make_string("");

        // Fold into left-associative chain of "+"
        HirNodePtr acc = std::move(parts[0]);
        for (size_t i = 1; i < parts.size(); ++i) {
            acc = hir_binop("+", std::move(acc), std::move(parts[i]), HT::STRING);
        }
        return acc;
    }

    // Desugar match expr { p1, p2 => r1  _ => r2 } → nested HirIf
    // Returns a block of stmts (let __match + if chain); wrapped as HirExprCall
    // is not possible since match is an expression — we return the HirIf tree
    // directly, relying on codegen to handle block-as-expression.
    HirNodePtr lower_match_expr(const Match* n) {
        // We lower match as a chain of HirIf nodes.
        // Since match is an expression, the result is the final HirIf value.
        auto tmp = fresh("__match");
        // Can't emit let here since we're in expr context; return the tree
        // starting from the if chain (the tmp capture is implicit).
        // In practice the codegen treats the whole HirIf as a value.
        auto subject = lower_expr(n->subject.get());

        // Build from last arm backward
        HirBlock else_block;
        for (int i = (int)n->arms.size() - 1; i >= 0; --i) {
            auto& arm = n->arms[i];
            HirBlock then_block;
            then_block.push_back(lower_expr(arm.result.get()));

            if (arm.patterns.empty()) {
                // Wildcard arm — always taken
                else_block = std::move(then_block);
            } else {
                // Build condition: p0 == subject or p1 == subject ...
                HirNodePtr cond = hir_binop("==",
                    lower_expr(arm.patterns[0].get()),
                    lower_expr(n->subject.get()), HT::BOOL);
                for (size_t j = 1; j < arm.patterns.size(); ++j) {
                    cond = hir_binop("or", std::move(cond),
                        hir_binop("==",
                            lower_expr(arm.patterns[j].get()),
                            lower_expr(n->subject.get()), HT::BOOL), HT::BOOL);
                }

                HirBlock new_else;
                new_else.push_back(std::make_unique<HirIf>(
                    std::move(cond), std::move(then_block), std::move(else_block)));
                else_block = std::move(new_else);
            }
        }

        // Unwrap single-element block if possible
        if (else_block.size() == 1) return std::move(else_block[0]);
        return hir_null(); // unreachable if all arms covered
    }

    HirNodePtr lower_lambda(const Lambda* n) {
        std::vector<HirParam> params;
        for (auto& p : n->params) {
            params.push_back({p.name, p.type_name.empty() ? HT::UNKNOWN : p.type_name});
        }

        HirBlock body;
        if (n->expr_body) {
            body.push_back(std::make_unique<HirReturn>(lower_expr(n->expr_body.get())));
        } else {
            body = lower_block(n->block_body);
        }

        return std::make_unique<HirFuncDef>("", std::move(params), HT::UNKNOWN, std::move(body));
    }

    // ── Statement lowering ────────────────────────────────────────────────────

    void lower_stmt(const Stmt* s, HirBlock& out) {
        if (!s) return;
        switch (s->kind) {
            case NodeKind::ExprStmt:
                out.push_back(lower_expr(static_cast<const ExprStmt*>(s)->expr.get()));
                break;
            case NodeKind::Assign:
                lower_assign(static_cast<const Assign*>(s), out);
                break;
            case NodeKind::CompoundAssign:
                lower_compound_assign(static_cast<const Assign*>(s), out);
                break;
            case NodeKind::TypedAssign:
                lower_typed_assign(static_cast<const TypedAssign*>(s), out);
                break;
            case NodeKind::ConstDecl:
                lower_const_decl(static_cast<const ConstDecl*>(s), out);
                break;
            case NodeKind::If:
                lower_if(static_cast<const If*>(s), out);
                break;
            case NodeKind::While:
                lower_while(static_cast<const While*>(s), out);
                break;
            case NodeKind::For:
                lower_for(static_cast<const For*>(s), out);
                break;
            case NodeKind::ForEach:
                lower_foreach(static_cast<const ForEach*>(s), out);
                break;
            case NodeKind::Return: {
                auto* r = static_cast<const Return*>(s);
                auto  v = r->value ? lower_expr(r->value.get()) : nullptr;
                out.push_back(std::make_unique<HirReturn>(std::move(v)));
                break;
            }
            case NodeKind::FuncDef:
                lower_funcdef(static_cast<const FuncDef*>(s), out);
                break;
            case NodeKind::StructDef:
                lower_structdef(static_cast<const StructDef*>(s), out);
                break;
            case NodeKind::ClassDef:
                lower_classdef(static_cast<const ClassDef*>(s), out);
                break;
            case NodeKind::AttrAssign: {
                auto* n = static_cast<const AttrAssign*>(s);
                out.push_back(std::make_unique<HirFieldStore>(
                    lower_expr(n->object.get()), n->attr, lower_expr(n->value.get())));
                break;
            }
            case NodeKind::IndexAssign: {
                auto* n = static_cast<const IndexAssign*>(s);
                out.push_back(std::make_unique<HirIndexStore>(
                    lower_expr(n->base.get()),
                    lower_expr(n->index.get()),
                    lower_expr(n->value.get())));
                break;
            }
            case NodeKind::Import:
                lower_import(static_cast<const Import*>(s), out);
                break;
            case NodeKind::Attempt:
                lower_attempt(static_cast<const Attempt*>(s), out);
                break;
            case NodeKind::Alert:
                out.push_back(std::make_unique<HirAlert>(
                    lower_expr(static_cast<const Alert*>(s)->expr.get())));
                break;
            case NodeKind::Switch:
                lower_switch(static_cast<const Switch*>(s), out);
                break;
            case NodeKind::Break:
                out.push_back(std::make_unique<HirBreak>());
                break;
            case NodeKind::Continue:
                out.push_back(std::make_unique<HirContinue>());
                break;
            case NodeKind::Pass:
                out.push_back(std::make_unique<HirPass>());
                break;
            default:
                break;
        }
    }

    // ── Variable assignment ───────────────────────────────────────────────────

    void lower_assign(const Assign* n, HirBlock& out) {
        out.push_back(std::make_unique<HirAssign>(n->name, lower_expr(n->value.get())));
    }

    // x += e  →  x = x + e
    void lower_compound_assign(const Assign* n, HirBlock& out) {
        // The RHS of a compound assign stored in the AST is already the RHS of
        // the operator (e.g. for x += 3, value = 3). We don't know the original
        // operator from the AST here; emit as a generic assign with the pre-lowered
        // value. The codegen is responsible for the read-modify-write semantics.
        out.push_back(std::make_unique<HirAssign>(n->name, lower_expr(n->value.get())));
    }

    void lower_typed_assign(const TypedAssign* n, HirBlock& out) {
        out.push_back(std::make_unique<HirLet>(n->name, n->type_name, lower_expr(n->value.get())));
    }

    void lower_const_decl(const ConstDecl* n, HirBlock& out) {
        auto t = n->type_name.empty() ? HT::UNKNOWN : n->type_name;
        out.push_back(std::make_unique<HirLet>(n->name, t, lower_expr(n->value.get())));
    }

    // ── Control flow ─────────────────────────────────────────────────────────

    // Lower if/elif/else into binary nested HirIf.
    // Built from the last branch backwards to create the nesting.
    void lower_if(const If* n, HirBlock& out) {
        HirBlock else_block = lower_block(n->else_body);

        for (int i = (int)n->branches.size() - 1; i >= 0; --i) {
            auto& br = n->branches[i];
            HirBlock then = lower_block(br.body);
            HirBlock wrapper;
            wrapper.push_back(std::make_unique<HirIf>(
                lower_expr(br.condition.get()), std::move(then), std::move(else_block)));
            else_block = std::move(wrapper);
        }

        // Unwrap the single wrapper
        for (auto& node : else_block) out.push_back(std::move(node));
    }

    void lower_while(const While* n, HirBlock& out) {
        out.push_back(std::make_unique<HirWhile>(
            lower_expr(n->condition.get()), lower_block(n->body)));
    }

    // Desugar: for i = start to end step k → while loop with counter
    void lower_for(const For* n, HirBlock& out) {
        auto end_var  = fresh("__end");
        auto step_var = fresh("__step");

        auto end_val  = lower_expr(n->end.get());
        auto step_val = n->step ? lower_expr(n->step.get()) : hir_int(1);

        out.push_back(std::make_unique<HirLet>(end_var,  HT::UNKNOWN, std::move(end_val)));
        out.push_back(std::make_unique<HirLet>(step_var, HT::UNKNOWN, std::move(step_val)));
        out.push_back(std::make_unique<HirLet>(n->var,   HT::INT,     lower_expr(n->start.get())));

        // Condition: i < __end
        auto cond = hir_binop("<", hir_load(n->var), hir_load(end_var), HT::BOOL);

        // Body + increment
        HirBlock body = lower_block(n->body);
        body.push_back(std::make_unique<HirAssign>(n->var,
            hir_binop("+", hir_load(n->var), hir_load(step_var), HT::INT)));

        out.push_back(std::make_unique<HirWhile>(std::move(cond), std::move(body)));
    }

    // Desugar: for x in iterable → index-based while loop
    void lower_foreach(const ForEach* n, HirBlock& out) {
        auto lst_var = fresh("__lst");
        auto len_var = fresh("__len");
        auto idx_var = fresh("__idx");

        out.push_back(std::make_unique<HirLet>(lst_var, HT::UNKNOWN, lower_expr(n->iterable.get())));

        std::vector<HirNodePtr> len_args;
        len_args.push_back(hir_load(lst_var));
        out.push_back(std::make_unique<HirLet>(len_var, HT::INT,
            std::make_unique<HirCall>("len", std::move(len_args), HT::INT)));

        out.push_back(std::make_unique<HirLet>(idx_var, HT::INT, hir_int(0)));

        auto cond = hir_binop("<", hir_load(idx_var), hir_load(len_var), HT::BOOL);

        HirBlock body;
        body.push_back(std::make_unique<HirLet>(n->var, HT::UNKNOWN,
            std::make_unique<HirIndex>(hir_load(lst_var), hir_load(idx_var))));

        for (auto& s : n->body) lower_stmt(s.get(), body);

        body.push_back(std::make_unique<HirAssign>(idx_var,
            hir_binop("+", hir_load(idx_var), hir_int(1), HT::INT)));

        out.push_back(std::make_unique<HirWhile>(std::move(cond), std::move(body)));
    }

    // Desugar switch { case v1, v2 { } ... else { } } → if/elif chain
    void lower_switch(const Switch* n, HirBlock& out) {
        auto tmp = fresh("__sw");
        out.push_back(std::make_unique<HirLet>(tmp, HT::UNKNOWN, lower_expr(n->subject.get())));

        HirBlock else_block = lower_block(n->else_body);

        for (int i = (int)n->cases.size() - 1; i >= 0; --i) {
            auto& c = n->cases[i];

            // Build condition: tmp == v0 or tmp == v1 or ...
            HirNodePtr cond = hir_binop("==", hir_load(tmp), lower_expr(c.values[0].get()), HT::BOOL);
            for (size_t j = 1; j < c.values.size(); ++j) {
                cond = hir_binop("or", std::move(cond),
                    hir_binop("==", hir_load(tmp), lower_expr(c.values[j].get()), HT::BOOL),
                    HT::BOOL);
            }

            HirBlock wrapper;
            wrapper.push_back(std::make_unique<HirIf>(
                std::move(cond), lower_block(c.body), std::move(else_block)));
            else_block = std::move(wrapper);
        }

        for (auto& node : else_block) out.push_back(std::move(node));
    }

    // ── Definitions ──────────────────────────────────────────────────────────

    void lower_funcdef(const FuncDef* n, HirBlock& out) {
        std::vector<HirParam> params;
        for (auto& p : n->params) {
            auto t = p.variadic ? HT::LIST : (p.type_name.empty() ? HT::UNKNOWN : p.type_name);
            params.push_back({p.name, t});
        }
        auto ret = n->return_type.empty() ? HT::UNKNOWN : n->return_type;
        bool variadic = false;
        for (auto& p : n->params) if (p.variadic) { variadic = true; break; }

        out.push_back(std::make_unique<HirFuncDef>(
            n->name, std::move(params), ret, lower_block(n->body), variadic));
    }

    void lower_structdef(const StructDef* n, HirBlock& out) {
        std::vector<HirStructField> fields;
        for (auto& f : n->fields) {
            HirStructField hf;
            hf.name       = f.name;
            hf.type       = f.type_name.empty() ? HT::UNKNOWN : f.type_name;
            hf.default_val = f.default_val ? lower_expr(f.default_val.get()) : nullptr;
            fields.push_back(std::move(hf));
        }
        out.push_back(std::make_unique<HirStructDef>(n->name, std::move(fields)));
    }

    void lower_classdef(const ClassDef* n, HirBlock& out) {
        HirBlock methods;
        for (auto& m : n->methods) {
            if (m->kind == NodeKind::FuncDef) {
                lower_funcdef(static_cast<const FuncDef*>(m.get()), methods);
            }
        }
        out.push_back(std::make_unique<HirClassDef>(n->name, n->parent, std::move(methods)));
    }

    // ── Other ─────────────────────────────────────────────────────────────────

    void lower_import(const Import* n, HirBlock& out) {
        out.push_back(std::make_unique<HirImport>(n->path, n->alias, n->names));
    }

    void lower_attempt(const Attempt* n, HirBlock& out) {
        out.push_back(std::make_unique<HirAttemptRescue>(
            lower_block(n->try_body),
            n->error_var,
            lower_block(n->catch_body),
            lower_block(n->finally_body)));
    }
};

// ─── Public API ───────────────────────────────────────────────────────────────

HirBlock lower_to_hir(const Program& program) {
    return Lowering{}.lower_program(program);
}

// ─── HIR printer ─────────────────────────────────────────────────────────────

static void ind(std::ostream& out, int n) { out << std::string(n * 2, ' '); }

static void print_hir_node(std::ostream& out, const HirNode* n, int depth);

static void print_hir_block(std::ostream& out, const HirBlock& block, int depth) {
    for (auto& n : block) print_hir_node(out, n.get(), depth);
}

static void print_hir_node(std::ostream& out, const HirNode* n, int depth) {
    if (!n) { ind(out, depth); out << "(null)\n"; return; }

    switch (n->kind) {
        case HirKind::Literal: {
            auto* lit = static_cast<const HirLiteral*>(n);
            ind(out, depth);
            using VK = HirLiteral::ValKind;
            switch (lit->vk) {
                case VK::Int:    out << "(int " << lit->i << ")\n"; break;
                case VK::Float:  out << "(float " << lit->f << ")\n"; break;
                case VK::String: out << "(str \"" << lit->s << "\")\n"; break;
                case VK::Bool:   out << "(bool " << (lit->b ? "true" : "false") << ")\n"; break;
                default:         out << "(null)\n"; break;
            }
            break;
        }
        case HirKind::Load:
            ind(out, depth); out << "(load " << static_cast<const HirLoad*>(n)->name << ")\n";
            break;
        case HirKind::Let: {
            auto* l = static_cast<const HirLet*>(n);
            ind(out, depth); out << "(let " << l->name << " : " << l->type << "\n";
            print_hir_node(out, l->value.get(), depth + 1);
            ind(out, depth); out << ")\n";
            break;
        }
        case HirKind::Assign: {
            auto* a = static_cast<const HirAssign*>(n);
            ind(out, depth); out << "(assign " << a->name << "\n";
            print_hir_node(out, a->value.get(), depth + 1);
            ind(out, depth); out << ")\n";
            break;
        }
        case HirKind::BinOp: {
            auto* b = static_cast<const HirBinOp*>(n);
            ind(out, depth); out << "(binop " << b->op << "\n";
            print_hir_node(out, b->left.get(),  depth + 1);
            print_hir_node(out, b->right.get(), depth + 1);
            ind(out, depth); out << ")\n";
            break;
        }
        case HirKind::UnaryOp: {
            auto* u = static_cast<const HirUnaryOp*>(n);
            ind(out, depth); out << "(unary " << u->op << "\n";
            print_hir_node(out, u->operand.get(), depth + 1);
            ind(out, depth); out << ")\n";
            break;
        }
        case HirKind::Call: {
            auto* c = static_cast<const HirCall*>(n);
            ind(out, depth); out << "(call " << c->func << "\n";
            for (auto& a : c->args) print_hir_node(out, a.get(), depth + 1);
            ind(out, depth); out << ")\n";
            break;
        }
        case HirKind::ExprCall: {
            ind(out, depth); out << "(exprcall\n";
            auto* c = static_cast<const HirExprCall*>(n);
            print_hir_node(out, c->callee.get(), depth + 1);
            for (auto& a : c->args) print_hir_node(out, a.get(), depth + 1);
            ind(out, depth); out << ")\n";
            break;
        }
        case HirKind::ObjectCall: {
            auto* c = static_cast<const HirObjectCall*>(n);
            ind(out, depth); out << "(objcall ." << c->method << "\n";
            print_hir_node(out, c->obj.get(), depth + 1);
            for (auto& a : c->args) print_hir_node(out, a.get(), depth + 1);
            ind(out, depth); out << ")\n";
            break;
        }
        case HirKind::If: {
            auto* i = static_cast<const HirIf*>(n);
            ind(out, depth); out << "(if\n";
            print_hir_node(out, i->cond.get(), depth + 1);
            ind(out, depth + 1); out << "(then\n";
            print_hir_block(out, i->then_block, depth + 2);
            ind(out, depth + 1); out << ")\n";
            if (!i->else_block.empty()) {
                ind(out, depth + 1); out << "(else\n";
                print_hir_block(out, i->else_block, depth + 2);
                ind(out, depth + 1); out << ")\n";
            }
            ind(out, depth); out << ")\n";
            break;
        }
        case HirKind::While: {
            auto* w = static_cast<const HirWhile*>(n);
            ind(out, depth); out << "(while\n";
            print_hir_node(out, w->cond.get(), depth + 1);
            print_hir_block(out, w->body, depth + 1);
            ind(out, depth); out << ")\n";
            break;
        }
        case HirKind::Return: {
            auto* r = static_cast<const HirReturn*>(n);
            ind(out, depth); out << "(return\n";
            if (r->value) print_hir_node(out, r->value.get(), depth + 1);
            ind(out, depth); out << ")\n";
            break;
        }
        case HirKind::Break:    ind(out, depth); out << "(break)\n";    break;
        case HirKind::Continue: ind(out, depth); out << "(continue)\n"; break;
        case HirKind::Pass:     ind(out, depth); out << "(pass)\n";     break;
        case HirKind::FieldLoad: {
            auto* f = static_cast<const HirFieldLoad*>(n);
            ind(out, depth); out << "(field-load ." << f->field << "\n";
            print_hir_node(out, f->obj.get(), depth + 1);
            ind(out, depth); out << ")\n";
            break;
        }
        case HirKind::FieldStore: {
            auto* f = static_cast<const HirFieldStore*>(n);
            ind(out, depth); out << "(field-store ." << f->field << "\n";
            print_hir_node(out, f->obj.get(),   depth + 1);
            print_hir_node(out, f->value.get(), depth + 1);
            ind(out, depth); out << ")\n";
            break;
        }
        case HirKind::Index: {
            auto* i = static_cast<const HirIndex*>(n);
            ind(out, depth); out << "(index\n";
            print_hir_node(out, i->collection.get(), depth + 1);
            print_hir_node(out, i->index.get(),      depth + 1);
            ind(out, depth); out << ")\n";
            break;
        }
        case HirKind::IndexStore: {
            auto* i = static_cast<const HirIndexStore*>(n);
            ind(out, depth); out << "(index-store\n";
            print_hir_node(out, i->collection.get(), depth + 1);
            print_hir_node(out, i->index.get(),      depth + 1);
            print_hir_node(out, i->value.get(),      depth + 1);
            ind(out, depth); out << ")\n";
            break;
        }
        case HirKind::List: {
            auto* l = static_cast<const HirList*>(n);
            ind(out, depth); out << "(list\n";
            for (auto& e : l->elements) print_hir_node(out, e.get(), depth + 1);
            ind(out, depth); out << ")\n";
            break;
        }
        case HirKind::Dict: {
            auto* d = static_cast<const HirDict*>(n);
            ind(out, depth); out << "(dict\n";
            for (auto& p : d->pairs) {
                print_hir_node(out, p.key.get(),   depth + 1);
                print_hir_node(out, p.value.get(), depth + 1);
            }
            ind(out, depth); out << ")\n";
            break;
        }
        case HirKind::FuncDef: {
            auto* f = static_cast<const HirFuncDef*>(n);
            ind(out, depth);
            out << "(func " << (f->name.empty() ? "<anon>" : f->name) << " -> " << f->return_type << "\n";
            ind(out, depth + 1); out << "(params";
            for (auto& p : f->params) out << " " << p.name << ":" << p.type;
            out << ")\n";
            print_hir_block(out, f->body, depth + 1);
            ind(out, depth); out << ")\n";
            break;
        }
        case HirKind::ClassDef: {
            auto* c = static_cast<const HirClassDef*>(n);
            ind(out, depth); out << "(class " << c->name;
            if (!c->parent.empty()) out << " extends " << c->parent;
            out << "\n";
            print_hir_block(out, c->methods, depth + 1);
            ind(out, depth); out << ")\n";
            break;
        }
        case HirKind::StructDef: {
            auto* s = static_cast<const HirStructDef*>(n);
            ind(out, depth); out << "(struct " << s->name << "\n";
            for (auto& f : s->fields) {
                ind(out, depth + 1); out << "(" << f.name << " : " << f.type << ")\n";
            }
            ind(out, depth); out << ")\n";
            break;
        }
        case HirKind::Import: {
            auto* i = static_cast<const HirImport*>(n);
            ind(out, depth); out << "(import \"" << i->path << "\"";
            if (!i->alias.empty()) out << " as " << i->alias;
            out << ")\n";
            break;
        }
        case HirKind::AttemptRescue: {
            auto* a = static_cast<const HirAttemptRescue*>(n);
            ind(out, depth); out << "(attempt\n";
            print_hir_block(out, a->try_block,    depth + 1);
            ind(out, depth + 1); out << "(rescue " << a->error_var << "\n";
            print_hir_block(out, a->rescue_block, depth + 2);
            ind(out, depth + 1); out << ")\n";
            if (!a->finally_block.empty()) {
                ind(out, depth + 1); out << "(finally\n";
                print_hir_block(out, a->finally_block, depth + 2);
                ind(out, depth + 1); out << ")\n";
            }
            ind(out, depth); out << ")\n";
            break;
        }
        case HirKind::Alert: {
            ind(out, depth); out << "(alert\n";
            print_hir_node(out, static_cast<const HirAlert*>(n)->value.get(), depth + 1);
            ind(out, depth); out << ")\n";
            break;
        }
        case HirKind::IsInstance: {
            auto* i = static_cast<const HirIsInstance*>(n);
            ind(out, depth); out << "(instanceof " << i->class_name << "\n";
            print_hir_node(out, i->obj.get(), depth + 1);
            ind(out, depth); out << ")\n";
            break;
        }
        default:
            ind(out, depth); out << "(unknown)\n";
            break;
    }
}

void print_hir(std::ostream& out, const HirBlock& block, int indent) {
    print_hir_block(out, block, indent);
}

}  // namespace luz
